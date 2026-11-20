# ClutchClips performance research

Independent research initiative. Goal: reach and eventually exceed Wayin and OpusClip on processing speed, highlight detection, editing, and UX, with a gaming specialization. This directory holds research only. It does not change production dependencies or PR #218.

## Status

Research pack drafted on branch `cursor/performance-research-6ad0` (2026-11-20). No production code changes. No merge to `main`. No deploy. Awaiting owner review before any implementation.

## Claim legend

Every factual claim in these docs carries one label in the same sentence or table cell:

| Label | Meaning |
|---|---|
| `measured` | Timed or scored on named hardware with named inputs |
| `verified` | Observed in our code or docs (file path cited) |
| `inferred` | Follows from verified structure; cost not re-timed here |
| `hypothesis` | Plausible but untested |
| `public-source` | Taken from a public page, LICENSE, or README on a dated read |
| `not measured` | Intentionally blank until hardware or owner OK |

## Hardware for this run

| Item | Value | Label |
|---|---|---|
| Cloud Agent VM | 4 vCPU, ~15 GiB RAM | measured 2026-11-20 |
| NVIDIA GPU | none (`nvidia-smi` missing) | measured |
| ffmpeg | 6.1.1 (Ubuntu package) | measured |
| Baseline product code | PR #218 head `release/step2-candidate` (read-only) | verified |
| Docs branch base | `main` | verified |

Full 2-hour VOD benches and any GPU / paid cloud runs need explicit owner approval. Until then those rows stay `not measured`.

## North-star targets (research objectives)

From SPEC.md §14 and the owner research brief. These are objectives to test, not predetermined conclusions.

| Metric | Research target | SPEC §14 |
|---|---|---|
| 2-hour video processing | under 5 minutes | ≤10 min (stretch 5) |
| First clips available | under 90 seconds | progressive results |
| Individual clip rendering | under 2 minutes | 1080p export ≤30 s |
| Editor loading (assets ready) | under 2 seconds | product UX |
| Repeat processing | reuse transcripts and signals | U1 / Heard on #218 |
| Highlight detection | measurable improvement over eval baseline | U5 / eval set |
| Infrastructure cost | sustainable across subscription tiers | owner OK on pricing |

Historical droplet baseline (`measured`, SPEC 2026-11-15): 2-hour VOD → 10 clips in **932.7 s** (transcribe 257 s, render 578 s).

## Documents

| File | Contents |
|---|---|
| [REPOSITORY-EVALUATION.md](REPOSITORY-EVALUATION.md) | External repos, licenses, production fit |
| [ARCHITECTURE-AUDIT.md](ARCHITECTURE-AUDIT.md) | Current pipeline, PR #218 deltas, bottlenecks |
| [COMPETITIVE-ANALYSIS.md](COMPETITIVE-ANALYSIS.md) | Wayin and OpusClip (public sources only) |
| [BENCHMARK-RESULTS.md](BENCHMARK-RESULTS.md) | Harness, configs, results and gaps |
| [GPU-INFRASTRUCTURE.md](GPU-INFRASTRUCTURE.md) | NVDEC/NVENC and decode options vs S5 #99 |
| [COST-ANALYSIS.md](COST-ANALYSIS.md) | Cost per video-hour estimates |
| [INTEGRATION-ROADMAP.md](INTEGRATION-ROADMAP.md) | Recommendation matrix and PR-sized roadmap |
| [bench/](bench/) | Harness notes (not wired into production) |

## Decision trail

Append-only log: `.audit/performance-research.tsv` (committed so a reviewer can audit the run).

## Sacred existing work (do not replace)

- Quality eval set: `clip-api/eval/`
- Wayin parity: `docs/PARITY.md`
- OpusClip parity plan (on #218): `docs/parity-opusclip.md`
- Understanding tickets: #101 (timeline), #199 (named sounds), #202 (HUD OCR)

Gaming-highlight research here proposes models that feed those tickets. It does not retune eval labels.
