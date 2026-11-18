"""Cut and render clips. Vertical layout ported from test-tools/auto_clip.py."""
import re
import shutil
import tempfile
from pathlib import Path

from . import layouts
from .captions import FONT_DIR, HOOK_SECONDS, IMPACT_FILE, IMPACT_FILL, build_ass, impact_size
from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout, run
# The geometry lives in layouts.py; these names are re-exported because callers and tests import them from here.
from .layouts import (ASPECTS, EDGE, FACECAM_PAD, FACECAM_REGIONS, FULL_FRAME, MAX_DODGE, LayoutPlan,  # noqa: F401
                      _crop_scale, _overlaps, avoid_camera, crop_rect, even, fill_crop, punch_in)

# Where the chat sits in the source video, as fractions: (x, y, width, height).
CHAT_REGIONS = {
    "top-right": (0.62, 0.0, 0.38, 0.42),
    "top-center": (0.33, 0.0, 0.34, 0.28),
    "top-left": (0.0, 0.0, 0.38, 0.42),
    "bottom-right": (0.62, 0.58, 0.38, 0.42),
    "bottom-left": (0.0, 0.58, 0.38, 0.42),
}
W, H, GAP = 1080, 1920, 40
SPLIT_TOP = 640          # facecam band height in the 9:16 split layout (top third)
OUT_FPS = 30
# Export sizes by name: the output's short side in pixels. An output is never larger than its source.
RESOLUTIONS = {"480": 480, "720": 720, "1080": 1080, "2k": 1440, "4k": 2160}
PREVIEW_SIDE = 540       # a preview render's short side: 540x960 for 9:16
FULL_ENCODE = ["-preset", "veryfast", "-crf", "20"]
PREVIEW_ENCODE = ["-preset", "ultrafast", "-crf", "30"]     # a preview is for looking at, not for posting


def gameplay_crop(src_w: int, src_h: int, tw: int, th: int, zoom: float, cam) -> tuple[str, str]:
    """The split layout's gameplay crop with the webcam overlay kept out of it.

    Returns (how, filter) where how is "clear" (the centred crop misses the camera), "shifted" (the crop moves the
    least distance that clears the camera: always for a camera on a frame edge, and for one inside the frame
    when a small step is enough) or "blocked" (the camera is in the way and cannot be stepped around). A blocked
    crop has no filter: the camera is never covered with a patch, so the caller draws a layout that shows it
    where it is instead (layouts.compose does that). `filter` reads [b] and writes [bot].
    """
    how, rect = avoid_camera(src_w, src_h, tw, th, zoom, cam)
    return how, (f"[b]{_crop_scale(rect, tw, th)}[bot]" if rect else "")


def resolve_layout(layout: str, facecam) -> str:
    if layout == "auto":
        return "split" if facecam else "fill"
    return layout


def fit_layout(layout: str, aspect: str) -> str:
    """classic exists only for 9:16; a 16:9 frame has no room for a stacked camera."""
    if layout == "classic" and aspect != "9:16":
        return "fill"
    if layout == "split" and aspect == "16:9":
        return "fill"
    return layout


def _camera(facecam):
    """(box, face, scene) from what a caller passed as `facecam`: a preset name, a box, or a facecam.CamBox."""
    if not facecam:
        return None, None, None
    box = FACECAM_REGIONS[facecam] if isinstance(facecam, str) else tuple(facecam)
    return box, getattr(facecam, "face", None), getattr(facecam, "scene", None)


def plan_for(src_w: int, src_h: int, layout: str, facecam, aspect: str = "9:16", zoom: float = 1.0,
             camera: str | None = None, split_ratio: float | None = None) -> LayoutPlan:
    """The layout plan for callers that pass a layout name and a camera instead of a plan. `camera` and
    `split_ratio` adjust the two-panel layouts (layouts.compose)."""
    box, face, scene = _camera(facecam)
    return layouts.compose(src_w, src_h, layout, aspect, scene=scene, cam=box, face=face, zoom=zoom, camera=camera,
                           split_ratio=split_ratio)


