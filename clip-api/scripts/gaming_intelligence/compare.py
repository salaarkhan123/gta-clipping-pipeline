"""A/B/C comparison framework for ClutchClips vs Gaming Intelligence.

Arms
  A — existing production detector ranking (clutch_rank / clutch_score)
  B — GI prototype ranking (gi_score / gi_rank) when features present
  C — combined: baseline + weighted GI family features (experimental; weights default 0)

Metrics are computed **only** when human ground-truth labels exist.
This module never invents ratings and never treats clutch_score as GT.

Statistical rules (constraints research):
- Prefer identical candidate pools for ranking comparisons.
- Confidence intervals resample at the source-video level, not clip level.
- Do not run significance tests when independent source count is too small.
- Keep rating dimensions separate; NDCG may use one declared gain mapping.
"""
from __future__ import annotations

import math
from typing import Any

from .dataset import REQUIRED_FOR_RATED, REQUIRED_FOR_RATED_LEGACY, is_rated, is_rated_legacy
from .stats import (
    decision_gates,
    group_by_source,
    independent_source_count,
    paired_bootstrap_ci,
    paired_delta_by_source,
    significance_allowed,
)

POSITIVE_GENUINE = {"yes"}
NEGATIVE_GENUINE = {"no"}


def _f(x: str | float | int | None) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _gain_from_quality(q: float | None) -> float:
    """Map quality/entertainment 1–5 → ranking gain. Unrated → 0."""
    if q is None:
        return 0.0
    if q >= 5:
        return 3.0
    if q >= 4:
        return 2.0
    if q >= 3:
        return 1.0
    return 0.0


def _primary_ordinal(row: dict[str, str]) -> float | None:
    """Prefer entertainment (v2 primary); fall back to quality for legacy sheets."""
    for key in ("entertainment_1_5", "quality_1_5"):
        v = _f(row.get(key))
        if v is not None:
            return v
    return None


def _dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked_gains: list[float], ideal_gains: list[float], k: int) -> float | None:
    if k <= 0:
        return None
    ideal = sorted((g for g in ideal_gains if g > 0), reverse=True)[:k]
    if not ideal:
        return None
    actual = (list(ranked_gains[:k]) + [0.0] * k)[:k]
    return _dcg(actual) / _dcg(ideal)


def precision_at_k(labels_positive: list[bool], k: int) -> float | None:
    if k <= 0 or not labels_positive:
        return None
    top = labels_positive[:k]
    if not top:
        return None
    return sum(1 for x in top if x) / len(top)


def binary_prf(y_true: list[bool], y_pred: list[bool]) -> dict[str, float | None]:
    if len(y_true) != len(y_pred) or not y_true:
        return {"precision": None, "recall": None, "f1": None, "fp_rate": None, "n": 0}
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if (not t) and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and (not p))
    tn = sum(1 for t, p in zip(y_true, y_pred) if (not t) and (not p))
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * prec * rec / (prec + rec)) if prec is not None and rec is not None and (prec + rec) else None
    fp_rate = fp / (fp + tn) if (fp + tn) else None
    return {
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "fp_rate": fp_rate,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "n": len(y_true),
    }


def spearman_rank(xs: list[float], ys: list[float]) -> float | None:
    """Spearman ρ without scipy. Returns None if <3 pairs or zero variance."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    deny = math.sqrt(sum((b - my) ** 2 for b in ry))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def arm_ranking(rows: list[dict[str, str]], arm: str) -> list[dict[str, Any]]:
    """Sort copies of rated+unrated rows by the arm's score (desc). Unscored → end."""

    def key(r: dict[str, str]) -> tuple[float, float]:
        if arm == "A":
            score = _f(r.get("clutch_score"))
            rank = _f(r.get("clutch_rank"))
            primary = score if score is not None else (1000.0 - (rank or 1000.0))
            return (-primary, float(rank or 0))
        if arm == "B":
            score = _f(r.get("gi_score"))
            return (-(score if score is not None else -1e9), 0.0)
        if arm == "C":
            gi = _f(r.get("gi_score"))
            base = _f(r.get("clutch_score")) or 0.0
            return (-(gi if gi is not None else base), 0.0)
        raise ValueError(f"unknown arm {arm}")

    return sorted((dict(r) for r in rows), key=key)


