#!/usr/bin/env python3
"""Measure the on-screen text of a clip: caption timing against the transcript, reading speed, and how often
captions or the hook cover a HUD element, the webcam or the streamer's head. docs/CONTRACTS.md "Captions and
on-screen text v1" defines each number and its limit.

The checks read the ASS file the renderer burns in (render.text_track), so they measure what ships.

Usage (from clip-api/, heavy steps through ~/ClutchClips-eval/heavy.sh):
  python scripts/caption_checks.py prepare --out DIR [--only forza,valorant]
      Transcribe each window in scripts/caption_eval_boxes.json (small.en, local) and find each video's camera
      and face. Writes DIR/<game>.json. Needs the eval videos in ~/ClutchClips-eval (EVAL_DIR overrides).
  python scripts/caption_checks.py measure --data DIR [--json OUT]
      The numbers, per game and overall, for 9:16 auto and the 16:9 original frame. Light: no video is read.
  python scripts/caption_checks.py sheet --data DIR --out DIR [--only gta5] [--aspect 9:16]
      Render each window as a preview, cut a contact sheet per game (DIR/<game>-<aspect>.jpg), delete the renders.

Exit 0 = ok, 1 = a limit is broken (measure), 2 = bad input.
"""
import argparse
import json
import math
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import captions as C  # noqa: E402
from app.pipeline import layouts as L  # noqa: E402
from app.pipeline import render as R  # noqa: E402

BOXES = Path(__file__).resolve().parent / "caption_eval_boxes.json"
EVAL_DIR = Path(os.environ.get("EVAL_DIR", Path.home() / "ClutchClips-eval"))
FPS = 30
# The limits (docs/CONTRACTS.md). A word may appear a little before it is said (a reader reads ahead); it should
# light up as it is said.
LIMITS = {"active_p95_ms": 120, "appear_early_p95_ms": 600, "cps_max": 20.0, "min_cue_s": 0.3, "max_words": 3,
          "dead_air_share": 0.02, "overlap_share": 0.0}
TEXT_STYLES = ("Cap", "Hook")       # the styles that draw text a viewer reads (CapShadow, Tag draw it again)


@dataclass
class Event:
    layer: int
    start: float
    end: float
    style: str
    name: str
    text: str

    @property
    def shown(self) -> str:
        return re.sub(r"\{[^}]*\}", "", self.text)


def _secs(t: str) -> float:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def read_ass(path: Path) -> tuple[dict, list[Event]]:
    """(styles by name: their fields, the Dialogue events) of an ASS file."""
    styles, events, fmt = {}, [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Format:") and fmt is None:
            fmt = [f.strip() for f in line[7:].split(",")]
        elif line.startswith("Style:"):
            values = [v.strip() for v in line[6:].split(",")]
            styles[values[0]] = dict(zip(fmt, values))
        elif line.startswith("Dialogue:"):
            p = line[9:].split(",", 9)
            events.append(Event(int(p[0]), _secs(p[1]), _secs(p[2]), p[3], p[4], p[9]))
    return styles, events


def norm(word: str) -> str:
    return re.sub(r"[^A-Z0-9'*]", "", word.upper().replace("’", "'"))


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, math.ceil(q * len(s)) - 1)]


# ---------- timing ----------
def timing(words, events: list[Event]) -> dict:
    """When each transcript word first shows on screen and when it lights up as the word being said, against
    when it is said (ms; negative = early). A word lights up in an event named "w<index>" (captions.py names
    the events of a style that marks the word being said); a style that marks none has no active numbers."""
    caps = sorted((e for e in events if e.style == "Cap"), key=lambda e: e.start)
    keys = [norm(w[2]) for w in words]
    appear: dict[int, float] = {}
    p = 0
    for e in caps:
        for token in (norm(t) for t in e.shown.split()):
            while p < len(keys) and not keys[p]:
                p += 1
            if not token or p >= len(keys):
                continue
            # Look a few words ahead: a word the style does not show (a lone dash) must not stall the match.
            for q in range(p, min(len(keys), p + 4)):
                if keys[q] == token:
                    appear[q] = e.start
                    p = q + 1
                    break
    active: dict[int, float] = {}
    for e in caps:
        m = re.fullmatch(r"w(\d+)", e.name)
        if m:
            i = int(m.group(1))
            active[i] = min(active.get(i, e.start), e.start)
    said = {i: w[0] for i, w in enumerate(words) if keys[i]}
    app = [(appear[i] - said[i]) * 1000 for i in said if i in appear]
    act = [(active[i] - said[i]) * 1000 for i in said if i in active]
    return {"words": len(said), "shown_share": round(len(appear) / max(1, len(said)), 3),
            "appear_early_p95_ms": round(-_pct([min(0.0, a) for a in app], 0.05)),
            "appear_abs_mean_ms": round(sum(abs(a) for a in app) / max(1, len(app))),
            "active_share": round(len(act) / max(1, len(said)), 3),
            "active_abs_mean_ms": round(sum(abs(a) for a in act) / max(1, len(act))) if act else None,
            "active_p95_ms": round(_pct([abs(a) for a in act], 0.95)) if act else None}


