#!/usr/bin/env python3
"""Contact sheet of clip thumbnails, the old way next to the new one, for moments of a local video.

Usage: python scripts/thumb_sheet.py <video> <moments.csv> <out_dir> [--limit 20] [--aspect 9:16] [--layout auto]
                                     [--source-framing] [--hooks hooks.txt]

<moments.csv> has `start` and `end` columns (seconds or h:mm:ss), like eval/benchmark-2h-labels.csv; an optional
`hook` column is the text to set (otherwise lines of --hooks are used in turn). For each moment:
- old: what the pipeline made before: the rendered clip's frame at 1 s, 360 px wide (the hook burned into the
  first 2.5 s, as with the AI's hook on; the captions, which need a transcript, are left out);
- new: thumbs.make_thumbnail, with the moment's own loudness.
Writes <out_dir>/sheet.jpg (pairs, old left), the single images, and timings.json (seconds and CPU seconds per
thumbnail, bytes on disk). Nothing is uploaded; the scratch renders are deleted.
"""
import argparse
import csv
import json
import resource
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.pipeline import PipelineOptions, probe  # noqa: E402
from app.pipeline.captions import FONT_DIR, IMPACT_FILE  # noqa: E402
from app.pipeline.facecam import resolve_facecam  # noqa: E402
from app.pipeline.ff import run  # noqa: E402
from app.pipeline.render import render_clip  # noqa: E402
from app.pipeline.signals import audio_rms_db  # noqa: E402
from app.pipeline.thumbs import make_thumbnail  # noqa: E402

HOOKS = ["He did NOT see that coming", "Worst getaway driver in Los Santos", "Cops gave up", "This went wrong fast",
         "Clean escape", "How did that work", "Never trust the bridge", "Full send off the pier", "Wrong car bro",
         "Chat called it", "He really thought", "One in a million crash"]
CELL = 270          # the width of each picture on the sheet


def seconds(value: str) -> float:
    parts = [float(p) for p in str(value).strip().split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def old_thumb(clip: Path, out: Path) -> None:
    """The thumbnail as the pipeline made it before thumbs.py: the rendered clip's frame at 1 s, 360 px wide."""
    run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", clip, "-frames:v", "1", "-vf", "scale=360:-2", out],
        cap=60)


def cpu() -> float:
    a, b = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime + a.ru_stime + b.ru_utime + b.ru_stime


def sheet(pairs: list[tuple[str, Path, Path]], out: Path) -> None:
    """Rows of old | new, two pairs a row, each picture CELL wide (its own aspect kept), labelled."""
    font = ImageFont.truetype(str(FONT_DIR / IMPACT_FILE), 18)
    tiles = []
    for label, old, new in pairs:
        ims = [Image.open(p).convert("RGB") for p in (old, new)]
        ims = [im.resize((CELL, round(CELL * im.height / im.width))) for im in ims]
        h = max(im.height for im in ims) + 30
        tile = Image.new("RGB", (2 * CELL + 10, h), (24, 24, 24))
        d = ImageDraw.Draw(tile)
        for k, (im, name) in enumerate(zip(ims, ("OLD", "NEW"))):
            tile.paste(im, (k * (CELL + 10), 30))
            d.text((k * (CELL + 10) + 4, 4), f"{label} {name}", font=font, fill=(230, 230, 230))
        tiles.append(tile)
    per_row = 2
    rows = [tiles[i:i + per_row] for i in range(0, len(tiles), per_row)]
    width = per_row * (2 * CELL + 10) + (per_row - 1) * 30
    height = sum(max(t.height for t in r) + 20 for r in rows)
    canvas = Image.new("RGB", (width, height), (10, 10, 10))
    y = 0
    for r in rows:
        for k, t in enumerate(r):
            canvas.paste(t, (k * (2 * CELL + 40), y))
        y += max(t.height for t in r) + 20
    canvas.save(out, "JPEG", quality=88)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("moments", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--layout", default="auto")
    ap.add_argument("--source-framing", action="store_true", help="no reframing: the source's own shape")
    ap.add_argument("--hooks", type=Path, help="one hook per line, used in turn")
    args = ap.parse_args(argv)
    hooks = [x.strip() for x in args.hooks.read_text().splitlines() if x.strip()] if args.hooks else HOOKS
    rows = list(csv.DictReader(args.moments.open()))
    step = max(1, len(rows) // args.limit)
    rows = rows[::step][:args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    info = probe(args.video)
    opts = PipelineOptions(facecam_region="auto", layout=args.layout, aspect=args.aspect,
                           vertical=not args.source_framing)
    layout, facecam = resolve_facecam(args.video, info, opts)
    pairs, timings = [], []
    with tempfile.TemporaryDirectory(prefix="thumbsheet_") as tmp:
        for k, row in enumerate(rows):
            start, end = seconds(row["start"]), seconds(row["end"])
            hook = row.get("hook") or hooks[k % len(hooks)]
            label = f"#{row.get('id', k + 1)}"
            old, new, clip = args.out / f"old-{k:02d}.jpg", args.out / f"new-{k:02d}.jpg", Path(tmp) / "c.mp4"
            render_clip(args.video, start, start + 1.5, clip, src_w=info.width, src_h=info.height,
                        vertical=opts.vertical, zoom=1.0, chat="none", words=[], font="DejaVu Sans", layout=layout,
                        facecam=facecam, aspect=args.aspect, hook=hook, has_audio=info.has_audio, loudness=False)
            t0, c0 = time.perf_counter(), cpu()
            old_thumb(clip, old)
            old_sec, old_cpu = time.perf_counter() - t0, cpu() - c0
            clip.unlink()
            levels = audio_rms_db(args.video, start=int(start), length=end - int(start) + 1) if info.has_audio else []
            loud = [-90.0] * int(start) + levels                   # by source second, as the pipeline keeps them
            t0, c0 = time.perf_counter(), cpu()
            made = make_thumbnail(args.video, info, start, end, new, options=opts, layout=layout, facecam=facecam,
                                  text=hook, loudness=loud)
            new_sec, new_cpu = time.perf_counter() - t0, cpu() - c0
            made.frame.unlink(missing_ok=True)
            pairs.append((label, old, new))
            timings.append({"moment": label, "start": start, "end": end, "hook": hook,
                            "old_sec": round(old_sec, 3), "old_cpu": round(old_cpu, 3), "old_bytes": old.stat().st_size,
                            "new_sec": round(new_sec, 3), "new_cpu": round(new_cpu, 3), "new_bytes": new.stat().st_size,
                            "thumbnail": {k: v for k, v in made.record.items() if k != "canvas"}})
            print(json.dumps(timings[-1]), flush=True)
    sheet(pairs, args.out / "sheet.jpg")
    (args.out / "timings.json").write_text(json.dumps(timings, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
