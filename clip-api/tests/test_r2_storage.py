"""The S3 backend with R2's settings (region "auto"), against moto's HTTP S3, with every request checked against
R2's documented rules (tests/r2_contract.py). The same pass runs against a real R2 bucket in test_r2_live.py."""
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import boto3
import pytest
import yaml
from moto.server import ThreadedMotoServer

from app import config, storage, worker
from app.db import new_session
from app.models import Upload, utcnow
from tests.r2_contract import MiB, R2Rules, exercise
from tests.test_api import upload
from tests.test_spaces_storage import load_script

BUCKET = "clips-r2"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def r2(monkeypatch):
    server = ThreadedMotoServer(port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    url = f"http://{host}:{port}"
    admin = boto3.client("s3", endpoint_url=url, region_name="us-east-1", aws_access_key_id="k",
                         aws_secret_access_key="s")
    admin.create_bucket(Bucket=BUCKET)
    for page in admin.get_paginator("list_objects_v2").paginate(Bucket=BUCKET):   # moto keeps state per process
        for o in page.get("Contents", []):
            admin.delete_object(Bucket=BUCKET, Key=o["Key"])
    for name, value in dict(STORAGE_BACKEND="s3", S3_ENDPOINT_URL=url, S3_BUCKET=BUCKET, S3_ACCESS_KEY_ID="k",
                            S3_SECRET_ACCESS_KEY="s", S3_REGION="auto").items():
        monkeypatch.setenv(name, value)
    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()
    rules = R2Rules(storage.get_storage().client)
    yield rules
    server.stop()
    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()


def test_every_storage_call_follows_r2_rules(r2):
    seen = exercise(storage.get_storage(), "t/")
    # moto serves multipart objects without checking the signature; R2 and Garage refuse (test_r2_live.py)
    assert seen["url_problems"] == ["u1.mp4 is readable without a signature"]
    assert seen["left"] == [] and seen["deleted"] == 1002
    assert r2.violations == []
    assert r2.calls.count("DeleteObjects") == 2                             # 1002 keys: 1000 + 2
    assert {"CreateMultipartUpload", "UploadPart", "CompleteMultipartUpload", "ListObjectsV2"} <= set(r2.calls)


def test_signed_links_never_outlive_seven_days(r2, monkeypatch):
    monkeypatch.setenv("SIGNED_URL_TTL_SEC", str(30 * 24 * 3600))
    config.get_settings.cache_clear()
    assert "X-Amz-Expires=604800" in storage.get_storage().url("clips/j/c.mp4")


def test_delete_prefix_raises_when_the_bucket_refuses_a_key(r2, monkeypatch):
    store = storage.get_storage()
    store.client.put_object(Bucket=BUCKET, Key="clips/job_1/a.mp4", Body=b"x")
    monkeypatch.setattr(store.client, "delete_objects", lambda **kw: {
        "Errors": [{"Key": "clips/job_1/a.mp4", "Code": "AccessDenied", "Message": "no"}]})
    with pytest.raises(RuntimeError, match="1 objects under clips/job_1/ not deleted.*AccessDenied"):
        store.delete_prefix("clips/job_1/")


@pytest.mark.parametrize("backend", ["s3", "local"])
def test_delete_prefix_only_takes_a_whole_folder(r2, backend, tmp_path):
    store = storage.get_storage() if backend == "s3" else storage.LocalStorage(tmp_path)
    src = tmp_path / "x.bin"
    src.write_bytes(b"x")
    for key in ("uploads/acct_1/u.mp4", "uploads/acct_10/u.mp4"):
        store.put(key, src)
    for bad in ("", "/", "uploads/acct_1"):                    # no slash: would also take acct_10
        with pytest.raises(ValueError):
            store.delete_prefix(bad)
    assert store.delete_prefix("uploads/acct_1/") == 1
    assert store.keys("uploads/") == ["uploads/acct_10/u.mp4"]
    assert store.delete_prefix("uploads/nobody/") == 0


def test_a_job_and_retention_through_r2(client, user, video, transcriber, r2):
    headers, account = user
    up = upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                         headers=headers).json()["job_id"]
    assert worker.run_once(transcriber) == "SUCCEEDED"
    clip = client.get(f"/v1/jobs/{job_id}", headers=headers).json()["clips"][0]
    assert "X-Amz-Signature" in clip["video_url"] and "X-Amz-Signature" in clip["captions_url"]
    with new_session() as db:
        db.get(Upload, up["upload_id"]).expires_at = utcnow() - timedelta(days=1)
        db.commit()
    assert worker.sweep_expired() >= 1
    assert storage.get_storage().keys(f"uploads/{account['id']}/") == []
    assert r2.violations == [] and "PutObject" in r2.calls and "DeleteObject" in r2.calls


