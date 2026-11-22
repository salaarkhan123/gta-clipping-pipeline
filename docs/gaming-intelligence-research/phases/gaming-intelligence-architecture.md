> Mirror of Project store gaming-intelligence phase docs. Prior pack and desk research: [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237), multimodal hierarchy [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257), serverless GPU capacity plane [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258). Do not duplicate the #237 pack; link `docs/gaming-intelligence-research/*`.

# Phase 3 — Architecture (two-stage A/B)

**Recommend A.** Cheap nominate (Tier 0+1) → selective verify (Tier 2). Reject B (dense always-on multimodal) as default. Evidence: [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) `MULTIMODAL-ARCHITECTURE.md`, [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257), capacity plane [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258). Weights **0** until labelled wins.

---

## A/B

| | **A — nominate then verify (default)** | **B — denser always-on multimodal** |
| --- | --- | --- |
| Shape | Tier 0 always-on CPU-first → Tier 1 specialists on reused PCM/crops → Tier 2 VLM/encoder on **capped** shortlist | VLM / video encoder over dense frames for most of a 2h VOD |
| Cost | Bounded by shortlist N and frame/token caps | Dominated by decode + forward over full span |
| Quality path | Quotas per route; fusion; abstention | Higher recall hypothesis; unmeasured ClutchClips cost/latency |
| Failure | Experimental off → byte-identical B0 | Failure modes expensive; hard to fall back cheaply |
| Verdict | **Adopt** | **Reject as default**; only revisit if A saturates recall with measured headroom |

Serverless GPU ([#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258)) is a **capacity plane** (0→N→0 workers for ffmpeg/Whisper/embed/OCR/VLM/render). It is **not** a second product architecture and does **not** imply choosing B.

---

## Tier map (A)

```
Source PTS (absolute seconds)
  Tier 0: Faster-Whisper/Heard · RMS/flux/bursts · chat_motion · CLIP/FastEmbed · optional llm_pass
  Tier 1: YAMNet/CLAP · PaddleOCR/Tesseract on HUD crops · UniVTG / compact action (weight 0)
  Tier 2: Qwen3-VL (or challenger) on timestamped frames + transcript · must abstain · cite PTS
  Fusion / cut / rank: family caps · variety · judge sub-scores · promote one class vs B0
```

---

## Fusion

1. **Route quotas** so gunfire cannot crowd out quiet dialogue (MULTIMODAL-ARCHITECTURE).  
2. **Family aggregation** before fusion (loudness + flux + predicted gunshot = one audio family).  
3. **Separate** event confidence from entertainment / editor preference.  
4. **Competing explanations:** replay, spectator, menu/BRB, overlays — tag; do not silently veto B0.  
5. **Cuts:** search setup←peak→payoff/reaction within bucket; reuse sentence/cut edges from #218 path.  
6. Promote **one** class or interaction at a time vs frozen B0 (`8e0d9bad` pin).

---

## Weight-0 contract

| Condition | Required behavior |
| --- | --- |
| All experimental weights 0, Tier 2 off | Candidate order/scores match today’s selector (fixed judge cache) |
| Research runner on | May compute Observations → private sidecar only; ranking weight 0 |
| Experimental failure / timeout | Keep baseline output; count toward availability |
| Product path | Skip model load / extra decode / vetoes when flags off |

---

## Cache keys

Key experimental caches by: **source digest · PTS range · game profile · model_id · model_sha · params/prompt hash**. Feature caches expire with upload/takedown. Tier-2 cache: `(model, frame PTS set, prompt hash)`.

---

## PTS clock

Use **source presentation timestamps** (seconds from original recording start). Restore absolute offset for ranged jobs once. Keep observation time, estimated event interval, and proposed clip boundaries as separate fields. Sparse sample and ASR timing carry uncertainty — do not pretend frame-perfect without measurement.

---

## Explicit non-goals

- Always-on VLM over full VODs.  
- Virality-as-probability in fusion.  
- GPU purchase/provision from this doc ([#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258) remains desk research).
