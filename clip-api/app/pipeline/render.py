"""Cut and render clips. Vertical layout ported from test-tools/auto_clip.py."""
import re
import shutil
import tempfile
from pathlib import Path

from .captions import build_ass
from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout, run

# Where the chat sits in the source video, as fractions: (x, y, width, height).
CHAT_REGIONS = {
    "top-right": (0.62, 0.0, 0.38, 0.42),
    "top-center": (0.33, 0.0, 0.34, 0.28),
    "top-left": (0.0, 0.0, 0.38, 0.42),
    "bottom-right": (0.62, 0.58, 0.38, 0.42),
    "bottom-left": (0.0, 0.58, 0.38, 0.42),
}
W, H, GAP = 1080, 1920, 40

# Where the streamer's facecam usually sits, as fractions: (x, y, width, height).
FACECAM_REGIONS = {
    "top-left": (0.0, 0.0, 0.30, 0.30),
    "top-right": (0.70, 0.0, 0.30, 0.30),
    "bottom-left": (0.0, 0.70, 0.30, 0.30),
    "bottom-right": (0.70, 0.70, 0.30, 0.30),
}
SPLIT_TOP = 640          # facecam band height in the 9:16 split layout (top third)
ASPECTS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}
FULL_FRAME = (0.0, 0.0, 1.0, 1.0)


def even(n) -> int:
    return int(n) // 2 * 2


def crop_rect(src_w: int, src_h: int, region, tw: int, th: int, zoom: float = 1.0) -> tuple[float, float, float, float]:
    """The centred crop of `region` (fractions) with the target aspect, in source pixels: (x, y, w, h)."""
    fx, fy, fw, fh = region
    x, y, w, h = src_w * fx, src_h * fy, src_w * fw, src_h * fh
    if w / h > tw / th:
        cw, ch = h * tw / th, h
    else:
        cw, ch = w, w * th / tw
    cw, ch = cw / zoom, ch / zoom
    return x + (w - cw) / 2, y + (h - ch) / 2, cw, ch


def _crop_scale(rect, tw: int, th: int) -> str:
    cx, cy, cw, ch = rect
    return f"crop={even(cw)}:{even(ch)}:{even(cx)}:{even(cy)},scale={tw}:{th},setsar=1"


def fill_crop(src_w: int, src_h: int, region, tw: int, th: int, zoom: float = 1.0) -> str:
    """Crop `region` (fractions) to the target aspect, centred, then scale to fill tw x th exactly."""
    return _crop_scale(crop_rect(src_w, src_h, region, tw, th, zoom), tw, th)


FACECAM_PAD = 0.02     # keep this much (fraction of the frame) between the gameplay crop and the camera box
MAX_DODGE = 0.3        # the gameplay crop may step this share of its own size to clear a camera inside the frame
EDGE = 0.02            # a camera box this close to a frame edge counts as sitting on that edge


