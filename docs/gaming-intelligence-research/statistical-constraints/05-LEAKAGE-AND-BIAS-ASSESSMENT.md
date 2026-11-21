# 5. Data leakage and selection-bias assessment

## Selection bias

| Source | Bias | Mitigation |
| --- | --- | --- |
| `gi-gta-label-sheet.csv` | Candidates are **ClutchClips proposals** → precision among proposals overstates discovery quality | Add ordinary draws + gap-hunt misses; report proposal-precision separately from discovery recall |
| Wayin sheet | Competitor positives only | Do not use as gaming-quality GT |
| YouNiverse pilot | High/low **reach** matching; metadata-only; 9 creators; one creator dominates | Keep in virality desk research; never as highlight GT |
| Popular published clips (Dataset A) | Success conditioned on distribution, title, audience | Record confounders; never treat views as highlight labels |
| Single VOD (`gta-online-1`) | 30 clips ≠ 30 independent observations | Source-level stats; expand recordings |

## Leakage risks

| Risk | Status | Control |
| --- | --- | --- |
| Using `clutch_score` as GT | Guarded in code (`treats_clutch_score_as_gt: false`) | Labeller warns; compare never uses it as label |
| Training on eval denylist VODs | Denylist checked in | `phase1/fixtures/denylist-eval-ids.json` |
| Tuning on held-out labels | Process rule | Dataset B `held_out_eval` + `validate-splits`; decision gate 6 |
| Blank ratings as negatives | Forbidden | Scorer/compare skip unrated |
| Dual-rater same person | Rejected | `pair_dual_rater_sheets` drops identical rater ids |
| Overlapping source footage across splits | Detectable | `validate-splits` flags recording/streamer leakage |
| Near-duplicate episodes across train/eval | Partially documented | Manual family grouping required when media arrives |

## Overlapping source footage

Known evaluation IDs (must travel as one family): `gta-online-1`, `gta-rp-1`, `zias-iceman`, local fixtures for gta5/gta6/gta-online/valorant/fortnite/forza. Public metadata IDs alone cannot prove disjointness against private footage — maintain private hash denylist when media is available.

## Statistical validity summary

Existing comparison *methods* (fixed pool, blocked until labels, no fabricated GT) are directionally valid. Existing *results* are not statistically claim-ready: n_rated=0, n_sources=1 for the GI sheet, and competitor/reach proxies answer different questions.