def layout_filter(src_w: int, src_h: int, layout: str, zoom: float, chat: str, facecam,
                  ow: int = W, oh: int = H, punch: str = "1") -> str:
    """The filter graph for a layout name (old names included) on the ow x oh canvas. classic is the old blurred
    9:16 layout. `punch` is a zoom expression over time for the gameplay picture (never a panel with a person)."""
    aspect = next((a for a, size in ASPECTS.items() if size == (ow, oh)), "9:16")
    if layouts.canonical(layout, aspect) == "classic":
        return vertical_filter(src_w, src_h, zoom, chat)
    return layouts.layout_graph(plan_for(src_w, src_h, layout, facecam, aspect, zoom), punch=punch)


def caption_top(src_w: int, src_h: int, layout: str, zoom: float, chat: str, oh: int = H) -> int:
    """Where captions sit for the old layout names. Layout plans carry their own (LayoutPlan.caption_top)."""
    if layout == "split":
        return even(oh / 3) - 60       # captions sit on the seam between camera and gameplay
    if layout == "fill":
        return int(oh * 0.70)
    return video_bottom(src_w, src_h, zoom, chat) + 30


def hook_top(layout: str, oh: int = H) -> int:
    """Where the on-screen hook sits, in pixels from the top: on the gameplay, clear of the camera and the captions."""
    if layout == "split":
        return even(oh / 3) + 120      # under the captions on the seam, at the top of the gameplay panel
    return int(oh * 0.18)


def capped_size(w: int, h: int, max_side: int | None) -> tuple[int, int] | None:
    """Output size when the plan caps resolution (max_side = short side, e.g. 720), else None."""
    if not max_side or min(w, h) <= max_side:
        return None
    k = max_side / min(w, h)
    return even(w * k), even(h * k)


def output_size(src_w: int, src_h: int, vertical: bool, aspect: str = "9:16", resolution: str | None = None,
                preview: bool = False, max_side: int | None = None) -> tuple[int, int]:
    """The size a clip is rendered at. Without `resolution` it is what it always was: the 1080 canvas of the
    aspect when reframing, the source's own size otherwise. With one, the short side is that resolution, capped
    at the source's short side (an export is never larger than its source). A preview is at most PREVIEW_SIDE.
    The plan cap `max_side` always wins."""
    ref = ASPECTS.get(aspect, ASPECTS["9:16"]) if vertical else (src_w, src_h)
    side = min(ref)
    if resolution is not None:
        if resolution not in RESOLUTIONS:
            raise PipelineError("bad_options", f"Unknown resolution. Use one of: {', '.join(RESOLUTIONS)}.")
        side = min(RESOLUTIONS[resolution], min(src_w, src_h))
    if preview:
        side = min(side, PREVIEW_SIDE)
    if max_side:
        side = min(side, max_side)
    if side == min(ref):
        return ref
    k = side / min(ref)
    return even(ref[0] * k), even(ref[1] * k)


