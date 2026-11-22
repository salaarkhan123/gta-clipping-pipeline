#!/usr/bin/env python3
"""Brand kit preview assets: one short real render per shape and layout, made by the clipping engine.

The brand kit page shows what a kit's layout looks like at each shape (9:16, 4:5, 1:1, 16:9). This script makes
those pictures once, at build time: for every shape and every layout the API offers for it, the engine
(run_pipeline, the same call a job makes) renders a few seconds of an approved wide clip with captions, the hook
and every edit switched off; the page draws the kit's caption and hook styles on top. Two-panel layouts are
rendered with the camera on top and below. Neighbouring layouts use different footage, and each shape starts on
a different clip.

  python scripts/make_kit_previews.py --seg SEG_DIR --public web-src/public/media/kit-preview [--only 1:1]

SEG_DIR holds the approved source segments (<name>.mp4, wide, with sound) that scripts/make_site_media.py fetched.
Writes <shape>-<layout>[-<camera>].mp4 (H.264, muted), .jpg (poster) and manifest.json (the shape lib/media.ts
reads) with the footage credit of every clip. Never calls a paid AI. Use only footage the owner may publish.
Exit 0 = ok, 1 = a render failed, 2 = bad input.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.pipeline import Deadline, PipelineError, PipelineOptions, probe, run_pipeline  # noqa: E402
from app.pipeline.ff import SAFE_IN, run  # noqa: E402
from app.routes_meta import clip_options  # noqa: E402

# What GET /v1/options lists per shape, so the pictures cover exactly the layouts the page offers. Provisional
# layouts are listed only while the API's PROVISIONAL_LAYOUTS switch is on: run this with the API's setting.
LAYOUTS_BY_ASPECT: dict = clip_options()["layout"]["by_aspect"]
PERMISSION = "owner-confirmed 2026-11-18"
# Approved sources (scripts/site_media/sources.json and the owner's second batch). `cam`: the engine finds the
# streamer's camera in this piece, so the layouts that give the camera its own panel have something to show. (xQc
# and iiTzTimmy have a camera on screen, but the detector does not pick it up in these seconds: they are used for
# the one-panel layouts.)
SOURCES = {
    "forza-m2": {"game": "Forza Horizon 5", "creator": "TmarTn2", "url": "https://www.youtube.com/watch?v=78kntDlbjMI", "cam": True},
    "xqc-m1": {"game": "GTA VI", "creator": "xQc", "url": "https://www.youtube.com/watch?v=VWNBp6SIEPU", "cam": False},
    "timmy-m1": {"game": "Valorant", "creator": "iiTzTimmy", "url": "https://www.youtube.com/watch?v=ovyMOe_017I", "cam": False},
    "cod-nick-m1": {"game": "Call of Duty: Warzone", "creator": "NICKMERCS", "url": "https://www.youtube.com/watch?v=eZ2rIdme-3c", "cam": True},
    "ninja-m1": {"game": "Fortnite", "creator": "Ninja", "url": "https://www.youtube.com/watch?v=ogbIEh-4rYw", "cam": True},
    "tgg2-m3": {"game": "GTA VI", "creator": "TGG", "url": "https://www.youtube.com/watch?v=1GtrjKhSwzM", "cam": True},
    "fc27-fpgg-m1": {"game": "EA SPORTS FC 27", "creator": "FP Good Game", "url": "https://www.youtube.com/watch?v=GURcXM3OcPE", "cam": False},
}
ALIAS_OF = {"split": "split2", "fill": "full"}                # older names: rendered only where the newer one is not offered
TWO_PANELS = {"split", "split2", "screen_first", "gameplay_a", "gameplay_b"}
NEEDS_CAM = TWO_PANELS | {"auto", "pip"}
SIZE = {"9:16": (360, 640), "4:5": (432, 540), "1:1": (480, 480), "16:9": (640, 360)}
START, SECONDS = 4.0, 5.0                                     # the part of each segment that is shown
PIECE = 12.0                                                  # seconds handed to the engine
MAX_BYTES, POSTER_BYTES = 330_000, 45_000
CAP = 600


def ffmpeg(*args) -> None:
    run(["ffmpeg", "-loglevel", "error", "-y", *[str(a) for a in args]], cap=CAP)


def variants(aspect: str) -> list[tuple[str, str | None]]:
    """(layout, camera) pairs to render for a shape, in the order the page lists the layouts."""
    out = []
    for layout in LAYOUTS_BY_ASPECT[aspect]:
        if ALIAS_OF.get(layout) in LAYOUTS_BY_ASPECT[aspect]:
            continue
        out += [(layout, "bottom"), (layout, "top")] if layout in TWO_PANELS else [(layout, None)]
    return out


def item_name(aspect: str, layout: str, camera: str | None) -> str:
    """The file and manifest id, under the layout's newer name (the page asks for "split" as "split2")."""
    return "-".join(x for x in (aspect.replace(":", "x"), ALIAS_OF.get(layout, layout), camera) if x)


