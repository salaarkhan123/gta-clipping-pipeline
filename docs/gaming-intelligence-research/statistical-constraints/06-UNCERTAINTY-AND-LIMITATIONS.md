# 6. Statistical uncertainty and limitations

## Sample size (current)

| Unit | n | Implication |
| --- | ---: | --- |
| Rated GI clips | 0 | All human-quality metrics blocked |
| Independent source videos on GI sheet | 1 | Even after rating, clips-as-iid CIs would be invalid |
| Dual-rater pairs | 0 | Reliability unknown |
| Games with labelled Dataset B | 0 | No multi-title generalization |

## Uncertainty method (when data exists)

1. Compute metric per **source recording**.
2. Bootstrap those source-level values (`n_boot=2000`, fixed seed).
3. Report mean + percentile CI only if `n_sources ≥ 5`.
4. Below that: descriptive mean only; message explains insufficiency.
5. Paired deltas: same sources across arms; bootstrap the per-source differences.
6. **No p-values** when `n_sources < 8`.

## Statistical vs practical significance

- Statistical significance without practical lift is not a ship gate.
- Practical threshold used in harness: mean ΔP@5 ≥ 0.05 **and** source-bootstrap CI lower bound > 0 (when CI is reliable).
- Producing more clips is not an improvement metric.

## Known limitations (active)

1. Proposal-only candidate sheets cannot measure discovery recall.
2. Single-streamer / single-VOD pilots do not generalize.
3. Incomplete ratings produce ranges (e.g. historical 30–100%), not confidence intervals.
4. CPU hook microbench ≠ full pipeline cost.
5. GPU cost figures are list-price estimates.
6. Dataset A engagement, if collected later, remains confounded by audience size, platform, date, and editing.
7. Virality outcomes are out of scope for highlight-quality claims.

## What would make uncertainty credible

- ≥5 (prefer ≥8) independent permissioned source recordings with complete labels
- Dual-rater reliability gate passed
- Held-out streamer-separated evaluation untouched during development
- Explicit reporting of n, CI method, and limitations beside every metric table
