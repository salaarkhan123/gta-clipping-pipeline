# Integration roadmap

Research recommendations only. **No implementation until the owner reviews this pack.**

Claim labels follow [RESEARCH.md](RESEARCH.md). Aligns with existing tickets (S0–S5, U1–U7, #199, #202) rather than a shadow backlog.

## Recommendation matrix

Scores are coordinator judgments from evidence in this directory. Speed/quality columns use: **High / Med / Low / Unknown**. Complexity: **S / M / L** (PR-sized). Cost: relative infra $. Risk: production/license. Customer impact: what streamers notice.

| ID | Improvement | Speed | Highlight quality | Complexity | Infra cost | License | Prod risk | Customer impact | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| R1 | Ship/measure preview-first + export-on-demand (#218 / S2) | High | None | S–M | Lower encode $ | n/a | Low | TTFC, cheaper rejects | render ~60% of job (`measured`); #218 modes (`verified`) |
| R2 | Pass `source_audio` / one-shot 16 kHz extract (S3) | Med | None | S | Low | n/a | Low | Slightly faster jobs | duplicate decode (`verified`) |
| R3 | Parallel preview encodes (S2/S4) | High | None | M | Med (CPU cores) | n/a | Med | Many clips sooner | serial loop (`verified`); M4 8-parallel (`measured` prior) |
| R4 | Cheaper / sparser `chat_motion` | Med | Low risk if sparse | S | Low | n/a | Low | Faster long VODs | 6.5× local blow-up (`measured` prior) |
| R5 | Measure + default `Heard` reuse paths (U1) | Med on repeats | None | S | Low | n/a | Low | Instant re-runs | `heard.py` (`verified` #218) |
| R6 | Stage queue / progressive moments before render (S1) | High perceived | None | M | Low–Med | n/a | Med | First moments &lt;90s goal | SPEC design; partial today |
| R7 | Dedicated render worker (S4 / setup B) | High | None | M | Med fixed $ | n/a | Med | Export SLO | SPEC setup B |
| R8 | S5 NVENC/NVDEC A/B on approved GPU | High? | None | M | High fixed $ | SDK EULA | Med–High | Faster exports | `not measured` |
| R9 | faster-whisper CUDA / batched ASR | Med? | Must not drop | M | Med | MIT | Med | Faster jobs | replace only if measured |
| R10 | Hosted ASR (#167) | Med | TBD | M | $/min | vendor ToS | Med (privacy) | Speed vs Terms | SPEC |
| R11 | Weight-0 sound events PANNs/YAMNet (#199) | Low (CPU) | High potential | M | Low–Med image | Apache | Med | Better shootouts | Agent 4 |
| R12 | Weight-0 HUD OCR (#202) | Low–Med decode | High potential | M | Low–Med | Apache | Med | Kill-feed clips | Agent 4 |
| R13 | Raise yt-dlp fragment concurrency carefully | Low–Med ingest | None | S | Low | Unlicense | Med (rate limits) | Faster imports | Agent 1; keep no-evasion |
| R14 | Overlap HLS download with early analysis | Med TTFC | None | L | Low | — | High eng | First clips sooner | hypothesis; policy OK if no evasion |
| R15 | WhisperX replace | Unknown | Align+/diarize | L | High image | deps gated | High | Unclear | **reject until measured win** |
| R16 | Remotion server render | Neg | — | L | High | Remotion | High | — | **reject** (Agent 5) |
| R17 | Streamlink for VOD | Neg/None | — | M | Low | BSD | High ToS | — | **reject** under rules |

## Prioritized independently testable PRs

Start after owner approval. Each PR ends with `job_timings.py` and/or eval metrics. Do not sacrifice highlight quality for speed.

### Wave A — highest impact / lowest risk (CPU, no new deps)

1. **PR-A1 (S2 measure):** On staging/#218, run 2h benchmark with `render=preview` vs `full`; report TTFC and total with `job_timings.py`.
2. **PR-A2 (S3):** Wire Clip Maker `source_audio=extract_audio(...)`; assert fewer ffmpeg audio spawns in tests; timings before/after.
3. **PR-A3 (chat_motion):** Sparse/keyframe sampling path behind flag; byte-identical candidates at weight parity; timings on 2h.
4. **PR-A4 (U1):** Report `transcript_reused` rates on repeat jobs; document ops playbook (no behavior change required).

### Wave B — concurrency / workers

5. **PR-B1 (S2/S4):** Parallel preview encodes capped by CPU count; correctness tests on clip order + `on_clip`.
6. **PR-B2 (S1):** Publish moments/`render=none` metadata before encodes; UI already progressive.
7. **PR-B3 (S4):** Document + optional compose service for render worker (owner provisions hardware).

### Wave C — understanding (quality), weight 0

8. **PR-C1 (#199):** Local sound-event tensor on existing WAV; weight 0; precision/recall sheet; no ranking change.
9. **PR-C2 (#202):** OCR on measured HUD ROIs only; weight 0; exact-match rate; no ranking change until ≥0.9.

### Wave D — GPU (owner OK required)

10. **PR-D1 (S5):** NVENC vs libx264 on identical clips; NVDEC sparse extract; cost table; go/no-go.

### Explicit non-goals until evidence

- Replacing ffmpeg, faster-whisper, or yt-dlp wholesale.
- Remotion in the worker.
- Streamlink / evasion for blocked sites.
- Merging research branch into `main` as product code.
- Touching PR #218 itself.

## Target achievability (research conclusion)

| Target | Verdict on current evidence |
|---|---|
| 2h &lt; 5 min | **Not achievable** on today’s 4-vCPU serial full-render path (`inferred` from 932.7 s / 10 clips). **Possibly achievable** with preview-first + parallel previews + stronger render host/GPU after measured Waves A/B/D. |
| First clip &lt; 90 s | **Plausible** with #218 preview/`none` + early callback; **not measured** this run. |
| Clip render &lt; 2 min | **Yes** for typical short clips on droplet (~58 s full); SPEC 30 s export needs Wave B/D. |
| Editor &lt; 2 s ready | **Plausible**; measure in web QA. |
| Reuse transcripts/signals | **Ready on #218**; measure hit rate. |
| Highlight improvement | **Only via eval-gated weight-0→weight PRs** (C1/C2). |
| Sustainable cost | **Requires** preview-first + export discipline; GPU only if $/h wins. |

## Stop gate

This research pack is complete when the owner has reviewed the eight docs and approved which Wave A–D PRs to schedule. Implementation is a separate initiative on product branches, never on PR #218’s release branch mid-flight.
