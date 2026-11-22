> Mirror of Project store gaming-intelligence phase docs. Prior pack and desk research: [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237), multimodal hierarchy [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257), serverless GPU capacity plane [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258). Do not duplicate the #237 pack; link `docs/gaming-intelligence-research/*`.

# Phase 2 — Model comparison

**Reuse.** [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) `REPOSITORY-EVALUATION.md` + store/PR [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257) multimodal extension. Licenses = publisher-stated as of 2026-11-20; **not legal advice** — pin artifact SHA before any ship. Publisher benches ≠ ClutchClips accuracy/latency/cost. ClutchClips timings = **unmeasured** unless cited from #237 probe aggregates.

Weights stay **0**. No paid GPU.

---

## Primary shortlist

| Candidate | Role | License (stated) | Speed class | Mem class | Usefulness for ClutchClips | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| **Qwen3-VL** (2B–8B Instruct first) | Tier-2 selective VLM verifier | Apache-2.0 (pin each size card) | Slow (GPU; capped shortlist) | High VRAM | Structured abstention + PTS citation on ambiguous windows | **Preferred Tier-2** — re-bench vs Qwen2.5-VL-7B at equal frames/tokens |
| **Qwen3** (text) | Text reasoner on transcript snippets | Apache-2.0 (pin card) | Medium (GPU/CPU by size) | Med–High | Cheap narrative verify without frames; cannot read HUD | **Pilot** for dialogue-only routes; never sole event proof |
| **PaddleOCR** PP-OCRv5 mobile | Tier-1 HUD recognition | Apache-2.0 code + selected mobile cards | Fast (CPU/GPU crops) | Low–Med | Scaffold #232; needs `#201` regions | **Keep** — recognition-only on changed crops |
| **YAMNet** | Tier-1 named AudioSet tags | Apache-2.0 + Google distribution | Fast (CPU on reused PCM) | Low | Adapter #231; laughter/siren/gunshot proxies | **Keep** — first audio ablation after labels |
| **CLAP** (LAION / MS) | Tier-1 text↔audio | LAION weights Apache-2.0 (code CC0); MS MIT (repo archived) | Fast–Med | Low–Med | Promptable audio search vs fixed YAMNet classes | **Pilot** on identical windows; do not replace YAMNet until measured |
| **UniVTG** | Tier-1/2 temporal grounding | MIT (verify checkpoint card) | Med (GPU features) | Med | NL query → time span; overlaps Find / prompt clipping | **Pilot** vs transcript+CLIP control; reject if no localization gain |

Publisher numbers (examples, **publisher**): PaddleOCR mobile rec T4 5.43/1.46 ms (normal/HP); YAMNet AudioSet mAP 0.306 / Pixel-6 task ~12.29 ms/window; Qwen2.5-VL-7B Video-MME 65.1/71.6 (w/o / w subtitles) — see REPOSITORY-EVALUATION. **ClutchClips wall time / VRAM: unmeasured.**

---

## Alternatives

| Candidate | Role | License (stated) | Speed | Mem | Usefulness | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| **Tesseract** 5.x | HUD OCR baseline | Apache-2.0 engine + tessdata_fast | Fast CPU | Low | Digit/line whitelist baseline before Paddle | **Keep as CPU baseline** |
| **VideoLLaMA3** | Tier-2 VLM challenger | Apache-2.0 code; hosted *service* NC; verify weight cards | Slow GPU | High | Overlaps Qwen3-VL | **Challenger only** if Qwen fails a named mode |
| **InternVideo2** Stage2 | Tier-2 retrieval / embeddings | Apache-2.0 repo; some HF cards gated | Slow GPU | High (~2.82 GB artifact + activations) | Retrieval ≠ clip quality | **Shortlist-only** after gate accept |
| **V-JEPA 2** | Embedding challenger | MIT code + HF MIT checkpoints (pin) | Med–Slow | Med–High | Dense motion vs CLIP every 2 s | **Optional** — must beat CLIP index at equal coverage |
| **PANNs** Cnn14 | Audio tagger challenger | MIT code; Zenodo weights CC BY 4.0 | Med | Med | Higher AudioSet mAP (publisher 0.431) vs YAMNet | **Challenger** if laughter/crowd precision wins at matched coverage |

**Blocked / defer without rights:** VideoMAE / TimeSformer **CC BY-NC**; YOLO AGPL/Enterprise; BEATs commercial grant unclear (unchanged from #237).

---

## Comparison axes (any promote)

1. Class P/R on labelled seconds (≥0.90 precision to *propose* a class).  
2. Localization error (median / p95 onset).  
3. Ranking: NDCG@5 / R@20 vs B0 (paired; creator-held-out).  
4. Latency: incremental s / source hour (measure; do not invent).  
5. Peak RSS / VRAM.  
6. `$` / source hour including cold start (ESTIMATE until bench).

Reject arms that lose quality or are cost-dominated at equal quality. Record nulls.
