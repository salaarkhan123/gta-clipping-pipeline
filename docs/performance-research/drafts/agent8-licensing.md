# Agent 8 — Licensing and verification (coordinator draft)

**Date reads:** 2026-11-20. Labels: mostly `public-source`.

## License matrix

| Component | License | SaaS risk notes |
|---|---|---|
| FFmpeg (system) | LGPL/GPL per build | Keep calling external binary; avoid static GPL link into proprietary code without counsel |
| faster-whisper | MIT | OK |
| CTranslate2 | MIT | OK |
| yt-dlp | Unlicense | OK for code; **not** a content license; Twitch/YouTube ToS still bind |
| OpenCV | Apache-2.0 | OK |
| numpy / Pillow | BSD-style | OK |
| fastembed | Apache-2.0 | OK |
| TorchCodec | BSD-3 + NVIDIA terms if CUDA wheel | Review NVIDIA notices before CUDA image |
| PyNvVideoCodec | MIT + Video Codec SDK EULA | Patent/third-party codec responsibility on licensee |
| WhisperX | Project license + torch/pyannote deps | pyannote/speaker models often gated; check before ship |
| Decord | Apache-2.0 | OK |
| PySceneDetect | BSD-3 | OK |
| Silero VAD | MIT | OK |
| MediaPipe | Apache-2.0 | OK |
| Remotion | Remotion company license | Poor fit; license not the only blocker |
| Streamlink | BSD-2 | OK code; ToS/client-integrity issues for Twitch |
| NVIDIA playbook samples | NVIDIA sample terms | Reference; do not paste into product casually |
| PANNs / YAMNet | Apache-2.0 typical | Confirm checkpoint license file before bundle |
| EasyOCR / PaddleOCR | Apache-2.0 | OK |

## Integration risks

| Risk | Severity | Mitigation |
|---|---|---|
| CUDA blobs in default CPU image | high ops | GPU-only worker image after S5 |
| WhisperX/pyannote model gates | medium | stay on faster-whisper |
| Codec patents with NVENC redistribution | medium | counsel + SDK EULA checklist |
| yt-dlp ToS / platform bans | high product | keep no-evasion policy; upload fallback |
| Copying competitor UI/copy | high legal | PARITY rules already forbid |

## Falsifiability checks for other agents

| Claim pattern | Falsify by |
|---|---|
| "X is 10× faster" | Same VOD, same host, `job_timings.py` before/after |
| "Replace ffmpeg" | Must render our layouts+ASS with equal quality |
| "WhisperX is faster" | Wall time + caption quality on eval clips |
| "Wayin does Y internally" | Only accept if public doc says so; else hypothesis |
| "GPU pays for itself" | $/video-hour including idle GPU |

## Production risk ranking (research adoption)

1. **Low:** preview-first wiring, `source_audio` one-shot, Heard reuse measurement, weight-0 signal scaffolding.
2. **Medium:** fragment concurrency, hosted ASR, OCR/sound models in image.
3. **High:** CUDA in prod image, NVENC money path, any ingest evasion (forbidden).
