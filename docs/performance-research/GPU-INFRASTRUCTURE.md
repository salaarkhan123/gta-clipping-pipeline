# GPU infrastructure

Aligns with SPEC §14 setup B and speed ticket **S5 #99**. No GPU provisioned in this research run.

Claim labels follow [RESEARCH.md](RESEARCH.md).

## 1. Current CPU path (verified)

| Stage | Implementation | GPU today |
|---|---|---|
| Decode for signals | ffmpeg CPU | no |
| ASR | faster-whisper CTranslate2 `device="cpu"` `int8` | no |
| Encode | libx264 veryfast / ultrafast | no |
| Facecam / CLIP | OpenCV / ONNX CPU | no |

This research VM: `nvidia-smi` missing (`measured` 2026-11-20). All NVDEC/NVENC numbers below are `not measured`.

## 2. Options under evaluation

### 2.1 FFmpeg NVDEC / NVENC

- Decode: `-hwaccel cuda` / `nvdec` for sparse frame extract (`public-source` ffmpeg docs).
- Encode: `h264_nvenc` for preview and export (`public-source`).
- Fits existing `render.py` / `ff.py` call style with encoder flag swaps (`hypothesis`).
- Requires NVIDIA driver + CUDA-capable ffmpeg build in the image (`inferred`).

### 2.2 PyNvVideoCodec

- MIT Python API over Video Codec SDK (`public-source` NVIDIA / PyPI 2026-11-20).
- Video Codec SDK EULA still applies for redistribution with NVIDIA GPUs (`public-source` NVIDIA license agreement).
- Strong candidate for decode→tensor and encode loops if we leave filter graphs in ffmpeg (`hypothesis`).

### 2.3 TorchCodec

- BSD-3; CUDA builds need NVIDIA license review (`public-source` 2026-11-20).
- Pulls PyTorch into the worker image (size/RAM) (`inferred`).
- Best if we already run torch models for gaming signals; otherwise heavy (`inferred`).

### 2.4 Decord

- Apache-2.0; efficient frame sampling historically popular (`public-source`).
- Maintenance quieter than TorchCodec; build/CUDA quirks common (`public-source` / `inferred`).
- Useful for sparse RGB arrays into OpenCV/OCR (`hypothesis`).

### 2.5 NVIDIA Accelerated Video for AI Playbook

- Pattern catalog (NVDEC → GPU preprocess → inference) (`public-source`).
- Not a library dependency; use as design reference for S5 benches (`inferred`).

## 3. Where GPU helps our pipeline (hypotheses)

| Workload | Likely GPU lever | Notes |
|---|---|---|
| Preview / export encode | NVENC | Attacks 59–62% render share (`inferred` from measured CPU split) |
| Sparse frame grab | NVDEC | Helps chat_motion / thumbs / judge frames if seek+decode bound |
| ASR | CTranslate2 CUDA or hosted ASR | S3 path; quality must hold on gaming audio |
| Sound-event / OCR models | GPU inference | Only after weight-0 CPU prototypes pass eval |

SPEC already rejects full-video proxy decode (`verified` SPEC §14). GPU should accelerate **sparse** and **windowed** work, not force full-frame tensors for 2h (`inferred`).

## 4. Proposed S5 benchmark plan (not executed)

Requires owner-approved GPU host. Identical inputs as CPU baseline.

1. libx264 vs `h264_nvenc` on 10 preview clips and 10 full exports from the 2h benchmark.
2. ffmpeg CPU vs NVDEC for `fps=2` and keyframe extracts over 2h.
3. faster-whisper CPU int8 vs CUDA float16/int8 on the same candidate windows; caption WER / eval unchanged.
4. Record utilization (SM %, NVDEC/NVENC sessions), peak VRAM, $/hour.

Until then every GPU speedup claim stays `not measured`.

## 5. Autoscaling (hypothesis)

- Analysis workers (CPU or small GPU) produce moments + previews.
- Render workers (NVENC or 16-vCPU per setup B) consume export queue (S4).
- Scale render replicas on export depth, not on upload count (`hypothesis`).

## 6. Recommendation

1. Keep ffmpeg as the orchestration surface.
2. Prioritize **NVENC preview/export A/B** on an approved GPU host before adopting TorchCodec/PyNv as required deps.
3. Do not enlarge the production CPU image with CUDA libraries until S5 shows a win that covers image size and ops cost (`inferred`).
