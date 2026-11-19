"""A refused or failed link import costs nothing, on both routes that start one: `POST /v1/imports` and
`POST /v1/clips/from-url`. The balance ends where it started. A link clip job that had reserved credits gets all of
them back in one release row (`reserve:<job>` then `settle:<job>`); a plain import never touches the ledger.
The site is the yt-dlp stand-in; no network."""
import pytest
from sqlalchemy import select

from app import worker
from app.db import new_session
from app.models import CreditLedger
from tests.ingest_support import fake_ydl, no_stray_imports, web  # noqa: F401
from tests.test_api import balance
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
