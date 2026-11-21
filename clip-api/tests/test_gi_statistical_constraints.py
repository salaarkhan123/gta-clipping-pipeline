"""Statistical constraints harness: agreement, source bootstrap, datasets, gates."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gaming_intelligence.compare import evaluate_arms  # noqa: E402
from scripts.gaming_intelligence.dataset import (  # noqa: E402
    REQUIRED_FOR_RATED,
    is_rated,
    load_label_sheet,
    sheet_stats,
)
from scripts.gaming_intelligence.datasets_ab import (  # noqa: E402
    assign_held_out_by_recording,
    census_dataset_a,
    census_dataset_b,
    init_dataset_a_template,
    init_dataset_b_template,
    validate_split_isolation,
)
from scripts.gaming_intelligence.stats import (  # noqa: E402
    agreement_report,
    decision_gates,
    pair_dual_rater_sheets,
    paired_bootstrap_ci,
    quadratic_weighted_kappa,
    significance_allowed,
)


def _v2_row(i: int, *, vod: str = "v1", genuine: str = "yes", ent: int = 4) -> dict[str, str]:
    return {
        "id": f"{vod}-{i}",
        "vod": vod,
        "game": "gta",
        "start": f"0:0{i}:00",
        "end": f"0:0{i}:30",
        "source": "test",
        "clutch_rank": str(i + 1),
        "clutch_score": str(90 - i),
        "quality_1_5": str(ent),
        "entertainment_1_5": str(ent),
        "gameplay_significance_1_5": "3",
        "opening_hook_1_5": "3",
        "context_1_5": "3",
        "editing_suitability_1_5": "3",
        "suitable_tiktok": "maybe",
        "suitable_shorts": "maybe",
        "suitable_reels": "maybe",
        "genuine_highlight": genuine,
        "clutch_correct": "yes",
        "event_tags": "",
        "notes": "",
        "rater": "r1",
        "rated_at": "2026-11-21T00:00:00Z",
        "adjudicated": "",
        "gi_score": str(50 + i),
    }


def test_quadratic_weighted_kappa_perfect():
    xs = [1, 2, 3, 4, 5, 3, 2]
    assert quadratic_weighted_kappa(xs, xs) == pytest.approx(1.0)


def test_bootstrap_descriptive_when_few_sources():
    out = paired_bootstrap_ci({"a": 0.4, "b": 0.6}, n_boot=100, seed=1)
    assert out["n_sources"] == 2
    assert out["reliable"] is False
    assert out["ci_low"] is None
    assert out["mean"] == pytest.approx(0.5)


def test_bootstrap_ci_with_enough_sources():
    src = {f"s{i}": 0.5 + (i % 3) * 0.1 for i in range(8)}
    out = paired_bootstrap_ci(src, n_boot=500, seed=7)
    assert out["reliable"] is True
    assert out["ci_low"] is not None
    assert out["ci_high"] is not None
    assert out["ci_low"] <= out["mean"] <= out["ci_high"]


def test_significance_blocked_on_small_n():
    assert significance_allowed(1)["allowed"] is False
    assert significance_allowed(20)["allowed"] is True


def test_agreement_flags_disagreements():
    # Spread ratings so kappa is defined; one large entertainment disagreement.
    ents = [1, 2, 3, 4, 5, 2, 3, 4, 5, 1, 3, 4]
    a = [_v2_row(i, ent=ents[i]) for i in range(12)]
    b = [_v2_row(i, ent=ents[i]) for i in range(12)]
    for r in b:
        r["rater"] = "r2"
    b[0]["entertainment_1_5"] = "5"  # abs diff vs a[0]=1 is 4
    pairs = pair_dual_rater_sheets(a, b)
    report = agreement_report(pairs)
    assert report["n_pairs"] == 12
    assert report["ordinal"]["entertainment_1_5"]["n"] == 12
    assert report["ordinal"]["entertainment_1_5"]["kappa_qw"] is not None
    assert any(d["field"] == "entertainment_1_5" for d in report["disagreements_for_adjudication"])
    assert report["labels_sufficiently_reliable"] is True


def test_same_rater_not_paired():
    a = [_v2_row(0)]
    b = [_v2_row(0)]
    assert pair_dual_rater_sheets(a, b) == []


def test_dataset_templates(tmp_path):
    a = init_dataset_a_template(tmp_path / "a.csv")
    b = init_dataset_b_template(tmp_path / "b.csv")
    ca = census_dataset_a(list(__import__("csv").DictReader(a.open())))
    cb = census_dataset_b(list(__import__("csv").DictReader(b.open())))
    assert ca["rows"] == 150
    assert ca["ingested_with_permission"] == 0
    assert ca["not_ground_truth_highlight_quality"] is True
    assert cb["rows"] == 150
    assert cb["human_rated_complete"] == 0
    assert cb["held_out_must_not_train"] is True


def test_split_isolation_detects_leakage():
    rows = [
        {"source_recording_id": "r1", "streamer_id": "s1", "split": "development"},
        {"source_recording_id": "r1", "streamer_id": "s1", "split": "held_out_eval"},
    ]
    v = validate_split_isolation(rows)
    assert v["ok"] is False
    assert "r1" in v["recording_leakage"]


def test_assign_held_out():
    rows = [
        {"source_recording_id": "r1", "split": ""},
        {"source_recording_id": "r2", "split": ""},
    ]
    out = assign_held_out_by_recording(rows, held_out_recording_ids={"r2"})
    assert out[0]["split"] == "development"
    assert out[1]["split"] == "held_out_eval"


def test_compare_blocked_on_real_sheet():
    path = ROOT / "eval" / "gi-gta-label-sheet.csv"
    report = evaluate_arms(load_label_sheet(path), min_rated=20)
    assert report["status"] == "blocked_no_human_labels"
    assert report["decision_gates"]["proceed_to_complex_models"] is False
    assert report["clips_treated_as_independent_for_ci"] is False


def test_compare_with_v2_labels_still_exploratory_single_vod():
    rows = [_v2_row(i, genuine="yes" if i < 3 else "no", ent=5 - (i % 5)) for i in range(5)]
    for r in rows:
        assert is_rated(r)
    report = evaluate_arms(rows, min_rated=20, seed=3)
    assert report["status"] == "insufficient_sample"
    assert report["exploratory"] is True
    assert report["significance_testing"]["allowed"] is False
    assert "A" in report["arms"]
    assert report["arms"]["A"]["precision@5"] is not None


def test_decision_gates_fail_closed():
    g = decision_gates(
        agreement=None,
        baseline_measured=False,
        improvement=None,
        cost=None,
        generalization=None,
    )
    assert g["all_gates_passed"] is False
    assert g["proceed_to_complex_models"] is False
    assert len(g["gates"]) == 6


def test_sheet_stats_v2_fields():
    path = ROOT / "eval" / "gi-gta-label-sheet.csv"
    stats = sheet_stats(load_label_sheet(path))
    assert stats["human_rated_complete_v2"] == 0
    assert set(REQUIRED_FOR_RATED) <= set(stats["required_for_rated"])
    assert stats["combines_dimensions_into_weighted_score"] is False


def test_audit_cli_json():
    from scripts.gaming_intelligence_cli import _audit_snapshot
    snap = _audit_snapshot()
    assert snap["invented_results"] is False
    assert snap["human_labels_sufficient"] is False
    assert snap["measured"]["compare_status"] == "blocked_no_human_labels"
    # Round-trip JSON serializable
    json.dumps(snap)
