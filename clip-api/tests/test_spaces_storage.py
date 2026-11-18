"""S3 backend end to end (upload, job, download) and the local-to-bucket migration, against moto's HTTP S3."""
import importlib.util
from datetime import timedelta
from pathlib import Path

import boto3
import httpx

from app import storage, worker
from app.config import get_settings
from app.db import new_session
from app.models import Upload, utcnow
from tests.test_api import upload
from tests.test_check_storage import BUCKET, keys, s3  # noqa: F401  (fixture)

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_storage.py"


def load_script():
    spec = importlib.util.spec_from_file_location("migrate_storage", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_upload_render_and_download_through_the_bucket(client, user, video, transcriber, s3):  # noqa: F811
    headers, account = user
    up = upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                         headers=headers).json()["job_id"]
    assert worker.run_once(transcriber) == "SUCCEEDED"
    stored = keys(s3)
    assert f"uploads/{account['id']}/{up['upload_id']}.mp4" in stored                 # the upload went to the bucket
    clip = client.get(f"/v1/jobs/{job_id}", headers=headers).json()["clips"][0]
    assert clip["video_url"].startswith(s3) and "X-Amz-Signature" in clip["video_url"]   # presigned, not via the api
    r = httpx.get(clip["video_url"])
    assert r.status_code == 200 and len(r.content) > 10_000
    assert r.headers["content-type"] == "video/mp4"
    assert r.headers["content-disposition"].startswith("attachment; filename=") and ".mp4" in r.headers["content-disposition"]
    assert httpx.get(clip["thumb_url"]).headers["content-type"] == "image/jpeg"
    assert httpx.get(clip["video_url"].split("?")[0]).status_code == 403              # the bucket itself is private
    with new_session() as db:                                                         # retention: past its date
        db.get(Upload, up["upload_id"]).expires_at = utcnow() - timedelta(days=1)
        db.commit()
    assert worker.sweep_expired() >= 1                                                # deletes from the bucket
    assert f"uploads/{account['id']}/{up['upload_id']}.mp4" not in keys(s3)


def test_migration_copies_everything_once_and_reruns_are_no_ops(s3, tmp_path):  # noqa: F811
    m = load_script()
    root = tmp_path / "storage"
    for key, data in {"uploads/acct_1/upl_1.mp4": b"v" * 5000, "clips/job_1/0.mp4": b"c" * 3000,
                      "clips/job_1/0.jpg": b"j" * 200, "transcripts/upl_1.json": b"{}"}.items():
        (root / key).parent.mkdir(parents=True, exist_ok=True)
        (root / key).write_bytes(data)
    bucket, lines = storage.S3Storage(), []
    assert m.migrate(root, bucket, dry_run=True, out=lines.append)["copied"] == 4 and keys(s3) == []   # dry run: nothing
    assert m.migrate(root, bucket) == {"copied": 4, "skipped": 0, "failed": 0, "bytes": 8202}
    assert sorted(keys(s3)) == sorted(k for k, _ in m.local_files(root))               # same keys as on disk
    assert m.migrate(root, bucket) == {"copied": 0, "skipped": 4, "failed": 0, "bytes": 0}             # idempotent
    (root / "clips/job_2").mkdir(parents=True)
    (root / "clips/job_2/0.mp4").write_bytes(b"n" * 100)                                # written after the first run
    bucket.client.put_object(Bucket=BUCKET, Key="clips/job_1/0.mp4", Body=b"cut")       # an interrupted copy
    assert m.migrate(root, bucket) == {"copied": 2, "skipped": 3, "failed": 0, "bytes": 3100}
    assert bucket.size("clips/job_1/0.mp4") == 3000 and (root / "uploads/acct_1/upl_1.mp4").is_file()   # local kept


def test_migration_reports_failures_and_exits_1(s3, tmp_path, monkeypatch, capsys):  # noqa: F811
    m = load_script()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    root = get_settings().storage_dir
    (root / "a.mp4").write_bytes(b"x" * 10)
    monkeypatch.setattr(storage.S3Storage, "put", lambda self, key, src: (_ for _ in ()).throw(OSError("network down")))
    assert m.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL a.mp4" in out and "failed 1" in out and keys(s3) == []


def test_migration_needs_the_s3_settings(monkeypatch, capsys):
    m = load_script()
    for name in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    try:
        assert m.main([]) == 2 and "S3_BUCKET" in capsys.readouterr().err
    finally:
        get_settings.cache_clear()
