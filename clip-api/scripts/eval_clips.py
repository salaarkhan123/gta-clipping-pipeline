#!/usr/bin/env python3
"""Score one clip run against a labelled moment sheet (the quality eval set).

Usage: python scripts/eval_clips.py <labels.csv> <job.json> [--json]

<job.json> is the response of GET /v1/jobs/<job_id> (its "clips" have start_sec / end_sec). Each clip is matched
to the labelled row it overlaps most (at least 10 s, or a third of the clip if shorter). Labels: 3 = would post
as-is, 2 = good, 1 = weak, 0 = junk; empty labels are ignored.

Reports: good_rate (clips on a 2 or 3), mean label, great_recall (share of 3-rated moments some clip found),
unlabelled clips (on no labelled row: the sheet missed them, or they are new), duplicates (two clips on the same
labelled moment, or less than 60 s apart) and clips per quarter of the video.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

GOOD, GREAT, DUP_GAP = 2, 3, 60.0


def seconds(t: str) -> float:
    parts = [float(p) for p in str(t).strip().split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def load_labels(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            label = (r.get("label") or "").strip()
            if label == "":
                continue
            rows.append({"id": r.get("id") or str(len(rows) + 1), "start": seconds(r["start"]),
                         "end": seconds(r["end"]), "label": int(float(label))})
    return rows


def load_clips(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    clips = data.get("clips", data) if isinstance(data, dict) else data
    return [{"start": float(c["start_sec"] if "start_sec" in c else c["start"]),
             "end": float(c["end_sec"] if "end_sec" in c else c["end"]),
             "title": c.get("title")} for c in clips]


def overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def match(clip: dict, rows: list[dict]) -> dict | None:
    need = min(10.0, (clip["end"] - clip["start"]) / 3)
    best = max(rows, key=lambda r: overlap(clip["start"], clip["end"], r["start"], r["end"]), default=None)
    if best is None or overlap(clip["start"], clip["end"], best["start"], best["end"]) < need:
        return None
    return best


def score(rows: list[dict], clips: list[dict], duration: float | None = None) -> dict:
    duration = duration or max([r["end"] for r in rows] + [c["end"] for c in clips] + [1.0])
    matched = [match(c, rows) for c in clips]
    labels = [m["label"] for m in matched if m]
    great = [r for r in rows if r["label"] >= GREAT]
    found_great = {m["id"] for m in matched if m and m["label"] >= GREAT}
    dup = 0
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            same_row = matched[i] is not None and matched[i] is matched[j]
            gap = max(0.0, max(clips[i]["start"], clips[j]["start"]) - min(clips[i]["end"], clips[j]["end"]))
            if same_row or gap < DUP_GAP:
                dup += 1
    quarters = [0, 0, 0, 0]
    for c in clips:
        quarters[min(3, int(4 * c["start"] / duration))] += 1
    return {
        "clips": len(clips),
        "good_rate": round(sum(1 for x in labels if x >= GOOD) / len(clips), 3) if clips else 0.0,
        "mean_label": round(sum(labels) / len(labels), 2) if labels else None,
        "great_recall": round(len(found_great) / len(great), 3) if great else None,
        "great_found": f"{len(found_great)} of {len(great)}",
        "unlabelled": sum(1 for m in matched if m is None),
        "duplicate_pairs": dup,
        "per_quarter": quarters,
        "per_clip": [{"start": c["start"], "end": c["end"], "title": c["title"],
                      "row": m["id"] if m else None, "label": m["label"] if m else None}
                     for c, m in zip(clips, matched)],
    }


def report(s: dict) -> str:
    lines = [f"clips {s['clips']} · good rate {s['good_rate']:.0%} · mean label {s['mean_label']} · "
             f"great moments found {s['great_found']}",
             f"unlabelled {s['unlabelled']} · duplicate pairs {s['duplicate_pairs']} · per quarter {s['per_quarter']}"]
    for c in s["per_clip"]:
        t = int(c["start"])
        lines.append(f"  {t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}  label {c['label'] if c['label'] is not None else '-'}"
                     f"  row {c['row'] or '-'}  {c['title'] or ''}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("labels", type=Path)
    ap.add_argument("job", type=Path)
    ap.add_argument("--duration", type=float, default=None, help="video length in seconds (default: from the data)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows, clips = load_labels(args.labels), load_clips(args.job)
    if not rows:
        print("no labelled rows yet: fill in the label column first", file=sys.stderr)
        return 2
    s = score(rows, clips, args.duration)
    print(json.dumps(s) if args.json else report(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
