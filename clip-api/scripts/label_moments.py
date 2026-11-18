#!/usr/bin/env python3
"""Fill the eval set v2 sheet with moments to rate, so labelling is rating, not hunting. See eval/README.md.

  python scripts/label_moments.py select <video> <out.json> [--duration 0-90]
      Run the pipeline's moment selection on a local video (no AI judge, no rendering, nothing uploaded) and write
      its moments, best first, in the job format eval_clips.py reads. About a minute for a 2-hour video.

  python scripts/label_moments.py add <labels-v2.csv> --vod ID --game GAME --held-out yes|no
                                       [--job <job.json> ...] [--sheet <v1.csv> ...] [--top 30]
      Add the `--top` best moments of each job file (a GET /v1/jobs/<id> response or a `select` output) and every
      row of each v1 sheet as rows to rate. A moment already covered by a row of that video (overlap above half of
      the shorter one) is skipped, so running it again, or with a new run, adds only what is new. v1 labels carry
      over (0 and 1 become 1). The sheet is created if missing and written back sorted by video and time.

Then rate the rows in eval/labeller.html, and check the sheet with `python scripts/eval_clips.py <labels-v2.csv>`.
"""
import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))      # the clip-api root, for `select`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_clips import SLUG, V2_FIELDS, hms, load_clips, overlap, parse_v2, ranked, seconds  # noqa: E402


def covered(start: float, end: float, rows: list[dict]) -> bool:
    return any(overlap(start, end, r["start"], r["end"]) > min(end - start, r["end"] - r["start"]) / 2 for r in rows)


def read_sheet(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_sheet(path: Path, rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: (r["vod"], seconds(r["start"]), seconds(r["end"])))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=V2_FIELDS, extrasaction="ignore", lineterminator="\n")   # as labeller.html
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in V2_FIELDS})


def candidates(jobs: list[Path], sheets: list[Path], top: int) -> list[tuple[float, float, str, str]]:
    """(start, end, rating, source) for every moment offered, in the order offered."""
    out = []
    for job in jobs:
        for i, c in enumerate(ranked(load_clips(job))[:top], 1):
            out.append((c["start"], c["end"], "", f"{job.stem}#{i}"))
    for sheet in sheets:
        with open(sheet, newline="") as f:
            for r in csv.DictReader(f):
                label = (r.get("label") or "").strip()
                rating = "" if label == "" else str(max(1, int(float(label))))
                out.append((seconds(r["start"]), seconds(r["end"]), rating, f"v1:{sheet.stem}#{r.get('id', '')}"))
    return out


def add(path: Path, vod: str, game: str, held_out: str, jobs: list[Path], sheets: list[Path], top: int) -> int:
    rows = read_sheet(path)
    if rows:
        _parsed, errors = parse_v2(path)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            print(f"fix {path} first", file=sys.stderr)
            return 1
    mine = [{"start": seconds(r["start"]), "end": seconds(r["end"])} for r in rows if r["vod"] == vod]
    for r in rows:
        if r["vod"] == vod and (r["game"], r["held_out"]) != (game, held_out):
            print(f"vod {vod} is already game {r['game']}, held_out {r['held_out']} in {path}", file=sys.stderr)
            return 1
    used = {r.get("id") for r in rows}
    n = 1
    added = []
    for start, end, rating, source in candidates(jobs, sheets, top):
        if covered(start, end, mine):
            continue
        while f"{vod}-{n}" in used:
            n += 1
        used.add(f"{vod}-{n}")
        mine.append({"start": start, "end": end})
        added.append({"id": f"{vod}-{n}", "vod": vod, "game": game, "start": hms(start), "end": hms(end),
                      "rating": rating, "reason": "", "held_out": held_out, "source": source})
    write_sheet(path, rows + added)
    minutes = sum(seconds(r["end"]) - seconds(r["start"]) for r in added) / 60
    print(f"added {len(added)} moments to {vod} ({minutes:.0f} min of video to rate) -> {path}")
    return 0


def select(video: Path, out: Path, duration: str) -> int:
    """The pipeline's own moments for a local video, best first, without the judge and before any rendering."""
    from app.pipeline import PipelineOptions, run_pipeline   # heavy: only this command needs the pipeline

    chosen = []

    class Chosen(Exception):
        pass

    def on_moments(moments):
        chosen.extend(moments)
        raise Chosen                     # stop before rendering: only the selection is wanted

    with tempfile.TemporaryDirectory(prefix="select_") as tmp:
        try:
            run_pipeline(video, PipelineOptions(duration=duration), Path(tmp), on_moments=on_moments)
        except Chosen:
            pass
    clips = [{"rank": i, "start_sec": m.start, "end_sec": m.end, "score": round(m.score, 4), "kind": m.kind}
             for i, m in enumerate(chosen, 1)]
    out.write_text(json.dumps({"source": video.name, "options": {"duration": duration}, "clips": clips}, indent=1))
    print(f"{len(clips)} moments -> {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select", help="the pipeline's moments for a local video, as a job file")
    s.add_argument("video", type=Path)
    s.add_argument("out", type=Path)
    s.add_argument("--duration", default="0-90", help="clip length bucket (moments.BUCKETS); 0-90 is the eval's")
    a = sub.add_parser("add", help="add moments to rate to a v2 sheet")
    a.add_argument("labels", type=Path)
    a.add_argument("--vod", required=True, help="short id for the video, e.g. gta-rp-1")
    a.add_argument("--game", required=True, help="gta-rp, gta-online, or the game, e.g. valorant")
    a.add_argument("--held-out", required=True, choices=["yes", "no"])
    a.add_argument("--job", type=Path, action="append", default=[])
    a.add_argument("--sheet", type=Path, action="append", default=[], help="a v1 sheet (id,start,end,label,...)")
    a.add_argument("--top", type=int, default=30, help="moments taken from each job file, best first")
    args = ap.parse_args(argv)
    if args.cmd == "select":
        if not args.video.is_file():
            print(f"not a file: {args.video}", file=sys.stderr)
            return 2
        return select(args.video, args.out, args.duration)
    for name in ("vod", "game"):
        if not SLUG.match(getattr(args, name)):
            print(f"--{name} {getattr(args, name)!r}: a short id (a-z, 0-9, dashes)", file=sys.stderr)
            return 2
    if not args.job and not args.sheet:
        print("give at least one --job or --sheet", file=sys.stderr)
        return 2
    return add(args.labels, args.vod, args.game, args.held_out, args.job, args.sheet, args.top)


if __name__ == "__main__":
    sys.exit(main())
