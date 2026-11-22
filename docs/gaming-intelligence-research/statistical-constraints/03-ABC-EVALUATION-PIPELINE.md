# 3. Reproducible A/B/C evaluation pipeline

## Arms (identical candidate pool for ranking)

| Arm | Definition | Production |
| --- | --- | --- |
| **A** | Existing ClutchClips baseline (`clutch_score` / `clutch_rank`) | Control |
| **B** | GI prototype (`gi_score`) | Off by default; weights 0 |
| **C** | Combined baseline + GI families | Experimental; default ≡ A |

Do **not** claim superiority because an arm emits more clips. Keep clip duration, candidate budgets, and preprocessing comparable; record unavoidable differences.

## Modes

1. **Fixed-pool ranking (primary for P@k / NDCG / Spearman).** Same sheet for A/B/C.
2. **End-to-end discovery.** Same raw source videos; each system nominates under the same budget; evaluate selected **and** missed highlights (gap-hunt / exhaustive labels).

## Metrics

| Metric | Definition |
| --- | --- |
| Precision@5 / @10 | Share of top-k with `genuine_highlight=yes` |
| Recall | Against independently annotated gameplay (requires gap-hunt / timeline labels) |
| Ranking correlation | Spearman of system score vs human entertainment (or quality legacy) |
| NDCG@5/@10 | Gains from declared ordinal mapping (5→3, 4→2, 3→1) — for ranking only; dimensions still stored separately |
| False positives | Labelled `no` appearing in top-5 |
| Runtime / CPU / peak RSS / $/source-hour | Separate benches; not invented here |

## Uncertainty

- Bootstrap resamples **source videos**, not clips (`paired_bootstrap_ci`).
- Significance tests disabled when `n_independent_sources < 8`.
- Distinguish statistical vs practical significance (practical: mean ΔP@5 ≥ 0.05 with CI low > 0 when CI reliable).

## Reproduce

```bash
cd clip-api
python3 scripts/gaming_intelligence_cli.py compare eval/gi-gta-label-sheet.csv \
  --seed 42 \
  --json-out /tmp/gi-abc.json \
  --md-out /tmp/gi-abc.md
python3 scripts/gaming_intelligence_cli.py agreement --primary rater1.csv --secondary rater2.csv
python3 scripts/gaming_intelligence_cli.py decide
```

Current compare status: **`blocked_no_human_labels`**. Artifact without labels: [artifacts/baseline-compare.json](artifacts/baseline-compare.json).

## Experiment envelope (reproducibility)

Every run records via `report.experiment_envelope`:

- dataset version / path
- source recording IDs
- model + code version
- feature configuration
- random seed
- evaluation methodology
- sample size
- metrics
- runtime + hardware
- known limitations
