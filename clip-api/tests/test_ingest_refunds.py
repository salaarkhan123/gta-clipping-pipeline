"""A refused or failed link import costs nothing, on both routes that start one: `POST /v1/imports` and
`POST /v1/clips/from-url`. The balance ends where it started. A link clip job that had reserved credits gets all of
them back in one release row (`reserve:<job>` then `settle:<job>`); a plain import never touches the ledger.
The site is the yt-dlp stand-in; no network."""
import pytest
from sqlalchemy import select

from app import worker
from app.config import get_settings
from app.db import new_session
from app.models import CreditLedger
from tests.ingest_support import fake_ydl, no_stray_imports, web  # noqa: F401
from app.pipeline import PipelineError
from tests.test_api import balance, upload
from tests.test_ingest_ranges import (YOUTUBE, clip, imp, job, long_link, long_video, quiet_queue,  # noqa: F401
                                      refunded_once, start, stored_files)

BOT_CHECK = ("ERROR: [youtube] aqz-KE-bpKQ: Sign in to confirm you’re not a bot. Use --cookies-from-browser or "
             "--cookies for the authentication.")
FORBIDDEN = "ERROR: unable to download video data: HTTP Error 403: Forbidden"


def ledger(account_id) -> list[tuple]:
    with new_session() as db:
        return [(r.kind, r.delta) for r in db.execute(select(CreditLedger).where(
            CreditLedger.account_id == account_id).order_by(CreditLedger.id)).scalars()]


@pytest.mark.parametrize("route", ["/v1/imports", "/v1/clips/from-url"])
@pytest.mark.parametrize("when", ["refused_at_the_door", "site_refuses_the_metadata", "site_refuses_at_import",
                                  "site_refuses_the_download"])
def test_a_refused_or_failed_import_is_zero_credits_net(client, user, long_link, route, when):
    headers, account = user
    send = start if route == "/v1/imports" else clip
    url = "https://www.youtube.com/@somechannel" if when == "refused_at_the_door" else YOUTUBE
    if when == "site_refuses_the_metadata":
        long_link.refuse_extract = BOT_CHECK                # at the preview's lookup, and at the import
    assert balance(client, headers) == 30
    r = send(client, headers, url)
    if when == "refused_at_the_door" or (when == "site_refuses_the_metadata" and send is clip):
        assert r.status_code == 422 and "pload" in r.json()["error"]["message"], r.text     # nothing was started
        assert ledger(account["id"]) == [("grant", 30)] and worker.run_once() is None
    else:
        assert r.status_code == 202, r.text
        reserved = r.json().get("credits_reserved", 0)
        assert reserved == (3 if send is clip else 0) and balance(client, headers) == 30 - reserved
        if when == "site_refuses_at_import":
            long_link.refuse_extract = BOT_CHECK            # the site answered the preview, then refuses the worker
        if when == "site_refuses_the_download":
            long_link.refuse_download = FORBIDDEN
        assert worker.run_once() == "FAILED"
        if send is clip:
            out = job(client, headers, r.json()["job_id"])
            assert out["status"] == "FAILED" and out["credits_charged"] == 0
            assert out["error"]["code"] == "source_refused"
            assert "upload the file instead" in out["error"]["message"].lower()
            assert "credits were returned" in out["error"]["message"]
            refunded_once(out["job_id"], 3)
            assert ledger(account["id"]) == [("grant", 30), ("reserve", -3), ("release", 3)]
        else:
            done = imp(client, headers, r.json()["import_id"])
            assert done["status"] == "FAILED" and done["error"]["code"] == "source_refused"
            assert done["upload_id"] is None and "upload the file instead" in done["error"]["message"].lower()
            assert ledger(account["id"]) == [("grant", 30)]
    assert balance(client, headers) == 30                   # net zero, whatever happened
    assert stored_files(account["id"]) == [] and worker.run_once() is None


# ---- the two later failures: while the import runs, and after it, in the clip job (#218) ----

