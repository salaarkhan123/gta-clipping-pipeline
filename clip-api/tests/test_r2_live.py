"""Opt-in: every storage call the app makes, the migration and scripts/check_storage.py against a real R2 bucket.

Runs only when R2_ENDPOINT_URL, R2_BUCKET, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are set (the owner runs it;
DEPLOY.md, "Moving files to Cloudflare R2"). R2_TEST_ORIGIN (default https://clutchclips.io) is the site origin the
bucket's CORS rules must allow. Everything is written under r2-live-test/<id>/ and deleted at the end. Cost: about
1,050 Class A operations (under half a cent) and 40 MiB stored for a minute.

    R2_ENDPOINT_URL=https://<account id>.r2.cloudflarestorage.com R2_BUCKET=... R2_ACCESS_KEY_ID=... \\
      R2_SECRET_ACCESS_KEY=... pytest -q tests/test_r2_live.py
"""
import os
import uuid

import httpx
import pytest

from app import config, storage
from tests.r2_contract import MiB, R2Rules, exercise
from tests.test_check_storage import load_script as load_check
from tests.test_spaces_storage import load_script as load_migrate

NAMES = ("R2_ENDPOINT_URL", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
pytestmark = pytest.mark.skipif(not all(os.environ.get(n) for n in NAMES),
                                reason="set R2_ENDPOINT_URL, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY")
ORIGIN = os.environ.get("R2_TEST_ORIGIN", "https://clutchclips.io")


@pytest.fixture
def bucket(monkeypatch):
    env = dict(STORAGE_BACKEND="s3", S3_REGION="auto", PUBLIC_WEB_URL=ORIGIN,
               **{n.replace("R2_", "S3_"): os.environ[n] for n in NAMES})
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()
    store = storage.get_storage()
    prefix = f"r2-live-test/{uuid.uuid4().hex}/"
    yield store, prefix, R2Rules(store.client)
    store.delete_prefix(prefix)
    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()


def test_every_storage_call_on_r2(bucket):
    store, prefix, rules = bucket
    seen = exercise(store, prefix)
    assert seen["url_problems"] == [] and seen["left"] == [] and seen["deleted"] == 1002
    assert rules.violations == []


def test_the_site_may_read_signed_links(bucket, tmp_path):
    store, prefix, _ = bucket
    src = tmp_path / "c.captions.json"
    src.write_bytes(b'{"words": []}')
    store.put(prefix + "c.captions.json", src)
    r = httpx.get(store.url(prefix + "c.captions.json"), headers={"Origin": ORIGIN}, timeout=60)
    assert r.status_code == 200 and r.headers.get("access-control-allow-origin") in (ORIGIN, "*"), \
        "paste the CORS rules from DEPLOY.md into the bucket's settings"
    other = httpx.get(store.url(prefix + "c.captions.json"), headers={"Origin": "https://evil.example"}, timeout=60)
    assert other.headers.get("access-control-allow-origin") is None


def test_direct_upload_on_r2(client, user, video, bucket):
    """The browser's path: signed part PUTs from the site's origin, a wrong-sized part refused, then complete."""
    store, prefix, rules = bucket
    headers, account = user
    up = client.post("/v1/uploads/multipart", json={"filename": "live.mp4", "size_bytes": video.stat().st_size},
                     headers=headers).json()
    token = {"upload_token": up["upload_token"]}
    (part,) = client.post("/v1/uploads/multipart/parts", json=token, headers=headers).json()["parts"]
    data = video.read_bytes()
    pre = httpx.options(part["url"], headers={"Origin": ORIGIN, "Access-Control-Request-Method": "PUT"}, timeout=60)
    assert pre.headers.get("access-control-allow-origin") in (ORIGIN, "*"), "the CORS rules need PUT (DEPLOY.md)"
    assert httpx.put(part["url"], content=data + b"x", timeout=120).status_code == 403      # size is signed
    assert httpx.put(part["url"], content=data, headers={"Origin": ORIGIN}, timeout=120).status_code == 200
    r = client.post("/v1/uploads/multipart/complete", json=token, headers=headers)
    assert r.status_code in (200, 201), r.text
    store.delete_prefix(f"uploads/{account['id']}/")
    assert rules.violations == []


def test_migration_and_check_script_on_r2(bucket, tmp_path, capsys):
    store, prefix, rules = bucket
    root = tmp_path / "storage"
    (root / prefix / "uploads").mkdir(parents=True)
    (root / prefix / "uploads/u.mp4").write_bytes(os.urandom(9 * MiB))     # multipart
    (root / prefix / "t.json").write_bytes(b"{}")
    m = load_migrate()
    assert m.migrate(root, store) == {"copied": 2, "skipped": 0, "failed": 0, "bytes": 9 * MiB + 2}
    assert m.migrate(root, store)["skipped"] == 2
    assert load_check().main() == 0, capsys.readouterr().out
    assert rules.violations == []
