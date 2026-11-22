# 8. Prioritized next experiments

Ordered by evidence leverage. Owner media/ratings required where marked. No fabricated labels. No GPU without approval.

| Priority | Experiment | Owner input? | Exit criterion | Unblocks |
| ---: | --- | --- | --- | --- |
| **P0** | Rate ≥20 (prefer 30) v2 fields on `gi-gta-label-sheet.csv` via `gi-labeller.html` | **Yes** | `compare` ≠ `blocked_no_human_labels` | Baseline P@5/@10 |
| **P0** | Second independent rater on ≥10 overlapping rows | **Yes** | `agreement` reliability gate | Gate 1 |
| **P1** | Gap-hunt ≥3 misses + ≥5 ordinary/weak intervals on same VOD | Yes | Recall + FP denominators exist | Discovery honesty |
| **P1** | Freeze fixed pool; run A/B/C compare (weights still 0 → B/C may match A) | No (once labelled) | Exploratory report with n + limitations | Gate 2 |
| **P2** | Add ≥4 more independent permissioned recordings (streamer-separated held-out) | Yes — media | `n_sources ≥ 5` | Source-level CI |
| **P2** | Fill Dataset B pilot rows per game (30 candidates each) with ordinary draws | Yes | Census shows ordinary_or_weak > 0 | Multi-title prep |
| **P3** | Dataset A permissioned ingest (30/game) with confounders recorded | Yes — rights | `ingested_with_permission` grows; still not GT | Characteristic study |
| **P3** | Full-VOD wall time / peak RSS / $/hour for A vs research B on same hosts | Optional spend | Measured cost table | Gate 5 |
| **P4** | Only if gates 1–6 pass: preregister nonzero weight on one interpretable family | Owner OK | Held-out ΔP@5 practical + CI | Complexity tier 3 |

## Stop / do-not conditions

- Do not raise weights or enable GI because the hook is fast.
- Do not run significance tests on one VOD’s clips.
- Do not merge/deploy/activate GI or provision paid GPUs from this research alone.
- Do not invent ratings to “complete” a deliverable.
- If evidence is insufficient, state the exact missing data (as in the table above) and stop.

## Immediate commands (no owner media)

```bash
cd clip-api
python3 scripts/gaming_intelligence_cli.py audit
python3 scripts/gaming_intelligence_cli.py decide
python3 -m pytest -q tests/test_gi_statistical_constraints.py tests/test_gaming_intelligence.py
```
