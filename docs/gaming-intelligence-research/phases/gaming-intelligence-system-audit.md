> Mirror of Project store gaming-intelligence phase docs. Prior pack and desk research: [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237), multimodal hierarchy [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257), serverless GPU capacity plane [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258). Do not duplicate the #237 pack; link `docs/gaming-intelligence-research/*`.

# Phase 1 — System audit (main @ tip)

**Scope.** Desk audit of `main` @ `b74a3e7` (#260) plus what open research PRs already cover. No new benches. Experimental ranking weights stay **0**.

**Do not duplicate** the [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) pack. Cite and extend: `docs/gaming-intelligence-research/*` (CURRENT-ARCHITECTURE, PHASE1-FINDINGS, COMPETITIVE-ANALYSIS, REPOSITORY-EVALUATION, VIRALITY-RESEARCH, GPU-REQUIREMENTS). Multimodal hierarchy: [#257](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/257). Serverless GPU as **capacity plane**: [#258](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/258).

---

## What #237 / #257 / #258 already cover

| PR | Delivers | Does **not** authorize |
| --- | --- | --- |
| **#237** | 12 research docs; B0 pin `8e0d9bad`; Phase 1 harness; eval census; 116-pair engagement desk study; GPU list-price matrix | Labels, weight > 0, paid GPU, product merge |
| **#257** | Tier 0→1→2 hierarchy; Qwen3-VL / UniVTG / CLAP shortlist; PTS embedding sidecar sketch | Always-on VLM; weight raises |
| **#258** | Pipeline-wide serverless GPU (ffmpeg/Whisper/embed/OCR/VLM/render); control plane CPU; 0→N→0 | Provisioning; ClutchClips GPU timings (still **not measured**) |

Production selector pin for gaming B0 remains merge `8e0d9bad` (PHASE1-FINDINGS). Tip `b74a3e7` adds frontend/API RC (#260); it does **not** populate `HUD_REGIONS` or enable named-sound weights.

---

## Inventory on `main` (tip)

| Layer | On main | Notes |
| --- | --- | --- |
| Speech | Faster-Whisper; Heard reuse; whole-transcript opt-in (#260) | Tier-0 |
| Visual index | ONNX CLIP / FastEmbed (~1 frame / 2 s) | Tier-0 Find |
| Audio signals | RMS 0.7 · flux 0.35 · bursts 0.35 | Active nomination |
| Chat | `chat_motion` (pixel edges; default region none) | Weight 1.0 when region set |
| Scene | weight **0.0** | Skipped decode |
| HUD | `HUD_REGIONS = {}` (`layouts.py`) | No OCR crops |
| Judge | 5 sub-scores: **hook, payoff, clarity, emotion, pacing** (`ranking.SCORES`) | Public rating = mean; not a view forecast |
| `SCORE_WEIGHTS` | Empty config default | Equal mean ranking |
| YAMNet / HUD OCR | Side branches (#231 / #232 / perf RC) | Experimental weights **0**; not product-on |
| Templates | gta5, valorant, cs2, fortnite, apex, minecraft, lol, other | Genre hints ≠ event detectors |

---

## Eval census (do not treat Clutch scores as GT)

| Asset | Rows | Rated |
| --- | ---: | ---: |
| `eval/labels-v2.csv` | 30 (`gta-online-1`) | **0** |
| `eval/wayin-zias-iceman.csv` | 15 | 15 (competitor proxies; historical overlap 7/15) |
| `eval/benchmark-2h-labels.csv` | 46 | **0** |
| Caption geometry | 6 videos | Boxes only |
| Private multigame sheets (audit) | ~55 | 0 on agent hosts |

**Hard rule.** ClutchClips AI rating / sub-scores are **model outputs**, not ground truth. Wayin overlap is competitor-reference, not gaming quality GT.

---

## Gaps vs OpusClip-class gaming event detection

Public competitor claims are marketing docs only (COMPETITIVE-ANALYSIS; feature-gap store doc). Summary matrix:

| Capability | OpusClip / Wayin / Eklipse (public docs) | ClutchClips main |
| --- | --- | --- |
| Dialogue / ASR highlights | Documented | Partial (Whisper + judge) |
| Loudness / reaction proxies | Documented | RMS / flux / bursts / chat_motion |
| Named game sounds | Claimed by some | Weight-0 adapters only |
| HUD / kill-feed / score OCR | Claimed by gaming specialists | Empty regions |
| Title-specific events (kill, clutch, goal) | Marketed | Templates + judge_focus only |
| NL prompt clipping that changes nomination | Documented | Prompt steers judge; nomination set largely fixed |
| Virality as view probability | Vendor “viral scores” | **Rejected** — sub-scores only, weights 0 for unvalidated signals |

---

## Owner blockers before claims

Rate labels-v2; supply held-out media + consent; sound/HUD second labels; keep experimental weights at 0 until precision floors (PHASE1-FINDINGS). No GPU rental from this audit.
