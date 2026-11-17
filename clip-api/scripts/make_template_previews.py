#!/usr/bin/env python3
"""Preview assets for the template gallery: schematic posters, and preview clips from footage we may use.

Usage:
  python scripts/make_template_previews.py --posters
      Rewrite clip-api/templates/<id>/poster.svg for every template and preset. No video needed. The posters
      are drawn here from the catalogue (app/templates.py), so they contain no footage and no third-party
      artwork. A preset's poster shows its panels with their sizes and one caption word where captions sit.

  python scripts/make_template_previews.py <video> --i-have-rights [--start 30] [--seconds 6]
                                           [--only id,id] [--game lol] [--out DIR]
      Render <out>/<id>/preview.mp4 for each template from a video the owner HAS THE RIGHTS to publish,
      using the template's options and today's renderer. Afterwards add the ids to PREVIEW_VIDEOS in
      app/templates.py and commit the files (see clip-api/templates/README.md).

Exit 0 = ok, 1 = a render failed, 2 = bad input.
"""
import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.templates import GAME_NAMES, GAMES, TEMPLATES  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "templates"

# The ClutchClips palette (web-src/app/globals.css).
BG, PANEL, CARD, LINE, TEXT, MUTED, LIME, CYAN, INK = (
    "#07080a", "#0d0f12", "#121418", "#23272e", "#f4f6f8", "#9aa3ad", "#b8ff3c", "#3cf0ff", "#0a0d05")
FONT = "Inter, 'Helvetica Neue', Arial, sans-serif"
CANVAS_W, CANVAS_H = 720, 900
FRAME_TOP, FRAME_MAX = 96, 520          # the frame is drawn inside a FRAME_MAX square under the header
SIZES = {"9:16": (292, 520), "4:5": (416, 520), "1:1": (520, 520), "16:9": (520, 292)}
LAYOUT_NAMES = {"auto": "Auto", "full": "Full", "fit": "Fit", "split2": "Split 2", "pip": "PiP",
                "screen_first": "Screen first", "gameplay_a": "Gameplay A", "gameplay_b": "Gameplay B"}

# Where the gameplay and the camera sit in each layout, as (x, y, w, h) fractions of the frame, plus where the
# captions and the hook go (fraction of the frame height). This is OUR reading of each layout's name: the
# renderer (app/pipeline/layouts.py) is the authority. The stacked layouts (split2, screen_first, gameplay_a,
# gameplay_b) are not listed: their boxes come from the template's own `panels` (see `_stacked`).
# gameplay_a and gameplay_b are provisional (PROVISIONAL_LAYOUTS in app/templates.py): their posters say so.
SCHEMATICS = {
    "auto":         {"game": (0, 0, 1, 1), "cam": (0, 0, 1, 1 / 3), "cam_dashed": True, "captions": 0.70, "hook": 0.42},
    "full":         {"game": (0, 0, 1, 1), "cam": None, "captions": 0.70, "hook": 0.16},
    "fit":          {"game": "fit", "cam": None, "captions": 0.74, "hook": 0.16},
    "pip":          {"game": (0, 0, 1, 1), "cam": (0.60, 0.04, 0.36, 0.20), "captions": 0.70, "hook": 0.32},
}
# The one word each preset's poster shows as its caption: ours, in our own lettering. A preset that is not
# listed gets the last one.
CAPTION_WORDS = {"racing-gameplay": "DRIFT", "racing-camera-top": "OVERTAKE", "shooter-gameplay": "HEADSHOT",
                 "fighting-screen-first": "COMBO", "moba-screen-first": "GANK", "moba-full": "WIPEOUT",
                 "moba-gameplay": "STEAL", None: "CLUTCH"}
WORD_SIZE = 46          # about 9% of the frame height, like the caption style the presets are made for


def _stacked(camera: str, ratio: float) -> dict:
    """The schematic of a camera panel over or under a gameplay panel. `ratio` is the top panel's share of the
    height. Each panel's label sits on its outer edge and says its share; `seam` is the line between them."""
    top, bottom = (0, 0, 1, ratio), (0, ratio, 1, 1 - ratio)
    shares = (f"{round(ratio * 100)}%", f"{100 - round(ratio * 100)}%")
    if camera == "top":         # captions on the line between the panels, the hook under them on the gameplay
        return {"cam": top, "game": bottom, "cam_share": shares[0], "game_share": shares[1], "cam_label_top": True,
                "seam": ratio, "captions": ratio + 0.03, "hook": ratio + 0.17}
    return {"game": top, "cam": bottom, "game_share": shares[0], "cam_share": shares[1], "label_top": True,
            "seam": ratio, "captions": ratio - 0.09, "hook": 0.14}


