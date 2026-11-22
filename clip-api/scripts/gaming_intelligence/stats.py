"""Statistical helpers for GI evaluation — source-video clustering, agreement, gates.

Rules:
- Never invent human labels or engagement outcomes.
- Do not treat multiple clips from the same recording as independent observations
  when forming confidence intervals.
- Skip significance tests when n_independent_sources is too small.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Callable, Hashable


# Minimum independent source videos before claiming a bootstrap CI is useful.
MIN_SOURCES_FOR_CI = 5
# Below this, paired significance tests are explicitly marked unreliable.
MIN_SOURCES_FOR_SIGNIFICANCE = 8


def group_by_source(
    rows: list[dict[str, Any]],
    *,
    source_key: str = "vod",
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = str(r.get(source_key) or r.get("source_recording_id") or "").strip() or "_unknown"
        out[key].append(r)
    return dict(out)


def independent_source_count(rows: list[dict[str, Any]], *, source_key: str = "vod") -> int:
    return len(group_by_source(rows, source_key=source_key))


def quadratic_weighted_kappa(
    a: list[int | float],
    b: list[int | float],
    *,
    min_score: int = 1,
    max_score: int = 5,
) -> float | None:
    """Cohen's kappa with quadratic weights for ordinal 1–5 ratings."""
    if len(a) != len(b) or len(a) < 2:
        return None
    cats = list(range(min_score, max_score + 1))
    n = len(cats)
    idx = {c: i for i, c in enumerate(cats)}
    conf = [[0.0] * n for _ in range(n)]
    for x, y in zip(a, b):
        if x not in idx or y not in idx:
            continue
        conf[idx[x]][idx[y]] += 1.0
    total = sum(sum(row) for row in conf)
    if total <= 0:
        return None
    weights = [[((i - j) / (n - 1)) ** 2 for j in range(n)] for i in range(n)]
    row_m = [sum(conf[i][j] for j in range(n)) for i in range(n)]
    col_m = [sum(conf[i][j] for i in range(n)) for j in range(n)]
    obs = sum(weights[i][j] * conf[i][j] for i in range(n) for j in range(n)) / total
    exp = sum(weights[i][j] * row_m[i] * col_m[j] / total for i in range(n) for j in range(n)) / total
    if exp <= 1e-12:
        return 1.0 if obs <= 1e-12 else None
    return 1.0 - (obs / exp)


def percent_agreement(a: list[Any], b: list[Any], *, adjacent: bool = False) -> float | None:
    if len(a) != len(b) or not a:
        return None
    hits = 0
    for x, y in zip(a, b):
        if x == y:
            hits += 1
        elif adjacent:
            try:
                if abs(float(x) - float(y)) <= 1:
                    hits += 1
            except (TypeError, ValueError):
                pass
    return hits / len(a)


