"""Link import end to end: consent, the log row, each refusal, a finished import that a clip job runs on, bulk,
and what an import costs (nothing). Direct links come from the local HTTPS server; platforms from the stand-in."""
import uuid

import pytest
from sqlalchemy import select

from app import ledger, routes_ingest, worker
from app.config import get_settings
from app.db import new_session
from app.models import CreditLedger, ImportLog, Job, Upload
from tests.ingest_support import fake_ydl, no_stray_imports, web  # noqa: F401
from tests.test_api import balance

VIDEO = "https://cdn.test/video.mp4"
TWITCH = "https://www.twitch.tv/videos/2301234567"


def start(client, headers, url=VIDEO, consent=True):
    return client.post("/v1/imports", json={"url": url, "consent": consent}, headers=headers)


def finish(client, headers, import_id) -> dict:
    """Run the worker on the waiting import and return it."""
    worker.run_once()
    return client.get(f"/v1/imports/{import_id}", headers=headers).json()


def log_rows(account_id) -> list[ImportLog]:
    with new_session() as db:
        return db.execute(select(ImportLog).where(ImportLog.account_id == account_id).order_by(ImportLog.id)).scalars().all()


def import_jobs(account_id) -> list[Job]:
    with new_session() as db:
        return db.execute(select(Job).where(Job.account_id == account_id, Job.id.like("imp%"))).scalars().all()


def stored_files(account_id) -> list[str]:
    folder = get_settings().storage_dir / "uploads" / account_id
    return sorted(p.name for p in folder.glob("*")) if folder.exists() else []


def ledger_rows(account_id) -> list[tuple]:
    with new_session() as db:
        return [(r.kind, r.delta) for r in db.execute(select(CreditLedger).where(
            CreditLedger.account_id == account_id).order_by(CreditLedger.id)).scalars()]


# ---- consent ----

@pytest.mark.parametrize("body", [
    {"url": VIDEO}, {"url": VIDEO, "consent": False}, {"url": VIDEO, "consent": None},
    {"url": VIDEO, "consent": "true"}, {"url": VIDEO, "consent": 1}, {"url": VIDEO, "consent": "yes"},
])
def test_without_consent_nothing_is_imported_and_the_422_says_why(client, user, web, body):
    headers, account = user
    r = client.post("/v1/imports", json=body, headers=headers)
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "consent_required"
    assert "consent must be true" in error["message"] and "permission to clip" in error["message"]
    assert log_rows(account["id"]) == [] and import_jobs(account["id"]) == []
    assert web.hits == [] and web.resolved == []                # nothing was looked up or fetched


