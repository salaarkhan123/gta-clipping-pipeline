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
    boto3.client("s3", endpoint_url=url, region_name="us-east-1",
                 aws_access_key_id="k", aws_secret_access_key="s").create_bucket(Bucket=BUCKET)
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
    assert lines == ["ok put", "ok get", "ok signed-url", "ok delete"]
    assert keys(s3) == []


def test_failed_step_exits_1_and_still_deletes(s3, capsys, monkeypatch):
    def boom(self, key, dest):
        raise RuntimeError("download broke")
    monkeypatch.setattr(storage.S3Storage, "fetch", boom)
    assert load_script().main() == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["ok put", "FAIL get: download broke", "ok delete"]
    assert keys(s3) == []
