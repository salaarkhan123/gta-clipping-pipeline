# Repository evaluation

Claim labels follow [RESEARCH.md](RESEARCH.md). Detailed drafts: [drafts/](drafts/).

## Method

Activity, license, dependencies, hardware, overlap with ClutchClips, production suitability. Do not replace existing pieces without measured superiority on our gaming workloads.

## Summary matrix

| Technology | License (dated read) | In CC today | Production fit | Recommendation |
|---|---|---|---|---|
| FFmpeg | LGPL/GPL components; we call system binary | yes | high | keep; add hwaccel behind S5 bench |
| faster-whisper / CTranslate2 | MIT (`public-source` 2026-11-20) | yes CPU int8 | high | keep; try batched/GPU only after measured win |
| yt-dlp | Unlicense (`public-source`) | yes pinned | high under our locked options | keep; tune fragment concurrency carefully |
| OpenCV headless | Apache-2.0 | yes Haar facecam | high | keep until MediaPipe measured better |
| fastembed CLIP | Apache-2.0 | yes | medium | keep for search |
| TorchCodec | BSD-3; CUDA build needs NVIDIA terms (`public-source` 2026-11-20) | no | medium (needs torch) | evaluate for sparse decode on GPU host only |
| PyNvVideoCodec | MIT wrapper; Video Codec SDK EULA underneath (`public-source`) | no | medium–high on NVIDIA | S5 candidate; patent/codec diligence |
| NVIDIA AV-for-AI playbook | sample/docs; follow NVIDIA notices | no | reference only | patterns for NVDEC, not a dependency |
| Decord | Apache-2.0 | no | medium; build friction | optional sparse decode experiment |
| WhisperX | BSD-ish + heavy torch/pyannote deps (`public-source`) | no | low for our CPU image | do not replace faster-whisper without eval proof |
| Silero VAD | MIT | via faster-whisper | high as-is | standalone only if pre-segment helps measured |
| PySceneDetect | BSD-3 | no (#218 timeline covers scenes) | medium | compare to timeline scene signal; do not dual-run |
| MediaPipe | Apache-2.0 | no | medium | facecam alternative; measure vs Haar |
| Remotion | Remotion license (company + commons) | no | **poor** for server clip worker | reject for core pipeline (`inferred` Agent 5) |
| Streamlink | BSD-2 | no | low for VOD + our no-browser rule | skip for VOD; live is out of scope now |
| ClipGen | check repo LICENSE before use | no | research reference | study ideas only; no copy |
| PANNs / YAMNet | Apache-2.0 (typical AudioSet models) | no | medium local audio events | feed #199 at weight 0 |
| PaddleOCR / EasyOCR | Apache-2.0 | no | medium | feed #202 HUD OCR at weight 0 |

## In production deep notes

### yt-dlp — Agent 1

- Pin `yt-dlp==2026.10.26` (`verified` requirements).
- Locked options: no cookies, proxy empty, no impersonation, allowlist extractors, `concurrent_fragment_downloads: 1` (`verified` `platforms.py`).
- Import completes **before** clip job; no overlap today (`verified`).
- Levers inside policy: safer fragment concurrency, optional timeframe fetch, HLS grow-file analysis (`hypothesis`). See [drafts/agent1-ingestion.md](drafts/agent1-ingestion.md).

### faster-whisper — Agent 3

- CPU int8 `small.en` / `base.en` (`verified`).
- Historical 257 s of 932.7 s on 2h→10 clips (`measured` SPEC).
- WhisperX adds alignment/diarization cost; not a drop-in speed win (`public-source` + `inferred`).
- `Heard` on #218 is the reuse path (`verified`). See [drafts/agent3-transcription.md](drafts/agent3-transcription.md).

### Remotion — Agent 5

Unfit to replace ffmpeg layouts/ASS in the Python worker: Chromium cost, duplicate graph, license/ops (`inferred`). See [drafts/agent5-render.md](drafts/agent5-render.md).

## Independently discovered (beyond the brief)

| Item | Why interesting | Label |
|---|---|---|
| FFmpeg `skip_frame` / bitstream filters | Already used for VP9 keyframes in #218 history | verified prior |
| CTranslate2 `BatchedInferencePipeline` | Potential ASR throughput without WhisperX | public-source |
| N_m3u8DL-RE / twitch-dl patterns | Partial HLS; many assume evasion → **reject** under CLAUDE.md | public-source |
| AudioSet ontology + PANNs | Named SFX for #199 | public-source |
| EasyOCR / PaddleOCR | Kill-feed text for #202 | public-source |
| DigitalOcean CPU-optimized / GPU droplets | Setup B / S5 pricing inputs | public-source |

## Do-not-adopt without measurement

1. Replacing ffmpeg with TorchCodec/Decord for **rendering** (layouts/ASS still need ffmpeg) (`inferred`).
2. Replacing faster-whisper with WhisperX for **speed** (`inferred`).
3. Streamlink for Twitch VOD under no-impersonation rules (`public-source` conflict risk).
4. Remotion for batch preview encodes (`inferred`).