def test_migration_to_r2_follows_r2_rules(r2, tmp_path):
    m = load_script()
    root = tmp_path / "storage"
    (root / "uploads/acct_1").mkdir(parents=True)
    (root / "uploads/acct_1/upl_1.mp4").write_bytes(b"v" * (9 * MiB))          # multipart
    (root / "transcripts").mkdir()
    (root / "transcripts/upl_1.json").write_bytes(b"{}")
    bucket = storage.S3Storage()                                  # the script builds its own client
    rules = R2Rules(bucket.client)
    assert m.migrate(root, bucket) == {"copied": 2, "skipped": 0, "failed": 0, "bytes": 9 * MiB + 2}
    assert m.migrate(root, bucket)["skipped"] == 2
    assert rules.violations == [] and "UploadPart" in rules.calls


def csp_sources(directive: str, env: dict) -> list[str]:
    """The site's CSP sources for one directive, with Caddy's {$VAR} placeholders filled from env."""
    caddy = (ROOT / "Caddyfile").read_text()
    site = caddy[caddy.index("{$WEB_DOMAIN} {"):]
    policy = re.search(r'header Content-Security-Policy "([^"]+)"', site).group(1)
    policy = re.sub(r"\{\$(\w+)\}", lambda m: env.get(m.group(1), ""), policy)
    rule = next(r.strip() for r in policy.split(";") if r.strip().startswith(directive + " "))
    return rule.split()[1:]


def allowed(url: str, sources: list[str]) -> bool:
    u = urlsplit(url)
    origin = f"{u.scheme}://{u.netloc}"
    return any(s.rstrip("/") == origin for s in sources)


@pytest.mark.parametrize("endpoint", ["https://0123abcd.r2.cloudflarestorage.com", "https://nyc3.digitaloceanspaces.com"])
def test_the_site_csp_allows_signed_bucket_links(endpoint, monkeypatch):
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert compose["services"]["caddy"]["environment"]["MEDIA_ORIGIN"] == "${S3_ENDPOINT_URL:-}"
    for name, value in dict(STORAGE_BACKEND="s3", S3_ENDPOINT_URL=endpoint, S3_BUCKET="clutchclips-media",
                            S3_ACCESS_KEY_ID="k", S3_SECRET_ACCESS_KEY="s", S3_REGION="auto").items():
        monkeypatch.setenv(name, value)
    config.get_settings.cache_clear()
    try:
        link = storage.S3Storage().url("clips/job_1/clip_1.mp4")      # signing is local: no request is sent
    finally:
        config.get_settings.cache_clear()
    env = {"API_DOMAIN": "api.clutchclips.io", "MEDIA_ORIGIN": endpoint}   # what docker-compose passes to Caddy
    for directive in ("img-src", "media-src", "connect-src"):            # thumbnails, video, captions fetch
        assert allowed(link, csp_sources(directive, env)), directive
    assert not allowed("https://evil.example/x.mp4", csp_sources("media-src", env))
    local = {"API_DOMAIN": "api.clutchclips.io"}                          # local storage: links on the API domain
    assert allowed("https://api.clutchclips.io/v1/files/t", csp_sources("media-src", local))
