"""Highlight quality, ranking and boundary metrics for Phase 1."""
from __future__ import annotations

import math
from collections import defaultdict


def precision_recall_f1(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    if prec is None or rec is None or (prec + rec) == 0:
        f1 = None
    else:
        f1 = 2 * prec * rec / (prec + rec)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "f1": f1}


def event_confusion(
    predictions: list[tuple[int, str]],
    labels: list[tuple[int, set[str]]],
    *,
    positive_class: str,
    onset_tol: int = 1,
) -> dict[str, float | None]:
    """One-to-one match of predicted onsets to labelled seconds for one class."""
    labelled = sorted(t for t, classes in labels if positive_class in classes)
    predicted = sorted(t for t, cls in predictions if cls == positive_class)
    used: set[int] = set()
    tp = 0
    for p in predicted:
        hit = next((t for t in labelled if t not in used and abs(t - p) <= onset_tol), None)
        if hit is None:
            continue
        used.add(hit)
        tp += 1
    fp = len(predicted) - tp
    fn = len(labelled) - tp
    return precision_recall_f1(tp, fp, fn)


def _dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked_gains: list[float], ideal_gains: list[float], k: int = 5) -> float | None:
    """NDCG@k. Gains use 3/1/0 for ratings 3/2/1 as in EVALUATION-FRAMEWORK.md."""
    if k <= 0:
        return None
    ideal = sorted((g for g in ideal_gains if g > 0), reverse=True)[:k]
    if not ideal:
        return None
    actual = list(ranked_gains[:k]) + [0.0] * max(0, k - len(ranked_gains))
    actual = actual[:k]
    return _dcg(actual) / _dcg(ideal)


def boundary_errors(
    predicted: list[tuple[float, float]],
    labelled: list[tuple[float, float]],
    *,
    tiou_thresholds: tuple[float, ...] = (0.3, 0.5, 0.7),
) -> dict:
    """Match predicted intervals to labelled ones by max IoU; report errors and tIoU hit rates."""
    def iou(a0: float, a1: float, b0: float, b1: float) -> float:
        inter = max(0.0, min(a1, b1) - max(a0, b0))
        union = (a1 - a0) + (b1 - b0) - inter
        return inter / union if union > 0 else 0.0

    used: set[int] = set()
    matches = []
    for p0, p1 in predicted:
        best_i, best = None, -1.0
        for i, (l0, l1) in enumerate(labelled):
            if i in used:
                continue
            score = iou(p0, p1, l0, l1)
            if score > best:
                best_i, best = i, score
        if best_i is None or best <= 0:
            continue
        used.add(best_i)
        l0, l1 = labelled[best_i]
        matches.append({
            "iou": best,
            "start_abs_err": abs(p0 - l0),
            "end_abs_err": abs(p1 - l1),
            "contains_midpoint": l0 <= (p0 + p1) / 2 <= l1,
        })

    def median(xs: list[float]) -> float | None:
        if not xs:
            return None
        xs = sorted(xs)
        mid = len(xs) // 2
        return xs[mid] if len(xs) % 2 else 0.5 * (xs[mid - 1] + xs[mid])

    tiou_hits = {
        str(t): sum(1 for m in matches if m["iou"] >= t) / len(labelled) if labelled else None
        for t in tiou_thresholds
    }
    return {
        "matched": len(matches),
        "unmatched_predictions": len(predicted) - len(matches),
        "unmatched_labels": len(labelled) - len(matches),
        "median_start_abs_err": median([m["start_abs_err"] for m in matches]),
        "median_end_abs_err": median([m["end_abs_err"] for m in matches]),
        "median_iou": median([m["iou"] for m in matches]),
        "tiou_recall": tiou_hits,
    }


def rating_gain(rating: int | None) -> float:
    if rating == 3:
        return 3.0
    if rating == 2:
        return 1.0
    return 0.0


def group_by_vod(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["vod"]].append(r)
    return out
