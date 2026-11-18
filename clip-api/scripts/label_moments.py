#!/usr/bin/env python3
"""Fill the eval set v2 sheet with moments to rate, so labelling is rating, not hunting. See eval/README.md.

  python scripts/label_moments.py select <video> <out.json> [--duration 0-90]
      Run the pipeline's moment selection on a local video (no AI judge, no rendering, nothing uploaded) and write
      its moments, best first, as a run file (`system: clutchclips`). Seconds for a 2-hour video.

  python scripts/label_moments.py wayin <source video> <folder of Wayin clips> <out.json> [--ranks <ranks.csv>]
      Find where each downloaded Wayin clip came from in the source video, by its audio (scripts/align_clips.py:
      its start and its end separately, because Wayin trims dead air), and write a run file (`system: wayin`).
      Rank = Wayin's order: a leading number in each file name (01_..., 02_...), else --ranks, a CSV with a header
      `filename,rank` or `filename,score` (higher score = better). Clips that cannot be placed with confidence are
      listed as refused and left out, never guessed.

  python scripts/label_moments.py add <labels-v2.csv> --vod ID --game GAME --held-out yes|no
                                       [--job <run.json> ...] [--sheet <v1.csv> ...] [--top 30]
      Add the moments of each run file (a `select` or `wayin` output, or a GET /v1/jobs/<id> response) and every
      row of each v1 sheet as rows to rate. `--top` caps runs of our own pipeline (best first); another system's
      run is added whole, because all of it is scored. A moment already covered by a row of that video (overlap
      above half of the shorter one) adds nothing new: its run is appended to the covering row's `source`. So
      running it again adds nothing, and a new run adds only what is new. v1 labels carry over (0 and 1 become 1).
      The sheet is created if missing and written back sorted by video and time. `source` stays in the CSV but
      the labeller never shows it: rating is blind to which system offered a moment.

Then rate the rows in eval/labeller.html, and check the sheet with `python scripts/eval_clips.py <labels-v2.csv>`.
"""
import argparse
import csv
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))      # the clip-api root, for `select`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_clips import OURS, SLUG, V2_FIELDS, hms, load_run, overlap, parse_v2, ranked, seconds  # noqa: E402

CLIP_TYPES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def covering(start: float, end: float, rows: list[dict]) -> dict | None:
    """The row (of one video) that already covers [start, end]: overlap above half of the shorter of the two."""
    return next((r for r in rows if overlap(start, end, seconds(r["start"]), seconds(r["end"]))
                 > min(end - start, seconds(r["end"]) - seconds(r["start"])) / 2), None)


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
        system, clips = load_run(job)
        for i, c in enumerate(ranked(clips)[:top] if system == OURS else ranked(clips), 1):
            out.append((c["start"], c["end"], "", f"{system}:{job.stem}#{c.get('rank') or i}"))
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
    mine = [r for r in rows if r["vod"] == vod]
    for r in mine:
        if (r["game"], r["held_out"]) != (game, held_out):
            print(f"vod {vod} is already game {r['game']}, held_out {r['held_out']} in {path}", file=sys.stderr)
            return 1
    used = {r.get("id") for r in rows}
    n = 1
    added = []
    for start, end, rating, source in candidates(jobs, sheets, top):
        row = covering(start, end, mine)
        if row is not None:
            if source not in (row.get("source") or "").split("+"):
                row["source"] = "+".join(filter(None, [row.get("source"), source]))
            continue
        while f"{vod}-{n}" in used:
            n += 1
        used.add(f"{vod}-{n}")
        row = {"id": f"{vod}-{n}", "vod": vod, "game": game, "start": hms(start), "end": hms(end),
               "rating": rating, "reason": "", "held_out": held_out, "source": source}
        mine.append(row)
        added.append(row)
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
    out.write_text(json.dumps({"system": OURS, "source": video.name, "options": {"duration": duration},
                               "clips": clips}, indent=1))
    print(f"{len(clips)} moments -> {out}")
    return 0


