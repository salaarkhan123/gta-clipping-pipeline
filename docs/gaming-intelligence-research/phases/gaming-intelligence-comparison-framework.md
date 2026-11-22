<!-- Mirrors store docs/gaming-intelligence-comparison-framework.md -->

# Baseline evaluation methodology & A/B/C comparison

**Status.** Framework + tests implemented. Quality metrics **blocked** until human labels exist (0/30 rated).

---

## Arms (same candidate sheet)

| Arm | Definition | Production impact |
| --- | --- | --- |
| **A** | Existing ClutchClips detector: order by `clutch_score` / `clutch_rank` | Control (today) |
| **B** | GI prototype: order by `gi_score` when research features present | Off by default |
| **C** | Combined: baseline + GI family weights (default all **0** → identical to A) | Experimental |

Candidates: `eval/gi-gta-label-sheet.csv` (30 GTA proposals). Do not tune thresholds on the held-out VOD once supplied.

---

## Metrics (computed only when labels exist)

| Metric | Definition |
| --- | --- |
| Precision / recall / F1 | Binary on `genuine_highlight` yes vs no (`maybe` excluded) |
| Precision@5 / @10 | Share of top-k with `genuine_highlight=yes` |
| NDCG@5 / @10 | Gains from `quality_1_5` (5→3, 4→2, 3→1, else 0) |
| Spearman vs quality | System score vs human `quality_1_5` |
| Missed high-quality | quality≥4 ∧ genuine=yes outside top-10 |
| FP rate | Among labelled no’s predicted positive |
| Processing time / CPU·mem | Separate CPU bench (hook) + future `job_timings.py` full path |

```bash
cd clip-api
python3 scripts/gaming_intelligence_cli.py compare eval/gi-gta-label-sheet.csv
```

Current output: `status=blocked_no_human_labels`, `minimum_additional_labels=20`.

---

## Leakage controls

- Human fields never auto-filled from `clutch_score`.
- Compare does not fit weights; weight changes require a separate, pre-registered experiment.
- Prefer fixing the candidate list before labelling; if regenerating candidates, version the sheet.
- Gap-hunt rows (owner-added misses) required for honest recall beyond “precision among proposals”.

---

## Sample-size limitation

| Rated complete | Interpretation |
| ---: | --- |
| 0 | Metrics blocked |
| 1–19 | `insufficient_sample` — exploratory only |
| ≥20 | Claim-eligible on this sheet (still GTA-only; not multi-title) |
| + gap-hunt + 2nd title | Required before generalizing past GTA Online |

**Minimum additional data to proceed:** ≥20 complete human ratings on this sheet (prefer 30); then ≥1 non-GTA VOD + held-out RP for transfer claims.