def _overlaps(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def gameplay_crop(src_w: int, src_h: int, tw: int, th: int, zoom: float, cam) -> tuple[str, str]:
    """The split layout's gameplay crop with the webcam overlay kept out of it.

    Returns (how, filter) where how is "clear" (the centred crop misses the camera), "shifted" (the crop moves the
    least distance that clears the camera: always for a camera on a frame edge, and for one inside the frame
    when a small step is enough) or "blurred" (the camera is in the way and cannot be stepped around, so the crop
    stays and a blurred patch covers it). `filter` reads [b] and writes [bot].
    """
    cx, cy, cw, ch = crop_rect(src_w, src_h, FULL_FRAME, tw, th, zoom)
    pad_x, pad_y = FACECAM_PAD * src_w, FACECAM_PAD * src_h
    bx, by, bw, bh = cam[0] * src_w - pad_x, cam[1] * src_h - pad_y, cam[2] * src_w + 2 * pad_x, cam[3] * src_h + 2 * pad_y
    box = (bx, by, bw, bh)
    if not _overlaps((cx, cy, cw, ch), box):
        return "clear", f"[b]{_crop_scale((cx, cy, cw, ch), tw, th)}[bot]"
    on_left, on_right = cam[0] <= EDGE, cam[0] + cam[2] >= 1 - EDGE
    on_top, on_bottom = cam[1] <= EDGE, cam[1] + cam[3] >= 1 - EDGE
    # Every way the crop could step clear of the camera and stay inside the frame: (distance, new origin, allowed).
    # A camera on a frame edge is always stepped away from. A camera inside the frame is only dodged when a small
    # step does it (MAX_DODGE of the crop): a bigger one would push the middle of the game out of the picture.
    moves = []
    if bx + bw + cw <= src_w:
        d = bx + bw - cx
        moves.append((d, (bx + bw, cy), on_left or d <= MAX_DODGE * cw))
    if bx - cw >= 0:
        d = cx - (bx - cw)
        moves.append((d, (bx - cw, cy), on_right or d <= MAX_DODGE * cw))
    if by + bh + ch <= src_h:
        d = by + bh - cy
        moves.append((d, (cx, by + bh), on_top or d <= MAX_DODGE * ch))
    if by - ch >= 0:
        d = cy - (by - ch)
        moves.append((d, (cx, by - ch), on_bottom or d <= MAX_DODGE * ch))
    moves = [m for m in moves if m[2]]
    if moves:
        _dist, (nx, ny), _ok = min(moves, key=lambda m: m[0])
        return "shifted", f"[b]{_crop_scale((nx, ny, cw, ch), tw, th)}[bot]"
    # Camera in the middle of the frame: cover it with a blurred copy of itself, then crop as usual.
    x0, y0 = even(max(0.0, bx)), even(max(0.0, by))
    w0, h0 = even(min(src_w - x0, bw)), even(min(src_h - y0, bh))
    return "blurred", (f"[b]split=2[b0][b1];[b1]crop={w0}:{h0}:{x0}:{y0},boxblur=20:3[cam];"
                       f"[b0][cam]overlay={x0}:{y0},{_crop_scale((cx, cy, cw, ch), tw, th)}[bot]")


OUT_FPS = 30


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


def punch_in(tw: int, th: int, expr: str) -> str:
    """Zoom the tw x th picture by `expr` (an ffmpeg expression of t, 1 = no zoom) about its centre. Empty for "1"."""
    if expr == "1":
        return ""
    return (f",scale=w='2*trunc({tw}*({expr})/2)':h='2*trunc({th}*({expr})/2)':eval=frame,crop={tw}:{th}")


def layout_filter(src_w: int, src_h: int, layout: str, zoom: float, chat: str, facecam,
                  ow: int = W, oh: int = H, punch: str = "1") -> str:
    """split: facecam top third + gameplay below. fill: gameplay fills the frame. classic: old blurred layout.
    `punch` is a zoom expression over time for the gameplay picture (split and fill only)."""
    if layout == "split":
        top = even(oh / 3)
        region = FACECAM_REGIONS[facecam] if isinstance(facecam, str) else tuple(facecam)
        _how, bottom = gameplay_crop(src_w, src_h, ow, oh - top, zoom, region)
        bottom = bottom[: -len("[bot]")] + punch_in(ow, oh - top, punch) + "[bot]"
        return (f"[0:v]split=2[a][b];"
                f"[a]{fill_crop(src_w, src_h, region, ow, top)}[top];"
                f"{bottom};"
                f"[top][bot]vstack=inputs=2,format=yuv420p[v]")
    if layout == "fill":
        return f"[0:v]{fill_crop(src_w, src_h, FULL_FRAME, ow, oh, zoom)}{punch_in(ow, oh, punch)},format=yuv420p[v]"
    return vertical_filter(src_w, src_h, zoom, chat)


def caption_top(src_w: int, src_h: int, layout: str, zoom: float, chat: str, oh: int = H) -> int:
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
PEAK_LIMIT_DB = -1.5
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


def render_clip(src: Path, start: float, end: float, out: Path, *, src_w: int, src_h: int,
                vertical: bool, zoom: float, chat: str, words, font: str,
                layout: str = "fill", facecam=None, style: str = "pop", aspect: str = "9:16",
                max_side: int | None = None, deadline: Deadline | None = None,
                segments: list[tuple[float, float]] | None = None, punch: str = "1", has_audio: bool = True,
                hook: str | None = None, flash: bool = False, loudness: bool = True) -> None:
    """Cut [start, end] from src and render it. `words` are clip-relative (start, end, text) or empty.

    With `segments` (source seconds, in playing order) those pieces are played back to back instead, and `words`
    are on that rendered timeline. `punch` is a zoom expression over rendered time for the gameplay picture.
    `hook` is a line of on-screen text for the first 2.5 s. `flash` marks the first segment as a flash-forward.
    `loudness` normalises the audio to -14 LUFS with peaks under -1.5 dB (on by default).
    """
    # Caption files live in the system temp dir so the path has no spaces (ffmpeg filter paths are fussy).
    tmp = Path(tempfile.mkdtemp(prefix="clipcap"))
    try:
        cap_filter = ""
        ow, oh = ASPECTS.get(aspect, ASPECTS["9:16"]) if vertical else (src_w, src_h)
        layout = fit_layout(layout, aspect)
        if words or hook:
            top = caption_top(src_w, src_h, layout, zoom, chat, oh) if vertical else 0
            build_ass(words, tmp / "cap.ass", vertical, top, font, style, play=(ow, oh), hook=hook,
                      hook_top=hook_top(layout, oh) if vertical else int(1080 * 0.1))
            cap_filter = f"ass=filename={tmp / 'cap.ass'}"
        size = capped_size(ow, oh, max_side)
        scale = ["-s", f"{size[0]}x{size[1]}"] if size else []
        pieces = segments if segments and segments != [(start, end)] else None
        lo, hi = (min(s for s, _ in pieces), max(e for _, e in pieces)) if pieces else (start, end)
        level = loudness_filter(measure_loudness(src, start, end, deadline)) if (loudness and has_audio) else ""
        if vertical:
            # 30 fps out: TikTok, Shorts and Reels play it natively and it cuts render time by ~40% on 60 fps VODs.
            graph = layout_filter(src_w, src_h, layout, zoom, chat, facecam, ow, oh, punch)
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
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", out], deadline)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_thumb(clip: Path, out: Path, deadline: Deadline | None = None) -> None:
    run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", clip, "-frames:v", "1",
         "-vf", "scale=360:-2", out], deadline, cap=60)
