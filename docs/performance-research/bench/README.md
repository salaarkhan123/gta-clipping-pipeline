# Benchmark harness notes

Research-only. Scripts here document how to reproduce baselines. They are not added to production `requirements.txt` or Docker images by this initiative.

## Existing product tools (use these first)

| Script | Purpose |
|---|---|
| `clip-api/scripts/bench_pipeline.py` | Time `run_pipeline` on one local video; one JSON line |
| `clip-api/scripts/job_timings.py` | Compare job stage timings vs SPEC targets |
| `clip-api/scripts/eval_clips.py` | precision@20, precision@40, recall on eval set |

## This VM

4 vCPU, ~15 GiB RAM, no NVIDIA GPU (measured 2026-11-20). Suitable for short fixture micro-benches only.