def wayin_ranks(files: list[Path], ranks_csv: Path | None) -> dict[str, int]:
    """file name -> Wayin's rank (1 = their best). Raises ValueError saying what to do when it cannot tell."""
    numbered = {f.name: int(m.group(1)) for f in files if (m := re.match(r"^(\d+)(?=\D)", f.name))}
    if len(numbered) == len(files):
        if len(set(numbered.values())) != len(files):
            raise ValueError("two clip files have the same leading number: number them 01, 02, ... in Wayin's order")
        return {name: i for i, name in enumerate(sorted(numbered, key=numbered.get), 1)}
    if ranks_csv is None:
        unnamed = sorted(f.name for f in files if f.name not in numbered)
        raise ValueError(f"no rank for {', '.join(unnamed[:3])}{' ...' if len(unnamed) > 3 else ''}: start each file "
                         "name with its place in Wayin's list (01_..., 02_...), or give --ranks <csv> with a header "
                         "filename,rank or filename,score")
    with open(ranks_csv, newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        key = "rank" if "rank" in cols else "score" if "score" in cols else None
        if "filename" not in cols or key is None:
            raise ValueError(f"{ranks_csv}: the header must be filename,rank or filename,score")
        given = {r["filename"].strip(): float(r[key]) for r in reader if (r.get(key) or "").strip()}
    missing = sorted(f.name for f in files if f.name not in given)
    if missing:
        raise ValueError(f"{ranks_csv} has no {key} for {', '.join(missing)}")
    order = sorted((f.name for f in files), key=lambda n: given[n] if key == "rank" else -given[n])
    return {name: i for i, name in enumerate(order, 1)}


def wayin(source: Path, folder: Path, out: Path, ranks_csv: Path | None) -> int:
    import align_clips as al                         # numpy and ffmpeg: only this command needs them

    files = sorted(f for f in folder.iterdir() if f.suffix.lower() in CLIP_TYPES and not f.name.startswith("."))
    if not files:
        print(f"no clip files ({', '.join(sorted(CLIP_TYPES))}) in {folder}", file=sys.stderr)
        return 2
    try:
        ranks = wayin_ranks(files, ranks_csv)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(f"reading the audio of {source.name} ...", file=sys.stderr)
    src = al.Source.of(source)
    clips, refused = [], []
    for f in sorted(files, key=lambda f: ranks[f.name]):
        m = al.align(src, f)
        line = (f"#{ranks[f.name]:<3} {f.name}: {m.clip_seconds:.0f} s clip, source {hms(m.start or 0)} to "
                f"{hms(m.end or 0)}, confidence start {m.start_confidence:.2f} end {m.end_confidence:.2f}")
        if m.ok:
            clips.append({"rank": ranks[f.name], "start_sec": m.start, "end_sec": m.end, "file": f.name,
                          "match": m.as_dict()})
            print(line + (f", {m.trimmed:.0f} s cut out" if m.trimmed is not None and m.trimmed >= 1 else ""))
        else:
            refused.append({"rank": ranks[f.name], "file": f.name, "why": m.why, "match": m.as_dict()})
            print(f"{line}  REFUSED: {m.why}")
    out.write_text(json.dumps({"system": "wayin", "source": source.name,
                               "aligned": {"window_s": al.WINDOW, "min_confidence": al.MIN_CONFIDENCE,
                                           "min_margin": al.MIN_MARGIN},
                               "clips": clips, "refused": refused}, indent=1))
    print(f"{len(clips)} of {len(files)} clips placed, {len(refused)} refused -> {out}")
    return 0 if clips else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select", help="the pipeline's moments for a local video, as a run file")
    s.add_argument("video", type=Path)
    s.add_argument("out", type=Path)
    s.add_argument("--duration", default="0-90", help="clip length bucket (moments.BUCKETS); 0-90 is the eval's")
    w = sub.add_parser("wayin", help="place downloaded Wayin clips in the source video, as a run file")
    w.add_argument("source", type=Path)
    w.add_argument("folder", type=Path)
    w.add_argument("out", type=Path)
    w.add_argument("--ranks", type=Path, default=None, help="CSV: filename,rank or filename,score")
    a = sub.add_parser("add", help="add moments to rate to a v2 sheet")
    a.add_argument("labels", type=Path)
    a.add_argument("--vod", required=True, help="short id for the video, e.g. gta-rp-1")
    a.add_argument("--game", required=True, help="gta-rp, gta-online, or the game, e.g. valorant")
    a.add_argument("--held-out", required=True, choices=["yes", "no"])
    a.add_argument("--job", type=Path, action="append", default=[], help="a run file (repeat for each system)")
    a.add_argument("--sheet", type=Path, action="append", default=[], help="a v1 sheet (id,start,end,label,...)")
    a.add_argument("--top", type=int, default=30, help="moments taken from each of our runs, best first")
    args = ap.parse_args(argv)
    if args.cmd == "select":
        if not args.video.is_file():
            print(f"not a file: {args.video}", file=sys.stderr)
            return 2
        return select(args.video, args.out, args.duration)
    if args.cmd == "wayin":
        if not args.source.is_file() or not args.folder.is_dir():
            print(f"need a source video file and a folder of clips: {args.source}, {args.folder}", file=sys.stderr)
            return 2
        return wayin(args.source, args.folder, args.out, args.ranks)
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
