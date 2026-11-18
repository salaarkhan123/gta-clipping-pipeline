"""Clips from a link: `POST /v1/clips/from-url {url, consent: true, options}` and the preview's `estimate`.

Every failure path ends in a refund, shown by the ledger: one `reserve:<job>` row and one `settle:<job>` row per
job, and the balance back where it started. Platforms come from the yt-dlp stand-in, direct links from the fake
DNS; no network."""
import subprocess
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app import url_clips, worker
from app.config import get_settings
from app.db import new_session
from app.ingest import preview as link_preview
from app.ingest.takedown import takedown
from app.models import Account, Clip, CreditLedger, ImportLog, Job, Upload, utcnow
from app.pipeline import PipelineError
from app.routes_media import active_jobs
from tests.ingest_support import fake_ydl, no_stray_imports, web  # noqa: F401
from tests.test_api import balance

TWITCH = "https://www.twitch.tv/videos/2301234567"


@pytest.fixture(autouse=True)
def quiet_queue():
    """Each test's worker run claims its own jobs: anything another test left waiting is set aside."""
    def clear():
        with new_session() as db:
            db.execute(update(Job).where(Job.status.in_(("WAITING", "QUEUED", "RUNNING")))
                       .values(status="CANCELED", finished_at=utcnow()))
            db.commit()
    clear()
    link_preview.clear_cache()
    yield
    clear()
    link_preview.clear_cache()


@pytest.fixture(scope="module")
def long_video(tmp_path_factory):
    """130 s, small: priced at 3 credits."""
    path = tmp_path_factory.mktemp("long") / "long.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=5:duration=130",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=130", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


def no_clips(*args, **kwargs):
    return []


def go(client, headers, url=TWITCH, consent=True, options=None, key=None):
    body = {"url": url, "consent": consent}
    if options is not None:
        body["options"] = options
    return client.post("/v1/clips/from-url", json=body, headers={**headers, **({"Idempotency-Key": key} if key else {})})


def get(client, headers, job_id) -> dict:
    return client.get(f"/v1/jobs/{job_id}", headers=headers).json()


def money(job_id) -> list[tuple]:
    with new_session() as db:
        return [(r.kind, r.delta, r.idempotency_key) for r in db.execute(
            select(CreditLedger).where(CreditLedger.job_id == job_id).order_by(CreditLedger.id)).scalars()]


def account_rows(account_id) -> list[tuple]:
    with new_session() as db:
        return [(r.kind, r.delta) for r in db.execute(select(CreditLedger).where(
            CreditLedger.account_id == account_id).order_by(CreditLedger.id)).scalars()]


def logs(account_id) -> int:
    with new_session() as db:
        return len(db.execute(select(ImportLog.id).where(ImportLog.account_id == account_id)).all())


def jobs_of(account_id) -> list[Job]:
    with new_session() as db:
        return db.execute(select(Job).where(Job.account_id == account_id).order_by(Job.created_at)).scalars().all()


def refunded_once(job_id, credits) -> None:
    assert money(job_id) == [("reserve", -credits, f"reserve:{job_id}"), ("release", credits, f"settle:{job_id}")]


