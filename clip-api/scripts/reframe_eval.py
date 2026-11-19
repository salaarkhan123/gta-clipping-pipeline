"""Reframing checks on the owner's eval footage (docs/REFRAME_EVAL.md). Run it through ~/ClutchClips-eval/heavy.sh.

    python scripts/reframe_eval.py facecam [--dir DIR] [--labels FILE] [--before] [--json OUT]
        Facecam detection against the hand-labelled set: scene right or wrong, IoU of the box, seconds taken.
        --before turns the looser second look off (the detector as it was).
    python scripts/reframe_eval.py crop [--dir DIR] [--labels FILE] [--aspect 9:16] [--json OUT]
        For each hand-labelled subject point, the clip around it is tracked: share of points inside the crop for a
        still centred crop and for the moving one, and the moving crop's speed and jitter (px per output frame).
    python scripts/reframe_eval.py boxes SRC START END [--aspect 9:16] [--layout auto] [--game ID]
        One clip's detected camera, layout and Reframe boxes v1 (with the crop path), as JSON: what the website's
        reframe demo draws.
    python scripts/reframe_eval.py sheet OUT.jpg CLIP.mp4 [CLIP.mp4 ...]
        A contact sheet of each clip's first, middle and last frames, one row per clip, for the owner to judge.

Footage is never committed: the labels name files relative to --dir.
"""
import argparse
import json
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline import action as A  # noqa: E402
from app.pipeline import facecam as F  # noqa: E402
from app.pipeline import layouts as L  # noqa: E402
from app.pipeline.ff import probe  # noqa: E402

LABELS = ROOT / "eval" / "reframe_labels.json"


def iou(a, b) -> float:
    """Intersection over union of two [x, y, w, h] boxes."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def score_facecam(labels: dict, base: Path, before: bool = False) -> list[dict]:
    """One row per labelled source: what the detector found against the label."""
    if before:
        F.weak_faces = lambda _frames: []
    rows = []
    for name, lab in labels["sources"].items():
        path = base / lab["file"]
        if not path.is_file():
            rows.append({"source": name, "error": "missing file"})
            continue
        info = probe(path)
        frames = F.sample_gray(path, info, 12)
        t0 = time.time()
        scene = F.classify(frames)
        took = time.time() - t0
        want, got = lab.get("facecam"), scene.cam
        rows.append({"source": name, "want_scene": lab["scene"], "got_scene": scene.kind,
                     "scene_ok": scene.kind == lab["scene"],
                     "iou": round(iou(want, got), 3) if want and got else (1.0 if not want and not got else 0.0),
                     "got": got, "want": want, "confidence": scene.confidence, "detect_seconds": round(took, 2)})
    return rows


def facecam_summary(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    with_cam = [r for r in ok if r["want"]]
    return {"sources": len(ok), "scene_accuracy": round(sum(r["scene_ok"] for r in ok) / max(1, len(ok)), 3),
            "cams": len(with_cam), "cams_found": sum(1 for r in with_cam if r["got"]),
            "mean_iou_on_cams": round(sum(r["iou"] for r in with_cam) / max(1, len(with_cam)), 3),
            "iou_ge_0.7": sum(r["iou"] >= 0.7 for r in with_cam),
            "false_cams": sum(1 for r in ok if not r["want"] and r["got"]),
            "mean_detect_seconds": round(sum(r["detect_seconds"] for r in ok) / max(1, len(ok)), 2)}


def score_crop(labels: dict, base: Path, aspect: str, window: float = 4.0) -> list[dict]:
    """Each labelled subject point: inside the still centred crop, inside the moving one, and the path's motion."""
    rows = []
    for pt in labels["subjects"]:
        lab = labels["sources"][pt["source"]]
        path = base / lab["file"]
        info = probe(path)
        a, b = max(0.0, pt["t"] - window), min(info.duration, pt["t"] + window)
        cam = lab.get("facecam")
        plan = L.compose(info.width, info.height, "full", aspect, scene="gameplay_cam" if cam else "gameplay",
                         cam=cam)
        (panel,) = [p for p in plan.panels if p.kind == "gameplay"][:1] or [plan.panels[0]]
        tr = A.track(path, a, b, exclude=[cam] if cam else (), game=lab.get("game"))
        moved = A.crop_path(plan, tr, b - a)
        mp = [p for p in moved.panels if p.kind == "gameplay"][0]
        sx = pt["x"] * info.width
        t = pt["t"] - a
        x_still = panel.src[0]
        x_move = A.at([(tt, r[0]) for tt, r in mp.path], t) if mp.path else mp.src[0]
        speed, jitter = A.motion([(tt, r[0]) for tt, r in mp.path] if mp.path else None, b - a, cuts=tr.cuts)
        rows.append({"source": pt["source"], "t": pt["t"], "x": pt["x"],
                     "still_in": x_still <= sx <= x_still + panel.src[2],
                     "follow_in": x_move <= sx <= x_move + mp.src[2],
                     "moved": bool(mp.path) or mp.src != panel.src, "speed": round(speed, 2),
                     "jitter": round(jitter, 3), "track_seconds": round(tr.seconds, 2),
                     "kinds": {k: tr.kinds.count(k) for k in set(tr.kinds)}})
    return rows


