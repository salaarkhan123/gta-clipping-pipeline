# Architecture audit

Read-only audit of ClutchClips on `main` (this checkout) and PR #218 (`release/step2-candidate`). This initiative does not modify PR #218.

Claim labels follow [RESEARCH.md](RESEARCH.md).

## 1. Pipeline overview

**Entry:** `run_pipeline` in [`clip-api/app/pipeline/__init__.py`](../../clip-api/app/pipeline/__init__.py) (`verified`).

| Stage | Timer name(s) | Module | Parallel? |
|---|---|---|---|
| Probe | `probe` | `ff.probe` | no |
| Facecam | `facecam_detect` | `facecam.resolve_facecam` (OpenCV Haar) | no |
| Chat motion | `chat_motion` | `signals.onscreen_chat_motion` | sequential vs audio |
| Audio levels | `audio_signal` | `signals.audio_rms_db` or reused `source_audio.levels` | sequential vs chat |
| Nominate | — | `windows.pick_windows` / `pick_spread`; on #218 also `llm_pass` | LLM pass threaded on #218 |
| Rough ASR | `transcribe_rough` | `transcribe` / `Heard` reuse on #218 | serial candidate loop on `main` |
| Judge | `judge_frames`, `judge_ai` | AI `clip_meta`; frames via ffmpeg | AI: `JUDGE_THREADS=4`; frames serial |
| Variety | — | `variety.pick_distinct` | — |
| Final ASR | `transcribe_final` | caption model on chosen clips | serial |
| Edit | `dead_air` | `edit.silences`, cuts, flash/zoom | per clip |
| Render | `render`, `thumbnail` | `render.render_clip`, thumb | **serial** best-first; `on_clip` progressive |

Worker: [`clip-api/app/worker.py`](../../clip-api/app/worker.py) claims Postgres `jobs` with `FOR UPDATE SKIP LOCKED`. `WORKER_CONCURRENCY` default 1, max 2 (`verified`).

## 2. Technologies already implemented

| Tech | Role | Path | GPU? |
|---|---|---|---|
| ffmpeg / ffprobe | probe, signals, extract, silence, loudness, render, thumbs | `pipeline/ff.py`, `signals.py`, `render.py`, ingest remux | no; **libx264** CPU |
| faster-whisper | captions (`small.en`) + index (`base.en`) | `pipeline/transcribe.py` | **CPU int8 only** (`device="cpu"`) |
| faster-whisper VAD | `vad_filter=True`; speech timestamps for language detect | `transcribe.py` | — |
| yt-dlp | Twitch / Kick / YouTube import | `ingest/platforms.py`, pinned in `requirements.txt` | — |
| OpenCV | facecam Haar | `pipeline/facecam.py` | CPU |
| fastembed CLIP | visual search index | `pipeline/visual.py` | CPU |
| numpy | signals, edit | pipeline | — |
| Anthropic API | judge / titles / virality | `app/ai.py` | API |
| boto3 | Spaces / R2 storage | `app/storage.py` | — |

**Not in production today** (`verified` by `requirements.txt` / grep): PySceneDetect, NVENC, CUDA Whisper, TorchCodec, PyNvVideoCodec, Decord, Remotion, MediaPipe, Streamlink, standalone Silero package. S5 GPU/NVENC remains ticket `#99`.

## 3. PR #218 deltas (frozen contract)

PR #218 head branch `release/step2-candidate`. Read-only via GitHub API (`verified` 2026-11-20). Do not edit that branch.