def agreement_report(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    ordinal_fields: tuple[str, ...] = (
        "entertainment_1_5",
        "gameplay_significance_1_5",
        "opening_hook_1_5",
        "context_1_5",
        "editing_suitability_1_5",
        "quality_1_5",
    ),
    categorical_fields: tuple[str, ...] = ("genuine_highlight",),
) -> dict[str, Any]:
    """Pairwise rater agreement. Does not invent missing ratings."""
    report: dict[str, Any] = {
        "n_pairs": len(pairs),
        "ordinal": {},
        "categorical": {},
        "disagreements_for_adjudication": [],
    }
    if not pairs:
        report["status"] = "blocked_no_dual_ratings"
        report["message"] = "Need ≥2 independent raters on overlapping clip IDs."
        return report

    for field in ordinal_fields:
        xs, ys, ids = [], [], []
        for left, right in pairs:
            av = (left.get(field) or "").strip()
            bv = (right.get(field) or "").strip()
            if not av or not bv:
                continue
            try:
                xs.append(int(float(av)))
                ys.append(int(float(bv)))
                ids.append(left.get("id") or right.get("id"))
            except (TypeError, ValueError):
                continue
        if len(xs) < 2:
            report["ordinal"][field] = {"n": len(xs), "kappa_qw": None, "exact_agreement": None}
            continue
        kappa = quadratic_weighted_kappa(xs, ys)
        exact = percent_agreement(xs, ys)
        adj = percent_agreement(xs, ys, adjacent=True)
        report["ordinal"][field] = {
            "n": len(xs),
            "kappa_qw": None if kappa is None else round(kappa, 4),
            "exact_agreement": None if exact is None else round(exact, 4),
            "adjacent_agreement": None if adj is None else round(adj, 4),
        }
        for i, (x, y) in enumerate(zip(xs, ys)):
            if abs(x - y) >= 2:
                report["disagreements_for_adjudication"].append({
                    "id": ids[i],
                    "field": field,
                    "rater_a": x,
                    "rater_b": y,
                    "abs_diff": abs(x - y),
                })

    for field in categorical_fields:
        xs, ys = [], []
        for left, right in pairs:
            av = (left.get(field) or "").strip().lower()
            bv = (right.get(field) or "").strip().lower()
            if not av or not bv:
                continue
            xs.append(av)
            ys.append(bv)
            if av != bv:
                report["disagreements_for_adjudication"].append({
                    "id": left.get("id") or right.get("id"),
                    "field": field,
                    "rater_a": av,
                    "rater_b": bv,
                })
        exact = percent_agreement(xs, ys)
        report["categorical"][field] = {
            "n": len(xs),
            "exact_agreement": None if exact is None else round(exact, 4),
        }

    # Gate: labels "sufficiently reliable" if weighted kappa ≥ 0.6 on ≥1 primary ordinal
    # with n≥10, or exact categorical agreement ≥ 0.8 with n≥10.
    reliable = False
    reasons: list[str] = []
    for field, m in report["ordinal"].items():
        if (m.get("n") or 0) >= 10 and m.get("kappa_qw") is not None and m["kappa_qw"] >= 0.6:
            reliable = True
            reasons.append(f"{field} kappa_qw={m['kappa_qw']} (n={m['n']})")
    for field, m in report["categorical"].items():
        if (m.get("n") or 0) >= 10 and m.get("exact_agreement") is not None and m["exact_agreement"] >= 0.8:
            reliable = True
            reasons.append(f"{field} agreement={m['exact_agreement']} (n={m['n']})")
    report["labels_sufficiently_reliable"] = reliable
    report["reliability_evidence"] = reasons or ["insufficient dual-rated sample or low agreement"]
    report["status"] = "ok" if pairs else "blocked_no_dual_ratings"
    return report