def _usable_rated(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    v2 = [r for r in rows if is_rated(r)]
    if v2:
        return v2, "v2"
    legacy = [r for r in rows if is_rated_legacy(r)]
    return legacy, "legacy"


def _arm_metrics_for_rows(ranked_rated: list[dict[str, str]], arm: str, ks: tuple[int, ...]) -> dict[str, Any]:
    ordinals = [_primary_ordinal(r) or 0.0 for r in ranked_rated]
    gains = [_gain_from_quality(q) for q in ordinals]
    pos_flags = [(r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE for r in ranked_rated]
    metrics: dict[str, Any] = {
        "ndcg@5": ndcg_at_k(gains, gains, 5),
        "ndcg@10": ndcg_at_k(gains, gains, 10),
    }
    for k in ks:
        metrics[f"precision@{k}"] = precision_at_k(pos_flags, k)

    if arm == "A":
        system_s = [
            _f(r.get("clutch_score")) or (1000.0 - (_f(r.get("clutch_rank")) or 1000.0))
            for r in ranked_rated
        ]
    elif arm == "B":
        system_s = [_f(r.get("gi_score")) or 0.0 for r in ranked_rated]
    else:
        system_s = [_f(r.get("gi_score")) or (_f(r.get("clutch_score")) or 0.0) for r in ranked_rated]
    metrics["spearman_vs_entertainment_or_quality"] = spearman_rank(system_s, ordinals)

    top10_ids = {(r.get("id") or "") for r in ranked_rated[:10]}
    missed = [
        r.get("id")
        for r in ranked_rated
        if (_primary_ordinal(r) or 0) >= 4
        and (r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE
        and (r.get("id") or "") not in top10_ids
    ]
    metrics["missed_high_quality_outside_top10"] = missed
    metrics["n_ranked_rated"] = len(ranked_rated)

    binary_rows = [
        r
        for r in ranked_rated
        if (r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE | NEGATIVE_GENUINE
    ]
    if binary_rows:
        y_true = [(r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE for r in binary_rows]
        y_pred = [True] * len(binary_rows)
        metrics["selection_precision_among_labelled"] = binary_prf(y_true, y_pred)["precision"]
        metrics["n_binary_labelled"] = len(binary_rows)
        metrics["genuine_yes"] = sum(1 for t in y_true if t)
        metrics["genuine_no"] = sum(1 for t in y_true if not t)
        # False-positive analysis among labelled negatives that appear in top-5
        top5_ids = {(r.get("id") or "") for r in ranked_rated[:5]}
        fp_top5 = [
            r.get("id")
            for r in binary_rows
            if (r.get("id") or "") in top5_ids
            and (r.get("genuine_highlight") or "").lower() in NEGATIVE_GENUINE
        ]
        metrics["false_positives_in_top5"] = fp_top5
    return metrics


def evaluate_arms(
    rows: list[dict[str, str]],
    *,
    min_rated: int = 20,
    ks: tuple[int, ...] = (5, 10),
    agreement: dict[str, Any] | None = None,
    cost: dict[str, Any] | None = None,
    generalization: dict[str, Any] | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Compute A/B/C metrics or return a blocked status when labels are insufficient."""
    rated, rubric = _usable_rated(rows)
    n_sources = independent_source_count(rated if rated else rows)
    report: dict[str, Any] = {
        "schema_required_fields_v2": list(REQUIRED_FOR_RATED),
        "schema_required_fields_legacy": list(REQUIRED_FOR_RATED_LEGACY),
        "rubric_used": rubric if rated else None,
        "n_rows": len(rows),
        "n_rated": len(rated),
        "n_independent_source_videos": n_sources,
        "min_rated_for_claim": min_rated,
        "treats_clutch_score_as_gt": False,
        "clips_treated_as_independent_for_ci": False,
        "dimensions_kept_separate": True,
        "comparison_mode": "fixed_pool_identical_candidates",
    }
    if len(rated) == 0:
        report["status"] = "blocked_no_human_labels"
        report["message"] = (
            "No complete human ratings. Fill the v2 rubric "
            "(entertainment/gameplay_significance/opening_hook/context/"
            "editing_suitability/genuine_highlight) via eval/gi-labeller.html "
            "before computing precision/recall/NDCG. Do not fabricate ratings."
        )
        report["minimum_additional_labels"] = min_rated
        report["decision_gates"] = decision_gates(
            agreement=agreement,
            baseline_measured=False,
            improvement=None,
            cost=cost,
            generalization=generalization,
        )
        return report
    if len(rated) < min_rated:
        report["status"] = "insufficient_sample"
        report["message"] = (
            f"Only {len(rated)} complete ratings; need ≥{min_rated} for reliable conclusions. "
            "Metrics below are exploratory only — do not claim significance."
        )
        report["minimum_additional_labels"] = min_rated - len(rated)
        report["exploratory"] = True
    else:
        report["status"] = "ok"
        report["exploratory"] = False

    sig = significance_allowed(n_sources)
    report["significance_testing"] = sig

    arms: dict[str, Any] = {}
    per_source_p5: dict[str, dict[str, float]] = {arm: {} for arm in ("A", "B", "C")}
    for arm in ("A", "B", "C"):
        ranked = arm_ranking(rows, arm)
        ranked_rated = [r for r in ranked if (is_rated(r) if rubric == "v2" else is_rated_legacy(r))]
        metrics = _arm_metrics_for_rows(ranked_rated, arm, ks)
        # Source-level P@5 when multiple VODs exist
        by_src = group_by_source(ranked_rated)
        for sid, src_rows in by_src.items():
            # Re-rank within source using same arm order already global; take local order from global
            ordered = [r for r in ranked_rated if (r.get("vod") or "") == sid]
            pos = [(r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE for r in ordered]
            p5 = precision_at_k(pos, 5)
            if p5 is not None:
                per_source_p5[arm][sid] = p5
        metrics["precision@5_source_bootstrap"] = paired_bootstrap_ci(
            per_source_p5[arm], seed=seed
        )
        arms[arm] = metrics

    report["arms"] = arms

    # Paired A→B / A→C deltas at source level
    deltas: dict[str, Any] = {}
    for other in ("B", "C"):
        d = paired_delta_by_source(per_source_p5["A"], per_source_p5[other])
        boot = paired_bootstrap_ci(d, seed=seed) if d else {
            "n_sources": 0,
            "mean": None,
            "reliable": False,
            "message": "No paired source-level precision@5 for both arms.",
        }
        practical = (
            boot.get("mean") is not None
            and boot["mean"] >= 0.05
            and bool(boot.get("reliable"))
            and boot.get("ci_low") is not None
            and boot["ci_low"] > 0
        )
        deltas[f"A_to_{other}"] = {
            "metric": "precision@5",
            "per_source_delta": d,
            "bootstrap": boot,
            "practical_improvement": practical,
            "ci_lower_bound_positive": bool(
                boot.get("ci_low") is not None and boot["ci_low"] > 0
            ),
            "meaningful_vs_uncertainty": practical,
            "statistical_vs_practical_note": (
                "Statistical significance is not reported when n_sources is small. "
                "Practical threshold here: mean ΔP@5 ≥ 0.05 with source-bootstrap CI low > 0."
            ),
        }
    report["paired_deltas"] = deltas

    best_imp = deltas.get("A_to_B") or deltas.get("A_to_C")
    report["decision_gates"] = decision_gates(
        agreement=agreement,
        baseline_measured=report["status"] in {"ok", "insufficient_sample"} and "A" in arms,
        improvement=best_imp,
        cost=cost,
        generalization=generalization,
    )

    report["notes"] = [
        "clutch_score is never used as ground truth.",
        "Recall of missed highlights outside the candidate sheet requires owner-added gap-hunt rows.",
        "Processing time / CPU-memory are reported by the separate CPU bench / job_timings, not this function.",
        "Virality / engagement is out of scope for this comparison.",
        "Do not claim a model is better solely because it produces more clips.",
    ]
    return report