| Area | What landed | Research implication |
|---|---|---|
| Transcript reuse (U1) | `pipeline/heard.py` `Heard` store; worker loads/saves `transcript.json` + parts; `transcript_reused` count | Cross-job reuse is the repeat-processing path. Respect model tags and first-piece ownership |
| Whole-file ASR | `transcribe_whole` optional, default **off**; `SourceAudio` one-decode path | Config knob for S3 experiments after merge |
| LLM nomination | `llm_pass.py`: ~5 min overlapping chunks, 8 threads, 150s budget; mix ≤⅔ LLM | Latency/cost center separate from ffmpeg |
| Multimodal judge | JPEG frame + timed transcript + timeline → cut/peak; judge-v2 scores | Profile judge × `JUDGE_THREADS` separately |
| Timeline / standby | `timeline.py`; weight-0 signals skipped | Gaming signals (#199/#202) plug in here at weight 0 |
| Preview-first | `render` = `full` \| `preview` \| `none`; `.preview.mp4`; export job | Time-to-first-clip research should assume this product path |
| Thumbnails | Free keyframe+hook (`thumbs.py`); premium AI separate | Free path is CPU ffmpeg |
| Edit / export | `ClipEditDoc`; re-render via export quote/job | Editor UX ≠ pipeline encode |
| Link import | Hardened yt-dlp; consent; span cuts; dedupe | Offline the 10-min north star once file is local |

**Injectable seams for later A/Bs (do not change on #218):** `judge`, `proposer`, `fast_transcriber`, `transcript`/`Heard`, `source_audio`, `timer` (`verified` from PR map).

## 4. Bottlenecks

| Finding | Evidence | Label |
|---|---|---|
| Render ~59–62% of a 2h→10-clip run; ~58 s/clip on droplet | SPEC §10 B / §14 (932.7 s total; render 578 s) | measured |
| Transcribe ~28% (257 s) on candidate windows | SPEC §14 | measured |
| Sequential render loop cannot hit 30–50 clips in 10 min at ~58 s/clip (~29–48 min if linear) | structure + measured rate | inferred |
| On `main`, Clip Maker does not pass `preview=True`; `PREVIEW_SIDE=540` exists in `render.py` but S2 not end-to-end on `main` | `run_pipeline` / `save_clip` vs `preview_key` | verified gap |
| On #218, preview/`none` + export split discovery from full encode | PR #218 render modes | verified |
| Clip Maker on `main` does not pass `source_audio` → repeated audio work (levels + N× `extract_wav` + silences + loudness + render seeks) | `worker.py` vs `stt.extract_audio` | verified pattern; dollar cost inferred |
| Candidate ASR serial; judge frame grabs serial | `__init__.py` loops | verified |
| `chat_motion` dense decode can dominate long VODs | local bench cited in prior swarm notes (42s→279s style slowdown) | measured (prior run); reconfirm `not measured` on this VM |
| Whisper CPU-only; NVENC untried | `device="cpu"`; S5 `#99` | verified |
| Jobs concurrency capped at 2 in one process; no stage queue / render-machine roles yet | `config.py`; SPEC S1/S4 | verified |
| North-star wants parallel previews; code renders one-by-one best-first (progressive via `on_clip`) | SPEC §14 vs loop | verified mismatch |

## 5. Duplicate / unnecessary computation

1. **Audio decoded multiple times per job** when `source_audio` is not supplied (`verified` call sites).
2. **Rough then final ASR** on overlapping windows when dual models are used; reuse via `Heard` on #218 reduces but does not eliminate caption-model passes (`verified`).
3. **Per-clip ffmpeg seeks** for silence, loudness, render, thumb (`verified` pattern).
4. **Chat motion** may decode far more than sparse analysis needs (`inferred` from 2 fps full-span design).
5. **Judge frame extract** separate from any earlier sparse decode (`verified`).

## 6. Concurrency opportunities (hypotheses until measured)

| Opportunity | Today | Hypothesis |
|---|---|---|
| Audio levels ∥ chat motion | sequential | overlap CPU-bound ffmpeg |
| Parallel preview encodes | serial loop | cut wall time ~N with CPU cores / render worker |
| Parallel candidate ASR | serial | limited by single Whisper model lock; need process pool or chunked GPU |
| Partial download → early analysis | full file then pipeline | only if ingest yields a growing local file and stages tolerate incompleteness |
| Stage queue (S1) | single job thread runs full pipeline | analysis worker publishes moments; render workers consume |

## 7. Memory and storage

- Work dir `data/work/job_*` wiped in `finally` (`verified`).
- Clips stored under `clips/{job_id}/`; transcripts `transcripts/{upload_id}.json`; index `index/{upload_id}.npz` (`verified`).
- Full-resolution encodes on `main` inflate storage vs preview-first on #218 (`inferred`).
- Eval videos must stay outside the repo (`clip-api/eval/README.md`).

## 8. Network / download

- yt-dlp options fixed; no cookies, proxies, impersonation, geo bypass (`verified` `ingest/platforms.py`).
- Link import latency is a **separate budget** from “file available on server → clips visible” (SPEC §14) (`verified` wording).
- Partial / streaming acquisition: see Agent 1 draft; constrained by public-only rule.

## 9. Frontend / perceived speed

- Progressive clips via `on_clip` while job `RUNNING` (`verified` worker).
- Editor load &lt;2 s when assets ready: depends on signed URL latency, preview size, and JS bundle; not measured on this VM (`not measured`).
- #218 export-on-demand means the results grid can show previews before 1080p exists (`verified` design).

## 10. What not to replace without evidence

Keep ffmpeg as the render/filter backbone until a side-by-side bench shows a better tool for **our** layouts and ASS captions. Keep faster-whisper until a contender beats it on gaming VODs for both speed and caption quality on the eval set. Keep yt-dlp under the existing ingest policy.

## 11. Seed for recommendation matrix

Highest-confidence speed levers from this audit alone (pending Agent consolidation):

1. Wire and measure preview-first / `render=none`+export (#218 / S2) — large wall-time and TTFC impact (`inferred` from render share).
2. Pass `source_audio` / one-shot extract (S3) — removes duplicate decode (`verified` gap).
3. Parallel preview encodes on a render worker (S4) — attacks serial render (`inferred`).
4. Sparse / cheaper `chat_motion` — attacks known decode cost (`measured` prior).
5. Transcript `Heard` reuse on repeat jobs — already on #218; measure hit rate (`verified` feature; hit rate `not measured`).
6. GPU ASR / NVENC (S5) — `not measured` here; requires owner-approved GPU host.
