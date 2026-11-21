# 1. Statistical methodology and dataset audit

**Date.** 2026-11-21 (America/Resolute) · continues PR #262  
**Machine-readable snapshot.** [artifacts/audit-snapshot.json](artifacts/audit-snapshot.json)

## Audit verdict

There is **no claim-ready evidence** that Gaming Intelligence improves highlight detection or ranking. The evaluation *harness* exists; human ground truth does not. All quality metrics that require labels are **blocked**, not “approximately good.”

## What is actually measured

| Item | Evidence | Notes |
| --- | --- | --- |
| GI disabled-by-default identity | Unit tests | `apply_gi(enabled=False)` returns input unchanged |
| Family weights default **0** | Unit tests + `DEFAULT_FAMILY_WEIGHTS` | Enabling GI with zero weights preserves order |
| CPU hook overhead (synthetic candidates) | `cpu-bench` | Milliseconds on Python annotate/rerank only — **not** full VOD pipeline |
| Label-sheet census | `sheet-stats` / `audit` | 30 GTA candidates, **0** complete human ratings (v2 and legacy) |
| Wayin competitor-overlap historical run | `eval_clips.py` + saved JSON | 7/15 overlap; rated P@20 interval 30–100% from incomplete judgement — **not** a sampling CI |
| Phase-1 B0 determinism | Synthetic fixture | Fingerprint + paid-call count 0 |
| Excerpt probe starts (GTA/Fortnite/Valorant) | EVALUATION-FRAMEWORK.md | Rank-order starts only; **no** human quality labels on those excerpts |
| YouNiverse reach pilot aggregates | VIRALITY-RESEARCH.md | Metadata pairs; **no** viewing of media; popularity study only |

## What is estimated (not measured)

| Item | Nature |
| --- | --- |
| GPU $/source-hour | List price × assumed billed minutes (`estimate-gpu`) |
| Full-VOD GI quality lift | No human labels → cannot measure |
| End-to-end detection recall on exhaustive timelines | No second-level / episode GT on gaming VODs |
| Named-sound / HUD OCR precision floors | Adapters weight-0; labelled seconds/frames missing |

## Human-labeled data sufficiency

| Asset | Rows | Complete human ratings | Enough for claim? |
| --- | ---: | ---: | --- |
| `eval/gi-gta-label-sheet.csv` | 30 | **0** | No |
| `eval/labels-v2.csv` | 30 | **0** | No |
| `eval/benchmark-2h-labels.csv` | 46 | **0** | No |
| `eval/wayin-zias-iceman.csv` | 15 | 15 competitor proxies (all “3”) | Not gaming-quality GT |
| Dual-rater overlaps | 0 | 0 | Agreement **not measurable** |
| Dataset A (online reference) | template 150 | 0 ingested with permission | Not started |
| Dataset B (ClutchClips eval) | template 150 | 0 | Not started |

**Minimum for exploratory sheet metrics:** ≥20 complete v2 ratings on one fixed candidate pool.  
**Minimum for source-level CI:** ≥5 independent source recordings (prefer ≥8 before any significance language).  
**Minimum for reliability gate:** dual ratings on ≥10 overlapping clips with weighted kappa ≥0.6 (or categorical agreement ≥0.8).

## Metrics that cannot currently be calculated

- Precision@5 / Precision@10 against human `genuine_highlight`
- Recall against independently annotated gameplay (requires gap-hunt / exhaustive windows)
- Ranking correlation (Spearman) with human entertainment/quality — claim-ready
- NDCG@5/@10 with human gains
- False-positive analysis among labelled negatives
- Inter-rater agreement / adjudication rates
- Paired A vs B source-bootstrap CI
- Runtime per source-video hour for GI-on full path (only hook microbench exists)
- Peak memory / processing cost per source-video hour for GI (CPU hook only; GPU not provisioned)

## Statistical validity of existing comparisons

| Comparison | Valid? | Why |
| --- | --- | --- |
| A/B/C on `gi-gta-label-sheet` | Framework valid; results blocked | Identical pool design is correct; n_rated=0 |
| Wayin overlap @20 | Descriptive only | Incomplete ratings → range not CI; competitor proxy ≠ quality |
| Signal probe vs RC selector | Not a quality experiment | Different nomination rules; no human labels; wall-time denominators differ |
| YouNiverse title-marker vs reach | Not highlight eval | Selection on views; 9 creators; no media labels |

## Methodology locked for future runs

1. **Fixed-pool ranking:** identical candidate union for arms A/B/C; order by arm score only.
2. **Discovery / end-to-end:** identical raw source videos; measure misses outside each arm’s pool separately.
3. **Clustering:** resample **source recordings** (and streamers when available) for CIs — never clips-as-iid.
4. **Significance:** forbidden when `n_independent_sources < 8` (`significance_allowed`).
5. **Practical improvement:** mean ΔP@5 ≥ 0.05 with source-bootstrap CI lower bound > 0 (when CI reliable).
6. **Decision gates:** all six must pass before model complexity increases (`decide`).

Reproduce:

```bash
cd clip-api
python3 scripts/gaming_intelligence_cli.py audit
python3 scripts/gaming_intelligence_cli.py compare eval/gi-gta-label-sheet.csv
python3 scripts/gaming_intelligence_cli.py decide
```
