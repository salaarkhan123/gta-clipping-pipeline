"""Takedown: everything that came from a source URL, or from one account's link imports, is removed; waiting
jobs are cancelled and refunded, running jobs are stopped and refunded; a second run changes nothing."""
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app import worker
from app.config import get_settings
from app.db import new_session
from app.ingest.takedown import takedown
from app.models import Clip, Export, ImportLog, Job, Upload, new_id
from app.storage import get_storage, transcript_key
from tests.ingest_support import no_stray_imports, web  # noqa: F401
from tests.test_api import balance, upload as hand_upload

# Each test imports from links of its own (the query makes them distinct sources), so a takedown in one test
# never meets another test's uploads: the database is shared by the whole run.
RUN = uuid.uuid4().hex[:8]
VIDEO = f"https://cdn.test/video.mp4?run={RUN}"
OTHER = f"https://other.test/video.mp4?run={RUN}"


@pytest.fixture
def link():
    return f"https://cdn.test/video.mp4?v={uuid.uuid4().hex[:10]}"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "admin.py"


def new_user(client):
    r = client.post("/v1/auth/signup", json={"email": f"u{uuid.uuid4().hex[:10]}@example.org", "password": "correct-horse-9"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]


def imported(client, headers, url=VIDEO) -> str:
    """Import a link to the end; returns the upload id."""
    imp = client.post("/v1/imports", json={"url": url, "consent": True}, headers=headers).json()
    worker.run_once()
    done = client.get(f"/v1/imports/{imp['import_id']}", headers=headers).json()
    assert done["status"] == "SUCCEEDED", done
    return done["upload_id"]


def clip_job(client, headers, upload_id) -> str:
    r = client.post("/v1/clips", json={"upload_id": upload_id, "options": {"max_clips": 1, "clip_length": 10}},
                    headers=headers)
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def files_of(account_id) -> list[str]:
    root = get_settings().storage_dir
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and account_id in str(p))


def clip_files(job_id) -> list[str]:
    folder = get_settings().storage_dir / "clips" / job_id
    return sorted(p.name for p in folder.glob("*")) if folder.exists() else []


