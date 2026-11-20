# Benchmark results

Claim labels follow [RESEARCH.md](RESEARCH.md).

## 1. Harness

| Tool | Purpose | Label |
|---|---|---|
| `clip-api/scripts/bench_pipeline.py` | End-to-end `run_pipeline` on one local video | verified |
| `clip-api/scripts/job_timings.py` | Stage timings vs SPEC targets (2h→600s, 4h→900s) | verified |
| `clip-api/scripts/eval_clips.py` | precision@20, precision@40, recall | verified |
| `docs/performance-research/bench/cpu-microbench-12s.json` | ffmpeg-only stage microbench on this VM | measured 2026-11-20 |

## 2. Hardware configurations

| Config | Specs | Used for |
|---|---|---|
| Production droplet (historical) | DigitalOcean `s-4vcpu-8gb`, Docker image | SPEC §10 B 2h baseline (`measured` 2026-11-15) |
| This research VM | 4 vCPU, ~15 GiB RAM, **no NVIDIA GPU**, ffmpeg 6.1.1 | CPU microbench only (`measured` 2026-11-20) |
| Owner GPU / 16-vCPU render worker | SPEC setup B / S5 #99 | `not measured` — needs owner OK |

## 3. Historical end-to-end baseline (droplet)

Source: SPEC.md §10 B / §14. Input: `GTA_Benchmark_2Hours.mkv` (~2:00:18, 1080p).

| Run | Clips | Total s | Transcribe s | Render s | Label |
|---|---|---|---|---|---|
| A | 3 | 675.4 | 200.4 | (remainder) | measured |
| B | 10 | **932.7** | **257.0** | **578.4** | measured |

Implied ~57.8 s/clip render on droplet (`inferred` from run B). Gap to research target (2h under 5 min with 30–50 clips) is large on both wall time and clip count (`inferred`).

## 4. CPU microbench (this VM, synthetic 12 s)

Fixture: ffmpeg `testsrc` 1280×720@30 + sine, 12 s. **Not** a gaming VOD. Results in [bench/cpu-microbench-12s.json](bench/cpu-microbench-12s.json).

| Stage | Seconds | × realtime | Label |
|---|---|---|---|
| Audio extract 16 kHz mono | ~0.06 | ~197× | measured |
| Sparse decode `fps=2` | ~0.20 | ~60× | measured |
| Keyframes only (`-skip_frame nokey`) | ~0.06 | ~190× | measured |
| Preview 540×960 ultrafast CRF28 | ~0.41 | ~29× | measured |
| Full encode veryfast CRF20 | ~0.78 | ~15× | measured |

**Caveats (`hypothesis` if extrapolated):** synthetic content encodes much easier than gameplay; filter graphs (split layouts, ASS, loudness) are absent; 2h linear scale is invalid for chat_motion and ASR.

## 5. Metrics still `not measured` (gated)

| Metric | Blocker |
|---|---|
| 2h end-to-end on PR #218 head | Long VOD + owner eval files not on this VM; storage |
| Time to first clip under 90 s | Needs preview-first job on realistic VOD |
| Individual clip render under 2 min / SPEC 30 s export | Needs render worker or GPU |
| Editor load under 2 s | Needs browser timing with warm assets |
| Highlight precision/recall delta | Needs eval set run; do not retune labels here |
| GPU NVDEC/NVENC / Whisper CUDA | No GPU; paid host needs OK |
| Concurrent multi-job throughput | Needs staging load test |
| Cost $/video-hour on production | See COST-ANALYSIS estimates |

## 6. Prior supporting measurements (cite only)

| Observation | Source | Label |
|---|---|---|
| M4: 1080×1920 veryfast ~6.3 s/clip; 540×960 ultrafast ~3.0 s; 8 parallel previews ~8 s wall | `docs/super-board/runs/2026-11-15-autonomous.md` | measured (prior) |
| `chat_motion` can inflate long VOD wall time ~6.5× in local bench | SPEC §10 B | measured (prior) |
| S1 progressive: first clip watchable ~41% through run | `docs/super-board/runs/2026-11-16-swarm.md` | measured (prior) |

## 7. Achievability of research targets (current evidence)

| Target | Achievable? | Basis |
|---|---|---|
| 2h under 5 minutes | **Unknown / unlikely on current 4-vCPU serial full-render path** | measured 932.7 s for 10 clips; 30–50 clips would be worse if serial (`inferred`) |
| First clip under 90 s | **Plausible with preview/`none` + early on_clip on #218** | hypothesis; `not measured` on this run |
| Clip render under 2 min | **Yes for short clips on droplet-class CPU**; SPEC 30 s export needs faster host or NVENC | inferred from ~58 s/clip full; M4 ~6 s |
| Editor under 2 s when ready | **Plausible**; not proven | not measured |
| Transcript/signal reuse | **Feature exists on #218 (`Heard`)** | verified; hit-rate not measured |
| Highlight quality up | **Requires eval runs + weight-0 signal PRs** | not measured here |
| Sustainable cost | See COST-ANALYSIS | estimate |

## 8. Reproduction

```bash
# Microbench only (no product deps)
ffmpeg -y -f lavfi -i testsrc=size=1280x720:rate=30 -f lavfi -i sine=frequency=1000:sample_rate=44100 \
  -t 12 -c:v libx264 -pix_fmt yuv420p -c:a aac /tmp/cc-bench-12s.mp4
# Then re-run the stages listed in cpu-microbench-12s.json with the same ffmpeg flags.

# Full pipeline (needs clip-api deps + a real video you own):
cd clip-api && python scripts/bench_pipeline.py /path/to/video.mp4
# Job timings after an API job:
python scripts/job_timings.py job.json --md
```
