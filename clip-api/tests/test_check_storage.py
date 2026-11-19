"""scripts/check_storage.py against a local HTTP S3 (moto's ThreadedMotoServer)."""
import importlib.util
from pathlib import Path

import boto3
import pytest
from moto.server import ThreadedMotoServer

from app import config, storage

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_storage.py"
BUCKET = "clips-test"


def load_script():
    spec = importlib.util.spec_from_file_location("check_storage", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def s3(monkeypatch):
    server = ThreadedMotoServer(port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    url = f"http://{host}:{port}"
    c = boto3.client("s3", endpoint_url=url, region_name="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    c.create_bucket(Bucket=BUCKET)
    for o in c.list_objects_v2(Bucket=BUCKET).get("Contents", []):   # moto keeps state for the whole process
        c.delete_object(Bucket=BUCKET, Key=o["Key"])
    for name, value in dict(STORAGE_BACKEND="s3", S3_ENDPOINT_URL=url, S3_BUCKET=BUCKET, S3_ACCESS_KEY_ID="k",
                            S3_SECRET_ACCESS_KEY="s", S3_REGION="us-east-1").items():
        monkeypatch.setenv(name, value)
    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()
    yield url
    server.stop()
    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()


def keys(url: str) -> list[str]:
    c = boto3.client("s3", endpoint_url=url, region_name="us-east-1", aws_access_key_id="k", aws_secret_access_key="s")
    return [o["Key"] for o in c.list_objects_v2(Bucket=BUCKET).get("Contents", [])]


def test_local_backend_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()
    try:
        assert load_script().main() == 2
    finally:
        config.get_settings.cache_clear()
        storage.get_storage.cache_clear()
    assert "only checks S3" in capsys.readouterr().out


def test_all_steps_ok_and_object_removed(s3, capsys):
    assert load_script().main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["ok put", "ok get", "ok signed-url", "ok cors", "ok private", "ok delete", "ok delete-prefix"]
    assert keys(s3) == []


def test_missing_cors_rules_fail_the_check(s3, capsys, monkeypatch):
    mod = load_script()
    real_get = mod.httpx.get

    def no_cors(url, **kw):                     # a bucket without CORS rules sends no Access-Control headers
        r = real_get(url, **kw)
        r.headers.pop("access-control-allow-origin", None)
        return r
    monkeypatch.setattr(mod.httpx, "get", no_cors)
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "FAIL cors: the bucket does not let http://localhost:3000 read files" in out and "ok delete-prefix" in out
    assert keys(s3) == []


def test_failed_step_exits_1_and_still_deletes(s3, capsys, monkeypatch):
    def boom(self, key, dest):
        raise RuntimeError("download broke")
    monkeypatch.setattr(storage.S3Storage, "fetch", boom)
    assert load_script().main() == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["ok put", "FAIL get: download broke", "ok delete", "ok delete-prefix"]
    assert keys(s3) == []


def test_signed_url_failure_exits_1_and_still_deletes(s3, capsys, monkeypatch):
    monkeypatch.setattr(storage.S3Storage, "url", lambda self, key, *a, **k: f"{s3}/{BUCKET}/missing-{key}")
    assert load_script().main() == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[:2] == ["ok put", "ok get"]
    assert lines[2].startswith("FAIL signed-url: signed URL returned HTTP 404")
    assert lines[3:] == ["ok delete", "ok delete-prefix"]
    assert keys(s3) == []


def test_put_failure_exits_1_and_skips_get(s3, capsys, monkeypatch):
    def boom(self, key, src):
        raise RuntimeError("upload broke")
    monkeypatch.setattr(storage.S3Storage, "put", boom)
    assert load_script().main() == 1
    assert capsys.readouterr().out.splitlines() == ["FAIL put: upload broke", "ok delete",
                                                    "FAIL delete-prefix: upload broke"]
