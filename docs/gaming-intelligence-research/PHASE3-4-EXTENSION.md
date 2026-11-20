---
cursor:
  subagentId: "bc-10a0d9cf-e8cb-50e7-8a82-3c84408a5771"
  role: research
  extends: "docs/gaming-intelligence-research on PR #237"
---

# Multimodal intelligence — Phase 3 & 4 extension

**Status.** Desk research + architecture only (2026-11-20). Extends [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) gaming-intelligence research (`MULTIMODAL-ARCHITECTURE.md`, `IMPLEMENTATION-ROADMAP.md` §§3A–4B, `REPOSITORY-EVALUATION.md`, `GPU-REQUIREMENTS.md`). Does **not** duplicate Phase 1 harness findings or rewrite Phase 2 detector tickets.

**Hard rules.** Preserve CLIP (`visual.py` / FastEmbed), Faster-Whisper, signal timeline, and scoring on `main` @ `8e0d9bad`. Experimental gaming weights stay **0**. No paid GPU / serverless provision without owner OK. Integrate only after a measured win against the frozen B0 control.

**Start gate (owner instruction).** Begin *integration and GPU benches* only after the current production release is successfully integrated and deployed.

| Gate item | State 2026-11-20 |
| --- | --- |
| Release [#218](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/218) on `main` / prod (`8e0d9bad`) | Done |
| Progressive-clips hotfix [#238](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/238) deployed | **Open** — owner deploy OK |
| Perf RC [#234](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/234)+[#235](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/235) on staging | **Open** — owner merge OK |
| Phase 1 owner labelling (#237 / 1A) | **Open** — blocks Phase 2+ weight raises |
| This document (desk research) | Allowed now — no infra, no weight changes |

Desk research may proceed. **Live model downloads, serverless GPU rental, and product integration wait** until #238 is deployed (or owner explicitly waives) **and** labelled eval media exist for any quality claim.

---

## 1. What already exists (do not rebuild)

| Layer | On `main` / open research | Phase role |
| --- | --- | --- |
| Speech | Faster-Whisper local; Heard reuse; `transcribe_whole` default off | Tier-0; keep |
| Audio signals | RMS, flux, bursts; YAMNet adapter weight 0 on [#231](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/231)/[#234](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/234) | Tier-0 / Tier-1 eval |
| Visual embeddings | ONNX CLIP every 2 s (`visual.py`); FastEmbed | Tier-0 index; keep |
| HUD / OCR | `HUD_REGIONS={}`; Paddle path scaffold [#232](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/232) | Tier-1 after #201 regions |
| Chat | `chat_motion` pixel activity (not IRC text) | Tier-0 |
| Ranking | Five editorial sub-scores + judge; `SCORE_WEIGHTS` empty | Control for 3A |
| Architecture sketch | Observation / Event / Candidate / Run records | Reuse as-is |

Upstream already evaluated (do not re-litigate): YAMNet, PaddleOCR mobile, Tesseract, InternVideo2 Stage2 (gated), Qwen2.5-VL-7B, VideoMAE NC, RF-DETR Nano, PANNs — see `REPOSITORY-EVALUATION.md` on #237.

---

## 2. Hierarchical pipeline design (Phase 3 core)

Goal: **cheap detectors nominate**; **expensive multimodal models verify a capped shortlist**. Never run a VLM / video encoder over every frame of a 2h VOD.

```
Source PTS clock (absolute seconds)
        │
┌───────▼──────── Tier 0 — always-on, CPU-first, existing pipeline ────────┐
│ Speech (Faster-Whisper / Heard) · audio RMS/flux/bursts · chat_motion     │
│ CLIP/FastEmbed sparse frames · facecam · scene standby · llm_pass (opt) │
│ Output: Observation[] + baseline Candidate[]  (B0 control, weight path) │
└───────┬──────────────────────────────────────────────────────────────────┘
        │ merge + quota per route (audio / dialogue / HUD / visual / uniform)
┌───────▼──────── Tier 1 — lightweight specialists (weight 0 until labelled)─┐
│ YAMNet/CLAP on reused PCM · PaddleOCR/Tesseract on measured HUD crops     │
│ MMAction2 / compact action head on short windows · UniVTG localization   │
│ Output: Event[] with calibrated class confidence; still research sidecar │
└───────┬──────────────────────────────────────────────────────────────────┘
        │ shortlist ≤ N ambiguous or high-stakes intervals (fixed budget)
┌───────▼──────── Tier 2 — selective expensive reasoning (Phase 4A only) ───┐
│ Qwen3-VL or VideoLLaMA3 on timestamped frames + transcript snippet        │
│ Optional: InternVideo / V-JEPA embeddings for retrieval corroboration     │
│ Must abstain; must cite frame PTS; cache by (model, frames, prompt hash)│
└───────┬──────────────────────────────────────────────────────────────────┘
        │
┌───────▼──────── Fusion / cut / rank (Phase 3A) ───────────────────────────┐
│ Family-wise fusion · interval merge · variety · judge sub-scores          │
│ Promote one class at a time vs B0; byte-identical when experimental off   │
└───────────────────────────────────────────────────────────────────────────┘
```

**Preserved contract.** When all experimental weights are 0 and Tier 2 is off: candidate order and scores match today’s selector (fixed judge cache). Failures in experimental arms fall back to baseline output and count toward availability metrics (`MULTIMODAL-ARCHITECTURE.md`).

**Modalities combined (explicit map).**

| Modality | Tier | Producer | Consumer |
| --- | --- | --- | --- |
| Speech / transcript | 0 | Faster-Whisper, Heard | Find, llm_pass, narrative events, Tier-2 prompts |
| Audio events | 0–1 | RMS/flux/bursts → YAMNet/CLAP | Nomination, gunfight/siren/laughter |
| Visual embeddings | 0–2 | CLIP now; V-JEPA / InternVideo optional | NL visual search, game/mode router |
| HUD recognition | 1 | PaddleOCR / Tesseract on ROI | Score/kill/banner Events |
| Gameplay actions | 1–2 | MMAction2 / title state machines / VLM | Kill, goal, crash, round end |
| Chat activity | 0 | chat_motion (± later chat text if rights) | Reaction lag features |
| Temporal localization | 1–2 | UniVTG / boundary search from peak | Setup–payoff cuts |

---

## 3. Candidate model evaluation (Phase 3–4 shortlist)

Licenses and publisher claims checked 2026-11-20 from project pages / HF cards. **Not legal advice** — pin the exact artifact SHA and re-read the card before any commercial ship. Publisher benchmark numbers are **not** ClutchClips gaming accuracy.

| Candidate | Role in hierarchy | Code / weights license (stated) | Fit vs existing pipeline | Decision for ClutchClips |
| --- | --- | --- | --- | --- |
| **YAMNet** | Tier-1 named sounds on reused PCM | Apache-2.0 impl + Google distribution | Already scaffolded (#231); compare vs RMS/flux | **Keep.** First audio ablation after labels (roadmap 1C). |
| **CLAP** (LAION `clap-htsat-*` / MS CLAP) | Tier-1 text↔audio for prompt audio search | LAION: code CC0, HF weights Apache-2.0; MS CLAP: MIT (repo archived) | Complements YAMNet for language queries (“sirens”, “crowd cheer”) | **Pilot** on identical windows as YAMNet if labels exist; do not replace YAMNet until measured. |
| **PaddleOCR** (PP-OCRv5 mobile) | Tier-1 HUD text | Apache-2.0 code + selected mobile cards | Scaffold #232; needs #201 regions | **Keep.** Recognition-only on changed crops; Tesseract as CPU baseline. |
| **MMAction2** | Tier-1 action recognition toolkit | Apache-2.0 | Kinetics/AVA ≠ gaming HUD events; useful scaffolding for short-clip classifiers | **Defer product.** Use only if a title-specific fine-tune on permissioned data beats state/OCR path. |
| **UniVTG** (showlab) | Tier-1/2 temporal grounding from text | MIT (verify selected checkpoint card) | Maps natural-language queries → time spans; overlaps Find + llm_pass | **Pilot** for prompt clipping (#203) against transcript+CLIP control; reject if no R@ localization gain. |
| **V-JEPA 2** (Meta) | Tier-0/2 video embeddings | MIT code + HF MIT checkpoints (pin card) | Dense motion features; heavier than CLIP every 2 s | **Optional embedding challenger** for visual search / action similarity — never default decode path. Must beat CLIP index on gaming prompts at equal coverage. |
| **InternVideo** / InternVideo2 | Tier-2 retrieval / encoder | Apache-2.0 repo; some HF cards gated (“no harmful human-subject experiments”) | Already noted in REPOSITORY-EVALUATION | **Shortlist-only** after gate accept; same budget as V-JEPA. |
| **Qwen3-VL** (2B–8B Instruct first) | Tier-2 selective VLM verifier | Apache-2.0 (Qwen3-VL repo / size cards — **pin each size**) | Successor to Qwen2.5-VL-7B already shortlisted | **Preferred Tier-2 verifier** to re-bench vs 2.5-VL at equal frames/tokens. Abstention + PTS citation mandatory. |
| **VideoLLaMA3** | Tier-2 VLM alternative | Apache-2.0 code; README: hosted *service* non-commercial; built on Qwen2.5 — **verify weight cards** | Overlaps Qwen3-VL role | **Challenger only** if Qwen3-VL fails a named failure mode; confirm commercial weight grant per checkpoint. |
| **Alternatives already ranked lower / blocked** | — | VideoMAE **CC BY-NC**; YOLO AGPL/Enterprise; BEATs commercial grant unclear | — | **No product use** without rights clearance (unchanged). |

### Comparison axes vs current pipeline (required for any promote)

1. **Detection accuracy** — per-class P/R on labelled seconds (sound, HUD, actions); ≥0.90 precision to *propose* a class (existing 1C/1D gates).
2. **Timestamp localization** — median / p95 onset error (s); UniVTG / VLM cuts vs current peak±bucket search.
3. **Ranking quality** — paired NDCG@5 / R@20 vs B0 on creator-held-out labels (Phase 3A: ≥0.03 NDCG@5 with paired 95% LB > 0).
4. **Latency** — incremental wall time per source hour; p95 job time; first preview time.
5. **Host RAM / GPU VRAM** — peak RSS; allocated + reserved VRAM; OOM rate.
6. **Cost per recording** — `$ / source hour` including cold start, idle, retries (see §5).

Any arm that loses on quality **or** is dominated on cost/latency at equal quality is rejected and documented as a null result.

---

## 4. Persistent timestamped multimodal embeddings

**Problem.** Today’s CLIP index and Heard transcript support Find, but prompt clipping still mostly steers the judge (#212 row 2.1). A durable, PTS-aligned store would back NL search, prompt nomination, and transcript reuse without re-decoding.

**Proposed research sidecar schema** (private; expires with upload/takedown):

| Field | Meaning |
| --- | --- |
| `upload_id`, `account_id` | Ownership; deleted on takedown |
| `t0`, `t1` | Source PTS interval |
| `modality` | `speech_seg` \| `audio_emb` \| `vision_emb` \| `hud_text` \| `event` |
| `vector` / `text` | Embedding or OCR/ASR string |
| `model_id`, `model_sha`, `params_hash` | Reproducibility |
| `rights_ok` | Consent / provider terms flag |

**Build policy.**

- Emit from Tier 0/1 only on jobs that already decode those windows (no second full pass).
- Vision: keep CLIP as default; A/B V-JEPA or InternVideo embeddings on the **same** frame set.
- Audio: optional CLAP embedding per 0.96–2 s hop on reused PCM after YAMNet gates.
- Speech: reuse Heard word timings; do not re-transcribe for embedding writes.
- Query path: `POST /v1/find` gains a research flag to fuse transcript BM25 + vector ANN; production default unchanged until measured.

**Promotion gate.** Embedding index must improve prompt recall (#197) or Find precision@10 without increasing judge call count or job price, unless a money PR says otherwise.

---

## 5. Benchmark protocol (Phase 3A / 4A)

Reuse `EVALUATION-FRAMEWORK.md` metrics. Add a **hierarchical cost card** per arm:

| Metric | How |
| --- | --- |
| Quality | Event P/R, localization error, NDCG@5, R@20, adverse strata |
| Latency | `scripts/job_timings.py` stages + Tier-2 queue time |
| Memory | Peak host RSS; `nvidia-smi` allocated/reserved (when GPU authorized) |
| Cost | Billed machine-seconds × rate + storage + API; `/ successful source hour` |
| Control | B0 pin `8e0d9bad` (or post-#238 SHA once deployed); experimental off = byte-identical candidates |

**Workload shapes.**

1. **CPU-only Tier 0+1** on permissioned labelled VODs (no rental).
2. **Authorized serverless GPU** (Phase 4A): fixed frame/token budget; Qwen3-VL **or** embedding encoder — never an inseparable bundle; L4-class first per `GPU-REQUIREMENTS.md`.
3. Reject configs dominated on quality/cost; record failed arms.

---

## 6. Serverless GPU architecture fit

Align with performance research `docs/performance-research/GPU-INFRASTRUCTURE.md` (#222): **keep ffmpeg** as the media path; GPU is for optional inference workers, not a second decode stack.

| Concern | Design choice |
| --- | --- |
| Default Clip Maker | Stays on current CPU worker; experimental off |
| Serverless role | Ephemeral GPU worker for Tier-2 verify or batch embedding backfill |
| Cold start | Amortize only when shortlist size justifies; measure cold vs warm |
| Data plane | Pull shortlisted frame JPEGs / PCM snippets by signed URL; no full VOD to GPU by default |
| Isolation | Research runner / feature flag; production ranking weight 0 until enablement review |
| Failures | Timeout → preceding Tier-1 score; never fail the job solely because Tier-2 OOM’d |
| Cost control | Hard cap: max Tier-2 calls per job; max tokens; owner spending limit before any provision |

**Do not provision** Runpod/Modal/DO GPU until Phase 3A shows a named failure mode that Tier-1 cannot fix and a dated quote exists (`IMPLEMENTATION-ROADMAP` 4A).

---

## 7. Phase 3 vs Phase 4 work packages (extension of roadmap)

| ID | Work | Depends on | Out of scope |
| --- | --- | --- | --- |
| **3A+** | Hierarchical fusion harness on research sidecar; family caps; ablations B/A/V/T/G/F | Labels 1A; adapters 1C/1D or 2A/2B outputs | Weight > 0 in product |
| **3E** | Persistent PTS embedding store + Find fusion flag | Heard + CLIP; optional CLAP | Replacing CLIP |
| **3P** | UniVTG / prompt-localization pilot vs #203 control | #197 prompt labels | Shipping prompt nomination without bench |
| **4A+** | Qwen3-VL (vs 2.5-VL) and optional V-JEPA/InternVideo on **capped** shortlist; serverless shape | Owner GPU OK; 3A failure mode named | Always-on VLM; VideoLLaMA3 unless Qwen fails |
| **4B** | Unchanged competitive protocol | Paid vendor OK | Fabricated parity claims |

---

## 8. Recommended experiment order (post-gate)

1. Owner: deploy [#238](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/238); land [#234](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/234) stack when ready; complete Phase 1 labels.
2. Run **1C YAMNet** and **1D PaddleOCR** offline vs baseline signals (weights still 0).
3. Add **CLAP** as audio-language challenger on the same PCM windows.
4. Implement **3A+** fusion on sidecar observations only.
5. Prototype **3E** embedding persistence for Find (CLIP first).
6. Only if 3A leaves a documented ambiguity class: authorize **4A+** Qwen3-VL shortlist verify on serverless GPU; compare V-JEPA embeddings offline if visual-search misses dominate.
7. Promote one class/profile at a time after paired ranking + cost gates.

---

## 9. Explicit non-actions

- Do not raise YAMNet/HUD/action weights above 0 without labelled ≥0.90 precision **and** Phase 3 ranking evidence.
- Do not replace CLIP, FastEmbed, Faster-Whisper, timeline, or judge scoring.
- Do not duplicate Phase 1 harness / B0 pin work.
- Do not rent or buy GPU / serverless capacity in this document’s scope.
- Do not claim gaming-event detection or OpusClip parity from publisher benchmarks.
- Do not use NC-licensed checkpoints (e.g. VideoMAE) in product research without rights.

---

## 10. Sources

- PR [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) research tree: `MULTIMODAL-ARCHITECTURE.md`, `IMPLEMENTATION-ROADMAP.md`, `REPOSITORY-EVALUATION.md`, `GPU-REQUIREMENTS.md`, `EVALUATION-FRAMEWORK.md`, `PHASE1-FINDINGS.md`
- Perf: `docs/performance-research/GPU-INFRASTRUCTURE.md` on [#222](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/222)
- Parity context: `docs/opusclip-212-*` in Project store (CPR-37), `docs/opusclip-212-*` in Project store (CPR-37)
- Publisher pages (2026-11-20): [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL/), [V-JEPA 2](https://github.com/facebookresearch/vjepa2), [InternVideo](https://github.com/OpenGVLab/InternVideo), [VideoLLaMA3](https://github.com/DAMO-NLP-SG/VideoLLaMA3/), [MMAction2](https://github.com/open-mmlab/mmaction2), [LAION CLAP](https://github.com/LAION-AI/CLAP), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), YAMNet (TF / MediaPipe)
