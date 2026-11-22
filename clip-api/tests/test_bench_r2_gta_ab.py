"""Credential-gated GTA R2 bench harness: no network when secrets are absent."""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bench_r2_gta_ab.py"


def load():
    spec = importlib.util.spec_from_file_location("bench_r2_gta_ab", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_check_reports_missing_credentials_without_network(monkeypatch, capsys):
    mod = load()
    for name in ("R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                 "S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert mod.main(["check"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["error"] == "missing_credentials"
    assert "R2_ENDPOINT_URL|S3_ENDPOINT_URL" in out["missing"]
    assert out["bucket"] == "clutchclips-benchmarks"
    assert out["key"] == "GTA_Benchmark_2Hours.mkv"


def test_render_workers_above_one_rejected(monkeypatch, capsys):
    mod = load()
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "y")
    # ab path validates render_workers before network.
    rc = mod.main(["ab", "--render-workers", "2", "--out", "/tmp/nope.mkv"])
    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "render_workers_must_be_1"
