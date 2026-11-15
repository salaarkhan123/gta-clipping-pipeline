"""Cut and render clips. Vertical layout ported from test-tools/auto_clip.py."""
import shutil
import tempfile
from pathlib import Path

from .captions import build_ass
from .ff import SAFE_IN, Deadline, run

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


def fill_crop(src_w: int, src_h: int, region, tw: int, th: int, zoom: float = 1.0) -> str:
    """Crop `region` (fractions) to the target aspect, centred, then scale to fill tw x th exactly."""
    fx, fy, fw, fh = region
    x, y, w, h = src_w * fx, src_h * fy, src_w * fw, src_h * fh
    if w / h > tw / th:
        cw, ch = h * tw / th, h
    else:
        cw, ch = w, w * th / tw
    cw, ch = cw / zoom, ch / zoom
    cx, cy = x + (w - cw) / 2, y + (h - ch) / 2
    return f"crop={even(cw)}:{even(ch)}:{even(cx)}:{even(cy)},scale={tw}:{th},setsar=1"


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


def layout_filter(src_w: int, src_h: int, layout: str, zoom: float, chat: str, facecam,
                  ow: int = W, oh: int = H) -> str:
    """split: facecam top third + gameplay below. fill: gameplay fills the frame. classic: old blurred layout."""
    if layout == "split":
        top = even(oh / 3)
        region = FACECAM_REGIONS[facecam] if isinstance(facecam, str) else tuple(facecam)
        return (f"[0:v]split=2[a][b];"
                f"[a]{fill_crop(src_w, src_h, region, ow, top)}[top];"
                f"[b]{fill_crop(src_w, src_h, FULL_FRAME, ow, oh - top, zoom)}[bot];"
                f"[top][bot]vstack=inputs=2,format=yuv420p[v]")
    if layout == "fill":
        return f"[0:v]{fill_crop(src_w, src_h, FULL_FRAME, ow, oh, zoom)},format=yuv420p[v]"
    return vertical_filter(src_w, src_h, zoom, chat)


def caption_top(src_w: int, src_h: int, layout: str, zoom: float, chat: str, oh: int = H) -> int:
    if layout == "split":
        return even(oh / 3) - 60       # captions sit on the seam between camera and gameplay
    if layout == "fill":
        return int(oh * 0.70)
    return video_bottom(src_w, src_h, zoom, chat) + 30


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


def render_clip(src: Path, start: float, end: float, out: Path, *, src_w: int, src_h: int,
                vertical: bool, zoom: float, chat: str, words, font: str,
                layout: str = "fill", facecam=None, style: str = "pop", aspect: str = "9:16",
                max_side: int | None = None, deadline: Deadline | None = None) -> None:
    """Cut [start, end] from src and render it. `words` are clip-relative (start, end, text) or empty."""
    # Caption files live in the system temp dir so the path has no spaces (ffmpeg filter paths are fussy).
    tmp = Path(tempfile.mkdtemp(prefix="clipcap"))
    try:
        cap_filter = ""
        ow, oh = ASPECTS.get(aspect, ASPECTS["9:16"]) if vertical else (src_w, src_h)
        layout = fit_layout(layout, aspect)
        if words:
            top = caption_top(src_w, src_h, layout, zoom, chat, oh) if vertical else 0
            build_ass(words, tmp / "cap.ass", vertical, top, font, style, play=(ow, oh))
            cap_filter = f"ass=filename={tmp / 'cap.ass'}"
        size = capped_size(ow, oh, max_side)
        scale = ["-s", f"{size[0]}x{size[1]}"] if size else []
        if vertical:
            # 30 fps out: TikTok, Shorts and Reels play it natively and it cuts render time by ~40% on 60 fps VODs.
            graph = layout_filter(src_w, src_h, layout, zoom, chat, facecam, ow, oh).replace("[0:v]", f"[0:v]fps={OUT_FPS},", 1)
            if cap_filter:
                graph = graph[: -len("[v]")] + "[pre];[pre]" + cap_filter + "[v]"
            vf = ["-filter_complex", graph, "-map", "[v]", "-map", "0:a?"]
        else:
            vf = ["-vf", f"fps={OUT_FPS}" + ("," + cap_filter if cap_filter else "")]
        run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
             *SAFE_IN, "-i", src, *vf, *scale,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], deadline)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_thumb(clip: Path, out: Path, deadline: Deadline | None = None) -> None:
    run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", clip, "-frames:v", "1",
         "-vf", "scale=360:-2", out], deadline, cap=60)