def vertical_filter(src_w: int, src_h: int, zoom: float, chat: str) -> str:
    """1080x1920: blurred background, enlarged chat on top (optional), video below."""
    cw = even(src_w / zoom)
    main_h = even(W * src_h / cw)
    parts = [
        "[0:v]split=3[a][b][c]",
        f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        "boxblur=25:2,eq=brightness=-0.12[bg]",
        f"[b]crop={cw}:{src_h}:{(src_w - cw) // 2}:0,scale={W}:{main_h},setsar=1[main]",
    ]
    if chat == "none":
        parts[0] = "[0:v]split=2[a][b]"
        parts.append(f"[bg][main]overlay=0:{(H - main_h) // 2},format=yuv420p[v]")
        return ";".join(parts)
    fx, fy, fw, fh = CHAT_REGIONS[chat]
    x, y, w, h = even(src_w * fx), even(src_h * fy), even(src_w * fw), even(src_h * fh)
    chat_w = 960
    chat_h = even(chat_w * h / w)
    max_chat_h = H - main_h - 3 * GAP - 120
    if chat_h > max_chat_h:
        chat_h = even(max_chat_h)
        chat_w = even(chat_h * w / h)
    top = max(GAP, (H - (chat_h + GAP + main_h)) // 2)
    parts.append(f"[c]crop={w}:{h}:{x}:{y},scale={chat_w}:{chat_h},setsar=1[chat]")
    parts.append(f"[bg][chat]overlay={(W - chat_w) // 2}:{top}[t]")
    parts.append(f"[t][main]overlay=0:{top + chat_h + GAP},format=yuv420p[v]")
    return ";".join(parts)


def video_bottom(src_w: int, src_h: int, zoom: float, chat: str) -> int:
    """Y position where the main video ends in the vertical layout (captions go below it)."""
    main_h = even(W * src_h / even(src_w / zoom))
    if chat == "none":
        return (H - main_h) // 2 + main_h
    _fx, _fy, fw, fh = CHAT_REGIONS[chat]
    w, h = even(src_w * fw), even(src_h * fh)
    chat_h = min(even(960 * h / w), even(H - main_h - 3 * GAP - 120))
    top = max(GAP, (H - (chat_h + GAP + main_h)) // 2)
    return top + chat_h + GAP + main_h


CUT_FADE = 0.03      # seconds of audio fade on each side of a cut, so cuts do not click
FLASH_FADE = 0.12    # seconds of white on each side of the cut from the flash-forward back to the start
# Every clip leaves at the loudness the platforms play at, with headroom so peaks do not distort.
TARGET_LUFS = -14.0
PEAK_LIMIT_DB = -2.0     # AAC encoding overshoots the limiter by up to ~0.6 dB; -2.0 keeps encoded peaks under -1 dB
MAX_GAIN_DB = 20.0      # never turn a near-silent clip up further than this: it would only amplify noise
QUIET_LUFS = -50.0      # below this there is nothing to normalise (a muted or silent clip)


def measure_loudness(src: Path, start: float, end: float, deadline: Deadline | None = None) -> float | None:
    """Integrated loudness (LUFS) of [start, end] of the source, or None when it is silent or cannot be measured."""
    try:
        out = run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", *SAFE_IN,
                   "-i", src, "-vn", "-af", "ebur128", "-f", "null", "-"], deadline, cap=120).stderr or ""
    except PipelineTimeout:
        raise
    except PipelineError:
        return None
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", out)
    if not found:
        return None
    lufs = float(found[-1])
    return lufs if lufs > QUIET_LUFS else None


def loudness_filter(measured: float | None) -> str:
    """One fixed gain to bring the clip to TARGET_LUFS, then a limiter so no peak passes PEAK_LIMIT_DB. A fixed
    gain keeps the clip's own dynamics (a one-pass normaliser rides the volume up and down instead, and fails
    outright on digital silence). Empty when there is nothing to measure."""
    if measured is None:
        return ""
    gain = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, TARGET_LUFS - measured))
    return f"volume={gain:.2f}dB,alimiter=limit={10 ** (PEAK_LIMIT_DB / 20):.4f}:level=disabled:attack=5:release=50"


