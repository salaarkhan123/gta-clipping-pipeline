> Mirror of Project store gaming-intelligence phase docs. Prior pack and desk research: [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237), multimodal hierarchy [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257), serverless GPU capacity plane [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258). Do not duplicate the #237 pack; link `docs/gaming-intelligence-research/*`.

# Phase 7 — Virality desk research

**Reuse.** [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) `VIRALITY-RESEARCH.md` (primary). No new cohort run in this phase. **No production virality coefficient.**

---

## Desk finding (116 pairs)

From fixed YouNiverse English metadata prefix (668,552 complete records; input SHA `6813f25b…`; cohort SHA `4b2b3064…`):

| Measure | Result |
| --- | --- |
| Matched pairs | **116** high/low reach within channel × game family × year |
| Creators | 9 (one creator = 44 pairs — heavy concentration) |
| Title action/highlight markers | Cases 40/116 (34%); controls 49/116 (42%) |
| Paired marker cells | Both 34 · neither 61 · case-only 6 · control-only 15 |

**Conclusion.** A printed title tag alone gives **no basis for a positive ranking weight**. Controls are less successful *relative to peers*, not “flops” in absolute terms. Archive is pre-Shorts (2019); no media was watched; lexical filters can admit commentary.

---

## Separate outcomes (do not collapse)

| Outcome | Meaning | Use in ClutchClips |
| --- | --- | --- |
| **Editor rating** | Human publishability (Phase 5 rubric) | Primary for selection eval / NDCG |
| **Retention** | Share of qualified starts reaching payoff / platform retention curve | Only with permissioned analytics + documented denominators |
| **Views / reach** | Platform counts at a defined age | Never as sole ranking target; era/platform/definition must travel with the number |

Wu et al. (Beyond Views): watch % depends strongly on duration; channel history carries information — **literature**, not a ClutchClips coefficient. YouTube Shorts view definition changed 2025-03-31 — keep metric definition with every observation.

---

## Explicit non-products

- No `virality` probability in the API or UI beyond existing editorial sub-scores.  
- No learned engagement weight in production ranking from this desk study.  
- No training on evaluation-only / denylisted IDs.  
- Do not treat judge `virality` JSON fields as view forecasts (product copy: AI rating / sub-scores).

---

## Next experiments (permissioned only)

Require owner OK + rights-cleared analytics before any of:

1. Fixed-age day-7 retention / completion with exposure denominators.  
2. Creator-held-out models: metadata baseline vs baseline + one frozen feature family.  
3. Paired concordance / group bootstrap by creator — not pooled naive accuracy.  
4. Randomized hook/caption/boundary variants **within** creators for causal editing claims.  
5. Never mix raw TikTok/YouTube/Twitch view counts as identical units.

Until then: keep engagement research offline; selection quality = editor labels + event P/R only.
