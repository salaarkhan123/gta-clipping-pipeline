# 7. Model complexity and performance recommendations

## Current recommendation

**Do not introduce LLMs, CV models, GPU inference, or additional neural networks for production highlight ranking.**  
**Do not raise GI family weights above 0.**  
**Do not enable GI in production.**

Decision gates (all failing today): [artifacts/decision-gates.json](artifacts/decision-gates.json)

```bash
python3 scripts/gaming_intelligence_cli.py decide
```

## Complexity ladder (evidence-gated)

| Tier | Allowed now? | Condition to enter |
| --- | --- | --- |
| 0 — Baseline ClutchClips | Yes (production) | — |
| 1 — Interpretable CPU features (RMS/flux already in baseline; GI hook weight-0) | Research only | Labels + baseline measured |
| 2 — Lightweight named-sound / HUD features at weight 0 offline | Offline eval only | Per-class precision floor on labelled seconds/frames |
| 3 — Nonzero GI weights on held-out | **No** | Gates 1–6 pass; Δ metric meaningful vs uncertainty; cost OK |
| 4 — Larger models / GPU | **No** | Tier 3 evidence + owner spend approval + measured $/source-hour |

## Performance stance

- Prefer interpretable, lightweight features first.
- Any proposed model must beat baseline **A** on held-out data with identical pools (ranking) or identical sources (discovery).
- Measure incremental runtime and peak memory on the same VODs.
- Hook overhead today is cheap; that is **not** a quality argument.

## Virality

Keep virality research separate. Do not claim human quality scores predict views/likes/retention without independent outcome data and confounder accounting. Never invent virality probabilities.