def segments_graph(segments: list[tuple[float, float]], lo: float, has_audio: bool, flash: bool = False,
                   audio_filter: str = "") -> str:
    """Filter graph that plays `segments` (source seconds) back to back. Reads input 0 (which starts at source
    time `lo`), writes [cv] and, with audio, [ca]. With `flash` the first segment is a flash-forward: it ends
    in a quick fade to white and the next one opens from white, so the jump back in time reads as intended."""
    n = len(segments)
    parts = [f"[0:v]fps={OUT_FPS},split={n}" + "".join(f"[s{i}]" for i in range(n))]
    if has_audio:
        parts.append(f"[0:a]asplit={n}" + "".join(f"[t{i}]" for i in range(n)))
    for i, (s, e) in enumerate(segments):
        fade = ""
        if flash and n > 1 and i == 0:
            fade = f",fade=t=out:st={max(0.0, e - s - FLASH_FADE):.3f}:d={FLASH_FADE}:color=white"
        elif flash and i == 1:
            fade = f",fade=t=in:st=0:d={FLASH_FADE}:color=white"
        parts.append(f"[s{i}]trim=start={s - lo:.3f}:end={e - lo:.3f},setpts=PTS-STARTPTS{fade}[v{i}]")
        if has_audio:
            d = e - s
            parts.append(f"[t{i}]atrim=start={s - lo:.3f}:end={e - lo:.3f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d={CUT_FADE},afade=t=out:st={max(0.0, d - CUT_FADE):.3f}:d={CUT_FADE}[a{i}]")
    if has_audio:
        parts.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cv]" + ("[cx]" if audio_filter else "[ca]"))
        if audio_filter:
            parts.append(f"[cx]{audio_filter}[ca]")
    else:
        parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cv]")
    return ";".join(parts)


HOOK_ROOM = 200      # pixels a hook may take from its top on the 1080 canvas: two lines and the box around them
TEXT_GAP = 16        # pixels kept between the hook and an impact caption


def impact_rows(plan: LayoutPlan | None, oh: int, position: str, under: int, below_video: int | None = None,
                k: float = 1.0) -> tuple[int, int]:
    """(the row of the middle of an impact caption, the hook's top) in a frame `oh` tall. With a layout plan the
    caption goes where the plan says for `position` and never on the person's head. Without one (the source's
    own frame, or the classic layout, where `below_video` is where the old captions start under the picture)
    there is no line between panels and no known person. `under` is where the hook would sit; it steps under
    the caption (or over it) when the two would overlap. `k` scales the hook's size for a frame that is not the
    1080 canvas."""
    half = impact_size(oh).half
    if plan is not None:
        center = layouts.caption_center(plan, position, half, IMPACT_FILL)
    else:
        center = layouts.caption_y(oh, position, half, None if below_video is None else int(below_video + half))
    top, bottom = center - half - TEXT_GAP * k, center + half + TEXT_GAP * k
    if under - 14 * k < bottom and under + HOOK_ROOM * k > top:
        if bottom + 24 * k + HOOK_ROOM * k <= 0.94 * oh:
            under = int(bottom + 24 * k)
        elif top - 24 * k - HOOK_ROOM * k >= 20 * k:
            under = int(top - 24 * k - HOOK_ROOM * k)
    return center, under


HOOK_POSITIONS = ("beginning", "end")
HOOK_MS = (500, 10000)      # the shortest and longest a hook may stay on screen, in milliseconds


def hook_window(length: float, position: str = "beginning", ms: int | None = None) -> tuple[float, float] | None:
    """When the hook is on screen, (from, to) seconds on a clip `length` long: the first HOOK_SECONDS (or `ms`),
    or the last ones for position "end". Never longer than the clip. None for the default (the caption files
    are then written exactly as before these options existed)."""
    if position == "beginning" and ms is None:
        return None
    if position not in HOOK_POSITIONS:
        raise PipelineError("bad_options", f"Unknown hook position. Use one of: {', '.join(HOOK_POSITIONS)}.")
    show = min(length, (ms if ms is not None else HOOK_SECONDS * 1000) / 1000)
    return (0.0, round(show, 3)) if position == "beginning" else (round(max(0.0, length - show), 3), round(length, 3))


