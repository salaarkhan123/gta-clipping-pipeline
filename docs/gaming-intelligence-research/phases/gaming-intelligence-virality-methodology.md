<!-- Mirrors store docs/gaming-intelligence-virality-methodology.md -->

# Virality research methodology (separate from highlight quality)

**Hard rules.** Highlight quality ≠ virality. No virality percentages. No claim of predicting views without independent engagement data. Extends #237 `VIRALITY-RESEARCH.md` (116 YouNiverse pairs → **no** title-marker boost).

---

## Three separate outcomes

| Outcome | What it answers | Data needed |
| --- | --- | --- |
| **Highlight quality** | Would an editor publish this cut? | Human rubric (this PR’s sheet) |
| **Retention / completion** | Do viewers stay? | Platform analytics with creator consent |
| **Reach / views** | Did it travel? | Matched-cohort engagement with exposure controls |

Never collapse these into one “virality score” shown as a probability.

---

## Candidate content features (observational)

| Feature | How to measure (research) | Notes |
| --- | --- | --- |
| Opening hook strength | Human 1–5 on first 3 s; optional judge `hook` | Editorial, not views |
| Time to main highlight | Seconds from clip start to peak event | Shorter ≠ always better |
| Audio excitement | RMS/flux/bursts / optional YAMNet laughter | Game mix confounds |
| Speech / reaction intensity | Transcript exclamations; facecam motion | Permission for face features |
| Gameplay event significance | Title-specific event tags | Per-game |
| Visual clarity | Human `context_1_5`; optional sharpness | Overlay clutter |
| Context required | Human `context_1_5` | High context → worse cold traffic |
| Clip duration | end−start | Platform norms differ |
| Pacing | Judge `pacing` / silence cuts | Not engagement |

---

## Evaluation protocol (when engagement data exists)

1. Creator-authorized posts only; log consent.
2. Match on creator, game family, age-at-measure, duration band.
3. Pre-register features; hold out creators and time windows.
4. Report effect sizes with uncertainty; null results kept.
5. Product copy: “AI rating” / sub-scores — **never** “X% chance to go viral”.

---

## What we know now

| Evidence | Conclusion |
| --- | --- |
| YouNiverse 116 pairs (#237) | Action words in titles **not** associated with higher reach in that archive |
| No Shorts-era matched cohort here | Cannot calibrate a modern Shorts/TikTok model |
| GI sheet | Quality labels pending — prerequisite before correlating with engagement |

**Next (owner):** supply consented post analytics for a fixed set of clips, or approve a new permissioned study design. No scrape / TOS bypass.