def _n(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _zone(box, fx: float, fy: float, fw: float, fh: float) -> tuple[float, float, float, float]:
    x, y, w, h = box
    return fx + x * fw, fy + y * fh, w * fw, h * fh


def _pill(cx: float, cy: float, label: str, fill: str, ink: str, stroke: str | None = None) -> str:
    # textLength pins the text to the pill whatever font the browser falls back to.
    inner, h = 8.2 * len(label), 28
    w = inner + 28
    edge = f' stroke="{stroke}" stroke-width="1.5"' if stroke else ""
    return (f'<rect x="{_n(cx - w / 2)}" y="{_n(cy - h / 2)}" width="{_n(w)}" height="{h}" rx="14" fill="{fill}"{edge}/>'
            f'<text x="{_n(cx)}" y="{_n(cy + 4.5)}" text-anchor="middle" font-size="12.5" font-weight="700" '
            f'textLength="{_n(inner)}" lengthAdjust="spacingAndGlyphs" fill="{ink}">{escape(label)}</text>')


def _caption_word(cx: float, cy: float, word: str, room: float) -> str:
    """One caption word the way the presets caption a clip: heavy capitals in our lime with a dark outline.
    Drawn twice (outline, then fill) so it looks the same in every viewer; the bar behind it keeps the panel
    edges from showing through the gaps in the letters."""
    width = min(len(word) * WORD_SIZE * 0.66, room)
    text = (f'<text x="{_n(cx)}" y="{_n(cy + WORD_SIZE * 0.35)}" text-anchor="middle" font-size="{WORD_SIZE}" '
            f'font-weight="900" textLength="{_n(width)}" lengthAdjust="spacingAndGlyphs" ')
    return (f'<rect x="{_n(cx - width / 2)}" y="{_n(cy - 11)}" width="{_n(width)}" height="22" fill="{INK}"/>'
            f'{text}fill="{INK}" stroke="{INK}" stroke-width="16" stroke-linejoin="round">{escape(word)}</text>'
            f'{text}fill="{LIME}">{escape(word)}</text>')


def poster_svg(t: dict) -> str:
    """The poster for one template: its layout as a schematic, its name and its settings. Same input, same text."""
    fw, fh = SIZES[t["aspect"]]
    fx, fy = (CANVAS_W - fw) / 2, FRAME_TOP + (FRAME_MAX - fh) / 2
    wide = fw > fh
    preset = t["kind"] == "preset"
    if t["panels"]["camera"]:
        if wide:
            raise ValueError(f'{t["id"]}: no schematic for a stacked layout in a wide frame; add one')
        s = _stacked(t["panels"]["camera"], t["panels"]["split_ratio"])
    else:
        s = SCHEMATICS[t["layout"]]
    game_box = s["game"]
    if game_box == "fit":            # the whole 16:9 picture, bars above and below when the frame is taller
        h = min(1.0, (fw * 9 / 16) / fh)
        game_box = (0, (1 - h) / 2, 1, h)
    cam_box = None if (wide and s.get("cam_dashed")) else s["cam"]     # a wide frame has no room for a stacked camera
    name_size = 44 if len(t["name"]) <= 18 else 36
    header = f'{t["genre"].replace("_", " ")} preset' if preset else GAME_NAMES[t["game"]]
    if preset:                       # a preset is a look: its line gives the panel sizes, not a clip length
        detail = f'{s["game_share"]} gameplay  ·  {s["cam_share"]} camera' if "seam" in s else "gameplay only"
    else:
        detail = "{}–{} s".format(*t["duration"].split("-"))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS_W} {CANVAS_H}" width="{CANVAS_W}" '
        f'height="{CANVAS_H}" role="img" aria-label="{escape(t["name"])}: {LAYOUT_NAMES[t["layout"]]} layout, '
        f'{t["aspect"]}" font-family="{FONT}">',
        f'<title>{escape(t["name"])}</title>',
        '<defs><pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse">'
        f'<path d="M26 0H0V26" fill="none" stroke="{LIME}" stroke-opacity="0.13" stroke-width="1"/></pattern></defs>',
        f'<rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{BG}"/>',
        f'<rect x="16" y="16" width="{CANVAS_W - 32}" height="{CANVAS_H - 32}" rx="28" fill="{PANEL}" stroke="{LINE}"/>',
        f'<text x="48" y="66" font-size="17" font-weight="700" letter-spacing="2.2" fill="{CYAN}">'
        f'{escape(header.upper())}</text>',
        f'<text x="{CANVAS_W - 48}" y="66" text-anchor="end" font-size="15" font-weight="700" letter-spacing="2" '
        f'fill="{MUTED}">CLUTCHCLIPS</text>',
        f'<rect x="{_n(fx)}" y="{_n(fy)}" width="{fw}" height="{fh}" rx="14" fill="{BG}" stroke="{LINE}" stroke-width="2"/>',
    ]
    gx, gy, gw, gh = _zone(game_box, fx, fy, fw, fh)
    parts += [
        f'<rect x="{_n(gx + 3)}" y="{_n(gy + 3)}" width="{_n(gw - 6)}" height="{_n(gh - 6)}" rx="11" fill="{CARD}"/>',
        f'<rect x="{_n(gx + 3)}" y="{_n(gy + 3)}" width="{_n(gw - 6)}" height="{_n(gh - 6)}" rx="11" fill="url(#grid)" '
        f'stroke="{LIME}" stroke-width="2"/>',
        f'<text x="{_n(gx + gw / 2)}" y="{_n(gy + 30 if s.get("label_top") else gy + gh - 20)}" text-anchor="middle" '
        f'font-size="12.5" font-weight="700" letter-spacing="2" fill="{LIME}">'
        f'GAMEPLAY{" · " + s["game_share"] if "game_share" in s else ""}</text>',
    ]
    if cam_box:
        cx, cy, cw, ch = _zone(cam_box, fx, fy, fw, fh)
        dash = ' stroke-dasharray="7 6"' if s.get("cam_dashed") else ""
        fill = "none" if s.get("cam_dashed") else PANEL
        r = min(cw, ch) * 0.15
        head = cy + ch / 2 - r * 0.7          # the head and shoulders together sit in the middle of the panel
        label = "CAMERA IF FOUND" if s.get("cam_dashed") else "CAMERA" + (" · " + s["cam_share"] if "cam_share" in s else "")
        parts += [
            f'<rect x="{_n(cx + 3)}" y="{_n(cy + 3)}" width="{_n(cw - 6)}" height="{_n(ch - 6)}" rx="11" fill="{fill}" '
            f'stroke="{CYAN}" stroke-width="2"{dash}/>',
            f'<circle cx="{_n(cx + cw / 2)}" cy="{_n(head)}" r="{_n(r)}" fill="none" stroke="{CYAN}" stroke-width="2"/>',
            f'<path d="M{_n(cx + cw / 2 - r * 1.9)} {_n(head + r * 2.4)}a{_n(r * 1.9)} {_n(r * 1.3)} 0 0 1 '
            f'{_n(r * 3.8)} 0" fill="none" stroke="{CYAN}" stroke-width="2"/>',
            f'<text x="{_n(cx + cw / 2)}" y="{_n(cy + 24 if s.get("cam_label_top") else cy + ch - 12)}" text-anchor="middle" '
            f'font-size="11" font-weight="700" letter-spacing="1.6" fill="{CYAN}">{label}</text>',
        ]
    mid = fx + fw / 2
    if t["hook"] and t["hook"]["enabled"]:
        label = f'HOOK · {t["hook"]["style"].upper()}' + (" · AT END" if t["hook"]["position"] == "end" else "")
        parts.append(_pill(mid, fy + s["hook"] * fh, label, LIME, INK))
    if preset:                       # one word: on the line between the panels, or in the lower third without one
        word = CAPTION_WORDS.get(t["id"], CAPTION_WORDS[None])
        parts.append(_caption_word(mid, fy + s.get("seam", s["captions"]) * fh, word, fw - 36))
    else:
        parts.append(_pill(mid, fy + s["captions"] * fh, f'CAPTIONS · {t["caption_style"].upper()}', BG, TEXT, TEXT))
    parts += [
        f'<text x="{CANVAS_W / 2:.0f}" y="712" text-anchor="middle" font-size="{name_size}" font-weight="800" '
        f'fill="{TEXT}">{escape(t["name"])}</text>',
        f'<text x="{CANVAS_W / 2:.0f}" y="760" text-anchor="middle" font-size="21" font-weight="600" fill="{MUTED}">'
        f'{LAYOUT_NAMES[t["layout"]]}  ·  {t["aspect"]}  ·  {detail}</text>',
        f'<rect x="{CANVAS_W / 2 - 60:.0f}" y="800" width="120" height="5" rx="2.5" fill="{LIME}"/>',
        f'<text x="{CANVAS_W / 2:.0f}" y="846" text-anchor="middle" font-size="14" letter-spacing="1.4" fill="{MUTED}">'
        f'{("PROVISIONAL PRESET · " if preset else "PROVISIONAL LAYOUT · ") if t["provisional"] else ""}'
        f'LAYOUT SCHEMATIC · NOT GAME FOOTAGE</text>',
        '</svg>',
    ]
    return "\n".join(parts) + "\n"


