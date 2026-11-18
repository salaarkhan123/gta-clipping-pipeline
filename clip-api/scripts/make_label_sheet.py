#!/usr/bin/env python3
"""Write a labelling sheet (CSV) of candidate moments for one video, for the quality eval set.

Usage: python scripts/make_label_sheet.py <video> <out.csv> [--top 40] [--per-quarter 10] [--length 30]

Candidates come from the pipeline's own cheap signal (audio loudness against its rolling baseline): the strongest
`--top` windows over the whole video, plus the strongest `--per-quarter` windows inside each quarter, so parts the
signal undervalues (see the 0.2e coverage check) still reach the person labelling. Overlapping windows are merged.
The owner rates each row 0-3 and adds rows for good moments the sheet missed. See eval/README.md.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import WEIGHTS  # noqa: E402
from app.pipeline.ff import probe  # noqa: E402
from app.pipeline.signals import audio_rms_db, baseline_z, normalise  # noqa: E402
from app.pipeline.windows import pick_windows  # noqa: E402

FIELDS = ["id", "start", "end", "label", "what_happens", "notes", "source"]


def hms(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def candidates(score: np.ndarray, duration: float, length: int, top: int, per_quarter: int) -> list[tuple[float, float, str]]:
    """(start, end, source) windows: global top plus each quarter's top, overlaps merged, sorted by time."""
    found = [(s, e, "top") for s, e, _m in pick_windows(score, length, top, duration)]
    q = len(score) / 4
    for k in range(4):
        a, b = int(k * q), int((k + 1) * q)
        part = np.zeros_like(score)
        part[a:b] = score[a:b]
        found += [(s, e, f"q{k + 1}") for s, e, _m in pick_windows(part, length, per_quarter, duration)]
    found.sort()
    merged: list[list] = []
    for s, e, src in found:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
            if src not in merged[-1][2].split("+"):
                merged[-1][2] += "+" + src
        else:
            merged.append([s, e, src])
    return [(s, e, src) for s, e, src in merged]


def write_sheet(rows: list[tuple[float, float, str]], out: Path) -> None:
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for i, (s, e, src) in enumerate(rows, 1):
            w.writerow({"id": i, "start": hms(s), "end": hms(e), "label": "", "what_happens": "", "notes": "",
                        "source": src})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--per-quarter", type=int, default=10)
    ap.add_argument("--length", type=int, default=30)
    args = ap.parse_args(argv)
    if not args.video.is_file():
        print(f"not a file: {args.video}", file=sys.stderr)
        return 2
    info = probe(args.video)
    n = int(info.duration) + 1
    db = audio_rms_db(args.video)
    if not db:
        print("no audio track: nothing to score", file=sys.stderr)
        return 1
    score = WEIGHTS["audio"] * normalise(baseline_z(db, floor=1.0), n)
    rows = candidates(score, info.duration, args.length, args.top, args.per_quarter)
    write_sheet(rows, args.out)
    print(f"{len(rows)} moments, {sum(e - s for s, e, _ in rows) / 60:.0f} min to watch -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
