# Agent 4 — Gaming highlight intelligence (coordinator draft)

**Scope:** Research only. Does **not** retune `clip-api/eval/` labels or replace #101 / #199 / #202 / parity docs.  
**Date:** 2026-11-20.

## Integration rule (preserve existing work)

New detectors write per-second (or event) series into the shared timeline with **weight 0** until precision ≥0.9 on labelled seconds (`verified` acceptance intent in issues #199, #202). Ranking code already skips weight-0 signals on #218 (`verified` architecture audit).

## Signal → model map

| Desired signal | Candidate tech | License (typical) | Fits ticket | Label |
|---|---|---|---|---|
| Gunshots / explosions / sirens / crashes | PANNs / CNN14 AudioSet; YAMNet; BEATs | Apache-2.0 (AudioSet models) | #199 | public-source |
| Laughter / screaming | AudioSet classes + speech emotion heads | varies | #199 / U2 | public-source |
| Kill feed / wasted / busted / banners | EasyOCR or PaddleOCR on HUD crops | Apache-2.0 | #202 + #201 HUD tables | public-source |
| Eliminations / streaks | OCR events + optional template ROIs | — | #202 | hypothesis |
| Chat activity spikes | existing `chat_motion`; official chat APIs later | — | U2 / 4.5 | verified existing motion |
| Facecam emotion / shock | lightweight face AU / valence on webcam box only; no identity store | model-dependent | U2 / Privacy | hypothesis |
| High-intensity gameplay | audio flux + motion energy already partial | — | timeline | verified partial |
| Wins / losses / achievements | HUD OCR + transcript LLM pass (#218 `llm_pass`) | — | U3 / #202 | hypothesis |
| Funny / storytelling | judge v2 + prompt; not a new detector first | API | U4 | verified path |

## Do not double-build

| Existing | Role |
|---|---|
| `signals.audio_rms_db` | loudness |
| `signals.onscreen_chat_motion` | on-screen chat energy |
| #218 `timeline.py` | per-second fusion / standby |
| Eval set v2 | precision/recall truth |
| `docs/parity-opusclip.md` R1 sound/OCR rows | product sequencing |

## Recommended research order (weight 0)

1. Offline PANNs/YAMNet on extracted 16 kHz audio from eval VODs → precision/recall per class (`not measured` here).
2. HUD OCR on measured regions only (#201 dependency) (`not measured`).
3. Only then propose non-zero weights in a money-free understanding PR.

## Quality vs speed

Gaming detectors must not erase the speed track. Prefer inference on **already extracted audio** and **sparse HUD crops**, never a second full decode (`inferred` from SPEC §14 design).