def poster_path(template_id: str, out: Path = OUT) -> Path:
    return out / template_id / "poster.svg"


def write_posters(out: Path = OUT) -> list[Path]:
    written = []
    for tid, t in TEMPLATES.items():
        path = poster_path(tid, out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(poster_svg(t), encoding="utf-8")
        written.append(path)
    return written


SAMPLE_CAPTION = "this is how your captions will look"


def render_previews(video: Path, out: Path = OUT, start: float = 0.0, seconds: float = 6.0,
                    only: list[str] | None = None, game: str | None = None, timeout: float = 600.0) -> list[Path]:
    """One short clip per template, cut from `video` with the template's options and today's renderer.
    The caller is responsible for having the rights to publish `video`."""
    from app.pipeline import Deadline, PipelineOptions, probe
    from app.pipeline.facecam import resolve_facecam
    from app.pipeline.render import render_clip

    info = probe(video)
    end = min(info.duration, start + seconds)
    if end - start < 1:
        raise ValueError("the chosen range is shorter than one second")
    step = (end - start - 0.6) / len(SAMPLE_CAPTION.split())
    words = [(round(0.3 + i * step, 2), round(0.3 + (i + 1) * step, 2), w) for i, w in enumerate(SAMPLE_CAPTION.split())]
    made = []
    for tid, t in TEMPLATES.items():
        if (only and tid not in only) or (game and t["game"] != game):
            continue
        options = PipelineOptions(**t["options"], facecam_region="auto")
        deadline = Deadline(timeout)
        layout, facecam = resolve_facecam(video, info, options, deadline)
        path = out / tid / "preview.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        render_clip(video, start, end, path, src_w=info.width, src_h=info.height, vertical=True, zoom=1.0,
                    chat="none", words=words, font=options.caption_font, layout=layout, facecam=facecam,
                    style=options.caption_style, aspect=options.aspect, max_side=540, deadline=deadline,
                    has_audio=info.has_audio, hook=t["name"] if options.hook_overlay else None)
        made.append(path)
    return made


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", nargs="?", type=Path, help="a video you have the rights to publish")
    ap.add_argument("--posters", action="store_true", help="rewrite the schematic posters and stop")
    ap.add_argument("--i-have-rights", action="store_true", help="confirm you may publish clips of this video")
    ap.add_argument("--start", type=float, default=0.0, help="where the preview starts, in seconds")
    ap.add_argument("--seconds", type=float, default=6.0, help="preview length")
    ap.add_argument("--only", default="", help="comma-separated template ids")
    ap.add_argument("--game", choices=GAMES, help="only this game's templates")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    if args.posters:
        print(f"wrote {len(write_posters(args.out))} posters under {args.out}")
        return 0
    if not args.video or not args.video.is_file():
        print("Give a video file, or --posters.", file=sys.stderr)
        return 2
    if not args.i_have_rights:
        print("Previews are published on the site. Pass --i-have-rights to confirm you own this footage or have "
              "permission to publish it.", file=sys.stderr)
        return 2
    only = [x for x in args.only.split(",") if x]
    unknown = [x for x in only if x not in TEMPLATES]
    if unknown:
        print(f"Unknown template ids: {', '.join(unknown)}", file=sys.stderr)
        return 2
    try:
        made = render_previews(args.video, args.out, args.start, args.seconds, only, args.game)
    except Exception as e:    # one clear line for the person at the terminal, whatever the renderer raised
        print(f"Render failed: {e}", file=sys.stderr)
        return 1
    print(f"rendered {len(made)} previews under {args.out}")
    print("Add these ids to PREVIEW_VIDEOS in app/templates.py: " + ", ".join(p.parent.name for p in made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
