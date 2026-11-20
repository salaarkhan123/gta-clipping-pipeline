# Cost analysis

Estimates only. No credit or list-price changes. Owner OK required before money PRs.

Claim labels follow [RESEARCH.md](RESEARCH.md).

## 1. Current operating shape (verified / SPEC)

| Piece | Role | Source |
|---|---|---|
| API + DB + analysis droplet | `s-4vcpu-8gb` class historically | SPEC §10 B measured host |
| `WORKER_CONCURRENCY` | 1 default, max 2 | `config.py` verified |
| Storage | Spaces / S3 via `storage.py` | verified |
| AI judge | Anthropic API per candidate | verified `ai.py` |
| Hosted ASR | optional behind config (setup B) | SPEC §14 verified design |
| Render worker | 16-vCPU CPU-optimized (setup B) | SPEC §14; owner provisions |

## 2. Public list prices used (date reads)

Prices move. Re-check before any money decision.

| Resource | Public ballpark | Label | Read |
|---|---|---|---|
| DO `s-4vcpu-8gb` | ~$24/mo on-demand class (confirm current) | public-source / verify at buy time | 2026-11-20 research (approximate) |
| DO CPU-optimized 16 vCPU | higher; confirm in DO calculator | public-source | needs live quote |
| DO GPU droplet (e.g. L40S/RTX class) | significantly higher $/hr | public-source | needs live quote + OK |
| Spaces storage | ~$0.02/GB-mo + bandwidth tiers | public-source | confirm |
| Anthropic judge tokens | per model pricing page | public-source | per ticket |
| Hosted ASR (Deepgram/Assembly/etc.) | per audio minute | public-source | #167 |

Exact dollar figures for GPU/CPU SKUs should be pasted from the vendor calculator into a follow-up when the owner approves a quote pull. Rows without a pasted quote stay **approximate**.

## 3. Cost model per video hour (framework)

Let:

- `T_cpu` = analysis wall minutes on analysis host × host $/min
- `T_render` = sum of encode minutes × render host $/min (or NVENC host)
- `C_asr` = ASR $/audio-minute × minutes transcribed (candidate windows or whole)
- `C_llm` = judge + llm_pass $/job
- `C_store` = GB-months for source + previews + exports × storage rate
- `C_egress` = download bandwidth

**Historical structure (`measured` time split):** render dominated (~60%), ASR ~30%, so shifting previews off the critical path and/or NVENC changes the dominant term (`inferred`).

### Illustrative scenarios (hypothesis, not quotes)

| Scenario | Analysis | Render | ASR | Relative $/h |
|---|---|---|---|---|
| A Today-like | 4 vCPU serial full encode | same host | local Whisper | baseline |
| B Preview-first + export on demand | same | encode only chosen clips | local | lower render energy (`inferred`) |
| C Setup B | 4 vCPU analysis | 16 vCPU render pool | local or hosted | higher fixed; better latency |
| D GPU NVENC | small analysis | GPU encode | local/CUDA | higher fixed; lower encode minutes (`hypothesis`) |

## 4. Progressive delivery economics

Shipping preview/`none` first (`verified` #218 design) means:

- Users can reject bad clips before paying full encode CPU (`inferred`).
- Storage grows with `.preview.mp4` plus optional export (`inferred`).
- Credit design already prices preview in-job and export separately in contracts (`verified` CONTRACTS / #218) — changing amounts is a money PR.

## 5. Tier sustainability (proposal only)

| Tier pressure | Risk | Mitigation proposal |
|---|---|---|
| Starter heavy 2h VODs | 4 vCPU queue pileup | concurrency 1; preview-first; timeframe option |
| Pro parallel projects | worker starvation | S4 render role; queue depth SLOs |
| Scale | margin on judge+ASR | hosted ASR only with Terms disclosure; judge pool caps already on #218 |

Do **not** change pack prices from this doc.

## 6. Open measurements

| Item | Status |
|---|---|
| $/video-hour on production with current image | not measured |
| Judge token $ per 2h job at JUDGE_THREADS=4 | not measured (needs log sample) |
| Spaces GB per 2h source + 40 previews | not measured |
| GPU encode $ vs 16-vCPU encode $ | not measured (needs OK) |
