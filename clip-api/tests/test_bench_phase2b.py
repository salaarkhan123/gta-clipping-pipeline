"""Unit tests for Phase 2B bench helpers (no full pipeline run)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bench_phase2b as bench  # noqa: E402


def test_dry_run_labels_claims():
    report = bench.dry_run_recipe()
    assert report["harness"] == "bench_phase2b"
    assert report["claims"]["2h_gaming_vod"] == "not measured"
    assert report["labels"]["synthetic"] == "synthetic"
    assert report["labels"]["content"] == "not gaming"
    assert report["labels"]["2h_extrapolation"] == "inferred"


def test_infer_2h_is_linear_and_labeled():
    out = bench.infer_2h(wall_seconds=100.0, source_minutes=10.0)
    assert out["label"] == "inferred"
    assert out["wall_seconds_2h"] == 1200.0
    assert "Not a measured 2h" in out["note"]


def test_cli_dry_run(capsys):
    assert bench.main(["--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert "preview-serial" in payload["configs"]


def test_unknown_config_exits_2(capsys):
    assert bench.main(["--video", "/no/such.mp4", "--configs", "nope"]) == 2
    assert "unknown configs" in capsys.readouterr().err


def test_build_options_serial_without_workers_field(monkeypatch):
    """On RC, missing render_workers must not break serial configs."""
    names = bench.option_field_names()
    opts, note = bench.build_options(
        render="preview", max_clips=5, clip_length=30, chat_region="none",
        render_workers=1, chat_motion_sample=None,
    )
    assert opts.render == "preview"
    if "render_workers" not in names:
        assert "render_workers" in note["skipped"] or note["applied"].get("render_workers") in (None, 1)
