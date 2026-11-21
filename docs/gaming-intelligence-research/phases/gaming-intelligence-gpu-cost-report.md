> Mirror of Project store gaming-intelligence phase docs. Prior pack and desk research: [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237), multimodal hierarchy [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257), serverless GPU capacity plane [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258). Do not duplicate the #237 pack; link `docs/gaming-intelligence-research/*`.

# Phase 8 — GPU cost report

**Hard rule.** Do not invent ClutchClips GPU measurements. Cite [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) `GPU-REQUIREMENTS.md` and [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258) serverless capacity notes. Weights stay **0**. No purchase / rental from this doc.

---

## MEASURED

| Item | Status |
| --- | --- |
| ClutchClips GPU wall time / source hour | **None** — not measured on authorized hardware |
| ClutchClips GPU VRAM / RSS under production graph | **None** |
| Cold-start serverless GPU for Clip Maker | **None** |
| NVDEC/NVENC / CUDA Whisper / Tier-2 VLM on ClutchClips media | **None** |

**Measured production constraint (CPU host):** ffmpeg + long AV1 + Whisper path has **OOM on ~8 GB** hosts (anon ~5.5–5.8 GB on ~7.9 GB, no swap) — cited in #258 / progressive-clip work (#238). This is a **host RAM** fact, not a GPU throughput number.

## Measured on this research host (CPU hook only, 2026-11-21)

| Item | Result | Label |
| --- | --- | --- |
| GI hook disabled median | ~0.004 ms / 40 candidates | **MEASURED** |
| GI hook enabled (weights 0) median | ~0.22 ms / 40 candidates | **MEASURED** |
| R2 GTA `head_object` | OK (~3.3 GB) | **MEASURED** (no media in artifacts) |
| ClutchClips L4 / VLM wall time | — | still **not measured** |

CPU-only historical timings from performance research (e.g. droplet 2h runs in #222 docs) are **not** GPU measurements and are not re-quoted here as GPU cost.

---

## ESTIMATED (list prices + sensitivity only)

Public USD/hour listings read **2026-11-19/20** (subject to change). Sources: Runpod Pod / DigitalOcean public pages via GPU-REQUIREMENTS / #258.

| SKU | Listed compute USD/h (example) | Illustrative $/source-hour @ **15 billed min / source hour** |
| --- | ---: | ---: |
| CPU Paperspace C6 | 0.16 | 0.040 |
| L4 | 0.69 | 0.173 |
| RTX 4000 Ada (DO) | 0.76 | 0.190 |
| RTX 4090 | 0.89 | 0.223 |
| A40 (Secure example in #258) | ~0.59 | ~0.148 |
| L40S | 1.09 | 0.273 |
| RTX 5090 | 1.39 | 0.348 |

**The 15 min / source hour figure is a sensitivity assumption, not a ClutchClips measurement.** Actual billed time may differ by orders of magnitude. Serverless worker list rates are often **higher** than Pod Secure (e.g. L4 ~0.75, 4090 ~1.34 in #258 public tables) — still ESTIMATE.

Cost formula when a bench exists:  
`(Σ billed machine hours × rate + storage + API + failed retries + cold starts) / successful source hours`.

L40S must process >~1.58× L4 source-hours per billed hour to beat L4 compute cost at equal quality (arithmetic from list prices only).

---

## Recommendation

1. **Do not purchase** a GPU workstation or reserve always-on GPU from this report.  
2. **Do not rent** until: production RAM/#238 path is stable, Phase 1 labels exist for any quality claim, and owner sets a spending cap.  
3. **Prepare an L4 bench script only** (pin container/driver/CUDA/ffmpeg/model SHAs; same permissioned VOD; log cold/warm, RSS, VRAM, $/successful recording). Prefer host RAM **≫ 8 GB** (target ≥32 GB; prefer ≥64 GB before concurrency >1) — ESTIMATE/design requirement from OOM lesson, not a measured GPU need.  
4. Default Clip Maker stays CPU until a measured hybrid win. Experimental detectors remain weight 0 on any GPU worker.

**Approval gate.** Measured source-hours/month, quality delta vs B0, p95 latency, memory headroom, current rental quote — then capped pilot only.
