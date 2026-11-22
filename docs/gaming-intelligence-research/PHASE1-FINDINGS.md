# Phase 1 findings — evaluation and baseline

**Status:** Phase 1 engineering complete on PR #237. Human-labelled gaming quality scores are still blocked on owner footage and ratings. No production weights changed. No merge, deploy or paid infrastructure requested.

**Pinned control:** production selector merge `8e0d9bad` · research pin file [`phase1/baseline-pin.json`](phase1/baseline-pin.json) · harness `clip-api/scripts/gaming_phase1/`.

## What Phase 1 delivered

| Codex item (1A–1D) | Result on this branch |
|---|---|
| **1A Rights / label manifest** | Public schemas + synthetic manifest + evaluation denylist. Legacy eval VOD IDs are marked `evaluation_only` / `excluded_from_training`. Blind dual-annotator pilot **not started** (no rated media on this host). |
| **1B Offline replay / baseline** | B0 harness freezes `WEIGHTS`, empty `HUD_REGIONS`, and reproduces selection with fingerprint + paid-call count `0`. Determinism verified on the synthetic 40 s fixture. |
| **1C Named audio** | Production audio RMS + flux + bursts inventoried and timed. YAMNet (#231) is **not** on this head; real per-class TP/FP/FN deferred until weight-zero adapter + labelled seconds exist. |
| **1D HUD** | Caption geometry boxes exist for six games; `HUD_REGIONS={}` and no OCR text labels. Exact-match ≥0.90 **not measurable** yet. |

## Evaluation dataset census (no fabricated ratings)

| Asset | Count | Rated / labelled |
|---|---:|---:|
| `eval/labels-v2.csv` | 30 rows · 1 VOD (`gta-online-1`) | **0** |
| `eval/benchmark-2h-labels.csv` | 46 | **0** |
| `eval/wayin-zias-iceman.csv` | 15 (competitor proxies, all 3) | 15 |
| Caption geometry (`caption_eval_boxes.json`) | 6 videos | boxes only, not clip worthiness |
| `HUD_REGIONS` | 0 games | — |
| Private multigame sheets (Codex audit) | ~55 rows across 6 games | 0 (media not on this agent) |

Historical Wayin overlap on the saved reaction run remains **7/15**; at K=20 the rated precision interval is still **30–100%** because 14 of 20 clips are unrated. That is a competitor-overlap reference, not gaming quality.

## Existing signal assessment

| Signal | Production weight | Observation |
|---|---:|---|
| Chat motion | 1.0 | Off unless user sets a chat region (default `none`). Edge-change proxy; overlays/false scrolls possible. |
| Audio RMS | 0.7 | Active. Dominates nomination on loud action; misses quiet narrative payoffs. |
| Audio flux | 0.35 | Active. Helps impacts/shouts; still unnamed classes. |
| Audio bursts | 0.35 | Active. Laughter-rhythm proxy; routine combat can pulse similarly. |
| Scene change | **0.0** | Skipped in production (no decode). Shadow keyframe timing is available in the harness; Codex’s 120 s probe showed **8.9–15.6 s** visual decode for reduced 1 fps frames — argue for shared/sparse decode, not for enabling scene blindly. |
| Transcript / judge | optional | Not exercised in B0. Quiet GTA RP depends on this route; needs B1 with cached ASR/judge. |
| Named sounds (YAMNet) | experimental 0 | Adapter on Cursor #231 / perf-integration; **do not enable**. |
| HUD OCR | experimental 0 | Scaffold on #232; empty regions; **do not enable**. |

### Misses, false positives, overhead (evidence-bounded)

- **Missed highlights (expected failure modes, not yet counted on rated gaming VODs):** quiet dialogue reversals; spectator-attributed kills; Rocket League replays double-counting goals; endgame builds without loud audio.
- **False-positive modes already suggested by prior work:** GTA colour/HUD heuristics returned **0/8** true events in top detections (#154 history); loud routine combat and chat-band scrolling can nominate filler.
- **Unnecessary overhead today:** continuous full-res visual decode is not required for B0; scene weight is already 0. Visual probes remain expensive relative to audio. Keep experimental detectors off the ranking path and share decode with Cursor’s performance work (#234) when measuring them.

## Metrics locked for later rated runs

Defined in [`EVALUATION-FRAMEWORK.md`](EVALUATION-FRAMEWORK.md) and implemented for offline use in `scripts/gaming_phase1/metrics.py`:

- Product sheet metrics via unchanged `eval_clips.py` (P@20/40 ranges, recall of 3s, unrated bounds).
- Event precision/recall/F1 with ±1 s onset tolerance.
- Ranking: **NDCG@5** primary (gains 3/1/0), plus P/R@5/20/40.
- Boundaries: temporal IoU at 0.3/0.5/0.7, median start/end absolute error.
- Cost: wall s / source hour, peak RSS, decode counts, paid calls (B0 must stay 0).

Proposed enablement gate (unchanged from Codex): **≥0.03 NDCG@5** vs B1 with paired 95% lower bound >0, and great-event R@20 non-inferior within −0.02, plus cost/time approval.

## Tests run

```text
cd clip-api && python3 -m pytest -q tests/test_gaming_phase1.py tests/test_eval_set.py tests/test_eval_set_v2.py
# 45 passed
python3 scripts/gaming_phase1_cli.py pin
python3 scripts/gaming_phase1_cli.py inventory
python3 scripts/eval_clips.py eval/wayin-zias-iceman.csv eval/runs/zias-iceman.staging-347ca2f.json
# historical 7/15 Wayin overlap; @20 precision range 30%–100%
```

Harness tests cover pin integrity, B0 determinism on the synthetic burst fixture, signal inventory, metrics helpers and the “zero ratings” inventory invariant. Aggregate JSON (no media) is under [`phase1/fixtures/`](phase1/fixtures/).

## Owner asks (required before Phase 2 claims)

1. **Rate `labels-v2` for `gta-online-1`** (30 rows) in `eval/labeller.html`, then gap-hunt ≥3 owner-added moments.
2. **Supply** `~/ClutchClips-eval/gta-rp-1` (held out) and one non-GTA VOD (Valorant/Fortnite/…); run `label_moments.py select/add` and rate them.
3. **Rate** the private multigame candidate sheets (or confirm paths + consent) so six-title coverage is real, not blank.
4. **Per-second sound labels** on six evaluation VODs for gunshot, crash, explosion, siren, scream, laughter (Phase 1C).
5. **HUD text labels:** ≥20 measured readable frames per supported game with expected strings (#201/#202), separate from caption-avoid boxes.
6. **Consent/use records** for each source (playback, annotation, embeddings, training, external models, redistribution).
7. **Do not approve** GPU rental, vendor paid runs, or nonzero experimental weights until the above exist and Phase 1C/1D pass their precision floors.

## Decision requested

Approve remaining Phase 1 **human labelling** (items 1–6). Hold Phase 2 implementation (game-specific detectors) until those labels land. Keep PR #234 as the sole owner of performance/adapter integration; this branch only shadows and evaluates.