def dead_air(words, events: list[Event], gap: float = 0.6, hold: float = 0.3) -> dict:
    """Seconds a caption is on screen while nobody speaks: outside every word (plus `hold` after it) and every
    pause between words shorter than `gap`."""
    speech, cur = [], None
    for s, e, _ in sorted(words):
        if cur and s - cur[1] < gap:
            cur[1] = max(cur[1], e)
        else:
            if cur:
                speech.append(cur)
            cur = [s, e]
    if cur:
        speech.append(cur)
    speech = [(s, e + hold) for s, e in speech]
    shown = _union([(e.start, e.end) for e in events if e.style == "Cap"])
    total = sum(e - s for s, e in shown)
    covered = sum(max(0.0, min(e, b) - max(s, a)) for s, e in shown for a, b in speech)
    return {"caption_s": round(total, 2), "dead_air_s": round(total - covered, 2),
            "dead_air_share": round((total - covered) / total, 3) if total else 0.0}


def _union(spans):
    out = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


# ---------- reading ----------
def cues(events: list[Event]) -> list[tuple[float, float, str]]:
    """The captions a viewer reads: consecutive Cap events with the same words are one caption."""
    out = []
    for e in sorted((e for e in events if e.style == "Cap"), key=lambda e: e.start):
        text = " ".join(e.shown.split())
        if out and out[-1][2] == text and e.start - out[-1][1] < 0.05:
            out[-1] = (out[-1][0], max(out[-1][1], e.end), text)
        else:
            out.append((e.start, e.end, text))
    return out


def reading(events: list[Event]) -> dict:
    found = cues(events)
    if not found:
        return {"cues": 0}
    cps = [len(t.replace(" ", "")) / max(0.05, e - s) for s, e, t in found]
    return {"cues": len(found),
            "words_max": max(len(t.split()) for _, _, t in found),
            "over_max_words_share": round(sum(len(t.split()) > LIMITS["max_words"] for *_, t in found) / len(found), 3),
            "cps_p95": round(_pct(cps, 0.95), 1),
            "over_cps_share": round(sum(c > LIMITS["cps_max"] for c in cps) / len(found), 3),
            "flash_share": round(sum(e - s < LIMITS["min_cue_s"] for s, e, _ in found) / len(found), 3)}


# ---------- placement ----------
def _tags(text: str, name: str) -> list[str]:
    return re.findall(r"\\" + name + r"\(?([-\d.,]+)\)?", text)


def text_rect(e: Event, styles: dict, play: tuple[int, int]) -> tuple[float, float, float, float] | None:
    """Where an event's letters are on the frame (x0, y0, x1, y1), outline included, at their final size."""
    st = styles.get(e.style)
    words = e.shown.split()
    if not st or not words:
        return None
    size = float(st["Fontsize"])
    outline = float(st["Outline"])
    if st["Fontname"] == C.IMPACT_FONT:
        em = size / (C.ANTON_ASCENT + C.ANTON_DESCENT)
        scale = float((_tags(e.text, "fscx") or ["100"])[-1]) / 100
        width = C.impact_width([C.impact_text(w) for w in words], em) * scale
        half = (C.ANTON_CAP * em / 2 + outline) * scale
        pos = _tags(e.text, "pos")
        x, y = (float(v) for v in pos[0].split(",")) if pos else (play[0] / 2, play[1] * C.LOWER_THIRD)
        y += (C.ANTON_ASCENT - C.ANTON_DESCENT - C.ANTON_CAP) / 2 * em * scale      # the middle of the capitals
        return x - width / 2, y - half, x + width / 2, y + half
    # Any other font: about half an em per letter, wrapped inside the margins, hung from MarginV.
    left, right, margin = float(st["MarginL"]), float(st["MarginR"]), float(st["MarginV"])
    room = play[0] - left - right
    width = min(room, 0.55 * size * len(e.shown))
    lines = math.ceil(0.55 * size * len(e.shown) / room)
    height = lines * size * 1.15 + 2 * outline
    x = left + room / 2
    align = int(st["Alignment"])
    top = margin - outline if align >= 7 else play[1] - margin - height + outline
    return x - width / 2 - outline, top, x + width / 2 + outline, top + height