def text_track(path: Path, words, *, src_w: int, src_h: int, vertical: bool, zoom: float, chat: str,
               plan: LayoutPlan | None, aspect: str, font: str, style: str, position: str = "auto",
               accent: str | None = None, hook: str | None = None,
               hook_at: tuple[float, float] | None = None, game: str | None = None) -> int:
    """Write the clip's captions and hook (an ASS file) for the frame render_clip draws: `plan` when reframing
    with one, the classic layout when reframing without one, the source's own frame when not reframing.
    Returns the number of captions. scripts/caption_checks.py measures exactly this file."""
    ow, oh = ASPECTS.get(aspect, ASPECTS["9:16"]) if vertical else (src_w, src_h)
    if not vertical:
        top, under, span = 0, int(1080 * 0.1), (0.0, 1.0)
    elif plan is not None:
        top, under, span = plan.caption_top, plan.hook_top, plan.text_span
    else:
        top, under, span = caption_top(src_w, src_h, "classic", zoom, chat, oh), hook_top("classic", oh), (0.0, 1.0)
    center = None
    if style == "impact":
        # Measured in the frame's own pixels (the old styles write a source frame as if it were 1920x1080).
        k = 1.0 if vertical else oh / 1080
        center, under = impact_rows(plan, oh, position, under if vertical else int(oh * 0.1),
                                    top if vertical and plan is None else None, k)
    # Always written for the 1080 canvas: the subtitle renderer scales it to whatever size the clip is.
    return build_ass(words, path, vertical, top, font, style, play=(ow, oh), hook=hook, hook_top=under,
                     span=span, center=center, accent=accent, hook_at=hook_at, game=game)