def preview(client, headers, url=TWITCH, options=None) -> dict:
    r = client.post("/v1/imports/preview", json={"url": url, **({"options": options} if options else {})},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---- the whole way, from paste to clips ----

def test_paste_preview_generate_import_clip(client, user, fake_ydl, transcriber):
    headers, account = user
    fake_ydl.info = {"duration": 40.0}
    seen = preview(client, headers)
    assert seen["supported"] is True and seen["duration_sec"] == 40.0
    assert seen["estimate"] == {"credits": 1, "basis": "source_minutes", "duration_sec": 40.0, "balance": 30,
                                "enough": True, "note": seen["estimate"]["note"]}
    assert len(fake_ydl.instances) == 1                         # metadata only

    r = go(client, headers, options={"max_clips": 1, "clip_length": 10, "project_name": "Ranked"})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["job_id"].startswith("job_") and job["status"] == "WAITING" and job["stage"] == "importing"
    assert job["credits_reserved"] == 1 and job["credits_charged"] == 0
    imp = job["import"]
    assert imp["import_id"].startswith("imp_") and imp["status"] == "QUEUED" and imp["upload_id"] is None
    assert imp["url"] == TWITCH and imp["platform"] == "twitch" and imp["reused"] is False
    assert len(fake_ydl.instances) == 1                         # the cached preview: no second lookup
    assert balance(client, headers) == 29 and logs(account["id"]) == 1     # reserved and logged before any fetch

    assert worker.run_once() == "SUCCEEDED"                     # the import, which queues the clip job
    queued = get(client, headers, job["job_id"])
    assert queued["status"] == "QUEUED" and queued["import"]["status"] == "SUCCEEDED"
    assert queued["import"]["progress"] == 100 and queued["upload_id"] == queued["import"]["upload_id"]
    assert get_settings().storage_dir.joinpath("uploads", account["id"]).exists()

    assert worker.run_once(transcriber) == "SUCCEEDED"          # the clip job
    done = get(client, headers, job["job_id"])
    assert done["status"] == "SUCCEEDED" and done["credits_charged"] == 1 and len(done["clips"]) == 1
    assert money(job["job_id"]) == [("reserve", -1, f"reserve:{job['job_id']}"),
                                    ("commit", 0, f"settle:{job['job_id']}")]
    assert balance(client, headers) == 29
    listed = client.get("/v1/imports", headers=headers).json()     # the import is a normal import
    assert listed["total"] == 1 and listed["imports"][0]["import_id"] == imp["import_id"]
    with new_session() as db:
        assert db.get(Job, job["job_id"]).name == "Ranked"


def test_automatic_discovery_is_the_default(client, user, fake_ydl):
    """Owner, 2026-11-18: no 3-clip limit. Every moment that passes, unless a count or a bucket is sent."""
    headers, _ = user
    fake_ydl.info = {"duration": 300.0}
    assert preview(client, headers)["estimate"]["credits"] == 5     # the price is the video's minutes either way
    auto = go(client, headers).json()
    assert auto["options"]["duration"] == url_clips.AUTO_DURATION and auto["options"]["limit"] is None
    assert auto["credits_reserved"] == 5
    named = go(client, headers, options={"max_clips": 2}).json()
    assert named["options"]["duration"] is None and named["options"]["max_clips"] == 2


def test_options_are_checked_like_post_clips(client, user, fake_ydl):
    headers, account = user
    fake_ydl.info = {"duration": 40.0}
    bad = go(client, headers, options={"max_clips": 99})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"
    outside = go(client, headers, options={"range": {"start": 100, "end": 200}})
    assert outside.status_code == 422 and outside.json()["error"]["code"] == "bad_range"
    assert client.post("/v1/imports/preview", json={"url": TWITCH, "options": {"range": {"start": 100, "end": 200}}},
                       headers=headers).json()["error"]["code"] == "bad_range"
    extra = client.post("/v1/clips/from-url", json={"url": TWITCH, "consent": True, "cookies": "x"}, headers=headers)
    assert extra.status_code == 422
    assert jobs_of(account["id"]) == [] and logs(account["id"]) == 0 and balance(client, headers) == 30


# ---- refused before anything is imported ----

def test_insufficient_credits_is_a_402_and_nothing_is_imported_or_logged(client, user, fake_ydl):
    headers, account = user
    fake_ydl.info = {"duration": 7200.0}                    # 120 credits; the account has 30
    assert preview(client, headers)["estimate"] | {"note": ""} == {
        "credits": 120, "basis": "source_minutes", "duration_sec": 7200.0, "balance": 30, "enough": False, "note": ""}
    r = go(client, headers)
    assert r.status_code == 402 and r.json()["error"]["code"] == "insufficient_credits"
    assert "120" in r.json()["error"]["message"]
    assert jobs_of(account["id"]) == [] and logs(account["id"]) == 0
    with new_session() as db:
        assert db.execute(select(Upload).where(Upload.account_id == account["id"])).all() == []
    assert account_rows(account["id"]) == [("grant", 30)]
    assert all(not i.params.get("progress_hooks") for i in fake_ydl.instances)   # nothing was downloaded


def test_consent_is_required(client, user, fake_ydl):
    headers, account = user
    for consent in (None, False, "true", 1):
        r = go(client, headers, consent=consent)
        assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"
    assert fake_ydl.instances == [] and jobs_of(account["id"]) == [] and logs(account["id"]) == 0


def test_the_import_switch_and_email_check_apply(client, user, fake_ydl, monkeypatch):
    headers, account = user
    monkeypatch.setattr(get_settings(), "imports_enabled", False)
    r = go(client, headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "imports_disabled"
    assert "Upload the file instead." in r.json()["error"]["message"]
    monkeypatch.setattr(get_settings(), "imports_enabled", True)
    with new_session() as db:
        db.get(Account, account["id"]).email_verified = False
        db.commit()
    r = go(client, headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"
    assert fake_ydl.instances == [] and jobs_of(account["id"]) == [] and account_rows(account["id"]) == [("grant", 30)]


@pytest.mark.parametrize("url, info, code", [
    ("https://internal.test/video.mp4", {}, "private_address"),
    (TWITCH, {"duration": 7 * 3600.0}, "video_too_long"),
    (TWITCH, {"is_live": True, "live_status": "is_live"}, "live_stream"),
    ("https://vimeo.com/123", {}, "unsupported_source"),
    ("https://cdn.test/video.mp4", {}, "duration_unknown"),     # a direct link: no length before a download
])
def test_refused_links_reserve_and_log_nothing(client, user, fake_ydl, web, url, info, code):
    headers, account = user
    fake_ydl.info = info
    r = go(client, headers, url=url)
    assert r.status_code == 422 and r.json()["error"]["code"] == code, r.text
    assert jobs_of(account["id"]) == [] and logs(account["id"]) == 0
    assert account_rows(account["id"]) == [("grant", 30)] and web.hits == []


# ---- the import fails: a full refund ----

@pytest.mark.parametrize("how, code", [("refused", "source_refused"), ("too_big", "file_too_large")])
def test_a_download_that_fails_midway_refunds_the_job(client, user, fake_ydl, monkeypatch, how, code):
    headers, account = user
    if how == "refused":
        fake_ydl.refuse_download = "ERROR: [twitch:vod] x: HTTP Error 403: Forbidden"
    else:
        fake_ydl.report_bytes = 10 ** 9                          # the progress hook sees more than the cap
        monkeypatch.setattr(get_settings(), "import_max_bytes", 10 ** 8)
    job = go(client, headers).json()
    assert balance(client, headers) == 29
    assert worker.run_once() == "FAILED"
    out = get(client, headers, job["job_id"])
    assert out["status"] == "FAILED" and out["error"]["code"] == code and out["import"]["status"] == "FAILED"
    assert "credits were returned" in out["error"]["message"]
    refunded_once(job["job_id"], 1)
    assert balance(client, headers) == 30 and worker.run_once() is None


def test_options_that_do_not_fit_the_stored_video_are_refunded(client, user, fake_ydl):
    """The metadata said 200 s, so a range at 100-150 s was fine; the file is 40 s."""
    headers, _ = user
    fake_ydl.info = {"duration": 200.0}
    job = go(client, headers, options={"range": {"start": 100, "end": 150}}).json()
    assert job["credits_reserved"] == 4
    assert worker.run_once() == "SUCCEEDED"
    out = get(client, headers, job["job_id"])
    assert out["status"] == "FAILED" and out["error"]["code"] == "bad_range"
    refunded_once(job["job_id"], 4)
    assert balance(client, headers) == 30


# ---- crashes: the sweeps finish or refund, exactly once ----

def test_a_worker_that_dies_during_the_import_is_swept_and_refunded_once(client, user, fake_ydl):
    headers, _ = user
    job = go(client, headers).json()
    assert worker.claim_job() == job["import"]["import_id"]
    with new_session() as db:
        db.get(Job, job["import"]["import_id"]).heartbeat_at = utcnow() - timedelta(hours=1)
        db.commit()
    assert worker.sweep_stale_jobs() == 1
    out = get(client, headers, job["job_id"])
    assert out["status"] == "FAILED" and out["error"]["code"] == "worker_lost"
    for _ in range(2):
        assert worker.sweep_stale_jobs() == 0 and url_clips.sweep_waiting() == 0
    refunded_once(job["job_id"], 1)
    assert balance(client, headers) == 30


def test_a_crash_after_the_import_before_chaining_is_finished_by_the_sweep(client, user, fake_ydl, monkeypatch):
    headers, _ = user
    job = go(client, headers).json()
    with monkeypatch.context() as m:                    # the import's own chaining step never runs
        m.setattr(url_clips, "resolve", lambda db, imp: [])
        assert worker.run_once() == "SUCCEEDED"
    assert get(client, headers, job["job_id"])["status"] == "WAITING"
    assert url_clips.sweep_waiting() == 1
    assert url_clips.sweep_waiting() == 0                # a second sweep changes nothing
    assert get(client, headers, job["job_id"])["status"] == "QUEUED"
    assert worker.run_once(pipeline=no_clips) == "SUCCEEDED"
    assert money(job["job_id"]) == [("reserve", -1, f"reserve:{job['job_id']}"),
                                    ("commit", 0, f"settle:{job['job_id']}")]


def test_a_waiting_job_whose_import_failed_unsettled_is_refunded_by_the_sweep(client, user, fake_ydl, monkeypatch):
    headers, _ = user
    fake_ydl.refuse_download = "ERROR: [twitch:vod] x: HTTP Error 403: Forbidden"
    job = go(client, headers).json()
    with monkeypatch.context() as m:
        m.setattr(url_clips, "resolve", lambda db, imp: [])
        assert worker.run_once() == "FAILED"
    assert balance(client, headers) == 29
    assert url_clips.sweep_waiting() == 1 and url_clips.sweep_waiting() == 0
    assert get(client, headers, job["job_id"])["error"]["code"] == "source_refused"
    refunded_once(job["job_id"], 1)


# ---- repeats ----

def test_a_double_click_starts_one_job(client, user, fake_ydl):
    headers, account = user
    first = go(client, headers)
    second = go(client, headers)
    assert first.status_code == 202 and second.status_code == 200
    assert second.json()["job_id"] == first.json()["job_id"]
    assert len(jobs_of(account["id"])) == 2                     # the clip job and its import
    assert logs(account["id"]) == 1 and balance(client, headers) == 29
    other = go(client, headers, options={"max_clips": 2})       # other options: another job, on the same import
    assert other.status_code == 202 and other.json()["import"]["import_id"] == first.json()["import"]["import_id"]
    assert logs(account["id"]) == 2 and balance(client, headers) == 28
    assert worker.run_once() == "SUCCEEDED"
    assert [get(client, headers, j)["status"] for j in (first.json()["job_id"], other.json()["job_id"])] == ["QUEUED"] * 2


def test_an_idempotency_key_returns_the_job_it_started(client, user, fake_ydl):
    headers, account = user
    first = go(client, headers, key="paste-1")
    again = go(client, headers, key="paste-1", options={"max_clips": 5})
    assert first.status_code == 202 and again.json()["job_id"] == first.json()["job_id"]
    assert len(fake_ydl.instances) == 1 and logs(account["id"]) == 1
    assert account_rows(account["id"]) == [("grant", 30), ("reserve", -1)]


def test_a_link_this_account_already_has_skips_the_import(client, user, fake_ydl):
    headers, account = user
    first = go(client, headers).json()
    worker.run_once()
    assert worker.run_once(pipeline=no_clips) == "SUCCEEDED"
    lookups = len(fake_ydl.instances)
    est = preview(client, headers, "https://twitch.tv/videos/2301234567")["estimate"]
    # Analysed before: charged on what is rendered. Automatic discovery may render the whole 40 s: 1 credit at most.
    assert est["basis"] == "rendered" and est["credits"] == 1
    r = go(client, headers, url="https://m.twitch.tv/videos/2301234567")
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "QUEUED" and job["credits_reserved"] == 1
    assert job["import"] == {"import_id": None, "status": "SUCCEEDED", "stage": "done", "progress": 100,
                             "url": TWITCH, "platform": "twitch", "reused": True,
                             "upload_id": get(client, headers, first["job_id"])["upload_id"], "error": None}
    assert len(fake_ydl.instances) == lookups                   # nothing looked up or downloaded
    assert logs(account["id"]) == 2                             # the consent is logged again
    assert len([j for j in jobs_of(account["id"]) if j.id.startswith("imp_")]) == 1
    assert worker.run_once(pipeline=no_clips) == "SUCCEEDED"
    assert get(client, headers, job["job_id"])["credits_charged"] == 0      # nothing rendered


# ---- cancel at any stage ----

def test_cancel_while_the_import_waits(client, user, fake_ydl):
    headers, _ = user
    job = go(client, headers).json()
    out = client.post(f"/v1/jobs/{job['job_id']}/cancel", headers=headers).json()
    assert out["status"] == "CANCELED" and out["import"]["status"] == "CANCELED"
    refunded_once(job["job_id"], 1)
    assert balance(client, headers) == 30 and worker.run_once() is None


def test_cancel_while_the_import_runs(client, user, fake_ydl):
    headers, account = user
    job = go(client, headers).json()
    imp_id = job["import"]["import_id"]
    assert worker.claim_job() == imp_id
    out = client.post(f"/v1/jobs/{job['job_id']}/cancel", headers=headers).json()
    assert out["status"] == "CANCELED" and balance(client, headers) == 30      # refunded at once
    assert worker.process_job(imp_id) == "CANCELED"             # the import stops at its next step
    refunded_once(job["job_id"], 1)
    assert not get_settings().storage_dir.joinpath("uploads", account["id"]).exists() or \
        list(get_settings().storage_dir.joinpath("uploads", account["id"]).glob("*")) == []


def test_cancelling_the_import_cancels_the_job_waiting_for_it(client, user, fake_ydl):
    headers, _ = user
    job = go(client, headers).json()
    client.post(f"/v1/imports/{job['import']['import_id']}/cancel", headers=headers)
    assert get(client, headers, job["job_id"])["status"] == "CANCELED"
    refunded_once(job["job_id"], 1)


def test_cancel_while_clipping(client, user, fake_ydl):
    headers, _ = user
    job = go(client, headers).json()
    worker.run_once()
    assert worker.claim_job() == job["job_id"]
    assert client.post(f"/v1/jobs/{job['job_id']}/cancel", headers=headers).json()["status"] == "RUNNING"
    assert worker.process_job(job["job_id"], pipeline=no_clips) == "CANCELED"
    refunded_once(job["job_id"], 1)
    assert balance(client, headers) == 30


# ---- the real length differs from the metadata ----

def test_a_longer_video_is_charged_the_quote_not_more(client, user, fake_ydl, long_video):
    headers, _ = user
    fake_ydl.video, fake_ydl.info = long_video, {"duration": 61.0}       # quoted 2; the file is 130 s (3)
    assert preview(client, headers)["estimate"]["credits"] == 2
    job = go(client, headers).json()
    assert job["credits_reserved"] == 2
    worker.run_once()
    assert worker.run_once(pipeline=no_clips) == "SUCCEEDED"
    out = get(client, headers, job["job_id"])
    assert out["credits_charged"] == 2 and balance(client, headers) == 28
    assert money(job["job_id"]) == [("reserve", -2, f"reserve:{job['job_id']}"), ("commit", 0, f"settle:{job['job_id']}")]


def test_a_shorter_video_is_charged_less(client, user, fake_ydl, long_video):
    headers, _ = user
    fake_ydl.video, fake_ydl.info = long_video, {"duration": 200.0}      # quoted 4; the file is 130 s (3)
    job = go(client, headers).json()
    assert job["credits_reserved"] == 4 and balance(client, headers) == 26
    worker.run_once()
    assert worker.run_once(pipeline=no_clips) == "SUCCEEDED"
    out = get(client, headers, job["job_id"])
    assert out["credits_charged"] == 3 and balance(client, headers) == 27
    assert money(job["job_id"]) == [("reserve", -4, f"reserve:{job['job_id']}"), ("commit", 1, f"settle:{job['job_id']}")]


def test_a_clip_job_that_fails_is_refunded(client, user, fake_ydl):
    headers, _ = user
    job = go(client, headers).json()
    worker.run_once()

    def broken(*args, **kwargs):
        raise PipelineError("no_moments", "Nothing to clip.")

    assert worker.run_once(pipeline=broken) == "FAILED"
    assert get(client, headers, job["job_id"])["error"]["code"] == "no_moments"
    refunded_once(job["job_id"], 1)
    assert balance(client, headers) == 30


# ---- takedown and retention ----

def test_takedown_of_a_waiting_link_job_refunds_it(client, user, fake_ydl):
    headers, _ = user
    job = go(client, headers).json()
    report = takedown(url="https://twitch.tv/videos/2301234567")
    assert {j for r in report.removed for j, _c in r.cancelled} == {job["job_id"], job["import"]["import_id"]}
    assert get(client, headers, job["job_id"])["status"] == "CANCELED"
    refunded_once(job["job_id"], 1)
    assert worker.run_once() is None


def test_takedown_and_retention_remove_a_finished_link_job(client, user, fake_ydl, transcriber):
    headers, account = user
    job = go(client, headers, options={"max_clips": 1, "clip_length": 10}).json()
    worker.run_once()
    assert worker.run_once(transcriber) == "SUCCEEDED"
    out = get(client, headers, job["job_id"])
    assert len(out["clips"]) == 1
    report = takedown(url=TWITCH)
    assert sum(r.clips for r in report.removed) == 1 and any(r.upload_removed for r in report.removed)
    assert get(client, headers, job["job_id"])["clips"] == []
    assert client.get("/v1/uploads", headers=headers).json()["uploads"] == []
    assert list(get_settings().storage_dir.joinpath("uploads", account["id"]).glob("*")) == []
    assert get(client, headers, job["job_id"])["credits_charged"] == 1       # a finished job keeps its charge


def test_retention_expires_a_link_job_like_any_other(client, user, fake_ydl, transcriber):
    headers, account = user
    job = go(client, headers, options={"max_clips": 1, "clip_length": 10}).json()
    worker.run_once()
    assert worker.run_once(transcriber) == "SUCCEEDED"
    upload_id = get(client, headers, job["job_id"])["upload_id"]
    past = utcnow() - timedelta(minutes=1)
    with new_session() as db:
        db.get(Upload, upload_id).expires_at = past
        db.get(Job, job["job_id"]).expires_at = past
        db.commit()
    assert worker.sweep_expired() >= 2
    with new_session() as db:
        assert db.get(Upload, upload_id).deleted_at is not None
        assert all(c.deleted_at for c in db.execute(select(Clip).where(Clip.job_id == job["job_id"])).scalars())
    assert list(get_settings().storage_dir.joinpath("uploads", account["id"]).glob("*")) == []


def test_a_link_job_counts_once_against_the_running_jobs_limit(client, user, fake_ydl):
    headers, account = user
    go(client, headers)
    with new_session() as db:
        assert active_jobs(db, account["id"]) == 1              # the waiting job; not its import as well
    assert go(client, headers, options={"max_clips": 2}).status_code == 202
    third = go(client, headers, options={"max_clips": 4})
    assert third.status_code == 429 and third.json()["error"]["code"] == "too_many_jobs"
    assert balance(client, headers) == 28 and logs(account["id"]) == 2


def test_jobs_that_end_without_a_worker_send_their_webhook(client, user, fake_ydl, monkeypatch):
    headers, _ = user
    sent = []
    monkeypatch.setattr(worker, "send_webhook", sent.append)
    fake_ydl.refuse_download = "ERROR: [twitch:vod] x: HTTP Error 403: Forbidden"
    job = go(client, headers).json()
    worker.run_once()
    assert job["job_id"] in sent