@pytest.mark.parametrize("how, code", [("site_drops_the_download", "source_refused"), ("too_big_midway", "file_too_large")])
def test_an_import_that_fails_while_running_costs_nothing_and_the_original_runs_the_same_job(
        client, user, long_link, long_video, monkeypatch, how, code):
    """The link clip job is accepted (credits reserved), then the download dies part way. The job fails with a
    message that says to upload the file (the site then offers Upload original video and keeps the settings), the
    reservation comes back in one release, nothing is stored; the original uploaded with the SAME options, the
    picked part becoming the job's range (lib/imports.ts optionsForUpload), is priced and charged on its own."""
    headers, account = user
    options = {"duration": "0-30", "limit": 2, "caption_style": "impact", "template": "gta-online-chaos"}
    r = clip(client, headers, YOUTUBE, start_sec=30, end_sec=90, options=options)
    assert r.status_code == 202, r.text
    reserved = r.json()["credits_reserved"]
    assert reserved > 0 and balance(client, headers) == 30 - reserved
    if how == "site_drops_the_download":
        long_link.refuse_download = FORBIDDEN
    else:
        long_link.report_bytes = 10 ** 9                 # the progress hook sees more than the cap, mid download
        monkeypatch.setattr(get_settings(), "import_max_bytes", 10 ** 8)
    assert worker.run_once() == "FAILED"
    out = job(client, headers, r.json()["job_id"])
    assert out["status"] == "FAILED" and out["error"]["code"] == code and out["import"]["status"] == "FAILED"
    assert "credits were returned" in out["error"]["message"] and out["credits_charged"] == 0
    refunded_once(out["job_id"], reserved)
    assert balance(client, headers) == 30 and stored_files(account["id"]) == []

    # Upload original video: the same options, the part picked for the import as the range.
    up = upload(client, headers, long_video)["upload_id"]
    same = {**options, "range": {"start": 30, "end": 90}}
    quote = client.post("/v1/clips/quote", json={"upload_id": up, "options": same}, headers=headers)
    assert quote.status_code == 200, quote.text
    again = client.post("/v1/clips", json={"upload_id": up, "options": same}, headers=headers)
    assert again.status_code == 202, again.text
    assert again.json()["credits_reserved"] == quote.json()["credits_reserved"]
    assert {k: again.json()["options"][k] for k in ("duration", "limit", "caption_style", "template")} == options
    assert again.json()["options"]["range"] == {"start": 30.0, "end": 90.0}
    assert balance(client, headers) == 30 - quote.json()["credits_reserved"]   # only the upload's job is charged
    assert ledger(account["id"])[:3] == [("grant", 30), ("reserve", -reserved), ("release", reserved)]


def test_a_link_clip_job_that_fails_after_its_import_is_refunded_once_and_keeps_the_video(client, user, long_link):
    """The import stores the video, then the clip job itself fails: the whole reservation comes back once, the
    import's consent log and the stored video stay (a new job on it needs no second download)."""
    headers, account = user
    r = clip(client, headers, YOUTUBE, start_sec=30, end_sec=90)
    assert r.status_code == 202, r.text
    reserved = r.json()["credits_reserved"]
    assert worker.run_once() == "SUCCEEDED"                   # the import
    def broken(*args, **kwargs):
        raise PipelineError("no_moments", "Nothing stood out enough to clip in this part.")
    assert worker.run_once(pipeline=broken) == "FAILED"       # the clip job it chained
    out = job(client, headers, r.json()["job_id"])
    assert out["status"] == "FAILED" and out["error"]["code"] == "no_moments" and out["credits_charged"] == 0
    assert out["import"]["status"] == "SUCCEEDED" and out["upload_id"]
    refunded_once(out["job_id"], reserved)
    assert balance(client, headers) == 30
    assert ledger(account["id"]) == [("grant", 30), ("reserve", -reserved), ("release", reserved)]
    assert stored_files(account["id"]) != []                  # the imported video is kept for another try
    again = client.post("/v1/clips", json={"upload_id": out["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                        headers=headers)
    assert again.status_code == 202, again.text and worker.run_once() is not None