def _hit(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def overlap(events: list[Event], styles: dict, play: tuple[int, int], keep_out: list) -> dict:
    """The share of frames with text on screen in which a caption or the hook covers a keep-out box."""
    rects = [(e, text_rect(e, styles, play)) for e in events if e.style in TEXT_STYLES]
    rects = [(e, r) for e, r in rects if r]
    end = max((e.end for e, _ in rects), default=0.0)
    out = {}
    for kind, styles_ in (("caption", ("Cap",)), ("hook", ("Hook",))):
        frames = hits = 0
        for f in range(int(end * FPS) + 1):
            t = f / FPS
            on = [r for e, r in rects if e.style in styles_ and e.start <= t < e.end]
            if on:
                frames += 1
                hits += any(_hit(r, k) for r in on for k in keep_out)
        out[f"{kind}_frames"] = frames
        out[f"{kind}_overlap_share"] = round(hits / frames, 3) if frames else 0.0
    out["out_of_frame"] = sum(r[0] < 0 or r[1] < 0 or r[2] > play[0] or r[3] > play[1] for _, r in rects)
    return out


def keep_out_boxes(plan: L.LayoutPlan | None, boxes: list[dict], src: tuple[int, int]) -> list:
    """The labelled source boxes where they land on the frame (x0, y0, x1, y1), plus the head when the plan
    knows it. In a two-panel layout the camera panel itself is not a keep-out box (captions sit on its seam), but
    the head inside it is."""
    sw, sh = src
    px = [(b["kind"], (b["box"][0] * sw, b["box"][1] * sh, b["box"][2] * sw, b["box"][3] * sh)) for b in boxes]
    if plan is None:
        return [(x, y, x + w, y + h) for _, (x, y, w, h) in px]
    out = [plan.head] if plan.head else []
    for p in plan.panels:
        if p.kind == "camera" and plan.layout in L.TWO_PANEL:
            continue
        if p.kind == "camera":                     # an inset: the whole picture is the person
            out.append((p.out[0], p.out[1], p.out[0] + p.out[2], p.out[1] + p.out[3]))
            continue
        kx, ky = p.out[2] / p.src[2], p.out[3] / p.src[3]
        for _kind, (x, y, w, h) in px:
            x0, y0 = max(x, p.src[0]), max(y, p.src[1])
            x1, y1 = min(x + w, p.src[0] + p.src[2]), min(y + h, p.src[1] + p.src[3])
            if x1 > x0 and y1 > y0:
                out.append((p.out[0] + (x0 - p.src[0]) * kx, p.out[1] + (y0 - p.src[1]) * ky,
                            p.out[0] + (x1 - p.src[0]) * kx, p.out[1] + (y1 - p.src[1]) * ky))
    return [tuple(round(v) for v in b) for b in out]


# ---------- one window ----------
SETUPS = {"9:16": dict(vertical=True, aspect="9:16"), "16:9": dict(vertical=False, aspect="16:9")}


def plan_for(item: dict, setup: str) -> L.LayoutPlan | None:
    if not SETUPS[setup]["vertical"]:
        return None
    sc = item["scene"]
    return L.compose(item["width"], item["height"], "auto", SETUPS[setup]["aspect"], scene=sc["kind"],
                     cam=sc.get("cam"), face=tuple(sc["face"]) if sc.get("face") else None)


def hook_for(words) -> str | None:
    """A stand-in hook for geometry only (no AI call): the first six words said in the window."""
    return " ".join(w[2] for w in words[:6]) or None


def check_window(item: dict, window: dict, setup: str, style: str = "impact", boxes: list | None = None) -> dict:
    words = [tuple(w) for w in window["words"]]
    plan = plan_for(item, setup)
    src = (item["width"], item["height"])
    play = L.ASPECTS[setup] if SETUPS[setup]["vertical"] else src
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cap.ass"
        R.text_track(path, words, src_w=src[0], src_h=src[1], zoom=1.0, chat="none", plan=plan, font="Arial",
                     style=style, hook=hook_for(words), **SETUPS[setup])
        styles, events = read_ass(path)
    keep = keep_out_boxes(plan, boxes if boxes is not None else item["boxes"], src)
    return {"timing": timing(words, events), "dead_air": dead_air(words, events), "reading": reading(events),
            "placement": overlap(events, styles, play, keep), "layout": plan.layout if plan else "original"}


def summarise(results: list[dict]) -> dict:
    """Totals over windows: words and frames weigh in proportion."""
    def wavg(part, key, weight):
        num = sum((r[part][key] or 0) * r[part][weight] for r in results if r[part].get(key) is not None)
        den = sum(r[part][weight] for r in results if r[part].get(key) is not None)
        return round(num / den, 3) if den else None
    return {
        "windows": len(results), "words": sum(r["timing"]["words"] for r in results),
        "appear_early_p95_ms": max((r["timing"]["appear_early_p95_ms"] for r in results), default=0),
        "appear_abs_mean_ms": wavg("timing", "appear_abs_mean_ms", "words"),
        "active_share": wavg("timing", "active_share", "words"),
        "active_p95_ms": max((r["timing"]["active_p95_ms"] or 0 for r in results), default=0),
        "dead_air_share": round(sum(r["dead_air"]["dead_air_s"] for r in results)
                                / max(0.01, sum(r["dead_air"]["caption_s"] for r in results)), 3),
        "cps_p95": max((r["reading"].get("cps_p95", 0) for r in results), default=0),
        "over_cps_share": wavg("reading", "over_cps_share", "cues"),
        "flash_share": wavg("reading", "flash_share", "cues"),
        "over_max_words_share": wavg("reading", "over_max_words_share", "cues"),
        "caption_overlap_share": wavg("placement", "caption_overlap_share", "caption_frames"),
        "hook_overlap_share": wavg("placement", "hook_overlap_share", "hook_frames"),
        "out_of_frame": sum(r["placement"]["out_of_frame"] for r in results),
    }


def broken(total: dict) -> list[str]:
    out = []
    if total["active_share"] is not None and total["active_share"] > 0 and total["active_p95_ms"] > LIMITS["active_p95_ms"]:
        out.append("active_p95_ms")
    for key in ("appear_early_p95_ms",):
        if total[key] > LIMITS[key]:
            out.append(key)
    if total["dead_air_share"] > LIMITS["dead_air_share"]:
        out.append("dead_air_share")
    for key in ("caption_overlap_share", "hook_overlap_share"):
        if (total[key] or 0) > LIMITS["overlap_share"]:
            out.append(key)
    if (total["over_cps_share"] or 0) > 0.05:
        out.append("over_cps_share")
    if total["out_of_frame"]:
        out.append("out_of_frame")
    return out


# ---------- commands ----------
def _labels(only: str | None) -> tuple[int, dict]:
    data = json.loads(BOXES.read_text())
    videos = data["videos"]
    if only:
        videos = {k: v for k, v in videos.items() if k in only.split(",")}
    return data["seconds"], videos


def cmd_prepare(args) -> int:
    from app.config import get_settings
    from app.pipeline.facecam import detect_scene
    from app.pipeline.ff import probe
    from app.pipeline.transcribe import FasterWhisperTranscriber, extract_wav
    seconds, videos = _labels(args.only)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stt = FasterWhisperTranscriber(get_settings().whisper_model)
    for name, label in videos.items():
        src = EVAL_DIR / f"{name}.mp4"
        if not src.is_file():
            print(f"{name}: {src} is missing", file=sys.stderr)
            return 2
        info = probe(src)
        scene = detect_scene(src, info)
        windows = []
        with tempfile.TemporaryDirectory() as tmp:
            for start in label["windows"]:
                wav = Path(tmp) / f"{start}.wav"
                extract_wav(src, start, seconds, wav)
                tr = stt.transcribe(wav)
                windows.append({"start": start, "end": start + seconds,
                                "words": [[round(s, 3), round(e, 3), t] for s, e, t in tr.words]})
                print(f"{name} @{start}: {len(tr.words)} words", flush=True)
        (out / f"{name}.json").write_text(json.dumps({
            "video": name, "game": label["game"], "width": info.width, "height": info.height,
            "scene": {"kind": scene.kind, "cam": scene.cam, "face": list(scene.face) if scene.face else None},
            "boxes": label["boxes"], "windows": windows}, indent=1))
    return 0


def measure(data: Path, style: str = "impact") -> dict:
    report = {}
    for f in sorted(data.glob("*.json")):
        item = json.loads(f.read_text())
        for setup in SETUPS:
            results = [check_window(item, w, setup, style) for w in item["windows"]]
            report.setdefault(setup, {})[item["video"]] = summarise(results)
            report[setup][item["video"]]["layout"] = sorted({r["layout"] for r in results})
    for setup, games in report.items():
        flat = [g for g in games.values()]
        report[setup]["ALL"] = {k: (max(v[k] for v in flat) if k.endswith(("p95_ms", "p95")) else
                                    sum(v[k] for v in flat) if k in ("windows", "words", "out_of_frame") else
                                    round(sum((v[k] or 0) * v["words"] for v in flat) / max(1, sum(v["words"] for v in flat)), 3))
                                for k in flat[0] if k != "layout"}
    return report


def cmd_measure(args) -> int:
    report = measure(Path(args.data), args.style)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1))
    cols = ("words", "appear_early_p95_ms", "active_share", "active_p95_ms", "dead_air_share", "cps_p95",
            "over_cps_share", "flash_share", "caption_overlap_share", "hook_overlap_share", "out_of_frame")
    bad = []
    for setup, games in report.items():
        print(f"\n{setup} ({args.style})\n" + "game".ljust(12) + " ".join(c[:14].rjust(14) for c in cols))
        for game, row in games.items():
            print(game.ljust(12) + " ".join(str(row[c]).rjust(14) for c in cols))
        bad += [f"{setup}:{k}" for k in broken(games["ALL"])]
    print("\nlimits broken: " + (", ".join(bad) if bad else "none"))
    return 1 if bad else 0


