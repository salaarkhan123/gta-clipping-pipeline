"""Phase 1 gaming research harness: baseline freeze, metrics, inventory (no fabricated ratings)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gaming_phase1.baseline import candidate_fingerprint, load_pin, select_b0
from scripts.gaming_phase1.inventory import inventory_eval_set
from scripts.gaming_phase1.metrics import boundary_errors, event_confusion, ndcg_at_k, precision_recall_f1
from scripts.gaming_phase1.signals import measure_signals

PIN = ROOT.parent / "docs/gaming-intelligence-research/phase1/baseline-pin.json"
MANIFEST = ROOT.parent / "docs/gaming-intelligence-research/phase1/fixtures/synthetic-source-manifest.json"
DENYLIST = ROOT.parent / "docs/gaming-intelligence-research/phase1/fixtures/denylist-eval-ids.json"


def test_baseline_pin_matches_runtime_weights():
    from app.pipeline import WEIGHTS
    from app.pipeline.layouts import HUD_REGIONS

    pin = load_pin(PIN)
    pin.assert_matches_runtime(WEIGHTS, HUD_REGIONS)
    assert pin.selector_merge_sha.startswith("8e0d9bad")
    assert all(w in pin.experimental_weights_remain_zero for w in ("hud_killfeed", "hud_banner"))


def test_b0_selection_is_deterministic(video, tmp_path):
    a = select_b0(video, max_clips=3, clip_length=10)
    b = select_b0(video, max_clips=3, clip_length=10)
    assert a["fingerprint"] == b["fingerprint"]
    assert a["paid_model_calls"] == 0
    assert a["arm"] == "B0"
    assert len(a["clips"]) >= 1
    # loud burst at 20-24s should influence selection on this fixture
    starts = [c["start_sec"] for c in a["clips"]]
    assert any(15 <= s <= 25 for s in starts) or any(c["end_sec"] >= 20 for c in a["clips"])
    out = tmp_path / "b0.json"
    out.write_text(json.dumps(a))
    loaded = json.loads(out.read_text())
    assert candidate_fingerprint(loaded["clips"]) == a["fingerprint"]


def test_signal_inventory_reports_active_and_zero_weights(video):
    report = measure_signals(video, start=0.0, length=20.0, chat_region="none")
    assert report.series_lengths["audio_rms"] > 0
    assert "audio_flux" in report.series_lengths
    assert "audio_bursts" in report.series_lengths
    assert report.active_weights["audio"] == 0.7
    assert "scene" in report.zero_weight_skipped
    assert report.wall_sec["audio_timeline"] >= 0


def test_metrics_helpers_on_synthetic_labels():
    assert precision_recall_f1(2, 1, 1)["f1"] == pytest.approx(2 / 3)
    conf = event_confusion(
        [(10, "gunshot"), (50, "gunshot")],
        [(10, {"gunshot"}), (11, {"laughter"})],
        positive_class="gunshot",
    )
    assert conf["tp"] == 1 and conf["fp"] == 1 and conf["fn"] == 0
    assert ndcg_at_k([3, 1, 0], [3, 1, 0], k=3) == pytest.approx(1.0)
    assert ndcg_at_k([3, 0, 1], [3, 1], k=3) < 1.0
    bounds = boundary_errors([(0.0, 10.0)], [(0.0, 10.0)])
    assert bounds["matched"] == 1
    assert bounds["median_iou"] == pytest.approx(1.0)


def test_eval_inventory_does_not_invent_ratings():
    inv = inventory_eval_set()
    assert inv.labels_v2_rated == 0
    assert inv.labels_v2_rows == 30
    assert inv.wayin_labelled == 15
    assert inv.hud_regions_populated == 0
    assert "gta-online-1" in inv.labels_v2_vods
    assert any("zero human ratings" in g for g in inv.gaps)


def test_phase1_fixtures_exist_and_exclude_eval_ids():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["version"] == 1
    assert any(s["excluded_from_training"] for s in manifest["sources"])
    deny = json.loads(DENYLIST.read_text())
    assert "gta-rp-1" in deny["evaluation_only_vod_ids"]
    assert "gta-online-1" in deny["evaluation_only_vod_ids"]
