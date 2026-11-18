"""Clip thumbnails: the clip's best frame, drawn in the clip's own layout, with its hook text on it. Free: no AI.

Choosing the frame is cheap on purpose. One ffmpeg pass decodes only the keyframes inside the clip (a stream VOD
has one every ~2 s, so a 30 s clip gives ~15; never more than MAX_FRAMES). Each keyframe comes out twice: small
and gray, to score, and drawn in the clip's own layout (the clip's plan through layouts.layout_graph: the same
camera and crop, no captions, no hook) at THUMB_RESOLUTION, so the winner needs no second decode. Each is scored on
- face: a face found whole inside the camera box (with no camera: inside what the layout shows, none cut by its
  edges), and how far it is from the clip's resting face (an open mouth, wide eyes, a lean towards the camera all
  move it away);
- action: how much the picture changes against the keyframes either side of it, up to 1.5 times the clip's usual
  change (more is a cut to another scene, not more action);
- loudness at that second (people shout when something happens), and closeness to the judge's peak;
- sharpness, up to the clip's usual sharpness (more is not better: text and maps are the sharpest pictures).
A frame that is dark, flat, blurred, a menu or a results card (mostly level and upright edges, or far more detail
than the rest of the clip) or right next to one (menus fade in and out), on a cut (or outside what the clip
keeps), or a transition (a flash between two similar neighbours, or a dissolve between two different ones) only
wins when no other frame is left.

The hook text (or the title when there is no hook) is then set on the winner in Anton, the impact captions' font:
as big as fits, wrapped or shrunk, never past the safe margins, never on the person's head.

AI-generated thumbnails are a separate paid option, not built here.
"""
import logging
import re
import shutil
from dataclasses import asdict, dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np

from . import layouts
from .captions import ACCENT, FONT_DIR, IMPACT_FILE, impact_text, keyword
from .censor import mask
from .ff import SAFE_IN, Deadline, MediaInfo, PipelineError, PipelineTimeout, run_binary
from .render import _camera, output_size, plan_for, vertical_filter

log = logging.getLogger("clipapi.thumbs")

THUMB_RESOLUTION = "720"      # the thumbnail's short side (never above the source's): 720x1280 for 9:16
SCAN_SIDE = 640               # frames are scored at this long side
MAX_FRAMES = 40               # keyframes looked at per clip, at most
EDGE_GUARD = 0.3              # seconds kept clear of every cut: a frame on a cut is mid-transition
JPEG_QUALITY = 85

# How much each part counts, with and without a camera. PEAK_BONUS is added near the judge's peak.
WEIGHTS_CAM = {"face": 0.35, "loud": 0.25, "action": 0.20, "sharp": 0.20}
WEIGHTS_NO_CAM = {"face": 0.0, "loud": 0.30, "action": 0.40, "sharp": 0.30}
PEAK_BONUS, PEAK_REACH = 0.15, 3.0
NO_FACE = 0.5                 # a frame whose camera shows no whole face keeps this share of its score
DARK, BRIGHT, FLAT = 28, 235, 14      # mean and spread of the gray picture (0-255) that make a frame unusable
BLUR = 0.5                    # a frame less sharp than this share of the clip's median sharpness is blurred
BUSY = 1.5                    # action counts up to this many times the clip's median change
UI_LINES = 0.38               # share of strong edges that are level or upright above which a frame is a menu or card
UI_DETAIL = 4.0               # this many times the clip's median sharpness: text or a map, not the game
MENU_FADE = 2.5               # seconds: a keyframe this close to a menu is likely fading into or out of it
FACE_MARGIN = 0.02            # a face this close to the camera box's edge is cut by it
FACE_ROWS = 160               # the camera box is looked at this many pixels tall
SCENE_ROWS = 240              # ... and a picture with no camera box (faces anywhere in it)
FULL = (0.0, 0.0, 1.0, 1.0)

