> Mirror of Project store gaming-intelligence phase docs. Prior pack and desk research: [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237), multimodal hierarchy [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257), serverless GPU capacity plane [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258). Do not duplicate the #237 pack; link `docs/gaming-intelligence-research/*`.

# Phase 5 — Entertainment rubric (human editorial)

**What this is.** Human dimensions for whether a gaming interval is worth publishing. Scale **0–3** per dimension (integer). Store dimensions separately; optional mean for sheet convenience only.

**What this is not.**  
- **Not** a virality probability.  
- **Not** a forecast of views, shares, or reach.  
- **Not** ground truth for “event occurred” (label events on a separate sheet).  
- **Not** a license to raise production `SCORE_WEIGHTS` or experimental detector weights.

Aligns with judge fields where overlapping (`ranking.SCORES`: hook, payoff, clarity, emotion, pacing) and with MULTIMODAL-ARCHITECTURE’s split: event ≠ editor preference ≠ audience response.

---

## Dimensions (0–3)

| Dimension | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| **Hook** | No reason to keep watching in first ~3 s | Weak tease; unclear stakes | Clear premise or tension early | Immediate stop-scroll premise |
| **Stakes** | Nothing at risk / routine | Mild pressure | Meaningful score/round/social risk | Decisive or irreversible stakes |
| **Payoff** | No landing | Partial / muted landing | Clear outcome or punchline | Strong, earned landing |
| **Reaction** | None / cut before response | Mild audible/visible response | Clear laugh/hype/shock after payoff | Peak reaction tightly timed to payoff |
| **Clarity** | Needs stream context | Partial sense with effort | Newcomer mostly follows | Self-contained for cold viewers |
| **Novelty** | Routine for this title | Slightly unusual | Distinct moment / reversal | Rare or highly surprising for the game |
| **Completeness** | Missing setup or trailing junk dominates | Repairable gaps | Setup→payoff→brief exit intact | Tight story arc; little trim needed |

**Composite (optional):** mean of the seven scores. Do **not** publish as “viral %”. Do **not** compare to platform view counts.

---

## Map to existing judge sub-scores

| Rubric | Judge sub-score overlap | Gap |
| --- | --- | --- |
| Hook | `hook` | Same intent; human rates source interval, judge rates proposed cut |
| Payoff | `payoff` | Same |
| Clarity | `clarity` | Same |
| Reaction | part of `emotion` / payoff landing | Rubric isolates onset vs payoff |
| Stakes | weak / implicit in emotion | **Human-only** until a stakes feature exists |
| Novelty | none dedicated | **Human-only** |
| Completeness | related to `pacing` + boundaries | Rubric includes setup/exit; pacing ≠ completeness |

Use rubric for **eval sheets**. Keep judge outputs as system predictions to score **against** human labels — never as GT.

---

## Labeling instructions (humans)

1. **Blind to outcomes.** Do not show Clutch scores, ranks, competitor picks, or view counts while rating.  
2. **Rate the source interval** as rendered for review (fixed aspect, no branded overlays that identify the system).  
3. **One rater primary; dual-rate ≥20%** for agreement (exact + adjacent). Adjudicate disagreements before unblinding systems.  
4. **Separate event labels** (kill, goal, siren, …) on second-level / episode sheets — do not overload this rubric.  
5. **Missing channels.** If no facecam / chat / HUD, mark missingness; do not invent reaction.  
6. **Game-relative novelty.** Score novelty within title/mode, not vs all media.  
7. **No view forecasting.** If tempted to predict performance, stop — use Phase 7 desk rules instead.  
8. **Consent.** Only permissioned eval media; evaluation-only denylist for training (PHASE1-FINDINGS / DATASET-PLAN).

### Sheet columns (minimum)

`source_id, t0, t1, hook, stakes, payoff, reaction, clarity, novelty, completeness, notes, rater_id, rated_at`

Gains for ranking metrics (EVALUATION-FRAMEWORK): map 3→gain 3, 2→1, 0–1→0 for NDCG unless a newer protocol is preregistered.