def crop_summary(rows: list[dict]) -> dict:
    n = max(1, len(rows))
    tracked = [r for r in rows if r["track_seconds"] > 0]
    return {"points": len(rows), "still_inside": round(sum(r["still_in"] for r in rows) / n, 3),
            "follow_inside": round(sum(r["follow_in"] for r in rows) / n, 3),
            "mean_speed_px_per_frame": round(sum(r["speed"] for r in rows) / n, 2),
            "mean_jitter_px_per_frame": round(sum(r["jitter"] for r in rows) / n, 3),
            "max_jitter_px_per_frame": max((r["jitter"] for r in rows), default=0.0),
            "track_seconds_per_8s_window": round(sum(r["track_seconds"] for r in tracked) / max(1, len(tracked)), 2)}


def clip_boxes(src: Path, start: float, end: float, aspect: str, layout: str, game: str | None) -> dict:
    """The camera, layout and boxes of one clip, as the renderer would draw it with follow on."""
    info = probe(src)
    scene = F.detect_scene(src, info)
    plan = L.compose(info.width, info.height, layout, aspect, scene=scene.kind, cam=scene.cam, face=scene.face,
                     confidence=scene.confidence)
    tr = A.track(src, start, end, exclude=[scene.cam] if scene.cam else (), game=game)
    plan = A.crop_path(plan, tr, end - start)
    return {"source": str(src), "start": start, "end": end, "aspect": aspect, "requested": layout,
            "note": plan.note, "boxes": L.reframe_boxes(plan, game=game),
            "track": {"seconds": round(tr.seconds, 2), "cuts": list(tr.cuts),
                      "kinds": {k: tr.kinds.count(k) for k in set(tr.kinds)}}}


def contact_sheet(out: Path, clips: list[Path], width: int = 270) -> None:
    """First, middle and last frame of each clip side by side, one row per clip, the file name on the left."""
    from PIL import Image, ImageDraw
    rows = []
    for clip in clips:
        info = probe(clip)
        frames = []
        for t in (0.2, info.duration / 2, max(0.0, info.duration - 0.3)):
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-protocol_whitelist", "file,pipe",
                                  "-i", str(clip), "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2pipe",
                                  "-vcodec", "png", "-"], capture_output=True, timeout=120).stdout
            frames.append(Image.open(BytesIO(raw)).convert("RGB"))
        rows.append((clip.stem, frames))
    h = max(f.height for _, fs in rows for f in fs)
    label_w = 180
    sheet = Image.new("RGB", (label_w + 3 * (width + 6), len(rows) * (h + 6)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, (name, frames) in enumerate(rows):
        y = i * (h + 6)
        d.text((6, y + 6), name[:28], fill=(230, 230, 230))
        for k, f in enumerate(frames):
            sheet.paste(f, (label_w + k * (width + 6), y))
    sheet.save(out, quality=85)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("facecam", "crop"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=Path, default=Path.home() / "ClutchClips-eval")
        p.add_argument("--labels", type=Path, default=LABELS)
        p.add_argument("--json", type=Path)
        p.add_argument("--before", action="store_true")
        p.add_argument("--aspect", default="9:16")
    bx = sub.add_parser("boxes")
    bx.add_argument("src", type=Path)
    bx.add_argument("start", type=float)
    bx.add_argument("end", type=float)
    bx.add_argument("--aspect", default="9:16")
    bx.add_argument("--layout", default="auto")
    bx.add_argument("--game")
    sh = sub.add_parser("sheet")
    sh.add_argument("out", type=Path)
    sh.add_argument("clips", type=Path, nargs="+")
    a = ap.parse_args()
    if a.cmd == "sheet":
        contact_sheet(a.out, a.clips)
        return
    if a.cmd == "boxes":
        print(json.dumps(clip_boxes(a.src, a.start, a.end, a.aspect, a.layout, a.game), indent=1))
        return
    labels = json.loads(a.labels.read_text())
    if a.cmd == "facecam":
        rows, s = score_facecam(labels, a.dir, a.before), None
        s = facecam_summary(rows)
    else:
        rows = score_crop(labels, a.dir, a.aspect)
        s = crop_summary(rows)
    for r in rows:
        print(json.dumps(r))
    print(json.dumps(s))
    if a.json:
        a.json.write_text(json.dumps({"rows": rows, "summary": s}, indent=1))


if __name__ == "__main__":
    main()
