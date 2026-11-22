"""A/B/C comparison framework for ClutchClips vs Gaming Intelligence.

Arms
  A — existing production detector ranking (clutch_rank / clutch_score)
  B — GI prototype ranking (gi_score / gi_rank) when features present
  C — combined: baseline + weighted GI family features (experimental; weights default 0)

Metrics are computed **only** when human ground-truth labels exist.
This module never invents ratings and never treats clutch_score as GT.
"""
from __future__ import annotations

import math
from typing import Any

from .dataset import REQUIRED_FOR_RATED, is_rated

POSITIVE_GENUINE = {"yes"}
NEGATIVE_GENUINE = {"no"}
# "maybe" is excluded from binary precision/recall denominators unless noted.


def _f(x: str | float | int | None) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _gain_from_quality(q: float | None) -> float:
    """Map quality 1–5 → ranking gain. Unrated → None (caller skips)."""
    if q is None:
        return 0.0
    # 5→3, 4→2, 3→1, 2→0, 1→0 (aligned with #237 3/1/0 spirit, stretched to 1–5)
    if q >= 5:
        return 3.0
    if q >= 4:
        return 2.0
    if q >= 3:
        return 1.0
    return 0.0


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
    return {"precision": prec, "recall": rec, "f1": f1, "fp_rate": fp_rate, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": len(y_true)}


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
            # lower clutch_rank is better when score missing
            primary = score if score is not None else (1000.0 - (rank or 1000.0))
            return (-primary, float(rank or 0))
        if arm == "B":
            score = _f(r.get("gi_score"))
            return (-(score if score is not None else -1e9), 0.0)
        if arm == "C":
            # Combined: clutch_score + optional gi bump already baked into gi_score when weights>0;
            # if gi_score absent, fall back to clutch.
            gi = _f(r.get("gi_score"))
            base = _f(r.get("clutch_score")) or 0.0
            return (-(gi if gi is not None else base), 0.0)
        raise ValueError(f"unknown arm {arm}")

    return sorted((dict(r) for r in rows), key=key)


def evaluate_arms(
    rows: list[dict[str, str]],
    *,
    min_rated: int = 20,
    ks: tuple[int, ...] = (5, 10),
) -> dict[str, Any]:
    """Compute A/B/C metrics or return a blocked status when labels are insufficient."""
    rated = [r for r in rows if is_rated(r)]
    report: dict[str, Any] = {
        "schema_required_fields": list(REQUIRED_FOR_RATED),
        "n_rows": len(rows),
        "n_rated": len(rated),
        "min_rated_for_claim": min_rated,
        "treats_clutch_score_as_gt": False,
    }
    if len(rated) == 0:
        report["status"] = "blocked_no_human_labels"
        report["message"] = (
            "No complete human ratings. Fill quality/entertainment/context/genuine_highlight/"
            "clutch_correct via eval/gi-labeller.html before computing precision/recall/NDCG."
        )
        report["minimum_additional_labels"] = min_rated
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

    # Binary: genuine_highlight yes vs no (maybe excluded)
    binary_rows = [r for r in rated if (r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE | NEGATIVE_GENUINE]
    y_true = [(r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE for r in binary_rows]

    arms: dict[str, Any] = {}
    for arm in ("A", "B", "C"):
        ranked = arm_ranking(rows, arm)
        ranked_rated = [r for r in ranked if is_rated(r)]
        qualities = [_f(r.get("quality_1_5")) or 0.0 for r in ranked_rated]
        gains = [_gain_from_quality(q) for q in qualities]
        ideal = list(gains)
        pos_flags = [(r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE for r in ranked_rated]

        # Pred: top-k of this arm treated as "selected positives" for P@k
        metrics: dict[str, Any] = {
            "ndcg@5": ndcg_at_k(gains, ideal, 5),
            "ndcg@10": ndcg_at_k(gains, ideal, 10),
        }
        for k in ks:
            metrics[f"precision@{k}"] = precision_at_k(pos_flags, k)

        # Ranking agreement with human quality (Spearman)
        human_q = [_f(r.get("quality_1_5")) or 0.0 for r in ranked_rated]
        if arm == "A":
            system_s = [_f(r.get("clutch_score")) or (1000.0 - (_f(r.get("clutch_rank")) or 1000.0)) for r in ranked_rated]
        elif arm == "B":
            system_s = [_f(r.get("gi_score")) or 0.0 for r in ranked_rated]
        else:
            system_s = [_f(r.get("gi_score")) or (_f(r.get("clutch_score")) or 0.0) for r in ranked_rated]
        metrics["spearman_vs_quality"] = spearman_rank(system_s, human_q)

        # Missed high-quality: quality≥4 and genuine=yes but outside top-10
        top10_ids = {(r.get("id") or "") for r in ranked_rated[:10]}
        missed = [
            r.get("id") for r in ranked_rated
            if (_f(r.get("quality_1_5")) or 0) >= 4
            and (r.get("genuine_highlight") or "").lower() in POSITIVE_GENUINE
            and (r.get("id") or "") not in top10_ids
        ]
        metrics["missed_high_quality_outside_top10"] = missed
        metrics["n_ranked_rated"] = len(ranked_rated)

        # Optional binary PR if clutch_correct used as "system said highlight"
        # For arm A: predict positive if clutch proposed the row (all candidates are proposals) —
        # that makes precision = share of genuine among candidates (selection precision).
        if binary_rows:
            # All sheet rows are detector proposals; binary precision = P(genuine|proposed)
            y_pred = [True] * len(binary_rows)  # proposed set
            metrics["selection_precision_among_labelled"] = binary_prf(y_true, y_pred)["precision"]
            metrics["n_binary_labelled"] = len(binary_rows)
            metrics["genuine_yes"] = sum(1 for t in y_true if t)
            metrics["genuine_no"] = sum(1 for t in y_true if not t)

        arms[arm] = metrics

    report["arms"] = arms
    report["notes"] = [
        "clutch_score is never used as ground truth.",
        "Recall of missed highlights outside the candidate sheet requires owner-added gap-hunt rows.",
        "Processing time / CPU-memory are reported by the separate CPU bench, not this function.",
    ]
    return report
