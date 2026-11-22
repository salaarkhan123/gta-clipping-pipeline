<!-- Mirrors store docs/gaming-intelligence-roadmap.md -->

# Phases 9–10 — Roadmap & final recommendation

**Branch.** `cursor/gaming-intelligence-research-8a00` (from `origin/main` only; independent of #261).  
**Hard constraints honored.** Weights 0 · no virality-% · no TOS scrape · no credentials/media in artifacts · CPU first · GPU = plan + estimates only.

Extends [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) / [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257) / [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258). Does not replace the Phase 1 owner labelling gate.

---

## Build order (post-labels)

| Step | Work | Gate |
| ---: | --- | --- |
| 0 | Owner labels GI sheet + #237 sound/HUD/consent asks | Rated rows exist |
| 1 | Land weight-0 YAMNet + HUD OCR adapters on main (if not already via perf RC) | Byte-identical ranking |
| 2 | Offline 1C/1D precision floors (≥0.90 propose-class) | Measured P on held-out |
| 3 | Architecture **A** fusion sidecar (family caps); promote one class | NDCG@5 ≥ +0.03 vs B0, paired LB > 0 |
| 4 | CLAP / UniVTG pilots only if labelled failure modes demand them | Ablation win |
| 5 | Optional L4 scale-to-zero bench (owner spend cap) for ffmpeg/Whisper/embed **before** Tier-2 VLM | Measured $/hour + quality |
| 6 | Qwen3-VL capped shortlist verify if ambiguity class remains | Cost + abstention metrics |
| 7 | Never ship Architecture B (dense always-on VLM) as default | Dominated on cost |

---

## Owner’s nine questions — answers

| # | Question | Answer |
| ---: | --- | --- |
| 1 | **What already works that we must keep?** | Faster-Whisper + Heard, CLIP/FastEmbed index, RMS/flux/bursts, optional chat_motion, five editorial sub-scores, variety, `run_pipeline` contract. B0 pin `8e0d9bad` weights. |
| 2 | **Which models are worth piloting?** | Tier-1: YAMNet then PaddleOCR (Tesseract baseline); CLAP/UniVTG as challengers. Tier-2: Qwen3-VL on a **capped** shortlist. Defer NC/gated/AGPL risks (VideoMAE, YOLO commercial). |
| 3 | **Nominate-then-verify (A) or dense multimodal (B)?** | **A.** Cheap detectors nominate; expensive VLM verifies ≤N windows. B rejected as default (cost/latency, no label proof). |
| 4 | **How do we evaluate without treating Clutch scores as truth?** | Export candidates → human entertainment rubric + publish flag. `clutch_score` stays a proposal column. Metrics: NDCG@5, P/R@k, tIoU — after labels. |
| 5 | **What is “entertaining”?** | Rubric dimensions hook/stakes/payoff/reaction/clarity/novelty/completeness + publish — **not** a virality probability ([rubric](gaming-intelligence-entertainment-rubric.md)). |
| 6 | **Did the CPU prototype improve selection?** | **Not claimed.** With weights 0 it preserves order (measured). Quality delta needs human ratings (currently 0/30). |
| 7 | **Can we predict virality / views?** | **No production coefficient.** #237 YouNiverse pairs: no title-marker boost; archive ≠ Shorts era. Keep editor rating, retention, and views as separate outcomes. |
| 8 | **When is GPU spend justified?** | Only after labels + a named measured question; L4 scale-to-zero first; host RAM ≫ 8 GB prod OOM case. List-price sensitivity ≠ throughput. |
| 9 | **What should we build next?** | (1) Owner labelling, (2) weight-0 adapter measurement, (3) Architecture A fusion on sidecar, (4) optional authorized L4 bench — **not** #261 coupling, **not** merge of experimental weights. |

---

## Implemented vs experimental (this PR)

| Item | State |
| --- | --- |
| Phase docs 1–3, 5, 7–8 + eval dataset + bench + roadmap | **Implemented** (docs) |
| #237 harness + pin mirrored for reuse | **Implemented** (research tree) |
| `app/pipeline/gaming_intelligence.py` hooks + cache + metrics | **Implemented**, default **off** |
| `scripts/gaming_intelligence*` dataset/CLI/bench | **Implemented** |
| GI label sheet `eval/gi-gta-label-sheet.csv` | **Implemented** (0 human ratings) |
| YAMNet/CLAP/OCR/VLM inference in product path | **Experimental / not on** |
| Weight raises | **Forbidden** until gates |
| GPU rental | **Not done** — plan only |

---

## Next steps (owner)

1. Rate `eval/gi-gta-label-sheet.csv` (and remaining #237 asks).
2. Approve whether weight-0 YAMNet/HUD land via perf RC or a dedicated PR.
3. Spending limit + SKU if/when an L4 bench is authorized.
4. Keep this research PR **unmerged** or docs-only merge at owner discretion — **do not** enable GI in production from this branch.