def render_clip(src: Path, start: float, end: float, out: Path, *, src_w: int, src_h: int,
                vertical: bool, zoom: float, chat: str, words, font: str,
                layout: str = "fill", facecam=None, style: str = "pop", aspect: str = "9:16",
                max_side: int | None = None, deadline: Deadline | None = None,
                segments: list[tuple[float, float]] | None = None, punch: str = "1", has_audio: bool = True,
                hook: str | None = None, flash: bool = False, loudness: bool = True,
                plan: LayoutPlan | None = None, resolution: str | None = None, preview: bool = False,
                position: str = "auto", accent: str | None = None, camera: str | None = None,
                split_ratio: float | None = None, hook_position: str = "beginning",
                hook_ms: int | None = None, game: str | None = None) -> None:
    """Cut [start, end] from src and render it. `words` are clip-relative (start, end, text) or empty.

    `style` is a caption style from captions.CAPTION_STYLES. For "impact", `position` ("auto", "seam", "lower",
    "center") is where the caption sits and `accent` (#RRGGBB) the keyword's colour; the other styles ignore
    both; `game` (a templates.GAMES id) adds that game's terms to the words impact emphasises. `camera`
    ("top" | "bottom") and `split_ratio` (the top panel's share, 0.25 to 0.75) adjust a two-panel
    layout made here from `layout`; a `plan` already has them.

    With `segments` (source seconds, in playing order) those pieces are played back to back instead, and `words`
    are on that rendered timeline. `punch` is a zoom expression over rendered time for the gameplay picture.
    `hook` is a line of on-screen text for the first 2.5 s, or for `hook_ms` milliseconds at the "beginning" or
    the "end" (`hook_position`) of the rendered clip. `flash` marks the first segment as a flash-forward.
    `loudness` normalises the audio to -14 LUFS with peaks under -2 dB before encoding, -1 dB after (on by default).

    When reframing (`vertical`), what is drawn is a layout plan: `plan` if one is given (layouts.plan_layout),
    otherwise the one for `layout` (any name in layouts.LAYOUTS, or an old one) and `facecam` (a preset name, a
    box, or what facecam.resolve_facecam returned). `resolution` ("480", "720", "1080", "2k", "4k") sets the
    output's short side, never above the source's; without it the size is what it always was. `preview` is a
    fast, small render to look at before paying for the real one. The plan cap `max_side` always wins.
    """
    # Caption files live in the system temp dir so the path has no spaces (ffmpeg filter paths are fussy).
    tmp = Path(tempfile.mkdtemp(prefix="clipcap"))
    try:
        cap_filter = ""
        if not vertical:
            plan = None
        elif plan is not None:
            aspect = plan.aspect
        elif layouts.canonical(layout, aspect) != "classic":
            plan = plan_for(src_w, src_h, layout, facecam, aspect, zoom, camera, split_ratio)
        ref = ASPECTS.get(aspect, ASPECTS["9:16"]) if vertical else (src_w, src_h)
        if words or hook:
            length = sum(e - s for s, e in segments) if segments else end - start
            text_track(tmp / "cap.ass", words, src_w=src_w, src_h=src_h, vertical=vertical, zoom=zoom, chat=chat,
                       plan=plan, aspect=aspect, font=font, style=style, position=position, accent=accent,
                       hook=hook, hook_at=hook_window(length, hook_position, hook_ms) if hook else None, game=game)
            cap_filter = f"ass=filename={tmp / 'cap.ass'}"
            if style == "impact":
                # The renderer is handed our own font file, so the text never depends on what the machine has
                # installed. A copy in the temp dir keeps the filter's path free of spaces.
                if not (FONT_DIR / IMPACT_FILE).is_file():
                    raise PipelineError("captions_unavailable", "The caption font is missing on this server.")
                (tmp / "fonts").mkdir()
                shutil.copy(FONT_DIR / IMPACT_FILE, tmp / "fonts" / IMPACT_FILE)
                cap_filter += f":fontsdir={tmp / 'fonts'}"
        size = output_size(src_w, src_h, vertical, aspect, resolution, preview, max_side)
        # A chosen resolution or a preview is drawn at its own size (sharper above 1080, far less work below it).
        # Everything else is drawn on the 1080 canvas and scaled after, exactly as before.
        direct = plan is not None and (resolution is not None or preview)
        scale = ["-s", f"{size[0]}x{size[1]}"] if (size != ref and not direct) else []
        pieces = segments if segments and segments != [(start, end)] else None
        lo, hi = (min(s for s, _ in pieces), max(e for _, e in pieces)) if pieces else (start, end)
        level = loudness_filter(measure_loudness(src, start, end, deadline)) if (loudness and has_audio) else ""
        if vertical:
            # 30 fps out: TikTok, Shorts and Reels play it natively and it cuts render time by ~40% on 60 fps VODs.
            graph = (layouts.layout_graph(plan, size if direct else None, punch) if plan is not None
                     else vertical_filter(src_w, src_h, zoom, chat))
            if pieces:
                graph = segments_graph(pieces, lo, has_audio, flash, level) + ";" + graph.replace("[0:v]", "[cv]", 1)
            else:
                graph = graph.replace("[0:v]", f"[0:v]fps={OUT_FPS},", 1)
            if cap_filter:
                graph = graph[: -len("[v]")] + "[pre];[pre]" + cap_filter + "[v]"
            vf = ["-filter_complex", graph, "-map", "[v]"]
        elif pieces:
            vf = ["-filter_complex", segments_graph(pieces, lo, has_audio, flash, level) + f";[cv]{cap_filter or 'null'}[v]", "-map", "[v]"]
        else:
            vf = ["-vf", f"fps={OUT_FPS}" + ("," + cap_filter if cap_filter else "")]
        if pieces:
            vf += ["-map", "[ca]"] if has_audio else []
        elif vertical:
            vf += ["-map", "0:a?"]
        if not pieces and level:
            vf += ["-af", level]
        run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{lo:.3f}", "-t", f"{hi - lo:.3f}",
             *SAFE_IN, "-i", src, *vf, *scale,
             "-c:v", "libx264", *(PREVIEW_ENCODE if preview else FULL_ENCODE), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "96k" if preview else "160k", "-ar", "48000", "-movflags", "+faststart", out], deadline)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_thumb(clip: Path, out: Path, deadline: Deadline | None = None) -> None:
    run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", clip, "-frames:v", "1",
         "-vf", "scale=360:-2", out], deadline, cap=60)
