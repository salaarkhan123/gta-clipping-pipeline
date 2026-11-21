# 4. Baseline performance report

**Honest scope.** Where data permits. No invented quality metrics.

## Claim-ready baseline (highlight quality)

| Metric | Value | Status |
| --- | --- | --- |
| Precision@5 (Arm A) | — | **Blocked** (0 human ratings) |
| Precision@10 (Arm A) | — | **Blocked** |
| NDCG@5 (Arm A) | — | **Blocked** |
| Spearman vs human entertainment | — | **Blocked** |
| Recall vs independent annotations | — | **Blocked** (no gap-hunt GT) |
| False positives in top-5 | — | **Blocked** |

Sample size: `n_rated=0`, `n_independent_source_videos=1` on `gi-gta-label-sheet.csv` (30 proposal rows).

Compare artifact: [artifacts/baseline-compare.json](artifacts/baseline-compare.json).

## Measured non-quality baselines (allowed)

| Item | Result |
| --- | --- |
| Candidate pool size | 30 (GTA Online staging proposals) |
| Human complete (v2) | 0 |
| GI production impact | Disabled; weights 0; identity when off |
| Hook CPU overhead | Measured via `cpu-bench` (synthetic; not full VOD) |
| Historical Wayin overlap | 7/15 on saved reaction run — competitor proxy only |

## What additional data is required

1. ≥20 (prefer 30) complete v2 human ratings on the fixed GTA sheet.
2. Dual-rater subset (≥10) + adjudication.
3. ≥3 gap-hunt misses for recall beyond proposal precision.
4. ≥4 additional independent source recordings before source-level CIs.
5. At least one non-GTA title before multi-game claims.

Until then: **baseline quality is unmeasured**, not “equal to competitors” and not “good enough.”
