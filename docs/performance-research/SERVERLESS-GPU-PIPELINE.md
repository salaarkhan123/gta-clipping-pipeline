---
cursor:
  subagentId: "bc-10a0d9cf-e8cb-50e7-8a82-3c84408a5771"
  role: research
  extends: "docs/performance-research/GPU-INFRASTRUCTURE.md (#222) + gaming GPU-REQUIREMENTS (#237)"
---

# Serverless GPU across the clipping pipeline

**Status.** Desk research only (2026-11-20). Extends [#222](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/222) `GPU-INFRASTRUCTURE.md` (keep ffmpeg) and [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) `GPU-REQUIREMENTS.md`. Corrects the earlier multimodal note that scoped serverless GPU to Tier-2 VLM only — see [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257) / [PHASE3-4-EXTENSION.md](../gaming-intelligence-research/PHASE3-4-EXTENSION.md) / [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257).

**Hard rules.** Preserve completed development on `main` @ `8e0d9bad`. Prioritize current production release ([#238](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/238) deploy, then [#234](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/234)/[#235](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/235)) **before** implementing these infrastructure changes. No paid GPU / serverless provision without owner OK. Every GPU number for ClutchClips workloads remains **`not measured`** until an authorized bench.

---

## 1. Architectural adjustment

| Previous (multimodal Phase 3–4 first draft) | Corrected |
| --- | --- |
| Serverless GPU ≈ Tier-2 VLM / embedding backfill only | **On-demand GPU workers may accelerate the whole Clip Maker path** when measured wins justify cost |
| Control plane mixed into GPU host | **Website, API, Postgres, Stripe/billing, job queue stay on CPU control plane**; GPU workers are ephemeral and scale **0 → N → 0** |

Multimodal hierarchy (cheap nominate → expensive verify) still holds. GPU is a **capacity plane**, not a second product architecture.

---

## 2. Control plane vs GPU workers

```
┌────────────── Control plane (always on, CPU) ─────────────────┐
│ Web (static) · API · Postgres · Redis/queue · Stripe · R2     │
│ Auth, credits ledger, job state, webhooks, admin              │
└───────────────────────────┬───────────────────────────────────┘
                            │ enqueue Clip Maker / export job
                            │ signed URLs for source + artifacts
┌───────────────────────────▼───────────────────────────────────┐
│ GPU worker pool (scale-to-zero)                               │
│  cold start → pull image → claim job → one shared decode plan │
│  → ASR / signals / embed / OCR / optional VLM / render        │
│  → upload previews → ACK → exit → scale to 0                  │
└───────────────────────────────────────────────────────────────┘
```

| Component | Runs where | Why |
| --- | --- | --- |
| Next.js site, `/v1` API, billing, ledger | Control plane | Latency, secrets, no GPU need |
| Job orchestration / worker poll | Control plane or thin CPU worker | Must accept jobs when GPU = 0 |
| `run_pipeline` heavy stages | GPU worker (hybrid/full) or CPU worker (today) | Where acceleration is measured |
| Object storage (R2) | Shared | Source of truth for media |

**Scale-to-zero.** No GPU billed when the queue is empty. Cold start is a first-class metric (§6). Do not keep an idle GPU droplet “just in case” without a measured utilization case (`GPU-REQUIREMENTS.md` rent-vs-buy).

---

## 3. Keep ffmpeg; avoid duplicate decode

Judgment from `GPU-INFRASTRUCTURE.md` stands: **ffmpeg remains the media path**. Do not introduce TorchCodec/Decord/PyNv as the production graph.

**One decode plan per job (research target).**

| Today (CPU prod, ~8 GB host) | Target hybrid/GPU worker |
| --- | --- |
| Many ffmpeg subprocesses: audio extract, chat_motion full-span decode, visual index pass, 12 facecam seeks, per-clip render seeks | Prefer **one sequential or sparse decode schedule** that feeds PCM, sparse RGB, and render windows from shared intermediates |
| AV1 2h + Whisper + ffmpeg → **host OOM** (~5.5–5.8 GB anon on ~7.9 GB, no swap) — `internal/prod-ssh-diagnostics.md`, [#238](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/238) | GPU worker must ship with **host RAM ≫ VRAM**; cap concurrency; stream/chunk long VODs; never assume NVDEC alone fixes RAM |

**NVDEC / NVENC via ffmpeg only** (when authorized bench exists):

- Decode: `-hwaccel cuda` where the filter graph allows; accept `hwdownload` before CPU-only filters (`ass`, `boxblur`, `crop` without CUDA twin).
- Encode: `h264_nvenc` / `hevc_nvenc` behind a feature flag for preview and export A/B vs `libx264`.
- Captioned clips still pay a download/upload tax — measure it; do not claim “full GPU graph” until `ass` path is timed.

---

## 4. Pipeline stages eligible for GPU

| Stage | Current (`main`) | GPU option to evaluate | Decode reuse rule |
| --- | --- | --- | --- |
| **FFmpeg decode** | Software decode | NVDEC via ffmpeg | Shared sparse/full pass; no second full-span decode for chat+visual |
| **FFmpeg encode / export** | `libx264` veryfast/ultrafast | NVENC flag | Same filter graph; measure quality + $/clip |
| **Faster-Whisper** | CPU Whisper | CUDA Faster-Whisper / CTranslate2 CUDA | Audio-only (`-vn`); no video decode |
| **Visual embeddings** | ONNX CLIP CPU (`visual.py`) | CUDA ONNX/TensorRT or batched GPU CLIP; optional V-JEPA later | Frames from shared sparse sampler |
| **HUD / OCR** | Weight-0 scaffold; CPU Paddle/Tesseract path | CUDA Paddle / TensorRT on **changed crops only** | Crops from shared frames; never full-frame OCR every frame |
| **Multimodal inference** | Judge on CPU/API; Tier-2 VLM research | Shortlist-only VLM on GPU worker | Frames + transcript snippets only |
| **Clip render / export** | CPU ffmpeg per window | NVENC + same layouts; parallel `RENDER_WORKERS` on GPU host with RAM budget | Seek windows; prefer remux of already-decoded segments when safe |

Experimental gaming detectors stay **weight 0** until labelled wins — GPU does not authorize enabling them.

---

## 5. Hardware matrix (L4, RTX 4090, A40, L40S)

Public list prices / Runpod Secure Cloud examples read **2026-11-20** (subject to change). **Host RAM is mandatory** given prod OOM on 8 GB.

| Config | VRAM (public) | Example host RAM / vCPU (Runpod Secure listing) | Example $/hr (Secure Pod, public) | Why consider | Risk for our graph |
| --- | ---: | --- | ---: | --- | --- |
| **NVIDIA L4** | 24 GB | ~50 GB RAM / 12 vCPU | ~$0.69 | Efficient NVDEC×4; first server GPU for decode+ASR+OCR | 24 GB VRAM tight if VLM + Whisper + NVENC coexist |
| **RTX 4090** | 24 GB | listings often ~41 GB RAM / 6 vCPU | ~$0.89 | Strong consumer throughput for ASR/embed | **Host RAM may be too low** for 2h AV1 + ffmpeg + models; verify SKU RAM before any rental |
| **NVIDIA A40** | 48 GB | ~50 GB RAM / 9 vCPU | ~$0.59 | Headroom for concurrent encode + Whisper + OCR | Older arch; measure NVENC quality vs L4/L40S |
| **NVIDIA L40S** | 48 GB | ~94 GB RAM / 16 vCPU | ~$1.09 | Best **host RAM** match to OOM lessons; room for concurrency | Highest $/hr — must win on source-hours per billed hour |

**OOM design requirements (non-negotiable for any GPU worker image).**

1. Host RAM floor: target **≥32 GB** for single 2h job experiments; prefer **≥64 GB** (L40S-class) before concurrency >1.
2. Cap `worker_concurrency` and `RENDER_WORKERS` so peak RSS stays under 70% of host RAM in benches.
3. No swap as a strategy; measure anon RSS under AV1 1080p60 like the failed prod asset.
4. Keep [#238](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/238) progressive-clip retention semantics on GPU workers too.

Illustrative $/source-hour arithmetic (same sensitivity assumption as `GPU-REQUIREMENTS.md`: **15 billed minutes per source hour**) is **not** a ClutchClips measurement:

| GPU | Illustrative compute $/source-hour @ 15 min |
| --- | ---: |
| L4 @ $0.69 | $0.173 |
| 4090 @ $0.89 | $0.223 |
| A40 @ $0.59 | $0.148 |
| L40S @ $1.09 | $0.273 |

Serverless **worker** rates are often higher than Pod Secure rates (public tables show L4 serverless ~$0.75, 4090 ~$1.34, A40 ~$1.22, L40S ~$1.89). Cold start and idle scale-to-zero change the invoice — measure both.

---

## 6. Architecture comparison

| Architecture | Shape | When it wins (hypothesis) | When it loses |
| --- | --- | --- | --- |
| **CPU-only** (today) | 4 vCPU / 8 GB droplet runs API+worker | Low volume; simplest ops | 2h AV1 OOM; north-star 10 min unlikely |
| **Hybrid CPU/GPU** | Control plane CPU; Clip Maker/export on scale-to-zero GPU workers; ffmpeg+NVENC/NVDEC + CUDA Whisper | Best cost/quality if GPU only runs while jobs exist | Cold start hurts interactive “first preview”; needs queue UX |
| **GPU-accelerated always-on** | Dedicated GPU VM always billed | Sustained high utilization | Idle cost; violates scale-to-zero preference |

**Recommended research order:** CPU baseline (post-#238) → hybrid scale-to-zero → only then consider reserved GPU if utilization data demands it.

---

## 7. Metrics to measure (authorized benches only)

Pin container, driver, CUDA, ffmpeg build, model SHAs. Same permissioned VOD set for every arm.

| Metric | Definition |
| --- | --- |
| Cold-start latency | Queue empty → worker ready to claim (image pull + CUDA init) |
| End-to-end processing time | Job accepted → `SUCCEEDED` with N previews |
| Time to first preview | Job accepted → first playable clip URL |
| Peak host RAM | Max anon/RSS during job (must cite AV1 2h case) |
| GPU VRAM | Allocated + reserved + device high-water |
| Concurrent job capacity | Max parallel jobs before OOM or quality cliff |
| Cost per successful recording | All billed GPU/CPU/storage/API / successful jobs (include failed retries & cold starts) |

Also retain selection quality vs B0 when experimental signals are off (byte-identical) or when flags are on (paired NDCG gates from gaming research).

**Workload matrix (minimum).**

1. Preview-only Clip Maker on 2h AV1 gaming VOD (file upload).
2. Same with `transcribe_whole` on/off.
3. Export HD of 5 edited clips.
4. Concurrency 1 / 2 / 4 on the same SKU.
5. Cold vs warm worker.

---

## 8. Implementation sequencing (after production priority)

1. **Now:** desk research (this doc); preserve [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257) multimodal research.
2. **Production first:** deploy [#238](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/238); land [#234](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/234)/[#235](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/235) when owner OK.
3. **Then (owner GPU OK):** S5-style ffmpeg NVDEC/NVENC A/B on one SKU with **sufficient host RAM** (#99).
4. CUDA Faster-Whisper A/B on reused PCM (no extra video decode).
5. Embedding / OCR on shared frame crops.
6. Optional Tier-2 VLM on shortlist (multimodal Phase 4A).
7. Wire scale-to-zero orchestration only after a measured hybrid win on cost and TTF preview.

Promote one stage at a time. A stage that fails quality or $/recording stays off.

---

## 9. Explicit non-actions

- Do not provision Runpod/Modal/DO GPU in this document’s scope.
- Do not replace ffmpeg with another decode stack.
- Do not merge website/API/DB onto GPU hosts.
- Do not raise gaming detector weights.
- Do not treat publisher or cloud list prices as ClutchClips throughput.

---

## 10. Sources

- `docs/performance-research/GPU-INFRASTRUCTURE.md` ([#222](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/222))
- `docs/gaming-intelligence-research/GPU-REQUIREMENTS.md` ([#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237))
- Prod OOM: Project store `internal/prod-ssh-diagnostics.md`, `internal/production-clipping-failure-hotfix.md`, [#238](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/238)
- Multimodal: [PHASE3-4-EXTENSION.md](../gaming-intelligence-research/PHASE3-4-EXTENSION.md) / [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257), [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257)
- Public hardware/pricing references: NVIDIA L4/L40S/A40/4090 product pages; Runpod pricing / GPU compare (read 2026-11-20)
