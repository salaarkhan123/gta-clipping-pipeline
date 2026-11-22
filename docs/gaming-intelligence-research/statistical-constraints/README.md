# Gaming Intelligence — Statistical Research Constraints

Continuation of PR #262. **Goal:** determine whether Gaming Intelligence produces measurably better gaming highlights than the current ClutchClips system, using defensible evidence.

**Status (2026-11-21):** Framework + audit + Dataset A/B templates shipped. Human labels still **0**. All six decision gates **fail**. Do not merge as production enablement. Weights stay **0**. No GPU purchase. No fabricated ratings.

## Deliverables

| # | Deliverable | Path |
| ---: | --- | --- |
| 1 | Statistical methodology and dataset audit | [01-STATISTICAL-METHODOLOGY-AND-AUDIT.md](01-STATISTICAL-METHODOLOGY-AND-AUDIT.md) · [artifacts/audit-snapshot.json](artifacts/audit-snapshot.json) |
| 2 | Dataset collection and labeling specification | [02-DATASET-AND-LABELING-SPEC.md](02-DATASET-AND-LABELING-SPEC.md) |
| 3 | Reproducible A/B/C evaluation pipeline | [03-ABC-EVALUATION-PIPELINE.md](03-ABC-EVALUATION-PIPELINE.md) |
| 4 | Baseline performance report (data-permitted) | [04-BASELINE-PERFORMANCE-REPORT.md](04-BASELINE-PERFORMANCE-REPORT.md) |
| 5 | Data leakage and selection-bias assessment | [05-LEAKAGE-AND-BIAS-ASSESSMENT.md](05-LEAKAGE-AND-BIAS-ASSESSMENT.md) |
| 6 | Statistical uncertainty and limitations | [06-UNCERTAINTY-AND-LIMITATIONS.md](06-UNCERTAINTY-AND-LIMITATIONS.md) |
| 7 | Model complexity and performance recommendations | [07-MODEL-COMPLEXITY-RECOMMENDATIONS.md](07-MODEL-COMPLEXITY-RECOMMENDATIONS.md) |
| 8 | Prioritized next experiments | [08-NEXT-EXPERIMENTS.md](08-NEXT-EXPERIMENTS.md) |

## Code

| Module | Role |
| --- | --- |
| `clip-api/scripts/gaming_intelligence/stats.py` | Source-level bootstrap, agreement, decision gates |
| `clip-api/scripts/gaming_intelligence/datasets_ab.py` | Dataset A/B templates + split isolation |
| `clip-api/scripts/gaming_intelligence/compare.py` | A/B/C metrics with clustering rules |
| `clip-api/scripts/gaming_intelligence/report.py` | Machine + human experiment envelopes |
| `clip-api/scripts/gaming_intelligence_cli.py` | `audit` · `compare` · `agreement` · `decide` · `init-dataset-*` |
| `clip-api/eval/gi-labeller.html` | Expanded 1–5 rubric (dimensions kept separate) |
| `clip-api/eval/datasets/` | Blank Dataset A/B templates (no invented values) |

## Hard rules

- Do not invent results, ratings, or engagement.
- Popularity ≠ highlight-quality ground truth.
- Virality research stays separate.
- Never train or optimize on held-out evaluation labels.
- Do not proceed to complex models until decision gates pass (`decide`).