def run_admin(*argv) -> None:
    spec = importlib.util.spec_from_file_location("admin_script_takedown", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    old = sys.argv
    sys.argv = ["admin.py", *argv]
    try:
        with pytest.raises(SystemExit) as e:
            mod.main()
    finally:
        sys.argv = old
    assert e.value.code in (0, None), e.value.code


def test_takedown_by_url_removes_the_upload_its_clips_and_files_and_refunds_waiting_jobs(client, user, web, transcriber, link):
    headers, account = user
    VIDEO = link
    upload_id = imported(client, headers, VIDEO)
    done_job = clip_job(client, headers, upload_id)
    assert worker.run_once(transcriber) == "SUCCEEDED"                   # one finished job with a clip: 1 credit
    waiting_job = clip_job(client, headers, upload_id)                   # one waiting job: credits held
    held = 30 - balance(client, headers) - 1
    assert held >= 1
    storage = get_storage()
    tkey = transcript_key(upload_id)                                     # a transcript kept for this upload
    note = get_settings().work_dir / "t.json"
    note.write_text("{}")
    storage.put(tkey, note)
    with new_session() as db:                                            # and a full-quality export of the clip
        clip = db.execute(select(Clip).where(Clip.job_id == done_job)).scalar_one()
        export_key = f"exports/{account['id']}/{clip.id}.mp4"
        storage.put(export_key, note)
        db.add(Export(id=new_id("exp"), clip_id=clip.id, account_id=account["id"], resolution="1080", options={},
                      status="DONE", storage_key=export_key))
        db.commit()
    assert len(clip_files(done_job)) >= 1 and storage.exists(f"uploads/{account['id']}/{upload_id}.mp4")

    # A dry run reports and changes nothing.
    dry = takedown(url=VIDEO, dry_run=True)
    assert dry.removed[0].upload_removed and dry.removed[0].clips == 1 and dry.removed[0].cancelled == [(waiting_job, held)]
    assert "dry run" in dry.lines()[0] and any("would remove" in line for line in dry.lines())
    assert storage.exists(f"uploads/{account['id']}/{upload_id}.mp4") and storage.exists(tkey) and storage.exists(export_key)
    assert client.get(f"/v1/jobs/{waiting_job}", headers=headers).json()["status"] == "QUEUED"
    assert len(client.get("/v1/uploads", headers=headers).json()["uploads"]) == 1

    # The real one, by a different spelling of the same link.
    report = takedown(url=VIDEO.replace("cdn.test", "CDN.test") + "#t=30")
    removed = report.removed[0]
    assert removed.upload_id == upload_id and removed.upload_removed and removed.clips == 1
    assert removed.cancelled == [(waiting_job, held)] and removed.stopping == []
    assert f"uploads/{account['id']}/{upload_id}.mp4" in removed.files and tkey in removed.files and export_key in removed.files
    text = "\n".join(report.lines())
    assert upload_id in text and account["id"] in text and VIDEO in text and "1 clip(s) removed" in text
    assert f"job {waiting_job} cancelled, {held} credit(s) returned" in text and "Import log: 1 row(s)" in text

    # Gone for the user: the upload, the clip, every stored file.
    assert client.get("/v1/uploads", headers=headers).json()["uploads"] == []
    assert client.get(f"/v1/projects/{upload_id}", headers=headers).status_code == 404
    assert client.get("/v1/clips", headers=headers).json()["total"] == 0
    assert client.get(f"/v1/jobs/{done_job}", headers=headers).json()["clips"] == []
    assert files_of(account["id"]) == [] and clip_files(done_job) == []
    assert not storage.exists(tkey) and not storage.exists(export_key)
    assert client.post("/v1/clips", json={"upload_id": upload_id}, headers=headers).status_code == 404
    with new_session() as db:
        assert db.get(Upload, upload_id).deleted_at is not None
        assert db.execute(select(Clip).where(Clip.job_id == done_job)).scalar_one().deleted_at is not None
        assert db.execute(select(Export).where(Export.account_id == account["id"])).scalar_one().storage_key is None
        assert len(db.execute(select(ImportLog).where(ImportLog.account_id == account["id"])).all()) == 1   # the log stays

    # The waiting job was cancelled and refunded through the ledger; the finished job stays charged.
    waiting = client.get(f"/v1/jobs/{waiting_job}", headers=headers).json()
    assert waiting["status"] == "CANCELED" and waiting["credits_charged"] == 0 and waiting["error"]["code"] == "taken_down"
    assert balance(client, headers) == 29
    assert worker.run_once(transcriber) is None                          # nothing is left to run

    # Twice: nothing changes, nothing is refunded again.
    again = takedown(url=VIDEO)
    assert not any(r.changed for r in again.removed)
    assert "Nothing to remove." in "\n".join(again.lines())
    assert balance(client, headers) == 29


def test_takedown_stops_a_running_job_and_the_worker_refunds_it(client, user, web, transcriber, link):
    headers, account = user
    VIDEO = link
    upload_id = imported(client, headers, VIDEO)
    job_id = clip_job(client, headers, upload_id)
    assert balance(client, headers) == 29
    assert worker.claim_job() == job_id                                  # a worker has it
    report = takedown(url=VIDEO)
    assert report.removed[0].stopping == [job_id] and report.removed[0].cancelled == []
    assert "told to stop" in "\n".join(report.lines())
    again = takedown(url=VIDEO)                                          # before the worker reacted
    assert again.removed[0].still_stopping == [job_id] and not again.removed[0].changed
    assert worker.process_job(job_id, transcriber) == "CANCELED"         # the worker's next step
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "CANCELED" and job["credits_charged"] == 0 and job["clips"] == []
    assert balance(client, headers) == 30                                # refunded
    assert files_of(account["id"]) == [] and clip_files(job_id) == []
    final = takedown(url=VIDEO)
    assert not any(r.changed for r in final.removed) and final.removed[0].still_stopping == []


def test_takedown_cancels_an_import_that_has_not_finished(client, user, web, link):
    headers, account = user
    VIDEO = link
    waiting = client.post("/v1/imports", json={"url": VIDEO, "consent": True}, headers=headers).json()
    report = takedown(url=VIDEO)
    assert report.removed[0].cancelled == [(waiting["import_id"], 0)]
    got = client.get(f"/v1/imports/{waiting['import_id']}", headers=headers).json()
    assert got["status"] == "CANCELED" and got["upload_id"] is None
    assert worker.run_once() is None and web.hits == []
    running = client.post("/v1/imports", json={"url": VIDEO, "consent": True}, headers=headers).json()
    assert worker.claim_job() == running["import_id"]
    assert takedown(url=VIDEO).removed[-1].stopping == [running["import_id"]]
    assert worker.process_job(running["import_id"]) == "CANCELED"        # it never becomes an upload
    assert client.get("/v1/uploads", headers=headers).json()["uploads"] == [] and files_of(account["id"]) == []
    assert balance(client, headers) == 30


def test_takedown_by_url_covers_every_account_and_only_that_url(client, web, link):
    VIDEO = link
    a_headers, a = new_user(client)
    b_headers, b = new_user(client)
    a_upload, b_upload = imported(client, a_headers, VIDEO), imported(client, b_headers, VIDEO)
    a_other = imported(client, a_headers, OTHER)
    report = takedown(url=VIDEO)
    assert sorted(r.upload_id for r in report.removed if r.changed) == sorted([a_upload, b_upload])
    assert [u["upload_id"] for u in client.get("/v1/uploads", headers=a_headers).json()["uploads"]] == [a_other]
    assert client.get("/v1/uploads", headers=b_headers).json()["uploads"] == []
    assert files_of(b["id"]) == [] and len(files_of(a["id"])) == 1


def test_takedown_by_account_removes_its_imports_and_nothing_else(client, web, video, transcriber):
    a_headers, a = new_user(client)
    b_headers, b = new_user(client)
    by_hand = hand_upload(client, a_headers, video)["upload_id"]          # an ordinary upload: not an import
    a_first, a_second = imported(client, a_headers), imported(client, a_headers, OTHER)
    b_upload = imported(client, b_headers)
    job_id = clip_job(client, a_headers, a_first)
    assert worker.run_once(transcriber) == "SUCCEEDED"

    dry = takedown(account=a["email"].upper(), dry_run=True)             # by email, any case
    assert sorted(r.upload_id for r in dry.removed if r.changed) == sorted([a_first, a_second])
    assert len(client.get("/v1/uploads", headers=a_headers).json()["uploads"]) == 3

    report = takedown(account=a["id"])                                   # by id
    assert sorted(r.upload_id for r in report.removed if r.changed) == sorted([a_first, a_second])
    assert sum(r.clips for r in report.removed) == 1 and "Import log: 2 row(s)" in "\n".join(report.lines())
    assert [u["upload_id"] for u in client.get("/v1/uploads", headers=a_headers).json()["uploads"]] == [by_hand]
    assert client.get(f"/v1/jobs/{job_id}", headers=a_headers).json()["clips"] == []
    assert [u["upload_id"] for u in client.get("/v1/uploads", headers=b_headers).json()["uploads"]] == [b_upload]
    assert len(files_of(a["id"])) == 1 and len(files_of(b["id"])) == 1

    again = takedown(account=a["id"])
    assert not any(r.changed for r in again.removed)
    with pytest.raises(LookupError):
        takedown(account="nobody@example.org")
    with pytest.raises(ValueError):
        takedown()
    with pytest.raises(ValueError):
        takedown(url=VIDEO, account=a["id"])


def test_a_url_nobody_imported_changes_nothing(client, user, web, link):
    headers, _ = user
    upload_id = imported(client, headers, link)
    report = takedown(url=f"https://cdn.test/some-other-video.mp4?v={uuid.uuid4().hex}")
    assert report.removed == [] and report.log_rows == 0 and "Nothing to remove." in "\n".join(report.lines())
    assert [u["upload_id"] for u in client.get("/v1/uploads", headers=headers).json()["uploads"]] == [upload_id]


def test_the_admin_command(client, user, web, capsys, link):
    headers, account = user
    VIDEO = link
    upload_id = imported(client, headers, VIDEO)
    run_admin("takedown", "--url", VIDEO, "--dry-run")
    out = capsys.readouterr().out
    assert "dry run" in out and upload_id in out and "upload would remove" in out
    assert len(client.get("/v1/uploads", headers=headers).json()["uploads"]) == 1
    run_admin("takedown", "--url", VIDEO)
    out = capsys.readouterr().out
    assert f"{upload_id}  account {account['id']}  direct  {VIDEO}" in out and "Total: 1 upload(s)" in out
    assert client.get("/v1/uploads", headers=headers).json()["uploads"] == []
    run_admin("takedown", "--url", VIDEO)
    assert "Nothing to remove." in capsys.readouterr().out
    run_admin("takedown", "--account", account["email"])
    assert "Nothing to remove." in capsys.readouterr().out
    for bad in (["takedown"], ["takedown", "--url", VIDEO, "--account", account["id"]]):
        old, sys.argv = sys.argv, ["admin.py", *bad]
        try:
            spec = importlib.util.spec_from_file_location("admin_script_takedown_bad", SCRIPT)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            with pytest.raises(SystemExit) as e:
                mod.main()
            assert e.value.code == 2                                     # argparse: exactly one of --url, --account
        finally:
            sys.argv = old
    capsys.readouterr()