def cmd_sheet(args) -> int:
    from PIL import Image, ImageDraw
    from app.pipeline.ff import run
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(Path(args.data).glob("*.json")):
        item = json.loads(f.read_text())
        if args.only and item["video"] not in args.only.split(","):
            continue
        src = EVAL_DIR / f"{item['video']}.mp4"
        for setup in args.aspect.split(","):
            tiles = []
            for w in item["windows"]:
                words = [tuple(x) for x in w["words"]]
                plan = plan_for(item, setup)
                with tempfile.TemporaryDirectory() as tmp:
                    clip = Path(tmp) / "clip.mp4"
                    R.render_clip(src, w["start"], w["end"], clip, src_w=item["width"], src_h=item["height"],
                                  zoom=1.0, chat="none", words=words, font="Arial", style=args.style,
                                  plan=plan, preview=True, hook=hook_for(words), loudness=False, **SETUPS[setup])
                    # Frames where text is on screen: the hook, then while words are being said.
                    times = [1.0] + [s + 0.15 for s, _, _ in words[2::max(1, len(words) // 5)]][:5]
                    for t in times[: args.per_window]:
                        jpg = Path(tmp) / f"{t:.2f}.jpg"
                        run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", clip, "-frames:v", "1",
                             jpg])
                        if jpg.is_file():
                            tiles.append((f"{item['video']} @{w['start'] + t:.0f}s", Image.open(jpg).copy()))
            if not tiles:
                continue
            tw = 270 if setup == "9:16" else 480
            th = round(tw * tiles[0][1].height / tiles[0][1].width)
            cols = 6 if setup == "9:16" else 3
            rows = math.ceil(len(tiles) / cols)
            sheet = Image.new("RGB", (cols * tw, rows * (th + 18)), (12, 12, 12))
            draw = ImageDraw.Draw(sheet)
            for i, (label, im) in enumerate(tiles):
                x, y = i % cols * tw, i // cols * (th + 18)
                sheet.paste(im.resize((tw, th)), (x, y + 18))
                draw.text((x + 4, y + 3), label, fill=(220, 220, 220))
            path = out / f"{item['video']}-{setup.replace(':', 'x')}.jpg"
            sheet.save(path, quality=82)
            print(path, flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--out", required=True)
    p.add_argument("--only")
    p = sub.add_parser("measure")
    p.add_argument("--data", required=True)
    p.add_argument("--json")
    p.add_argument("--style", default="impact")
    p = sub.add_parser("sheet")
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--only")
    p.add_argument("--aspect", default="9:16,16:9")
    p.add_argument("--style", default="impact")
    p.add_argument("--per-window", type=int, default=4)
    args = ap.parse_args(argv)
    return {"prepare": cmd_prepare, "measure": cmd_measure, "sheet": cmd_sheet}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