def test_bulk_needs_consent_too(client, user, web):
    headers, account = user
    r = client.post("/v1/imports/bulk", json={"urls": [VIDEO], "consent": False}, headers=headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"
    assert log_rows(account["id"]) == []


def test_needs_a_login_and_takes_no_other_fields(client, user, web):
    headers, account = user
    assert client.post("/v1/imports", json={"url": VIDEO, "consent": True}).status_code == 401
    for extra in ({"cookies": "session=abc"}, {"proxy": "http://proxy.invalid"}, {"username": "x", "password": "y"},
                  {"impersonate": "chrome"}, {"options": {"geo_bypass": True}}, {"headers": {"User-Agent": "Mozilla"}}):
        r = client.post("/v1/imports", json={"url": VIDEO, "consent": True, **extra}, headers=headers)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error", r.text
    assert log_rows(account["id"]) == []


# ---- refusals at the door ----

@pytest.mark.parametrize("url, code", [
    ("https://vimeo.com/123456", "unsupported_source"),
    ("https://example.test/index.html", "unsupported_source"),
    ("http://cdn.test/video.mp4", "https_only"),
    ("https://user:pw@cdn.test/video.mp4", "credentials_in_url"),
    ("https://www.twitch.tv/somechannel", "unsupported_link"),
    ("https://www.youtube.com/playlist?list=PL1", "unsupported_link"),
    ("https://internal.test/video.mp4", "private_address"),
    ("https://169.254.169.254/latest/video.mp4", "private_address"),
    ("https://127.0.0.1/video.mp4", "private_address"),
    ("https://nowhere.test/video.mp4", "unreachable"),
    ("not a link", "bad_url"),
])
def test_refused_links_are_a_clear_422_and_nothing_is_logged_or_queued(client, user, web, url, code):
    headers, account = user
    r = start(client, headers, url)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == code and len(r.json()["error"]["message"]) > 20
    assert log_rows(account["id"]) == [] and import_jobs(account["id"]) == []
    assert web.hits == [] and web.connected == []


def test_the_switch_turns_imports_off(client, user, web, monkeypatch):
    headers, account = user
    monkeypatch.setattr(get_settings(), "imports_enabled", False)
    r = start(client, headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "imports_disabled"
    assert "Upload the file instead." in r.json()["error"]["message"]
    bulk = client.post("/v1/imports/bulk", json={"urls": [VIDEO], "consent": True}, headers=headers)
    assert bulk.status_code == 503
    assert client.get("/v1/imports/sources").json()["enabled"] is False
    assert log_rows(account["id"]) == []


def test_an_import_queued_before_the_switch_went_off_fails_cleanly(client, user, web, monkeypatch):
    headers, _ = user
    imp = start(client, headers).json()
    monkeypatch.setattr(get_settings(), "imports_enabled", False)
    done = finish(client, headers, imp["import_id"])
    assert done["status"] == "FAILED" and done["error"]["code"] == "imports_disabled"
    assert web.hits == []


# ---- a successful import ----

def test_a_direct_link_becomes_an_upload_that_a_clip_job_runs_on(client, user, web, video, transcriber):
    headers, account = user
    r = start(client, headers, VIDEO + "#t=5")
    assert r.status_code == 202, r.text
    imp = r.json()
    assert imp["import_id"].startswith("imp_") and imp["status"] == "QUEUED"
    assert imp["url"] == VIDEO and imp["platform"] == "direct" and imp["upload_id"] is None and imp["error"] is None

    # Logged before anything is fetched: account, link, platform, consent, time.
    assert web.hits == [] and web.connected == []
    rows = log_rows(account["id"])
    assert len(rows) == 1
    assert (rows[0].account_id, rows[0].source_url, rows[0].platform, rows[0].consent) == (account["id"], VIDEO, "direct", True)
    assert rows[0].created_at is not None

    # Nothing is reserved or charged, and nothing can be used yet.
    assert balance(client, headers) == 30 and ledger_rows(account["id"]) == [("grant", 30)]
    assert client.get("/v1/uploads", headers=headers).json()["uploads"] == []
    placeholder = import_jobs(account["id"])[0].upload_id
    early = client.post("/v1/clips", json={"upload_id": placeholder}, headers=headers)
    assert early.status_code == 404 and early.json()["error"]["code"] == "upload_not_found"

    done = finish(client, headers, imp["import_id"])
    assert done["status"] == "SUCCEEDED" and done["progress"] == 100 and done["reused"] is False, done
    up = done["upload"]
    assert done["upload_id"] == up["upload_id"] == placeholder
    assert up["filename"] == "video.mp4" and up["size_bytes"] == video.stat().st_size
    assert 39 <= up["duration_sec"] <= 41 and (up["width"], up["height"]) == (640, 360) and up["has_audio"] is True
    assert up["credits_required"] == 1 and up["analyzed"] is False
    assert [u["upload_id"] for u in client.get("/v1/uploads", headers=headers).json()["uploads"]] == [up["upload_id"]]
    assert stored_files(account["id"]) == [f"{up['upload_id']}.mp4"]
    with new_session() as db:
        row = db.get(Upload, up["upload_id"])
        assert (row.source_url, row.source_platform) == (VIDEO, "direct")
        assert row.content_hash and row.deleted_at is None
    assert balance(client, headers) == 30 and ledger_rows(account["id"]) == [("grant", 30)]    # the import was free

    # The upload behaves exactly like an uploaded file: a clip job runs on it and is charged as usual.
    job = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                      headers=headers)
    assert job.status_code == 202, job.text
    assert balance(client, headers) == 29
    assert worker.run_once(transcriber) == "SUCCEEDED"
    result = client.get(f"/v1/jobs/{job.json()['job_id']}", headers=headers).json()
    assert result["status"] == "SUCCEEDED" and result["credits_charged"] == 1 and len(result["clips"]) == 1
    assert 12 <= result["clips"][0]["start_sec"] <= 24
    project = client.get(f"/v1/projects/{up['upload_id']}", headers=headers).json()
    assert len(project["clips"]) == 1


def test_importing_the_same_link_again_reuses_the_upload(client, user, web):
    headers, account = user
    first = finish(client, headers, start(client, headers).json()["import_id"])
    again = finish(client, headers, start(client, headers).json()["import_id"])
    assert again["status"] == "SUCCEEDED" and again["reused"] is True
    assert again["upload_id"] == first["upload_id"]
    assert len(stored_files(account["id"])) == 1                    # one file on disk
    assert len(client.get("/v1/uploads", headers=headers).json()["uploads"]) == 1
    assert len(log_rows(account["id"])) == 2                        # both imports are on record


def test_the_same_bytes_from_another_link_are_a_separate_upload(client, user, web):
    """Every upload has one source, so a takedown of that source finds all of it."""
    headers, account = user
    first = finish(client, headers, start(client, headers).json()["import_id"])
    other = finish(client, headers, start(client, headers, "https://other.test/video.mp4").json()["import_id"])
    assert other["status"] == "SUCCEEDED" and other["reused"] is False
    assert other["upload_id"] != first["upload_id"] and len(stored_files(account["id"])) == 2


def test_a_link_already_being_imported_is_not_queued_twice(client, user, web):
    headers, account = user
    first = start(client, headers).json()
    second = start(client, headers, VIDEO + "#again").json()
    assert second["import_id"] == first["import_id"]
    assert len(import_jobs(account["id"])) == 1 and len(log_rows(account["id"])) == 1


def test_drive_style_download_takes_its_name_from_the_server(client, user, web, monkeypatch):
    """Google Drive and Dropbox links have no file name in the URL: the download names the file."""
    headers, _ = user
    from app.ingest import sources
    real = sources._gdrive

    def local_drive(host, path, query):
        source = real(host, path, query)
        return sources.Source(source.platform, source.downloader, source.url, "https://cdn.test/download") if source else None

    monkeypatch.setattr(sources, "_gdrive", local_drive)
    imp = start(client, headers, "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view?usp=sharing").json()
    assert imp["platform"] == "gdrive" and imp["url"] == "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view"
    done = finish(client, headers, imp["import_id"])
    assert done["status"] == "SUCCEEDED" and done["upload"]["filename"] == "Shared Recording.mp4"


# ---- failures in the worker: the log row is there, nothing is stored, nothing is charged ----

@pytest.mark.parametrize("path, code", [
    ("/redirect-private.mp4", "private_address"),
    ("/redirect-metadata.mp4", "private_address"),
    ("/redirect-http.mp4", "https_only"),
    ("/page.mp4", "not_a_video"),
    ("/garbage.mp4", "unsupported_media"),          # the right name and type, but ffprobe says it is no video
    ("/forbidden.mp4", "source_refused"),
    ("/huge-declared.mp4", "file_too_large"),
    ("/loop.mp4", "too_many_redirects"),
])
def test_a_failed_import_is_logged_cleaned_up_and_free(client, user, web, path, code):
    headers, account = user
    imp = start(client, headers, f"https://cdn.test{path}").json()
    done = finish(client, headers, imp["import_id"])
    assert done["status"] == "FAILED" and done["error"]["code"] == code, done
    assert "pload" in done["error"]["message"] or "Maximum" in done["error"]["message"]
    assert done["upload_id"] is None and done["upload"] is None
    rows = log_rows(account["id"])
    assert len(rows) == 1 and rows[0].source_url == f"https://cdn.test{path}" and rows[0].consent is True
    assert stored_files(account["id"]) == []
    assert client.get("/v1/uploads", headers=headers).json()["uploads"] == []
    assert balance(client, headers) == 30 and ledger_rows(account["id"]) == [("grant", 30)]
    assert list(get_settings().work_dir.glob("imp_*")) == []        # the working folder is gone


def test_size_time_and_length_limits_apply(client, user, web, monkeypatch):
    headers, _ = user
    s = get_settings()
    monkeypatch.setattr(s, "import_max_bytes", 100_000)
    assert finish(client, headers, start(client, headers).json()["import_id"])["error"]["code"] == "file_too_large"
    monkeypatch.setattr(s, "import_max_bytes", 8 * 1024 ** 3)
    monkeypatch.setattr(s, "max_upload_bytes", 100_000)               # the upload limit applies to imports too
    assert finish(client, headers, start(client, headers).json()["import_id"])["error"]["code"] == "file_too_large"
    monkeypatch.setattr(s, "max_upload_bytes", 8 * 1024 ** 3)
    monkeypatch.setattr(s, "import_max_duration_sec", 30)             # the test video is 40 s
    assert finish(client, headers, start(client, headers).json()["import_id"])["error"]["code"] == "video_too_long"
    monkeypatch.setattr(s, "import_max_duration_sec", 6 * 3600)
    monkeypatch.setattr(s, "min_duration_sec", 60)
    assert finish(client, headers, start(client, headers).json()["import_id"])["error"]["code"] == "video_too_short"
    monkeypatch.setattr(s, "min_duration_sec", 5)
    monkeypatch.setattr(s, "import_timeout_sec", 1)
    slow = finish(client, headers, start(client, headers, "https://cdn.test/slow.mp4").json()["import_id"])
    assert slow["error"]["code"] == "import_timeout"


def test_a_reserved_import_job_is_refunded_when_it_fails(client, user, web):
    """Imports reserve nothing today. If one ever does, every failure path still ends in a refund."""
    headers, account = user
    imp = start(client, headers, "https://cdn.test/page.mp4").json()
    with new_session() as db:
        job = db.get(Job, imp["import_id"])
        job.credits_reserved = 7
        ledger.reserve(db, account["id"], job.id, 7)
        db.commit()
    assert balance(client, headers) == 23
    assert finish(client, headers, imp["import_id"])["status"] == "FAILED"
    assert balance(client, headers) == 30
    assert ledger_rows(account["id"]) == [("grant", 30), ("reserve", -7), ("release", 7)]


def test_a_reserved_import_job_is_refunded_when_it_is_cancelled(client, user, web):
    headers, account = user
    imp = start(client, headers).json()
    with new_session() as db:
        job = db.get(Job, imp["import_id"])
        job.credits_reserved = 4
        ledger.reserve(db, account["id"], job.id, 4)
        db.commit()
    r = client.post(f"/v1/imports/{imp['import_id']}/cancel", headers=headers)
    assert r.json()["status"] == "CANCELED" and balance(client, headers) == 30
    assert worker.run_once() is None                                 # nothing left to run


def test_cancel_before_and_during(client, user, web):
    headers, account = user
    imp = start(client, headers).json()
    assert client.post(f"/v1/imports/{imp['import_id']}/cancel", headers=headers).json()["status"] == "CANCELED"
    assert ledger_rows(account["id"]) == [("grant", 30)]             # no ledger row for a free job
    running = start(client, headers).json()
    assert worker.claim_job() == running["import_id"]
    assert client.post(f"/v1/imports/{running['import_id']}/cancel", headers=headers).json()["status"] == "RUNNING"
    assert worker.process_job(running["import_id"]) == "CANCELED"
    assert web.hits == [] and stored_files(account["id"]) == []


def test_imports_are_private_to_their_account(client, user, web):
    headers, _ = user
    imp = start(client, headers).json()
    other = client.post("/v1/auth/signup", json={"email": f"u{uuid.uuid4().hex[:10]}@example.org",
                                                 "password": "correct-horse-9"}).json()
    theirs = {"Authorization": f"Bearer {other['token']}"}
    assert client.get(f"/v1/imports/{imp['import_id']}", headers=theirs).status_code == 404
    assert client.post(f"/v1/imports/{imp['import_id']}/cancel", headers=theirs).status_code == 404
    assert client.get("/v1/imports", headers=theirs).json() == {"total": 0, "imports": []}
    mine = client.get("/v1/imports", headers=headers).json()
    assert mine["total"] == 1 and mine["imports"][0]["import_id"] == imp["import_id"]
    assert client.get("/v1/imports/job_notanimport", headers=headers).status_code == 404


# ---- platforms, through the stand-in ----

def test_a_twitch_link_goes_through_the_platform_downloader(client, user, fake_ydl, video):
    headers, account = user
    imp = start(client, headers, "https://m.twitch.tv/videos/2301234567?t=1h").json()
    assert imp["platform"] == "twitch" and imp["url"] == TWITCH
    done = finish(client, headers, imp["import_id"])
    assert done["status"] == "SUCCEEDED", done
    assert done["upload"]["filename"] == "Ranked grind_ part 3 _ finale.mp4"
    assert done["upload"]["size_bytes"] == video.stat().st_size
    assert len(fake_ydl.instances) == 1 and fake_ydl.instances[0].urls == [TWITCH]
    options = fake_ydl.instances[0].params
    for name in ("cookiefile", "cookiesfrombrowser", "username", "password", "impersonate", "geo_bypass"):
        assert not options[name]
    assert options["proxy"] == "" and options["extractor_args"] == {} and options["js_runtimes"] == {}
    assert log_rows(account["id"])[0].platform == "twitch"


@pytest.mark.parametrize("url, platform, raw, starts, code", [
    ("https://kick.com/somechannel/videos/0a1b2c3d-1111-2222-3333-444455556666", "kick",
     "ERROR: [kick:vod] x: Unable to download JSON metadata: HTTP Error 403: Forbidden", "Kick refused the download.",
     "source_refused"),
    ("https://youtu.be/dQw4w9WgXcQ", "youtube",
     "ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies",
     "YouTube often refuses automated downloads: upload the file instead", "login_required"),
    (TWITCH, "twitch", "ERROR: [twitch:vod] 2301234567: This video is only available for subscribers",
     "This video needs a login", "login_required"),
])
def test_a_site_that_refuses_is_a_clean_failure(client, user, fake_ydl, url, platform, raw, starts, code):
    headers, account = user
    fake_ydl.refuse_extract = raw
    imp = start(client, headers, url).json()
    done = finish(client, headers, imp["import_id"])
    assert done["status"] == "FAILED" and done["platform"] == platform
    assert done["error"]["code"] == code and done["error"]["message"].startswith(starts), done
    assert "pload the file instead" in done["error"]["message"] and "cookie" not in done["error"]["message"].lower()
    assert len(fake_ydl.instances) == 1 and len(fake_ydl.instances[0].urls) == 1     # one attempt, then stop
    assert len(log_rows(account["id"])) == 1 and stored_files(account["id"]) == []
    assert balance(client, headers) == 30


# ---- bulk ----

def test_bulk_lists_every_link_with_its_import_or_its_refusal(client, user, web, fake_ydl):
    headers, account = user
    urls = [VIDEO, "https://vimeo.com/1", TWITCH, "http://cdn.test/video.mp4", VIDEO + "#same",
            "https://internal.test/video.mp4", "https://other.test/video.mp4"]
    r = client.post("/v1/imports/bulk", json={"urls": urls, "consent": True}, headers=headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert [row["url"] for row in out["imports"]] == urls
    codes = [(row["error"] or {}).get("code") for row in out["imports"]]
    assert codes == [None, "unsupported_source", None, "https_only", None, "private_address", None]
    assert out["accepted"] == 4 and out["refused"] == 3
    ids = [row["import"]["import_id"] for row in out["imports"] if row["import"]]
    assert ids[0] == ids[2] and len(set(ids)) == 3                  # the repeated link is the same import
    assert [row.source_url for row in log_rows(account["id"])] == [VIDEO, TWITCH, "https://other.test/video.mp4"]
    assert balance(client, headers) == 30
    statuses = []
    while worker.run_once() is not None:
        pass
    for import_id in dict.fromkeys(ids):
        statuses.append(client.get(f"/v1/imports/{import_id}", headers=headers).json()["status"])
    assert statuses == ["SUCCEEDED"] * 3
    assert len(client.get("/v1/uploads", headers=headers).json()["uploads"]) == 3


def test_bulk_limits(client, user, web):
    headers, account = user
    assert routes_ingest.BULK_MAX == 10
    eleven = [f"https://cdn.test/video.mp4?n={i}" for i in range(11)]
    r = client.post("/v1/imports/bulk", json={"urls": eleven, "consent": True}, headers=headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_urls"
    assert client.post("/v1/imports/bulk", json={"urls": [], "consent": True}, headers=headers).json()["error"]["code"] == "no_urls"
    assert log_rows(account["id"]) == []
    ten = client.post("/v1/imports/bulk", json={"urls": eleven[:10], "consent": True}, headers=headers).json()
    assert ten["accepted"] == 10 and len(log_rows(account["id"])) == 10
    # Ten are waiting: one more is refused until one finishes.
    more = start(client, headers, eleven[10])
    assert more.status_code == 429 and more.json()["error"]["code"] == "too_many_imports"
    assert len(log_rows(account["id"])) == 10


def test_sources_endpoint_lists_what_can_be_imported(client):
    out = client.get("/v1/imports/sources").json()
    assert [s["platform"] for s in out["sources"]] == ["twitch", "kick", "direct", "gdrive", "dropbox", "youtube"]
    assert out["bulk_max"] == 10 and out["enabled"] is True and "permission to clip" in out["consent"]
    assert out["max_bytes"] == 8 * 1024 ** 3 and out["max_duration_sec"] == 6 * 3600
    assert ".mp4" in out["file_types"]
