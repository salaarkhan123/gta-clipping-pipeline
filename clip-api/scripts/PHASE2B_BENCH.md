# Phase 2B bench recipe

Harness: `scripts/bench_phase2b.py`

## What it measures

Local `run_pipeline` wall time on a **synthetic** lavfi stress video (not gaming VOD):

| Config | Purpose |
|---|---|
| `preview-serial` / `full-serial` | RC baseline: `render=preview` vs `render=full`, workers=1 |
| `preview-w1` / `preview-w2` / `preview-w4` | B1 parallel encode (`render_workers`) when present |
| `preview-chat-dense` / `preview-chat-sparse` / `preview-chat-coarse` | A3/CPR-14 `chat_motion_sample` when present |

Each JSON line includes `wall_seconds`, `stages`, `first_clip_sec`, `peak_rss_mb`, `clips`, `nproc`, plus labels `synthetic` / `not gaming`. `extrapolate_2h` is always `inferred`.

## Claims this VM cannot make

- Real **2h gaming VOD**: `not measured`
- **GPU / NVENC**: `pending` when `nvidia-smi` is missing

## Commands

```bash
# RC baseline (this branch = release/step2-candidate tip)
python scripts/bench_phase2b.py --generate --minutes 10 --out-dir /tmp/p2b \
  --configs preview-serial,full-serial --max-clips 8 --transcriber none \
  --jsonl /tmp/p2b/rc-baseline.jsonl

# B1 workers (checkout with render_workers)
python scripts/bench_phase2b.py --video /tmp/p2b/synthetic_10m.mp4 \
  --configs preview-w1,preview-w2 --max-clips 8 --transcriber none \
  --jsonl /tmp/p2b/b1-workers.jsonl
```