# Text. Sizes are shares of the canvas's short side; rows are shares of its height.
FONTS = (FONT_DIR / IMPACT_FILE, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
CAP_MAX, CAP_MIN = 0.10, 0.055        # the capitals' height
MAX_LINES = 3
MARGIN = 0.06                 # of the text span's width, each side
STROKE = 0.08                 # the dark outline, of the font's em (as the impact captions)
LINE = 1.3                    # line pitch, in capital heights
SAFE_TALL = (0.13, 0.87)      # 9:16: inside the 3:4 crop profile grids show
SAFE_OTHER = (0.07, 0.93)
MAX_BLOCK = 0.36              # the text never takes more than this share of the height
HEAD_GAP = 0.01               # kept between the text and the head, of the height
DARK_INK = (8, 8, 8)


@dataclass
class Frame:
    t: float                  # source seconds
    gray: np.ndarray          # the whole source picture, small and gray: what is scored
    image: Path | None = None # the frame drawn in the clip's layout: what the thumbnail is made from


@dataclass
class Scored:
    t: float
    score: float
    ok: bool                  # passed every check
    face: bool | None         # a whole face in the camera box; None: no camera
    failed: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Canvas:
    """Where text may go on a thumbnail `size` pixels big: never over `avoid` (x0, y0, x1, y1 boxes: the head,
    an inset camera), on `seam` (the line between two stacked panels) when there is one, centred in `span` (the
    part of the width the clip's own text is centred in)."""
    size: tuple[int, int]
    avoid: tuple = ()
    seam: float | None = None
    span: tuple[float, float] = (0.0, 1.0)


@dataclass
class TextBlock:
    lines: list[list[str]]
    font: str
    px: int                   # font size (em)
    cap: int                  # capital height
    stroke: int
    pitch: int                # baseline to baseline
    top: int                  # the block's outer top edge, outline included
    height: int
    widths: list[float]       # each line, outline included
    center_x: float
    accent: int | None        # the keyword: its index among all the words

    def box(self) -> tuple[float, float, float, float]:
        half = max(self.widths) / 2
        return self.center_x - half, self.top, self.center_x + half, self.top + self.height


@dataclass
class Thumb:
    path: Path                # the thumbnail: the frame with the text on it (just the frame when there is no text)
    frame: Path               # the frame alone (what an AI is shown)
    record: dict              # kept in the clip's features: which frame, why, and where text may go


# ---------- the frames ----------
def scan_size(info: MediaInfo) -> tuple[int, int]:
    if info.width >= info.height:
        return SCAN_SIDE, layouts.even(SCAN_SIDE * info.height / info.width)
    return layouts.even(SCAN_SIDE * info.width / info.height), SCAN_SIDE


def layout_graph_for(info: MediaInfo, options, layout: str, facecam) -> tuple[str, tuple]:
    """The filter graph (reads [0:v], writes [v]) that draws a frame the way render_clip draws the clip with these
    options, at THUMB_RESOLUTION on the short side (never above the source); and the parts of the source it shows
    ([x, y, w, h] fractions)."""
    vertical, aspect = getattr(options, "vertical", True), getattr(options, "aspect", "9:16")
    w, h = output_size(info.width, info.height, vertical, aspect, THUMB_RESOLUTION,
                       max_side=getattr(options, "max_side", None))
    if not vertical:
        return f"[0:v]scale={w}:{h},setsar=1[v]", (FULL,)
    if layouts.canonical(layout, aspect) == "classic":
        graph = vertical_filter(info.width, info.height, getattr(options, "zoom", 1.0),
                                getattr(options, "chat_region", "none"))
        return graph[: -len("[v]")] + f",scale={w}:{h},setsar=1[v]", (FULL,)
    plan = plan_for(info.width, info.height, layout, facecam, aspect, getattr(options, "zoom", 1.0),
                    getattr(options, "camera", None), getattr(options, "split_ratio", None))
    view = tuple((p.src[0] / info.width, p.src[1] / info.height, p.src[2] / info.width, p.src[3] / info.height)
                 for p in plan.panels)
    return layouts.layout_graph(plan, (w, h)), view


def grab_frames(src, info: MediaInfo, start: float, end: float, graph: str, folder: Path,
                deadline: Deadline | None = None, keyframes: bool = True, most: int = MAX_FRAMES) -> list[Frame]:
    """The frames in [start, end) with their source times, each small and gray (to score) and drawn through `graph`
    into `folder` as JPEG (to use). With `keyframes` only keyframes are decoded, so a frame costs a few
    milliseconds; the list is empty when the span holds none. Without, the first `most` frames from `start`."""
    w, h = scan_size(info)
    folder.mkdir(parents=True, exist_ok=True)
    out, log_text = run_binary(["ffmpeg", "-hide_banner", "-loglevel", "info",
                                *(["-skip_frame", "nokey"] if keyframes else []),
                                "-ss", f"{start:.3f}", "-t", f"{max(0.05, end - start):.3f}", *SAFE_IN, "-i", src,
                                "-an", "-sn", "-filter_complex",
                                f"[0:v]split=2[sa][sb];[sa]scale={w}:{h},format=gray,showinfo[g];"
                                + graph.replace("[0:v]", "[sb]", 1),
                                "-map", "[g]", "-fps_mode", "passthrough", "-frames:v", str(most),
                                "-f", "rawvideo", "pipe:1",
                                "-map", "[v]", "-fps_mode", "passthrough", "-frames:v", str(most), "-q:v", "2",
                                "-f", "image2", folder / "k%03d.jpg"], deadline, cap=60)
    times = [float(x) for x in re.findall(r"\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:(-?[\d.]+)", log_text)]
    n = min(len(times), len(out) // (w * h))
    # The decoder can hand over the next keyframe after the span when there is none inside it: not this clip's.
    return [Frame(start + times[i], np.frombuffer(out, np.uint8, w * h, i * w * h).reshape(h, w),
                  folder / f"k{i + 1:03d}.jpg") for i in range(n) if -0.05 <= times[i] <= end - start]


# ---------- choosing one ----------
def _box_px(box, w: int, h: int) -> tuple[int, int, int, int]:
    x, y, bw, bh = box
    x0, y0 = max(0, int(x * w)), max(0, int(y * h))
    return x0, y0, min(w, int((x + bw) * w)), min(h, int((y + bh) * h))


@dataclass
class Faces:
    patch: np.ndarray | None  # the biggest whole face, normalised 24x24 (for its expression)
    seen: bool                # any face where it would be seen
    cut: bool                 # a face cut by the edge of what is seen


def _inside_box(f, box, margin: float) -> bool:
    x, y, w, h = box
    return (f[0] >= x + margin * w and f[1] >= y + margin * h
            and f[0] + f[2] <= x + w - margin * w and f[1] + f[3] <= y + h - margin * h)


def _faces(gray: np.ndarray, cam=None, view=(FULL,)) -> Faces:
    """The faces of one frame. With a camera box, the streamer's face in it: whole, or cut by the box. Without
    one, every face in the parts of the source the layout shows (`view`, [x, y, w, h] fractions): whole, or cut
    by a panel edge (a face outside every panel is not seen at all)."""
    import cv2
    from .facecam import _detector
    H, W = gray.shape
    box = cam if cam is not None else FULL
    x0, y0, x1, y1 = _box_px(box, W, H)
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0 or min(crop.shape) < 8:
        return Faces(None, False, False)
    rows, least = (FACE_ROWS, 0.25) if cam is not None else (SCENE_ROWS, 0.1)   # a webcam face fills its box
    k = rows / crop.shape[0]
    crop = cv2.resize(crop, (max(8, int(crop.shape[1] * k)), rows),
                      interpolation=cv2.INTER_LINEAR if k > 1 else cv2.INTER_AREA)
    ch, cw = crop.shape
    small = max(20, int(least * min(ch, cw)))
    found = _detector().detectMultiScale(crop, scaleFactor=1.2, minNeighbors=4, minSize=(small, small))
    bx, by, bw, bh = (x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H)
    faces = [(bx + x / cw * bw, by + y / ch * bh, w / cw * bw, h / ch * bh) for x, y, w, h in found]   # fractions
    if cam is None:          # only faces the layout shows count
        faces = [f for f in faces if any(f[0] < v[0] + v[2] and f[0] + f[2] > v[0] and f[1] < v[1] + v[3]
                                         and f[1] + f[3] > v[1] for v in view)]
    whole = [f for f in faces if any(_inside_box(f, v, FACE_MARGIN) for v in ([cam] if cam is not None else view))]
    cut = len(whole) < len(faces)
    if not whole:
        return Faces(None, bool(faces), cut)
    px0, py0, px1, py1 = _box_px(max(whole, key=lambda f: f[2] * f[3]), W, H)
    face = gray[py0:py1, px0:px1]
    if face.size == 0 or min(face.shape) < 4:
        return Faces(None, True, cut)
    patch = cv2.resize(face, (24, 24), interpolation=cv2.INTER_AREA).astype(np.float32)
    return Faces((patch - patch.mean()) / (patch.std() + 1e-3), True, cut)


def _straight(gray: np.ndarray, play: np.ndarray) -> float:
    """The share of the strong edges in `play` that are level or upright (within 4 degrees). Menus, results cards
    and scoreboards are drawn in straight lines; a game world seldom is."""
    import cv2
    g = gray.astype(np.float32)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    strong = (np.hypot(gx, gy) > 60) & play
    if not strong.any():
        return 0.0
    angle = np.degrees(np.arctan2(gy[strong], gx[strong])) % 90
    return float(((angle < 4) | (angle > 86)).mean())


def _blend(before: np.ndarray, frame: np.ndarray, after: np.ndarray, play: np.ndarray) -> bool:
    """`frame` is a dissolve between two different pictures: close to a mix of the keyframes either side of it,
    and close to neither."""
    p, f, n = before[play], frame[play], after[play]
    span = float(np.abs(p - n).mean())
    if span < 15:
        return False                                   # the two sides are alike: nothing to dissolve between
    d = p - n
    a = float(np.clip(np.dot(f - n, d) / (np.dot(d, d) + 1e-6), 0.0, 1.0))
    mixed = float(np.abs(f - (a * p + (1 - a) * n)).mean())
    return 0.2 < a < 0.8 and mixed < 0.35 * span


def _norm(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    return [(v - lo) / (hi - lo) if hi > lo else 0.0 for v in values]


def inside(t: float, segments) -> bool:
    """`t` is in a piece the clip keeps, and at least EDGE_GUARD from its cuts."""
    return any(s + EDGE_GUARD <= t <= e - EDGE_GUARD for s, e in segments)


def score_frames(frames: list[Frame], cam=None, segments=None, loudness=None, peak: float | None = None,
                 view=(FULL,)) -> list[Scored]:
    """Score each frame (see the module doc). `cam` is the camera box [x, y, w, h] as fractions of the source, or
    None; without one, the faces that count are those in `view` (the parts of the source the layout shows).
    A clip has people when it has a camera, or when faces are seen in a third of its frames: then a frame without
    a whole face, or with a face cut by an edge, loses half its score. `segments` are the pieces of the source the
    clip keeps (default: the frames' own span). `loudness(t)` gives the level at source second t, or None. `peak`
    is the judge's most striking second."""
    import cv2
    if not frames:
        return []
    h, w = frames[0].gray.shape
    segments = segments or [(frames[0].t - EDGE_GUARD, frames[-1].t + EDGE_GUARD)]
    play = np.ones((h, w), bool)                       # the picture that is not the camera
    if cam is not None:
        x0, y0, x1, y1 = _box_px(cam, w, h)
        play[y0:y1, x0:x1] = False
        if not play.any():
            play[:] = True                             # the camera is the whole picture
    sw = 160
    sh = max(2, int(sw * h / w))
    small_play = cv2.resize(play.astype(np.uint8), (sw, sh), interpolation=cv2.INTER_NEAREST).astype(bool)
    small = [cv2.resize(f.gray, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.float32) for f in frames]

    def diff(i: int, j: int) -> float:
        return float(np.abs(small[i] - small[j])[small_play].mean())

    n = len(frames)
    sharp = [float(cv2.Laplacian(f.gray, cv2.CV_32F)[play].var()) for f in frames]
    usual = float(np.median(sharp)) or 1.0
    menu = [_straight(f.gray, play) > UI_LINES or sharp[i] > UI_DETAIL * usual for i, f in enumerate(frames)]
    action, transient = [], []
    for i in range(n):
        near = [diff(i, j) for j in (i - 1, i + 1) if 0 <= j < n]
        action.append(sum(near) / len(near) if near else 0.0)
        transient.append(0 < i < n - 1 and (min(near) > 1.8 * diff(i - 1, i + 1) + 8           # a flash
                                            or _blend(small[i - 1], small[i], small[i + 1], small_play)))
    busy = BUSY * (float(np.median(action)) or 1.0)
    faces = [_faces(f.gray, cam, view) for f in frames]
    people = cam is not None or sum(x.seen for x in faces) >= max(2, n / 3)
    found = [x.patch for x in faces if x.patch is not None]
    rest = np.median(np.stack(found), axis=0) if len(found) >= 2 else None
    expression = [float(np.abs(x.patch - rest).mean()) if x.patch is not None and rest is not None else 0.0
                  for x in faces]
    levels = [loudness(f.t) if loudness else None for f in frames]
    loud = _norm([v if v is not None else 0.0 for v in levels]) if any(v is not None for v in levels) else [0.0] * n
    next_to_menu = [not menu[i] and any(menu[j] and abs(frames[j].t - frames[i].t) <= MENU_FADE
                                        for j in (i - 1, i + 1) if 0 <= j < n) for i in range(n)]
    weights = WEIGHTS_CAM if people else WEIGHTS_NO_CAM
    parts = {"face": _norm(expression), "loud": loud, "action": [min(1.0, a / busy) for a in action],
             "sharp": [min(1.0, s / usual) for s in sharp]}
    out = []
    for i, f in enumerate(frames):
        score = sum(weights[k] * parts[k][i] for k in weights)
        if peak is not None:
            score += PEAK_BONUS * max(0.0, 1 - abs(f.t - peak) / PEAK_REACH)
        mean, spread = float(f.gray.mean()), float(f.gray.std())
        failed = [name for name, bad in (("dark", mean < DARK), ("bright", mean > BRIGHT), ("flat", spread < FLAT),
                                         ("blurred", sharp[i] < BLUR * usual), ("menu", menu[i]),
                                         ("menu_edge", next_to_menu[i]), ("transition", transient[i]),
                                         ("cut", not inside(f.t, segments))) if bad]
        face = (faces[i].patch is not None and not faces[i].cut) if people else None
        if face is False:
            score *= NO_FACE
            failed.append("face_cut" if faces[i].cut else "no_face")
        out.append(Scored(f.t, round(score, 4), not failed, face, failed))
    return out


def best(scored: list[Scored], middle: float) -> Scored:
    """The frame to use: the best that passed every check; when none did, the one that failed fewest (a frame on a
    cut fails worst: it may not be in the clip at all). Ties go to the frame nearest the middle of the clip."""
    return max(scored, key=lambda s: (s.ok, -("cut" in s.failed), -len(s.failed), s.score, -abs(s.t - middle)))


# ---------- the text ----------
def _font_for(text: str) -> str | None:
    """The first of FONTS that has every letter of `text`, or None."""
    from PIL import ImageFont
    for path in FONTS:
        if not Path(path).is_file():
            continue
        font = ImageFont.truetype(str(path), 64)
        missing = bytes(font.getmask(""))        # a private-use character: no font draws it, so this is .notdef
        if all(ch.isspace() or bytes(font.getmask(ch)) != missing for ch in set(text)):
            return str(path)
    return None


def _wrap(words: list[str], width, room: float, most: int) -> list[list[str]] | None:
    """`words` in as few lines as fit `room` pixels (at most `most` lines), the lines as even as possible. A word
    wider than the room on its own is broken into pieces. None when they need more lines."""
    pieces = []
    for word in words:
        while len(word) > 1 and width(word) > room:
            cut = max([k for k in range(1, len(word)) if width(word[:k]) <= room] or [1])
            pieces.append(word[:cut])
            word = word[cut:]
        pieces.append(word)
    lines, cur = [], []
    for word in pieces:
        if cur and width(" ".join(cur + [word])) > room:
            lines.append(cur)
            cur = []
        cur.append(word)
    lines.append(cur)
    if len(lines) > most:
        return None
    if len(lines) == 1 or len(pieces) > 12:
        return lines
    best_lines, best_w = lines, max(width(" ".join(x)) for x in lines)
    for cuts in combinations(range(1, len(pieces)), len(lines) - 1):          # the most even break, for short text
        split = [pieces[a:b] for a, b in zip((0, *cuts), (*cuts, len(pieces)))]
        widest = max(width(" ".join(x)) for x in split)
        if widest < best_w - 0.5:
            best_lines, best_w = split, widest
    return best_lines


def _shorten(words: list[str], width, room: float, most: int) -> list[list[str]]:
    """Text that does not fit even at the smallest size: the words that fit, the last one ending in an ellipsis."""
    while words:
        lines = _wrap(words[:-1] + [words[-1] + "…"], width, room, most)
        if lines is not None:
            return lines
        words = words[:-1]
    return [["…"]]


def fit_text(text: str | None, canvas: Canvas) -> TextBlock | None:
    """Lay `text` out on `canvas`: upper case, as large as fits (capitals CAP_MAX of the short side, down to CAP_MIN),
    in up to MAX_LINES lines, inside the safe margins and rows, off every `avoid` box when there is room. Text that
    does not fit at the smallest size is cut short with an ellipsis: it never runs past the margins.
    None when there is no text or no font that has its letters."""
    from PIL import ImageFont
    words = [w for w in (impact_text(x) for x in (text or "").split()) if w]
    if not words:
        return None
    path = _font_for(" ".join(words))
    if path is None:
        return None
    cw, ch = canvas.size
    side = min(cw, ch)
    span_w = (canvas.span[1] - canvas.span[0]) * cw
    center_x = (canvas.span[0] + canvas.span[1]) / 2 * cw
    rows = SAFE_TALL if ch >= 1.5 * cw else SAFE_OTHER
    tallest = min((rows[1] - rows[0]) * ch, MAX_BLOCK * ch)
    probe = ImageFont.truetype(path, 100).getbbox("H")
    cap_em = (probe[3] - probe[1]) / 100
    px_max, px_min = int(CAP_MAX * side / cap_em), max(8, int(CAP_MIN * side / cap_em))

    def measure(px: int):
        font = ImageFont.truetype(path, px)
        stroke = max(2, round(STROKE * px))
        cap = round(cap_em * px)
        return font, stroke, cap, round(LINE * cap), span_w * (1 - 2 * MARGIN) - 2 * stroke

    chosen = None
    for px in range(px_max, px_min - 1, -max(1, px_max // 40)):
        font, stroke, cap, pitch, room = measure(px)
        lines = _wrap(words, font.getlength, room, MAX_LINES)
        if lines is not None and (len(lines) - 1) * pitch + cap + 2 * stroke <= tallest:
            chosen = (font, px, stroke, cap, pitch, lines)
            break
    if chosen is None:                                 # the smallest size, cut short
        font, stroke, cap, pitch, room = measure(px_min)
        most = max(1, min(MAX_LINES, int((tallest - cap - 2 * stroke) // pitch) + 1))
        chosen = (font, px_min, stroke, cap, pitch, _shorten(words, font.getlength, room, most))
    font, px, stroke, cap, pitch, lines = chosen
    widths = [font.getlength(" ".join(x)) + 2 * stroke for x in lines]
    flat = [w for line in lines for w in line]
    block = TextBlock(lines, path, px, cap, stroke, pitch, 0, (len(lines) - 1) * pitch + cap + 2 * stroke, widths,
                      center_x, keyword(flat) if path.endswith(IMPACT_FILE) else None)
    block.top = _place(block, canvas, rows)
    return block


def _place(block: TextBlock, canvas: Canvas, rows: tuple[float, float]) -> int:
    """The block's top row: the most wanted place (the seam; else the upper third, the lower third, the middle;
    in a wide frame the top, the bottom, the middle), moved the least distance that keeps it off every `avoid`
    box, inside the safe rows."""
    cw, ch = canvas.size
    lo, hi = rows[0] * ch, rows[1] * ch - block.height
    centers = [canvas.seam] if canvas.seam else []
    centers += [0.30 * ch, 0.68 * ch, 0.5 * ch] if ch >= 1.2 * cw else [0.22 * ch, 0.78 * ch, 0.5 * ch]
    x0, _, x1, _ = block.box()
    gap = HEAD_GAP * ch
    boxes = [b for b in canvas.avoid if b[0] < x1 and b[2] > x0]

    def overlap(top: float) -> float:
        return sum(max(0.0, min(top + block.height, b[3] + gap) - max(top, b[1] - gap)) for b in boxes)

    options = []
    for rank, c in enumerate(centers):
        want = min(max(c - block.height / 2, lo), hi)
        for top in [want] + [t for b in boxes for t in (b[3] + gap, b[1] - gap - block.height)]:
            if lo <= top <= hi:
                options.append((overlap(top) > 0.5, rank, abs(top - want), top))
    if not options:                                    # taller than the safe rows allow: as high as they start
        return int(round(max(0.0, min(lo, ch - block.height))))
    return int(round(min(options)[3]))


def draw_text(image, block: TextBlock, accent: str | None = None):
    """`block` drawn on `image` (a PIL RGB image): white capitals with a dark outline and a soft shadow, the
    keyword in the accent colour."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    font = ImageFont.truetype(block.font, block.px)
    colour = _rgb(accent) or _rgb(ACCENT)
    drop = max(2, round(0.05 * block.px))
    placed, k = [], 0
    for i, line in enumerate(block.lines):
        left = block.center_x - block.widths[i] / 2 + block.stroke
        base = block.top + block.stroke + block.cap + i * block.pitch
        for j, word in enumerate(line):
            x = left + (font.getlength(" ".join(line[:j]) + " ") if j else 0)
            placed.append((x, base, word, k == block.accent))
            k += 1
    shadow = Image.new("L", image.size, 0)
    sd = ImageDraw.Draw(shadow)
    for x, y, word, _ in placed:
        sd.text((x + drop, y + drop), word, font=font, anchor="ls", fill=170, stroke_width=block.stroke,
                stroke_fill=170)
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, round(0.06 * block.px))))
    image.paste(Image.new("RGB", image.size, DARK_INK), (0, 0), shadow)
    d = ImageDraw.Draw(image)
    for x, y, word, key in placed:
        d.text((x, y), word, font=font, anchor="ls", fill=colour if key else (255, 255, 255),
               stroke_width=block.stroke, stroke_fill=DARK_INK)
    return image


def _rgb(colour: str | None) -> tuple[int, int, int] | None:
    if not colour or not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour):
        return None
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def thumb_text(meta: dict | None, censor: bool = False) -> str | None:
    """The words a thumbnail carries: the clip's hook, or its title when it has no hook. Swears masked with
    `censor`, as in the clip."""
    meta = meta if isinstance(meta, dict) else {}
    text = meta.get("hook") or meta.get("title")
    if not isinstance(text, str) or not text.strip():
        return None
    return " ".join(mask(w) for w in text.split()) if censor else text


def write_thumbnail(frame: Path, out: Path, text: str | None, canvas: Canvas, accent: str | None = None) -> bool:
    """The thumbnail `out`: `frame` with `text` laid out on `canvas`. Returns whether text was drawn (no text, or no
    font for its letters, gives the frame alone)."""
    from PIL import Image
    with Image.open(frame) as im:
        image = im.convert("RGB")
    if image.size != tuple(canvas.size):              # a canvas measured for another size: scale its boxes
        sx, sy = image.size[0] / canvas.size[0], image.size[1] / canvas.size[1]
        canvas = Canvas(image.size, tuple((b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy) for b in canvas.avoid),
                        canvas.seam * sy if canvas.seam else None, canvas.span)
    block = fit_text(text, canvas)
    if block is not None:
        draw_text(image, block, accent)
    image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return block is not None


# ---------- the whole thumbnail ----------
def canvas_for(info: MediaInfo, options, layout: str, facecam, size: tuple[int, int]) -> Canvas:
    """Where text may go on a `size` thumbnail of a clip drawn with these options: off the person's head and off
    an inset camera, on the seam between stacked panels."""
    w, h = size
    vertical, aspect = getattr(options, "vertical", True), getattr(options, "aspect", "9:16")
    if vertical and layouts.canonical(layout, aspect) != "classic":
        plan = plan_for(info.width, info.height, layout, facecam, aspect, getattr(options, "zoom", 1.0),
                        getattr(options, "camera", None), getattr(options, "split_ratio", None))
        sx, sy = w / plan.size[0], h / plan.size[1]
        boxes = [plan.head] if plan.head else []
        boxes += [(p.out[0], p.out[1], p.out[0] + p.out[2], p.out[1] + p.out[3]) for p in plan.panels
                  if p.kind == "camera" and p.out[2] < plan.size[0] and p.out[3] < plan.size[1]]   # an inset
        return Canvas(size, tuple((b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy) for b in boxes),
                      plan.seam * sy if plan.seam else None, plan.text_span)
    box = _camera(facecam)[0] if not vertical else None
    if box:                                            # the source's own framing: keep off its camera
        return Canvas(size, (_box_px(box, w, h),))
    return Canvas(size)


def make_thumbnail(src, info: MediaInfo, start: float, end: float, out: Path, *, options, layout: str, facecam,
                   text: str | None = None, segments=None, peak: float | None = None, loudness: list | None = None,
                   deadline: Deadline | None = None) -> Thumb:
    """The thumbnail of the clip [start, end] of `src`, drawn as render_clip draws the clip with `options`, `layout`
    and `facecam`: written to `out` (JPEG), with the frame alone next to it. `text` is the hook (or title) to set
    on it; `segments` the pieces of the source the clip keeps; `peak` the judge's most striking second;
    `loudness` the level of each source second (dB). Raises PipelineError when no frame can be drawn."""
    out = Path(out)
    segments = segments or [(start, end)]
    longest = max(segments, key=lambda s: s[1] - s[0])
    middle = (longest[0] + longest[1]) / 2
    graph, view = layout_graph_for(info, options, layout, facecam)
    folder, frame = out.with_suffix(".frames"), out.with_suffix(".frame.jpg")
    pick = None
    try:
        frames = grab_frames(src, info, start, end, graph, folder, deadline)
        if frames:
            levels = loudness or []
            level = (lambda t: levels[int(t)] if 0 <= int(t) < len(levels) else None) if levels else None
            try:
                pick = best(score_frames(frames, _camera(facecam)[0], segments, level, peak, view), middle)
            except PipelineTimeout:
                raise
            except Exception:
                log.exception("thumbnail frame scoring failed; using the frame nearest the middle")
            chosen = next(f for f in frames if f.t == pick.t) if pick else min(frames, key=lambda f: abs(f.t - middle))
        else:          # no keyframe inside the clip (shorter than the keyframe spacing): the middle of the clip
            t = max(0.0, min(middle, info.duration - 0.1))
            frames = grab_frames(src, info, t, t + 0.1, graph, folder, deadline, keyframes=False, most=1)
            if not frames:
                raise PipelineError("thumbnail_failed", "The thumbnail could not be drawn.")
            chosen = frames[0]
        if not chosen.image.exists():
            raise PipelineError("thumbnail_failed", "The thumbnail could not be drawn.")
        shutil.move(chosen.image, frame)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    from PIL import Image
    with Image.open(frame) as im:
        size = im.size
    canvas = canvas_for(info, options, layout, facecam, size)
    try:
        drawn = write_thumbnail(frame, out, text, canvas, getattr(options, "caption_accent", None))
    except PipelineTimeout:
        raise
    except Exception:
        log.exception("thumbnail text failed; the frame is used alone")
        drawn = False
        shutil.copy(frame, out)
    record = {"at": round(chosen.t, 3), "frames": len(frames) if pick else 0,
              "score": pick.score if pick else None, "face": pick.face if pick else None,
              "failed": pick.failed if pick else [], "text": drawn,
              "canvas": {**asdict(canvas), "size": list(size)}}
    return Thumb(out, frame, record)


def canvas_of(record: dict | None) -> Canvas | None:
    """The Canvas kept in a clip's features["thumbnail"], so the text can be set later (when the title comes
    after the clip)."""
    c = (record or {}).get("canvas")
    if not isinstance(c, dict):
        return None
    try:
        size = tuple(int(v) for v in c["size"])
        canvas = Canvas(size, tuple(tuple(float(v) for v in b) for b in c.get("avoid") or ()),
                        float(c["seam"]) if c.get("seam") is not None else None,
                        tuple(float(v) for v in c.get("span") or (0.0, 1.0)))
    except (KeyError, TypeError, ValueError):
        return None
    ok = len(size) == 2 and min(size) > 0 and len(canvas.span) == 2 and all(len(b) == 4 for b in canvas.avoid)
    return canvas if ok else None