def pair_dual_rater_sheets(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    *,
    id_key: str = "id",
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Match rows by clip id. Same rater twice is rejected."""
    by_id = {str(r.get(id_key) or ""): r for r in secondary if r.get(id_key)}
    pairs = []
    for r in primary:
        cid = str(r.get(id_key) or "")
        other = by_id.get(cid)
        if not other:
            continue
        ra = (r.get("rater") or "").strip().lower()
        rb = (other.get("rater") or "").strip().lower()
        if ra and rb and ra == rb:
            continue
        pairs.append((r, other))
    return pairs


def paired_bootstrap_ci(
    source_metrics: dict[Hashable, float],
    *,
    n_boot: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Bootstrap CI by resampling independent source videos (not clips)."""
    keys = list(source_metrics.keys())
    vals = [source_metrics[k] for k in keys]
    n = len(vals)
    if n == 0:
        return {
            "n_sources": 0,
            "mean": None,
            "ci_low": None,
            "ci_high": None,
            "method": "source_bootstrap",
            "reliable": False,
            "message": "No independent sources.",
        }
    mean = sum(vals) / n
    if n < MIN_SOURCES_FOR_CI:
        return {
            "n_sources": n,
            "mean": mean,
            "ci_low": None,
            "ci_high": None,
            "method": "descriptive_only",
            "reliable": False,
            "message": (
                f"Only {n} independent source videos; need ≥{MIN_SOURCES_FOR_CI} "
                "for a defensible source-level bootstrap CI. Report the mean as descriptive."
            ),
        }
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_i = int(math.floor(alpha / 2 * n_boot))
    hi_i = int(math.ceil((1 - alpha / 2) * n_boot)) - 1
    hi_i = min(max(hi_i, 0), n_boot - 1)
    return {
        "n_sources": n,
        "mean": mean,
        "ci_low": means[lo_i],
        "ci_high": means[hi_i],
        "n_boot": n_boot,
        "seed": seed,
        "alpha": alpha,
        "method": "source_bootstrap",
        "reliable": True,
        "message": None,
    }


def paired_delta_by_source(
    arm_a: dict[Hashable, float],
    arm_b: dict[Hashable, float],
) -> dict[Hashable, float]:
    """Per-source metric(B) − metric(A) for sources present in both arms."""
    return {k: arm_b[k] - arm_a[k] for k in arm_a if k in arm_b}


def significance_allowed(n_sources: int) -> dict[str, Any]:
    allowed = n_sources >= MIN_SOURCES_FOR_SIGNIFICANCE
    return {
        "allowed": allowed,
        "n_sources": n_sources,
        "minimum_required": MIN_SOURCES_FOR_SIGNIFICANCE,
        "message": (
            None
            if allowed
            else (
                f"n_independent_sources={n_sources} < {MIN_SOURCES_FOR_SIGNIFICANCE}. "
                "Do not run or report p-values; use descriptive paired deltas only."
            )
        ),
    }


def decision_gates(
    *,
    agreement: dict[str, Any] | None,
    baseline_measured: bool,
    improvement: dict[str, Any] | None,
    cost: dict[str, Any] | None,
    generalization: dict[str, Any] | None,
) -> dict[str, Any]:
    """Six gates from the statistical research constraints. Fail closed."""
    gates: list[dict[str, Any]] = []

    labels_ok = bool(agreement and agreement.get("labels_sufficiently_reliable"))
    gates.append({
        "id": 1,
        "name": "human_label_reliability",
        "passed": labels_ok,
        "evidence": (agreement or {}).get("reliability_evidence") or ["no dual-rater agreement yet"],
        "required_next": None if labels_ok else "Collect dual ratings on ≥10 overlapping clips; adjudicate diffs ≥2.",
    })

    gates.append({
        "id": 2,
        "name": "baseline_measured",
        "passed": baseline_measured,
        "evidence": ["baseline metrics computed on held-out human labels"] if baseline_measured else ["baseline quality metrics blocked (no/insufficient labels)"],
        "required_next": None if baseline_measured else "Complete ≥20 human ratings on Dataset B development or eval sheet.",
    })

    imp_ok = bool(
        improvement
        and improvement.get("practical_improvement")
        and improvement.get("ci_lower_bound_positive")
    )
    gates.append({
        "id": 3,
        "name": "experimental_improves_metric",
        "passed": imp_ok,
        "evidence": improvement or {"status": "not_run"},
        "required_next": None if imp_ok else "Run fixed-pool A/B/C on identical candidates with held-out labels.",
    })

    unc_ok = bool(improvement and improvement.get("meaningful_vs_uncertainty"))
    gates.append({
        "id": 4,
        "name": "improvement_vs_uncertainty",
        "passed": unc_ok,
        "evidence": improvement or {"status": "not_run"},
        "required_next": None if unc_ok else "Need enough independent source videos for source-level CI; do not claim significance early.",
    })

    cost_ok = bool(cost and cost.get("acceptable"))
    gates.append({
        "id": 5,
        "name": "processing_cost_acceptable",
        "passed": cost_ok,
        "evidence": cost or {"status": "not_measured_on_full_vod"},
        "required_next": None if cost_ok else "Measure wall s / source hour, peak RSS, and $/source hour on identical VODs.",
    })

    gen_ok = bool(generalization and generalization.get("holds_on_held_out"))
    gates.append({
        "id": 6,
        "name": "generalizes_beyond_development",
        "passed": gen_ok,
        "evidence": generalization or {"status": "held_out_not_evaluated"},
        "required_next": None if gen_ok else "Evaluate on held-out recordings (streamer-separated); never tune on those labels.",
    })

    all_pass = all(g["passed"] for g in gates)
    return {
        "all_gates_passed": all_pass,
        "proceed_to_complex_models": all_pass,
        "gates": gates,
        "recommendation": (
            "Evidence supports considering a more complex model or weight raise."
            if all_pass
            else "Do not increase model complexity. Satisfy failing gates first."
        ),
    }


def metric_per_source(
    rows_by_source: dict[Hashable, list[dict[str, Any]]],
    metric_fn: Callable[[list[dict[str, Any]]], float | None],
) -> dict[Hashable, float]:
    out: dict[Hashable, float] = {}
    for sid, rows in rows_by_source.items():
        val = metric_fn(rows)
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            out[sid] = float(val)
    return out
