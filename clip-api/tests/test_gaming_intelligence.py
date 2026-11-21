"""GI research hooks: disabled-by-default, cache, metrics, dataset sheet."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline.gaming_intelligence import (  # noqa: E402
    DEFAULT_FAMILY_WEIGHTS,
    GIConfig,
    apply_gi,
    cache_key_for,
    combine_score,
    env_enabled,
    maybe_rerank_moments,
)
from scripts.gaming_intelligence.bench import estimate_gpu_cost, write_cpu_bench_stub  # noqa: E402
from scripts.gaming_intelligence.dataset import (  # noqa: E402
    candidates_from_labels_v2,
    candidates_from_run,
    export_label_sheet,
    sheet_stats,
)


def _cands():
    return [
        {"start_sec": 10.0, "end_sec": 40.0, "score": 80.0, "rank": 1},
        {"start_sec": 100.0, "end_sec": 130.0, "score": 70.0, "rank": 2, "gi_audio_named": 1.0},
        {"start_sec": 200.0, "end_sec": 230.0, "score": 60.0, "rank": 3},
    ]


def test_default_family_weights_are_zero():
    assert DEFAULT_FAMILY_WEIGHTS
    assert all(v == 0.0 for v in DEFAULT_FAMILY_WEIGHTS.values())


def test_env_enabled_default_off(monkeypatch):
    monkeypatch.delenv("GI_ENABLED", raising=False)
    assert env_enabled() is False
    monkeypatch.setenv("GI_ENABLED", "1")
    assert env_enabled() is True


def test_disabled_is_identity():
    cands = _cands()
    result = apply_gi(cands, config=GIConfig(enabled=False))
    assert result.enabled is False
    assert result.features == []
    assert [c["start_sec"] for c in result.candidates] == [10.0, 100.0, 200.0]
    assert result.metrics["skipped"] is True


def test_enabled_zero_weights_preserves_order():
    cands = _cands()
    result = apply_gi(cands, config=GIConfig(enabled=True))
    assert result.enabled is True
    assert result.metrics["order_changed"] is False
    assert [c["start_sec"] for c in result.candidates] == [10.0, 100.0, 200.0]
    assert len(result.features) == 3
    assert all(f.gi_score == f.baseline_score for f in result.features)


def test_enabled_with_weight_can_rerank():
    cands = _cands()
    cfg = GIConfig(enabled=True, family_weights={**DEFAULT_FAMILY_WEIGHTS, "audio_named": 50.0})
    result = apply_gi(cands, config=cfg)
    assert result.metrics["order_changed"] is True
    # candidate with gi_audio_named=1.0 should rise: 70+50=120 > 80
    assert result.candidates[0]["start_sec"] == 100.0
    assert result.candidates[0]["gi_rank"] == 1


def test_cache_roundtrip(tmp_path):
    cands = _cands()
    cfg = GIConfig(enabled=True, cache_dir=tmp_path)
    a = apply_gi(cands, config=cfg)
    assert a.metrics["cache_hit"] is False
    b = apply_gi(cands, config=cfg)
    assert b.metrics["cache_hit"] is True
    assert a.cache_key == b.cache_key == cache_key_for(cands)
    assert (tmp_path / f"{a.cache_key}.json").is_file()


def test_combine_score_zero_weight_equals_baseline():
    assert combine_score(42.0, {"audio_named": 1.0}, DEFAULT_FAMILY_WEIGHTS) == 42.0


def test_maybe_rerank_moments_off_returns_same_list():
    moments = [{"start": 1, "end": 2, "score": 1}]
    assert maybe_rerank_moments(moments, enabled=False) is moments


def test_dataset_from_run_leaves_human_blank(tmp_path):
    run = {
        "system": "clutchclips",
        "clips": [
            {"start_sec": 5.0, "end_sec": 35.0, "rank": 1, "score": 88},
            {"start_sec": 90.0, "end_sec": 120.0, "rank": 2, "score": 70},
        ],
    }
    rows = candidates_from_run(run, vod="gta-demo", game="gta-online")
    assert len(rows) == 2
    assert rows[0]["clutch_score"] == "88"
    assert rows[0]["hook"] == ""
    assert rows[0]["publish"] == ""
    out = export_label_sheet(rows, tmp_path / "sheet.csv")
    stats = sheet_stats(rows)
    assert stats["rows"] == 2
    assert stats["unrated"] == 2
    assert stats["treats_clutch_score_as_gt"] is False
    assert out.is_file()


def test_labels_v2_export_does_not_copy_rating_as_gt():
    path = ROOT / "eval" / "labels-v2.csv"
    if not path.is_file():
        pytest.skip("labels-v2.csv missing")
    rows = candidates_from_labels_v2(path)
    assert len(rows) == 30
    assert all(r["hook"] == "" for r in rows)
    assert sheet_stats(rows)["unrated"] == 30


def test_estimate_gpu_clearly_marked():
    est = estimate_gpu_cost(sku="l4", billed_minutes_per_source_hour=15.0)
    assert est["kind"] == "estimate"
    assert est["clutchclips_gpu_throughput"] == "not_measured"
    assert est["estimated_compute_usd"] == pytest.approx(0.1725)


def test_cpu_bench_writes_measured_report(tmp_path):
    report = write_cpu_bench_stub(_cands(), tmp_path / "bench.json", repeats=5)
    assert report["kind"] == "measured_cpu_gi_hook_overhead"
    assert report["gpu"] == "not_run"
    assert report["disabled"]["n"] == 5
    data = json.loads((tmp_path / "bench.json").read_text())
    assert data["candidates"] == 3