def assign(aspects: list[str]) -> dict:
    """Which source each render uses: camera layouts rotate through the sources with a camera, the others through
    all of them starting with the camera-free one, and each shape starts one further along."""
    with_cam = [s for s, v in SOURCES.items() if v["cam"]]
    every = [s for s, v in SOURCES.items() if not v["cam"]] + with_cam
    plan = {}
    for a_i, aspect in enumerate(aspects):
        cam_i, any_i, last = a_i * 2, a_i, None
        for layout, camera in variants(aspect):
            pool = with_cam if layout in NEEDS_CAM else every
            i = cam_i if layout in NEEDS_CAM else any_i
            if camera == "top":                               # the same clip as its "bottom" twin
                plan[(aspect, layout, camera)] = plan[(aspect, layout, "bottom")]
                continue
            if pool[i % len(pool)] == last:
                i += 1
            last = pool[i % len(pool)]
            plan[(aspect, layout, camera)] = last
            if layout in NEEDS_CAM:
                cam_i = i + 1
            else:
                any_i = i + 1
    return plan


def encode(src: Path, out: Path, size: tuple[int, int]) -> dict:
    w, h = size
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps=30,format=yuv420p"
    mp4, crf = out.with_suffix(".mp4"), 28
    while True:
        ffmpeg("-t", SECONDS, *SAFE_IN, "-i", src, "-an", "-vf", vf, "-c:v", "libx264", "-profile:v", "high", "-preset", "slow",
               "-movflags", "+faststart", "-crf", crf, mp4)
        if mp4.stat().st_size <= MAX_BYTES or crf >= 42:
            break
        crf += 3
    poster = out.with_suffix(".jpg")
    for q in (4, 7, 11, 16, 22):                              # mjpeg quality: lower is better
        ffmpeg("-ss", "1.0", *SAFE_IN, "-i", src, "-frames:v", "1", "-vf", vf.split(",fps")[0], "-c:v", "mjpeg", "-q:v", q, poster)
        if poster.stat().st_size <= POSTER_BYTES:
            break
    return {"src": mp4.name, "poster": poster.name}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seg", type=Path, required=True)
    ap.add_argument("--public", type=Path, required=True)
    ap.add_argument("--only", help="one shape, e.g. 1:1 (the manifest keeps the other shapes' items)")
    args = ap.parse_args(argv)
    missing = [s for s in SOURCES if not (args.seg / f"{s}.mp4").exists()]
    if missing:
        print(f"missing segments in {args.seg}: {', '.join(missing)}", file=sys.stderr)
        return 2
    aspects = [a for a in SIZE if a in LAYOUTS_BY_ASPECT]
    plan = assign(aspects)
    args.public.mkdir(parents=True, exist_ok=True)
    manifest_path = args.public / "manifest.json"
    items = {i["id"]: i for i in json.loads(manifest_path.read_text())["items"]} if manifest_path.exists() else {}
    failed = 0
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        pieces = {}
        for (aspect, layout, camera), source in plan.items():
            if args.only and aspect != args.only:
                continue
            if source not in pieces:                          # the same few seconds of a source for all its renders
                pieces[source] = tmp / f"{source}.mp4"
                ffmpeg("-ss", START, "-t", PIECE, *SAFE_IN, "-i", args.seg / f"{source}.mp4", "-c:v", "libx264", "-preset", "veryfast",
                       "-crf", "18", "-c:a", "aac", pieces[source])
            item_id = item_name(aspect, layout, camera)
            options = PipelineOptions(limit=1, max_clips=1, clip_length=int(PIECE) - 2, max_side=540, vertical=True, aspect=aspect, layout=layout,
                                      camera=camera, split_ratio=0.6 if camera else None, facecam_region="auto", captions=False,
                                      hook_overlay=False, thumbnail_text=False, flash_forward=False, tighten=False, punch_zoom=False)
            work = tmp / item_id
            work.mkdir()
            try:
                clips = run_pipeline(pieces[source], options, work, transcriber=None, deadline=Deadline(CAP))
                if not clips:
                    raise PipelineError("no_clip", "the engine returned no clip")
                files = encode(Path(clips[0].video_path), args.public / item_id, SIZE[aspect])
            except PipelineError as e:
                print(f"FAILED {item_id} ({source}): {e}", file=sys.stderr)
                failed += 1
                continue
            info, meta = probe(args.public / files["src"]), SOURCES[source]
            items[item_id] = {"id": item_id, "label": f"{layout} at {aspect}", "kind": "video", **files, "width": info.width, "height": info.height,
                              "duration_sec": round(info.duration, 2), "aspect": aspect, "layout": layout, "camera": camera, "game": meta["game"],
                              "credit": f"Footage: {meta['creator']}" if meta["creator"] else None,
                              "source": {"id": source, "creator": meta["creator"], "url": meta["url"]}, "commercial_permission": PERMISSION}
            print(f"ok {item_id} <- {source} ({(args.public / files['src']).stat().st_size // 1000} kB)", flush=True)
    order = [item_name(a, l, c) for a in aspects for l, c in variants(a)]
    credits = sorted({(i["source"]["creator"], i["source"]["url"]) for i in items.values() if i["source"]["creator"]})
    manifest_path.write_text(json.dumps({"section": "kit-preview", "version": 1, "permission": PERMISSION,
                                         "credits": [{"creator": c, "url": u} for c, u in credits],
                                         "items": [items[i] for i in order if i in items]}, indent=1) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
