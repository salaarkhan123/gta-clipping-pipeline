#!/usr/bin/env python3
"""Where one job spent its time, and how that compares with an earlier job. This is the number every speed
change reports.

Usage: python scripts/job_timings.py <job.json> [--baseline <older-job.json>] [--md] [--json]

<job.json> is the response of GET /v1/jobs/<job_id>:
    curl -s $API/v1/jobs/<job_id> -H "authorization: Bearer $KEY" > job.json

Prints the end-to-end time (queue + run) against the target for a video of that length, then one row per stage
with its share of the run and, with --baseline, the change. Jobs from before stage timing existed only have the
coarse stages shown in the dashboard; when either job is one of those, both are compared on the coarse stages.
--md prints a table to paste into a PR. Exit 0 = ok, 2 = the file has no timings (the job has not finished).
"""
import argparse
import json
import sys
from pathlib import Path

# Fine pipeline stage -> the coarse stage the dashboard shows.
COARSE = {"download": "downloading", "probe": "probing", "facecam_detect": "probing", "chat_motion": "chat_motion",
          "audio_signal": "audio", "transcribe_rough": "transcribing", "transcribe_final": "transcribing",
          "judge_frames": "judging", "judge_ai": "judging", "dead_air": "rendering", "render": "rendering",
          "thumbnail": "rendering", "titles": "writing_titles", "store": "uploading"}
TARGETS = ((2 * 3600, 600.0), (4 * 3600, 900.0))    # the goal: a 2 h video in 10 min, a 4 h video in 15 min


def target_sec(source_sec: float) -> float:
    """Allowed end-to-end seconds for a video this long: through the two goal points, proportional below 2 h."""
    (d0, t0), (d1, t1) = TARGETS
    if source_sec <= d0:
        return t0 * source_sec / d0
    return t0 + (t1 - t0) * (source_sec - d0) / (d1 - d0)


def load(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    result = data.get("result") or {}
    if "elapsed_sec" not in result:
        raise ValueError(f"{path}: no timings in this job (status {data.get('status')}); it has to finish first")
    counts = result.get("counts") or {}
    speed, elapsed = result.get("speed_x") or 0, result["elapsed_sec"]
    source = counts.get("source_sec") or (speed * elapsed)             # older jobs: back out of the speed factor
    return {"job_id": data.get("job_id"), "status": data.get("status"), "elapsed": elapsed,
            "queue": result.get("queue_sec", 0.0), "total": result.get("total_sec", elapsed), "source": source,
            "clips": counts.get("clips", len(data.get("clips") or [])), "counts": counts,
            "fine": result.get("stages"), "coarse": result.get("timings") or {}}


def coarse_of(job: dict) -> dict:
    if not job["fine"]:
        return dict(job["coarse"])
    out: dict[str, float] = {}
    for name, sec in job["fine"].items():
        key = COARSE.get(name, name)
        out[key] = out.get(key, 0.0) + sec
    return out


def compare(job: dict, base: dict | None = None) -> dict:
    fine = bool(job["fine"]) and (base is None or bool(base["fine"]))
    stages = job["fine"] if fine else coarse_of(job)
    before = (base["fine"] if fine else coarse_of(base)) if base else {}
    names = sorted(set(stages) | set(before), key=lambda n: -(stages.get(n, 0.0) or before.get(n, 0.0)))
    rows = [{"stage": n, "sec": round(stages.get(n, 0.0), 1), "share": round(stages.get(n, 0.0) / max(job["elapsed"], 0.1), 3),
             **({"before": round(before.get(n, 0.0), 1), "change": round(stages.get(n, 0.0) - before.get(n, 0.0), 1)} if base else {})}
            for n in names]
    other = round(job["elapsed"] - sum(stages.values()), 1)
    if abs(other) >= 0.5:
        rows.append({"stage": "(not in a stage)", "sec": other, "share": round(other / max(job["elapsed"], 0.1), 3),
                     **({"before": round(base["elapsed"] - sum(before.values()), 1),
                         "change": round(other - (base["elapsed"] - sum(before.values())), 1)} if base else {})})
    goal = target_sec(job["source"])
    c = job["counts"]
    rates = {}
    if job["fine"] and job["fine"].get("render") and c.get("clips"):
        rates["render_sec_per_clip"] = round(job["fine"]["render"] / c["clips"], 1)
        if c.get("rendered_sec"):
            rates["render_x_realtime"] = round(c["rendered_sec"] / job["fine"]["render"], 2)
    asr = (job["fine"] or {}).get("transcribe_rough", 0.0) + (job["fine"] or {}).get("transcribe_final", 0.0)
    heard = c.get("transcribed_rough_sec", 0) + c.get("transcribed_final_sec", 0)
    if asr and heard:
        rates["transcribe_x_realtime"] = round(heard / asr, 1)
    return {"job_id": job["job_id"], "detail": "fine" if fine else "coarse", "source_min": round(job["source"] / 60, 1),
            "clips": job["clips"], "queue_sec": job["queue"], "run_sec": job["elapsed"], "total_sec": job["total"],
            "target_sec": round(goal, 1), "meets_target": job["total"] <= goal, "rates": rates, "stages": rows,
            **({"baseline": {"job_id": base["job_id"], "total_sec": base["total"], "clips": base["clips"],
                             "change_sec": round(job["total"] - base["total"], 1)}} if base else {})}


def render(c: dict, md: bool = False) -> str:
    over = c["total_sec"] - c["target_sec"]
    verdict = "meets the target" if c["meets_target"] else f"misses the target by {over / 60:.1f} min"
    head = [f"{c['source_min']} min of video, {c['clips']} clips: {c['total_sec']:.0f} s end to end "
            f"({c['queue_sec']:.0f} s queued + {c['run_sec']:.0f} s running). Target {c['target_sec']:.0f} s: {verdict}."]
    if "baseline" in c:
        b = c["baseline"]
        head.append(f"Before: {b['total_sec']:.0f} s for {b['clips']} clips. Change: {b['change_sec']:+.0f} s.")
    if c["rates"]:
        head.append(" · ".join(f"{k.replace('_', ' ')} {v}" for k, v in c["rates"].items()))
    with_base = "baseline" in c
    cols = ["stage", "seconds", "share"] + (["before", "change"] if with_base else [])
    table = [[r["stage"], f"{r['sec']:.1f}", f"{r['share']:.0%}"] + ([f"{r['before']:.1f}", f"{r['change']:+.1f}"] if with_base else [])
             for r in c["stages"]]
    if md:
        lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
        lines += ["| " + " | ".join(row) + " |" for row in table]
    else:
        widths = [max(len(x) for x in col) for col in zip(cols, *table)]
        lines = ["  ".join(x.ljust(w) if i == 0 else x.rjust(w) for i, (x, w) in enumerate(zip(row, widths))) for row in [cols, *table]]
    return "\n".join(head + [""] + lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job", type=Path)
    ap.add_argument("--baseline", type=Path, help="an earlier job to compare with")
    ap.add_argument("--md", action="store_true", help="markdown table for a PR")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        c = compare(load(args.job), load(args.baseline) if args.baseline else None)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    print(json.dumps(c) if args.json else render(c, args.md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
