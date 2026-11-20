# GPU bench recommendations (S5 / Wave D1)

Scaffolding for issue #99 and research PR-D1. **No paid GPU is provisioned in this PR.**
CPU `libx264` + faster-whisper `device=cpu` / `int8` remain the production defaults.

Claim labels: `measured`, `verified`, `inferred`, `hypothesis`, `public-source`, `not measured`.

## What this PR ships

| Piece | Path | Role |
|---|---|---|
| A/B harness | `clip-api/scripts/bench_nvenc.py` | Times libx264 vs `h264_nvenc` on the same window; prints `skipped: no NVENC` and exits 0 on CPU-only hosts |
| Plug-in helpers | `clip-api/app/pipeline/gpu.py` | Probe NVENC / NVDEC / CUDA Whisper; build encoder and Whisper kwargs |
| Config flags (off) | `VIDEO_ENCODER`, `WHISPER_DEVICE`, `NVDEC` | Defaults `libx264` / `cpu` / `false` |
| Render path | `render_clip` | Still hardcodes `libx264` (comment marks the future plug-in) |
| Whisper path | `FasterWhisperTranscriber(device=...)` | Default `cpu`; worker reads `Settings.whisper_device` |

## How to run the harness (owner GPU host only)

```bash
cd clip-api
python scripts/bench_nvenc.py                  # synthetic 720p lavfi source
python scripts/bench_nvenc.py /path/to.mp4 --seconds 5 --runs 3
python scripts/bench_nvenc.py --nvdec-probe --whisper-probe
```

JSON always includes a `libx264` timing when ffmpeg works. The `nvenc` field is filled only when
`probe_nvenc()` succeeds. This document does **not** contain fabricated GPU milliseconds.

## Infra options (owner provisions; agents do not)

Public list prices change; treat the figures below as orientation only (`public-source` at
research time) and re-check the vendor page before buying.

| Option | Fit | Notes |
|---|---|---|
| Stay on CPU droplet + optional 16-vCPU render worker (SPEC setup B) | Default | No NVIDIA driver, no CUDA image, no NVENC EULA surface |
| On-demand NVIDIA GPU droplet / VM (Ada-class or similar with NVENC) | Bench host | Owner starts it, runs `bench_nvenc.py`, stops it. Do not leave idle |
| Always-on GPU worker | Only after go | Needs measured $/job win vs CPU parallel previews (Wave B) |

Research pack context: `docs/performance-research/GPU-INFRASTRUCTURE.md` on the research branch
(PR #222). Judgment there: keep ffmpeg; do not pull PyNvVideoCodec / TorchCodec / Decord into
the slim image until a real-graph bench wins (`inferred` / `not measured` for speed).

## Go / no-go criteria

Run the harness on an **owner-provided** GPU with the same filter shape the product uses
(vertical scale/crop, captions when enabled). Then decide:

### Go (consider wiring `VIDEO_ENCODER=h264_nvenc` on a GPU worker only)

1. NVENC wall time for a typical export window is **at least 2× faster** than libx264
   `veryfast` CRF 20 on that same host (`measured` on the bench JSON `speedup_x264_over_nvenc`).
2. Side-by-side frames look acceptable for preview and for full export (owner visual check).
   NVENC is bitrate/preset based — it is not a free CRF swap (`public-source`).
3. Cost: GPU $/hour × job minutes beats the CPU path after Wave A/B wins are already in
   (preview-first, parallel previews). If CPU parallel already hits the 10-minute preview goal,
   GPU is optional (`inferred`).
4. Driver + ffmpeg in the **GPU image** load `h264_nvenc` cleanly; CPU image stays CUDA-free.
5. Failure mode: missing GPU falls back to libx264 or fails the job with a refund — never hangs.

### No-go (keep CPU defaults)

1. Harness reports `skipped: no NVENC` on the candidate host (no driver / no encoder).
2. Speedup &lt; 2× on the real graph, or quality is visibly worse than libx264 CRF 20.
3. Caption / blur path forces `hwdownload` so often that NVENC gains disappear (`hypothesis`
   until measured with ASS burn-in).
4. Only vendor blog FPS numbers exist — those are `not measured` for ClutchClips and do not
   decide S5.

### NVDEC (optional, separate gate)

- Plug-in: `gpu.nvdec_input_args(True)` → `-hwaccel cuda`.
- **Not wired** into `render_clip` in this PR: crop, boxblur, and `ass` need CPU frames.
- Go only if a sparse-decode or long chat-motion bench shows a net win **after** download
  into the CPU filter graph (`not measured` here).

### CUDA faster-whisper (optional, separate gate)

- Plug-in: `Settings.whisper_device=cuda` → `whisper_model_kwargs` → `device=cuda`,
  `compute_type=float16`.
- Go only if word-error rate on the eval set does not regress and stage `transcribe` /
  `transcribe_whole` wall time drops enough to matter after one-shot audio (Wave A2).
- No-go if the CUDA ctranslate2 stack is absent (`skipped: no CUDA Whisper`) or quality drops.

## Cost table (fill after a real bench)

Leave cells blank until `bench_nvenc.py` has been run on the paid host. Do not invent numbers.

| Workload | Host | libx264 s | NVENC s | Speedup | $/job CPU | $/job GPU | Decision |
|---|---|---|---|---|---|---|---|
| 5 s preview window | _TBD_ | | | | | | |
| 30 s full export | _TBD_ | | | | | | |
| 2 h job, N previews | _TBD_ | | | | | | |

## Explicit non-goals of Wave D1

- Provisioning or starting cloud GPUs from an agent.
- Merging GPU-required changes into PR #218 / making GPU mandatory.
- Replacing ffmpeg, faster-whisper, or yt-dlp wholesale.
- Shipping fabricated before/after timings in this document.
