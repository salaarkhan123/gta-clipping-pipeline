"""Reframe layouts: what kind of picture a source is, and where each part of it goes in the output frame.

    plan_layout(info, frames, requested, aspect) -> LayoutPlan     decide the scene type and the boxes
    compose(src_w, src_h, layout, aspect, scene=..., cam=...)       the same, when the scene is already known
    layout_graph(plan, size, punch) -> str                         the ffmpeg filter graph that draws a plan

The rule every layout follows (owner, 2026-11-16): people are never blurred, never cropped out and never cut by
a crop edge. A webcam overlay is either left out of a gameplay crop completely (and shown in its own panel) or
kept whole inside it. When a layout cannot do that for a given source, a plainer one that can is drawn instead
(`LayoutPlan.layout` says which, `LayoutPlan.note` says why). Nothing here ever covers a camera with a patch.

Scene types: "gameplay_cam" (gameplay with a webcam overlay), "camera" (the camera fills the frame) and
"gameplay" (no camera).
"""
from dataclasses import dataclass

from .ff import PipelineError

LAYOUTS = ("auto", "full", "fit", "split2", "trio", "grid4", "pip", "ots", "screen_first", "gameplay_a", "gameplay_b")
# Which layouts may be asked for in which output shape (docs/PARITY.md section 1).
ALLOWED = {
    "16:9": ("auto", "full", "fit", "grid4", "split2", "trio", "pip", "ots", "screen_first"),
    "9:16": ("auto", "full", "fit", "grid4", "split2", "trio", "pip", "screen_first", "gameplay_a", "gameplay_b"),
    "1:1": ("auto", "full", "fit", "grid4", "trio"),
    "4:5": ("auto", "full", "fit", "grid4", "split2", "trio", "pip", "screen_first", "gameplay_a", "gameplay_b"),
}
# Every layout is built. trio, grid4 and ots are our own reading of the names (PROVISIONAL: WayinVideo's docs give
# only the names): see _trio, _grid4 and _ots. The name stays so callers that test it keep working.
NOT_BUILT: tuple[str, ...] = ()
BUILT = tuple(name for name in LAYOUTS if name not in NOT_BUILT)
# The layout names from before the reframe layouts. They keep working, in every shape, with their old meaning:
# split = split2 (plain fill in 16:9), fill = full, classic = the blurred 9:16 layout with a chat panel (render.py).
LEGACY = ("split", "fill", "classic")
NEEDS_CAMERA = ("split", "split2", "pip", "screen_first", "gameplay_a", "gameplay_b", "trio", "grid4", "ots")
# The two-panel layouts: a camera panel and a gameplay panel. `camera` and `split_ratio` apply to these, whether
# the layout was asked for by name or "auto" chose it; every other layout ignores both.
TWO_PANEL = ("split2", "screen_first", "gameplay_a", "gameplay_b")
CAMERA_SIDES = ("top", "bottom")          # which panel the camera is: the first one (top, or left in a wide frame)
SPLIT_RATIO = (0.25, 0.75)                # the first panel's share of the frame: of the height, or of a wide frame's width
CAPTION_POSITIONS = ("auto", "seam", "lower", "center")
SCENES = ("gameplay_cam", "camera", "gameplay")

ASPECTS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}
FULL_FRAME = (0.0, 0.0, 1.0, 1.0)
# Where the streamer's facecam usually sits, as fractions: (x, y, width, height).
FACECAM_REGIONS = {
    "top-left": (0.0, 0.0, 0.30, 0.30),
    "top-right": (0.70, 0.0, 0.30, 0.30),
    "bottom-left": (0.0, 0.70, 0.30, 0.30),
    "bottom-right": (0.70, 0.70, 0.30, 0.30),
}

FACECAM_PAD = 0.02     # keep this much (fraction of the frame) between the gameplay crop and the camera box
MAX_DODGE = 0.3        # the gameplay crop may step this share of its own size to clear a camera inside the frame
EDGE = 0.02            # a camera box this close to a frame edge counts as sitting on that edge
MAX_AVOID_ZOOM = 1.35  # a gameplay panel may zoom in this much further when that is what keeps the camera out of it
HEAD_PAD = (0.15, 0.35, 0.10)    # hair, a headset and the chin around a detected face box: sides, top, bottom (of the face size)
PIP_SHAPE = (0.8, 1.9)           # the inset keeps the camera's own shape, within these width / height limits
PIP_BORDER = 4                   # pixels of white edge around the inset, on the 1080 canvas
LOWER_THIRD = 0.70               # where a caption sits when there is no line between panels to sit on
SAFE_ROWS = (0.05, 0.92)         # a caption stays between these shares of the height (clear of the apps' own buttons)
FACE_GAP = 14                    # pixels kept between a caption and the head, on a 1920-high canvas
BLIND_HEAD = 0.85                # no face known: the head is taken to be anywhere in the camera picture but its lowest 15%

Rect = tuple[float, float, float, float]     # x, y, width, height


# ---------- geometry ----------
def even(n) -> int:
    return int(n) // 2 * 2


def crop_rect(src_w: int, src_h: int, region, tw: int, th: int, zoom: float = 1.0) -> Rect:
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


def path_expr(points) -> str:
    """An ffmpeg expression of t through the (t, value) points in straight lines, flat before the first point and
    after the last."""
    expr = f"{points[-1][1]:.1f}"
    for (t0, v0), (t1, v1) in reversed(list(zip(points, points[1:]))):
        expr = f"if(lt(t,{t1:.3f}),{v0:.1f}+{v1 - v0:.1f}*(t-{t0:.3f})/{t1 - t0:.3f},{expr})"
    return f"if(lt(t,{points[0][0]:.3f}),{points[0][1]:.1f},{expr})"


def _moving_crop_scale(path, tw: int, th: int) -> str:
    """Like _crop_scale for a crop that slides along `path` ((t, rect) points, every rect the same size)."""
    _x, _y, cw, ch = path[0][1]
    xs, ys = [(t, r[0]) for t, r in path], [(t, r[1]) for t, r in path]
    return (f"crop=w={even(cw)}:h={even(ch)}:x='{path_expr(xs)}':y='{path_expr(ys)}',"
            f"scale={tw}:{th},setsar=1")


def fill_crop(src_w: int, src_h: int, region, tw: int, th: int, zoom: float = 1.0) -> str:
    """Crop `region` (fractions) to the target aspect, centred, then scale to fill tw x th exactly."""
    return _crop_scale(crop_rect(src_w, src_h, region, tw, th, zoom), tw, th)


def _overlaps(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _union(a: Rect, b: Rect) -> Rect:
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    return x0, y0, max(a[0] + a[2], b[0] + b[2]) - x0, max(a[1] + a[3], b[1] + b[3]) - y0


def _inside(box: Rect, rect: Rect, tol: float = 0.0) -> bool:
    return (box[0] >= rect[0] - tol and box[1] >= rect[1] - tol and box[0] + box[2] <= rect[0] + rect[2] + tol
            and box[1] + box[3] <= rect[1] + rect[3] + tol)


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), max(lo, hi))


def punch_in(tw: int, th: int, expr: str) -> str:
    """Zoom the tw x th picture by `expr` (an ffmpeg expression of t, 1 = no zoom) about its centre. Empty for "1"."""
    if expr == "1":
        return ""
    return (f",scale=w='2*trunc({tw}*({expr})/2)':h='2*trunc({th}*({expr})/2)':eval=frame,crop={tw}:{th}")


def cam_px(cam, src_w: int, src_h: int) -> Rect:
    return cam[0] * src_w, cam[1] * src_h, cam[2] * src_w, cam[3] * src_h


def head_box(face, src_w: int, src_h: int) -> Rect:
    """The whole head around a detected face (centre x, centre y, w, h as fractions), in source pixels."""
    cx, cy, fw, fh = face
    side, top, bottom = HEAD_PAD
    x0, x1 = max(0.0, cx - fw / 2 - side * fw), min(1.0, cx + fw / 2 + side * fw)
    y0, y1 = max(0.0, cy - fh / 2 - top * fh), min(1.0, cy + fh / 2 + bottom * fh)
    return x0 * src_w, y0 * src_h, (x1 - x0) * src_w, (y1 - y0) * src_h


def person_box(cam, face, src_w: int, src_h: int) -> Rect | None:
    """Everything of the person that must stay whole: the camera box and the head, in source pixels."""
    boxes = ([cam_px(cam, src_w, src_h)] if cam else []) + ([head_box(face, src_w, src_h)] if face else [])
    if not boxes:
        return None
    return boxes[0] if len(boxes) == 1 else _union(*boxes)


def hold(rect: Rect, box: Rect, src_w: int, src_h: int, limit: float | None = None) -> Rect | None:
    """`rect` moved the least distance that puts `box` whole inside it, staying in the frame. None when the box
    is bigger than the crop, or when the step is more than `limit` of the crop's own size."""
    x, y, w, h = rect
    bx, by, bw, bh = box
    if bw > w + 0.5 or bh > h + 0.5:
        return None
    nx = _clamp(_clamp(x, bx + bw - w, bx), 0.0, src_w - w)
    ny = _clamp(_clamp(y, by + bh - h, by), 0.0, src_h - h)
    if limit is not None and (abs(nx - x) > limit * w or abs(ny - y) > limit * h):
        return None
    return nx, ny, w, h


def _dodge(src_w: int, src_h: int, rect: Rect, box: Rect, cam) -> tuple[str, Rect | None]:
    """`rect` moved the least distance that clears `box` (the padded camera). ("clear" | "shifted", rect), or
    ("blocked", None) when no allowed step does it."""
    cx, cy, cw, ch = rect
    if not _overlaps(rect, box):
        return "clear", rect
    bx, by, bw, bh = box
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
    if not moves:
        return "blocked", None
    _dist, (nx, ny), _ok = min(moves, key=lambda m: m[0])
    return "shifted", (nx, ny, cw, ch)


def _keep_out(src_w: int, src_h: int, cam, face=None) -> Rect:
    """The part of the source a gameplay picture must stay clear of: the padded camera box and the head."""
    pad_x, pad_y = FACECAM_PAD * src_w, FACECAM_PAD * src_h
    box = (cam[0] * src_w - pad_x, cam[1] * src_h - pad_y, cam[2] * src_w + 2 * pad_x, cam[3] * src_h + 2 * pad_y)
    return _union(box, head_box(face, src_w, src_h)) if face else box


def avoid_camera(src_w: int, src_h: int, tw: int, th: int, zoom: float, cam, face=None,
                 max_zoom: float = 1.0) -> tuple[str, Rect | None]:
    """The gameplay crop (target shape tw:th) with the webcam overlay kept out of it completely.

    Returns (how, rect): "clear" (the centred crop misses the camera), "shifted" (the crop moves the least
    distance that clears it), "zoomed" (it also had to zoom in, by at most `max_zoom`, to find room beside the
    camera) or ("blocked", None): the camera is in the way and cannot be stepped around. A blocked crop is never
    patched over: the caller draws a layout that shows the camera where it is instead.
    """
    box = _keep_out(src_w, src_h, cam, face)
    step = 0
    while 1 + 0.05 * step <= max_zoom + 1e-9:
        how, rect = _dodge(src_w, src_h, crop_rect(src_w, src_h, FULL_FRAME, tw, th, zoom * (1 + 0.05 * step)), box, cam)
        if rect is not None:
            return ("zoomed" if step else how), rect
        step += 1
    return "blocked", None


def camera_crop(src_w: int, src_h: int, cam, tw: int, th: int, face=None) -> Rect | None:
    """The part of the camera box shown in a tw x th camera panel. Without a known face it is the centred crop of
    the box. With one, the crop moves (and, if the panel's shape leaves too little of the box, grows past the
    box) until the whole head is inside it, so a face is never cut by the panel edge. None if that cannot be done."""
    base = crop_rect(src_w, src_h, cam, tw, th)
    if not face:
        return base
    head = head_box(face, src_w, src_h)
    moved = hold(base, head, src_w, src_h)
    if moved is not None:
        return moved
    k = max(head[2] / base[2], head[3] / base[3])
    w, h = base[2] * k, base[3] * k
    if w > src_w or h > src_h:
        return None
    return (_clamp(head[0] + head[2] / 2 - w / 2, 0.0, src_w - w), _clamp(head[1] + head[3] / 2 - h / 2, 0.0, src_h - h), w, h)


# ---------- the plan ----------
@dataclass(frozen=True)
class Panel:
    kind: str                           # "camera" | "gameplay" | "source" (the whole picture, fit only)
    src: Rect                           # the crop, in source pixels
    out: tuple[int, int, int, int]      # where it lands on the canvas: x, y, w, h
    punch: bool = False                 # punch-in zooms may play here: only ever a panel with no person in it
    border: int = 0                     # pixels of white edge (the inset)
    # A crop that moves over the clip: (seconds from the clip's start, crop in source pixels), in time order, each
    # the same size as `src`. Between two points the crop slides in a straight line. None: `src` the whole clip.
    path: tuple[tuple[float, Rect], ...] | None = None


@dataclass(frozen=True)
class LayoutPlan:
    requested: str                      # what was asked for
    layout: str                         # what is drawn: full | fit | split2 | pip | screen_first | gameplay_a | gameplay_b
    scene: str                          # gameplay_cam | camera | gameplay
    aspect: str
    size: tuple[int, int]               # the canvas the boxes are measured on (ASPECTS[aspect]); it scales to any output size
    panels: tuple[Panel, ...]           # drawn in this order
    background: Rect | None = None      # fit: the source crop blurred behind the picture (never one with a person in it)
    cam: tuple | None = None            # the camera box, as fractions of the source
    face: tuple | None = None           # the face (centre x, centre y, w, h), as fractions of the source
    caption_top: int = 0                # where captions and the hook sit, in canvas pixels from the top
    hook_top: int = 0
    text_span: tuple[float, float] = (0.0, 1.0)    # the part of the width the text is centred in
    note: str | None = None             # why `layout` is not the one that was asked for
    seam: int | None = None             # the line between two stacked panels, in canvas pixels from the top
    head: tuple | None = None           # where a caption must not go: the person's head on the canvas (x0, y0, x1, y1)
    source: tuple[int, int] | None = None   # the source's size in pixels: what `panels[].src` are measured in


def canonical(layout: str, aspect: str) -> str:
    """Today's name for a layout, old names included. "classic" stays itself in 9:16 (it is drawn by render.py)."""
    if layout == "classic":
        return "classic" if aspect == "9:16" else "full"     # classic exists only for 9:16
    if layout == "split":
        return "full" if aspect == "16:9" else "split2"      # the old split never stacked a camera into a 16:9 frame
    return "full" if layout == "fill" else layout


def legacy_name(layout: str) -> str:
    """The name older callers know a drawn layout by (run_pipeline switches punch-in zooms on "split" and "fill")."""
    return {"split2": "split", "full": "fill"}.get(layout, layout)


def layout_problem(layout: str, aspect: str) -> tuple[str, str] | None:
    """(error code, message) when `layout` cannot be asked for in `aspect`, else None."""
    if aspect not in ALLOWED:
        return "bad_options", f"Unknown aspect. Use one of: {', '.join(ALLOWED)}."
    if layout in LEGACY:
        return None
    if layout not in LAYOUTS:
        return "bad_options", f"Unknown layout. Use one of: {', '.join(LAYOUTS)}."
    usable = [name for name in ALLOWED[aspect] if name in BUILT]
    if layout not in ALLOWED[aspect]:
        return "bad_options", f"The {layout} layout is not available in {aspect}. Use one of: {', '.join(usable)}."
    if layout in NOT_BUILT:
        return ("layout_unavailable", f"The {layout} layout needs several people tracked on screen, which is not "
                                      f"available yet. Use one of: {', '.join(usable)}.")
    return None


def check_layout(layout: str, aspect: str) -> str:
    """The canonical name of a layout that may be asked for in this shape; PipelineError otherwise."""
    problem = layout_problem(layout, aspect)
    if problem:
        raise PipelineError(*problem)
    return canonical(layout, aspect)


@dataclass(frozen=True)
class _Ctx:
    sw: int
    sh: int
    aspect: str
    size: tuple[int, int]
    scene: str
    cam: tuple | None
    face: tuple | None
    zoom: float
    camera: str | None = None           # "top" | "bottom": which panel the camera is; None = the layout's own
    split_ratio: float | None = None    # the first panel's share of the frame; None = the layout's own


# name: (camera first?, the camera's share of the frame when stacked, ... when side by side)
_SPLITS = {
    "split2": (True, 1 / 3, 1 / 3),
    "screen_first": (False, 0.30, 0.28),
    # PROVISIONAL. WayinVideo's docs give only the names "Gameplay A" and "Gameplay B", not what they look like.
    # Until the owner confirms with screenshots: A = camera panel on top, gameplay below; B = gameplay on top,
    # camera panel below; each half the frame. No parity is claimed for either.
    "gameplay_a": (True, 0.5, 0.5),
    "gameplay_b": (False, 0.5, 0.5),
}


def _two(c: _Ctx, name: str) -> dict | None:
    """Camera panel and gameplay panel: stacked in a tall or square frame, side by side in a wide one."""
    if c.scene != "gameplay_cam":
        return None
    cam_first, share_v, share_h = _SPLITS[name]
    if c.camera:
        cam_first = c.camera == "top"
    ow, oh = c.size
    stacked = oh >= ow
    length = oh if stacked else ow
    n = even(length * (share_v if stacked else share_h))        # the camera panel
    if c.split_ratio is not None:                               # the first panel's share, whichever panel that is
        first = even(length * c.split_ratio)
        n = first if cam_first else length - first
    if stacked:
        cam_out, game_out = ((0, 0, ow, n), (0, n, ow, oh - n)) if cam_first else ((0, oh - n, ow, n), (0, 0, ow, oh - n))
    else:
        cam_out, game_out = ((0, 0, n, oh), (n, 0, ow - n, oh)) if cam_first else ((ow - n, 0, n, oh), (0, 0, ow - n, oh))
    cam_src = camera_crop(c.sw, c.sh, c.cam, cam_out[2], cam_out[3], c.face)
    _how, game_src = avoid_camera(c.sw, c.sh, game_out[2], game_out[3], c.zoom, c.cam, c.face, MAX_AVOID_ZOOM)
    if cam_src is None or game_src is None:
        return None
    cam_panel, game_panel = Panel("camera", cam_src, cam_out), Panel("gameplay", game_src, game_out, punch=True)
    panels = (cam_panel, game_panel) if cam_first else (game_panel, cam_panel)
    if oh < ow:        # side by side: the text is centred on the gameplay
        return dict(panels=panels, caption_top=int(oh * 0.70), hook_top=int(oh * 0.18),
                    text_span=(game_out[0] / ow, (game_out[0] + game_out[2]) / ow))
    if cam_first:      # captions sit on the seam between camera and gameplay, the hook under them
        return dict(panels=panels, caption_top=n - 60, hook_top=min(n + 120, oh - 220), seam=n)
    seam = oh - n      # camera at the bottom: all text stays on the gameplay above it
    return dict(panels=panels, caption_top=seam - 150, hook_top=max(20, min(int(oh * 0.10), seam - 290)), seam=seam)


def _pip(c: _Ctx) -> dict | None:
    """Gameplay fills the frame; the camera, lifted out of it, is a small inset in the top-left corner."""
    if c.scene != "gameplay_cam":
        return None
    ow, oh = c.size
    _how, game_src = avoid_camera(c.sw, c.sh, ow, oh, c.zoom, c.cam, c.face)
    if game_src is None:
        return None
    _x, _y, cw, ch = cam_px(c.cam, c.sw, c.sh)
    shape = _clamp(cw / ch, *PIP_SHAPE)
    iw = even(ow * (0.36 if oh > ow else 0.30 if oh == ow else 0.24))
    ih = even(iw / shape)
    cam_src = camera_crop(c.sw, c.sh, c.cam, iw, ih, c.face)
    if cam_src is None:
        return None
    x, y = even(ow * 0.04), even(oh * 0.05)
    panels = (Panel("gameplay", game_src, (0, 0, ow, oh), punch=True),
              Panel("camera", cam_src, (x, y, iw, ih), border=PIP_BORDER))
    return dict(panels=panels, caption_top=int(oh * 0.70), hook_top=max(int(oh * 0.18), y + ih + 24))


# ---------- trio, grid4, ots: PROVISIONAL, our own reading of WayinVideo's names (their docs give no pictures) ----------
DETAIL_ZOOM = 2.0       # a second gameplay picture shows this much closer than the widest crop of its shape
OTS_INSET = (0.34, 0.42)          # the over-the-shoulder camera inset's width: share of a wide frame, of a tall one
OTS_TIGHT = (2.6, 2.4, 0.45)      # the person's inset around the face: widths, heights (of the face), and how far down
WIDE_ZOOM = 1.5                   # a full-shape gameplay picture may zoom in this much to clear the camera (grid4, ots)


def _detail(c: _Ctx, tw: int, th: int, anchors, zoom: float = DETAIL_ZOOM) -> Rect | None:
    """A closer gameplay picture of shape tw:th, centred on the first anchor (fractions) where it can be taken
    clear of the camera and the head: it never shows any part of the person."""
    _x, _y, w, h = crop_rect(c.sw, c.sh, FULL_FRAME, tw, th, zoom)
    for ax, ay in anchors:
        rect = (_clamp(ax * c.sw - w / 2, 0.0, c.sw - w), _clamp(ay * c.sh - h / 2, 0.0, c.sh - h), w, h)
        if c.scene != "gameplay_cam":
            return rect
        _how, moved = _dodge(c.sw, c.sh, rect, _keep_out(c.sw, c.sh, c.cam, c.face), c.cam)
        if moved is not None:
            return moved
    return None


def _away_from_camera(c: _Ctx) -> tuple[float, float]:
    """The middle of the quarter of the frame diagonally across from the camera."""
    cx, cy = c.cam[0] + c.cam[2] / 2, c.cam[1] + c.cam[3] / 2
    return (0.75 if cx < 0.5 else 0.25), (0.75 if cy < 0.5 else 0.25)


def _trio(c: _Ctx) -> dict | None:
    """The gameplay large, and two smaller panels: the camera and a closer look at the middle of the game.
    Tall frames: the two small panels side by side on top. Square: under the gameplay. Wide: a column on the right."""
    if c.scene != "gameplay_cam":
        return None
    ow, oh = c.size
    if oh > ow:
        n = even(oh / 3)
        main, cam_out, det_out = (0, n, ow, oh - n), (0, 0, ow // 2, n), (ow // 2, 0, ow - ow // 2, n)
    elif oh == ow:
        n = even(oh * 2 / 3)
        main, cam_out, det_out = (0, 0, ow, n), (0, n, ow // 2, oh - n), (ow // 2, n, ow - ow // 2, oh - n)
    else:
        n = even(ow * 2 / 3)
        main, cam_out, det_out = (0, 0, n, oh), (n, 0, ow - n, oh // 2), (n, oh // 2, ow - n, oh - oh // 2)
    cam_src = camera_crop(c.sw, c.sh, c.cam, cam_out[2], cam_out[3], c.face)
    _how, game = avoid_camera(c.sw, c.sh, main[2], main[3], c.zoom, c.cam, c.face, MAX_AVOID_ZOOM)
    det = _detail(c, det_out[2], det_out[3], [(0.5, 0.5), _away_from_camera(c)])
    if cam_src is None or game is None or det is None:
        return None
    panels = (Panel("gameplay", game, main, punch=True), Panel("camera", cam_src, cam_out), Panel("gameplay", det, det_out))
    if oh > ow:        # captions on the line under the top row, the hook under them on the gameplay
        return dict(panels=panels, caption_top=n - 60, hook_top=min(n + 120, oh - 220), seam=n)
    if oh == ow:       # the small panels are at the bottom: all text stays on the gameplay above them
        return dict(panels=panels, caption_top=n - 150, hook_top=max(20, min(int(oh * 0.10), n - 290)), seam=n)
    return dict(panels=panels, caption_top=int(oh * 0.70), hook_top=int(oh * 0.18), text_span=(0.0, n / ow))


def _grid4(c: _Ctx) -> dict | None:
    """Four equal panels: the camera (top left), the gameplay (top right), a closer look at the middle of the game
    (bottom left) and one at the part of the frame across from the camera (bottom right)."""
    if c.scene != "gameplay_cam":
        return None
    ow, oh = c.size
    hw, hh = even(ow / 2), even(oh / 2)
    cells = [(0, 0, hw, hh), (hw, 0, ow - hw, hh), (0, hh, hw, oh - hh), (hw, hh, ow - hw, oh - hh)]
    cam_src = camera_crop(c.sw, c.sh, c.cam, hw, hh, c.face)
    _how, game = avoid_camera(c.sw, c.sh, cells[1][2], cells[1][3], c.zoom, c.cam, c.face, WIDE_ZOOM)
    centre = _detail(c, cells[2][2], cells[2][3], [(0.5, 0.5), _away_from_camera(c)])
    across = _detail(c, cells[3][2], cells[3][3], [_away_from_camera(c), (0.5, 0.5)])
    if None in (cam_src, game, centre, across):
        return None
    panels = (Panel("camera", cam_src, cells[0]), Panel("gameplay", game, cells[1], punch=True),
              Panel("gameplay", centre, cells[2]), Panel("gameplay", across, cells[3]))
    # Captions on the middle line, the hook under them on the bottom row (the camera is in the top row).
    return dict(panels=panels, caption_top=hh - 60, hook_top=min(hh + 120, oh - 220), seam=hh)


def _ots(c: _Ctx) -> dict | None:
    """Over the shoulder: the gameplay fills the frame and the camera, cropped tight on the person, is a large
    inset in the lower corner on the camera's own side. The text is centred on the rest of the width."""
    if c.scene != "gameplay_cam":
        return None
    ow, oh = c.size
    _how, game = avoid_camera(c.sw, c.sh, ow, oh, c.zoom, c.cam, c.face, WIDE_ZOOM)
    if game is None:
        return None
    region = c.cam
    if c.face:          # head and shoulders, inside the camera box
        fx, fy, fw, fh = c.face
        kw, kh, down = OTS_TIGHT
        x0, x1 = max(c.cam[0], fx - kw * fw / 2), min(c.cam[0] + c.cam[2], fx + kw * fw / 2)
        y0, y1 = max(c.cam[1], fy + down * fh - kh * fh / 2), min(c.cam[1] + c.cam[3], fy + down * fh + kh * fh / 2)
        if x1 > x0 and y1 > y0:
            region = (x0, y0, x1 - x0, y1 - y0)
    shape = _clamp(region[2] * c.sw / (region[3] * c.sh), 0.8, 1.25)
    iw = even(ow * (OTS_INSET[0] if ow > oh else OTS_INSET[1]))
    ih = even(min(iw / shape, 0.55 * oh))
    cam_src = camera_crop(c.sw, c.sh, region, iw, ih, c.face)
    if cam_src is None:
        return None
    margin_x, margin_y = even(ow * 0.03), even(oh * 0.05)
    left = c.cam[0] + c.cam[2] / 2 < 0.5
    x, y = (margin_x if left else ow - iw - margin_x), oh - ih - margin_y
    span = ((x + iw) / ow + 0.02, 1.0) if left else (0.0, x / ow - 0.02)
    panels = (Panel("gameplay", game, (0, 0, ow, oh), punch=True),
              Panel("camera", cam_src, (x, y, iw, ih), border=PIP_BORDER))
    return dict(panels=panels, caption_top=int(oh * 0.70), hook_top=int(oh * 0.18), text_span=span)


_BUILDERS = {"trio": _trio, "grid4": _grid4, "ots": _ots}


def _full(c: _Ctx) -> dict | None:
    """One crop fills the frame. With a person in the source the crop holds them whole, or this is not drawn."""
    ow, oh = c.size
    rect = crop_rect(c.sw, c.sh, FULL_FRAME, ow, oh, c.zoom)
    punch = True
    if c.scene == "gameplay_cam":
        # The camera stays where the streamer put it. Only a small step: a big one would lose the middle of the game.
        rect, punch = hold(rect, person_box(c.cam, c.face, c.sw, c.sh), c.sw, c.sh, MAX_DODGE), False
    elif c.scene == "camera" and c.face:
        head = head_box(c.face, c.sw, c.sh)
        if head[2] > rect[2] or head[3] > rect[3]:
            return None
        x, y, w, h = rect       # the person is the subject: centre the crop on them
        rect, punch = (_clamp(c.face[0] * c.sw - w / 2, 0.0, c.sw - w), _clamp(c.face[1] * c.sh - h / 2, 0.0, c.sh - h), w, h), False
    if rect is None:
        return None
    return dict(panels=(Panel("gameplay" if c.scene != "camera" else "camera", rect, (0, 0, ow, oh), punch=punch),),
                caption_top=int(oh * 0.70), hook_top=int(oh * 0.18))


def _fit(c: _Ctx) -> dict:
    """The whole source, letterboxed. The bars are a blurred piece of the gameplay with no person in it, or black."""
    ow, oh = c.size
    k = min(ow / c.sw, oh / c.sh)
    mw, mh = min(ow, even(round(c.sw * k))), min(oh, even(round(c.sh * k)))
    if ow - mw <= 8 and oh - mh <= 8:
        mw, mh = ow, oh
    x, y = even((ow - mw) / 2), even((oh - mh) / 2)
    background = None
    if (mw, mh) != (ow, oh):
        if c.scene == "gameplay":
            background = crop_rect(c.sw, c.sh, FULL_FRAME, ow, oh)
        elif c.scene == "gameplay_cam":
            _how, background = avoid_camera(c.sw, c.sh, ow, oh, 1.0, c.cam, c.face, MAX_AVOID_ZOOM)
    caption_top, hook_top = int(oh * 0.70), int(oh * 0.18)
    if oh - (y + mh) >= 200:       # room under and over the picture: the text goes on the bars
        caption_top, hook_top = y + mh + 30, max(40, y - 150)
    return dict(panels=(Panel("source", (0.0, 0.0, float(c.sw), float(c.sh)), (x, y, mw, mh)),), background=background,
                caption_top=caption_top, hook_top=hook_top)


def _head_on_canvas(c: _Ctx, panels) -> tuple[float, float, float, float] | None:
    """Where the head lands on the canvas (x0, y0, x1, y1), when a face is known and a panel shows it."""
    if not c.face:
        return None
    head = head_box(c.face, c.sw, c.sh)
    for p in reversed(panels):
        if _inside(head, p.src, tol=2.0):
            kx, ky = p.out[2] / p.src[2], p.out[3] / p.src[3]
            x0, y0 = p.out[0] + (head[0] - p.src[0]) * kx, p.out[1] + (head[1] - p.src[1]) * ky
            return x0, y0, x0 + head[2] * kx, y0 + head[3] * ky
    return None


def _person_on_canvas(c: _Ctx, panels) -> tuple[float, float, float, float] | None:
    """Where a caption must not go (x0, y0, x1, y1 on the canvas): the head, when a face is known. When only the
    camera box is known, the head is taken to be anywhere in the camera picture except its lowest part (the
    shoulders and chest), so a caption never sits where a face might be."""
    head = _head_on_canvas(c, panels)
    if head is not None or not c.cam or c.scene != "gameplay_cam":
        return head
    box = cam_px(c.cam, c.sw, c.sh)
    for p in reversed(panels):
        if p.kind == "camera":
            x, y, w, h = p.out
            return float(x), float(y), float(x + w), y + BLIND_HEAD * h
        if _inside(box, p.src, tol=4.0):                # the camera is part of this picture, where the streamer put it
            kx, ky = p.out[2] / p.src[2], p.out[3] / p.src[3]
            x0, y0 = p.out[0] + (box[0] - p.src[0]) * kx, p.out[1] + (box[1] - p.src[1]) * ky
            return x0, y0, x0 + box[2] * kx, y0 + BLIND_HEAD * box[3] * ky
    return None


def caption_y(oh: int, position: str, half: float, seam: int | None = None, head=None,
              reach: tuple[float, float] | None = None) -> int:
    """The row (pixels from the top of a frame `oh` tall) of the middle of a one-line caption that is `half`
    pixels tall above and below it.

    "seam": on the line between two stacked panels (`seam`), or the lower third when there is no such line;
    "lower": the lower third; "center": the middle of the frame; "auto": the seam when there is one, else the
    lower third. Wherever that is, the caption never covers `head` (x0, y0, x1, y1): it moves the least distance
    that clears it, up or down. `reach` is the part of the width (x0, x1, in pixels) the widest caption covers.
    """
    if position not in CAPTION_POSITIONS:
        raise PipelineError("bad_options", f"Unknown caption_position. Use one of: {', '.join(CAPTION_POSITIONS)}.")
    want = oh * (0.5 if position == "center" else LOWER_THIRD)
    if position in ("auto", "seam") and seam is not None:
        want = seam
    lo, hi = SAFE_ROWS[0] * oh + half, SAFE_ROWS[1] * oh - half
    y = _clamp(want, lo, hi)
    if head is not None and (reach is None or (head[0] < reach[1] - 1 and head[2] > reach[0] + 1)):
        gap = FACE_GAP * oh / 1920
        top, bottom = head[1] - gap, head[3] + gap
        if y + half > top and y - half < bottom:
            ways = [v for v in (top - half, bottom + half) if lo <= v <= hi]
            # No room above or below the head inside the safe rows: as far from the middle of it as the frame allows.
            y = min(ways, key=lambda v: abs(v - y)) if ways else max((lo, hi), key=lambda v: abs(v - (top + bottom) / 2))
    return int(round(y))


def caption_center(plan: LayoutPlan, position: str, half: float, fill: float = 1.0) -> int:
    """caption_y for a layout plan, in the plan's canvas pixels. `fill` is the share of the text span the widest
    caption covers."""
    ow, oh = plan.size
    mid, width = (plan.text_span[0] + plan.text_span[1]) / 2 * ow, (plan.text_span[1] - plan.text_span[0]) * ow * fill
    return caption_y(oh, position, half, plan.seam, plan.head, (mid - width / 2, mid + width / 2))


def _text_off_the_face(c: _Ctx, parts: dict) -> dict:
    """Move captions and the hook off the person's head when the one picture has them where the text would go."""
    head = _head_on_canvas(c, parts["panels"])
    if head is None:
        return parts
    ow, oh = c.size
    x0, y0, x1, y1 = head
    if x1 < 0.12 * ow or x0 > 0.88 * ow:
        return parts                                   # the text is centred and never reaches this far out
    cap, hook = parts["caption_top"], parts["hook_top"]
    if y0 < cap + 110 and y1 > cap - 20:               # the caption line
        cap = int(y0 - 130) if y0 - 130 >= 0.3 * oh else int(y1 + 40) if y1 + 40 <= oh - 200 else cap
    if y0 < hook + 130 and y1 > hook:
        hook = int(y1 + 30) if y1 + 30 <= 0.5 * oh else int(y0 - 150) if y0 - 150 >= 20 else hook
    return {**parts, "caption_top": cap, "hook_top": hook}


_NOTES = {
    "no_camera": "No webcam overlay was found in this video, so the gameplay fills the frame.",
    "camera_only": "The camera fills this video, so there is no separate gameplay to place.",
    "in_the_way": "The camera could not be shown cleanly in the layout that was asked for, so this one is used "
                  "instead: people are never blurred or cut.",
}


def split_problem(camera, split_ratio) -> str | None:
    """Why `camera` / `split_ratio` cannot be used, or None. Both may be None: the layout's own."""
    if camera is not None and camera not in CAMERA_SIDES:
        return f"Unknown camera. Use one of: {', '.join(CAMERA_SIDES)}."
    if split_ratio is not None and not (isinstance(split_ratio, (int, float)) and not isinstance(split_ratio, bool)
                                        and SPLIT_RATIO[0] <= split_ratio <= SPLIT_RATIO[1]):
        return f"split_ratio must be between {SPLIT_RATIO[0]} and {SPLIT_RATIO[1]}: the top panel's share of the height."
    return None


def compose(src_w: int, src_h: int, layout: str, aspect: str, *, scene: str | None = None, cam=None, face=None,
            zoom: float = 1.0, requested: str | None = None, camera: str | None = None,
            split_ratio: float | None = None) -> LayoutPlan:
    """The boxes for `layout` (a canonical name or "auto") on a source whose scene type is already known.
    `cam` is the webcam overlay [x, y, w, h] and `face` the person's face (centre x, centre y, w, h), both as
    fractions of the source. Raises PipelineError("layout_unavailable") for the layouts that are not built.

    `camera` ("top" | "bottom") and `split_ratio` (0.25 to 0.75, the top panel's share of the height) adjust the
    two-panel layouts (TWO_PANEL); None keeps the layout's own. In a wide frame the panels sit side by side:
    "top" is the left panel and the ratio is its share of the width. Every other layout ignores both."""
    if aspect not in ASPECTS:
        raise PipelineError("bad_options", f"Unknown aspect. Use one of: {', '.join(ASPECTS)}.")
    problem = split_problem(camera, split_ratio)
    if problem:
        raise PipelineError("bad_options", problem)
    if layout in NOT_BUILT:
        raise PipelineError(*layout_problem(layout, "16:9"))
    layout = canonical(layout, aspect)
    if layout != "auto" and layout not in BUILT:
        raise PipelineError("bad_options", f"Unknown layout. Use one of: {', '.join(LAYOUTS)}.")
    scene = scene or ("gameplay_cam" if cam else "gameplay")
    if scene == "gameplay_cam" and not cam:
        scene = "gameplay"
    c = _Ctx(src_w, src_h, aspect, ASPECTS[aspect], scene, tuple(cam) if cam else None, tuple(face) if face else None, zoom,
             camera, split_ratio)
    first = layout
    if layout == "auto":       # per scene: a stream with a camera gets both in view; anything else fills the frame
        first = "split2" if scene == "gameplay_cam" and aspect != "16:9" else "full"
    # What to draw, most wanted first. Each later one shows more of the source as it is, and fit always works.
    order = {"full": ["full", "pip", "fit"], "fit": ["fit"], "pip": ["pip", "full", "fit"]}.get(first, [first, "full", "pip", "fit"])
    for name in order:
        if name == "pip" and name != first and "pip" not in ALLOWED[aspect]:
            continue           # a fallback is only ever a layout this shape offers
        parts = (_fit(c) if name == "fit" else _full(c) if name == "full" else _pip(c) if name == "pip"
                 else _BUILDERS[name](c) if name in _BUILDERS else _two(c, name))
        if parts is None:
            continue
        if name in ("full", "fit"):
            parts = _text_off_the_face(c, parts)
        note = None
        if name != first:
            note = _NOTES["no_camera" if scene == "gameplay" else "camera_only" if scene == "camera" else "in_the_way"]
        return LayoutPlan(requested=requested or layout, layout=name, scene=scene, aspect=aspect, size=c.size,
                          cam=c.cam, face=c.face, note=note, head=_person_on_canvas(c, parts["panels"]),
                          source=(src_w, src_h), **parts)
    raise PipelineError("layout_unavailable", "This video could not be reframed.")     # unreachable: fit always draws


def plan_layout(info, frames, requested: str, aspect: str, *, zoom: float = 1.0, cam=None,
                camera: str | None = None, split_ratio: float | None = None) -> LayoutPlan:
    """Decide the scene type of a source and the boxes for the layout that was asked for.

    `info` is the source's MediaInfo, `frames` gray frames sampled across it (facecam.sample_gray), `requested`
    a name from LAYOUTS (or an old one) and `aspect` the output shape. `cam` is a camera box the caller already
    knows ([x, y, w, h] fractions): detection is skipped. Raises PipelineError("bad_options") for a layout the
    shape does not offer and PipelineError("layout_unavailable") for trio, grid4 and ots. `camera` and
    `split_ratio` are the two-panel controls (see compose).
    """
    name = check_layout(requested, aspect)
    if name == "classic":
        raise PipelineError("bad_options", "The classic layout has no plan: render it with layout='classic'.")
    if cam:
        return compose(info.width, info.height, name, aspect, scene="gameplay_cam", cam=cam, zoom=zoom, requested=requested,
                       camera=camera, split_ratio=split_ratio)
    from .facecam import classify       # facecam imports render, which imports this module
    scene = classify(frames or [])
    return compose(info.width, info.height, name, aspect, scene=scene.kind, cam=scene.cam, face=scene.face, zoom=zoom,
                   requested=requested, camera=camera, split_ratio=split_ratio)


# ---------- boxes for the stages that draw on top (docs/CONTRACTS.md, "Reframe boxes v1") ----------
# Where each game's HUD sits in a 16:9 source, as fractions [x, y, w, h], measured on the owner's eval footage
# (docs/REFRAME_EVAL.md). Only HUD a caption must not cover: the kill feed, the minimap, the speedometer.
# Empty until the first measured entries land: an unmeasured game has no HUD rather than a guessed one.
HUD_REGIONS: dict[str, tuple[tuple[str, Rect], ...]] = {}
HUD_GAMES = {"gta6": "gta5", "gta-online": "gta5"}      # games that share another game's HUD


def hud_regions(game: str | None) -> tuple[tuple[str, Rect], ...]:
    """(kind, [x, y, w, h] fractions) for each HUD element of `game` (a templates.GAMES id). None, "other" or a
    game with no measured HUD: none. Never guessed."""
    return HUD_REGIONS.get(HUD_GAMES.get(game or "", game or ""), ())


def _xyxy(r) -> list[int]:
    return [int(round(r[0])), int(round(r[1])), int(round(r[0] + r[2])), int(round(r[1] + r[3]))]


def _on_canvas(box: Rect, src: Rect, out) -> Rect | None:
    """Where the part of `box` (source pixels) that the crop `src` shows lands in `out` (canvas pixels), or None."""
    x0, y0 = max(box[0], src[0]), max(box[1], src[1])
    x1, y1 = min(box[0] + box[2], src[0] + src[2]), min(box[1] + box[3], src[1] + src[3])
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    kx, ky = out[2] / src[2], out[3] / src[3]
    return out[0] + (x0 - src[0]) * kx, out[1] + (y0 - src[1]) * ky, (x1 - x0) * kx, (y1 - y0) * ky


def _shown(box: Rect, panels) -> Rect | None:
    """The canvas box covering every place `box` (source pixels) is shown by a panel, over the whole clip (every
    point of a moving crop), or None when no panel shows any of it. A camera panel's own picture is left out."""
    hits = []
    for p in panels:
        if p.kind == "camera":
            continue
        for src in ([r for _t, r in p.path] if p.path else [p.src]):
            hit = _on_canvas(box, src, p.out)
            if hit:
                hits.append(hit)
    if not hits:
        return None
    acc = hits[0]
    for h in hits[1:]:
        acc = _union(acc, h)
    return acc


def reframe_boxes(plan: LayoutPlan | None, *, src: tuple[int, int] | None = None, cam=None, face=None,
                  game: str | None = None, confidence: float | None = None) -> dict:
    """Where everything a caption must respect is on the output, for one clip (docs/CONTRACTS.md, "Reframe boxes v1").

    `plan` is what is drawn; without one (the original 16:9 picture, not reframed) `src` is the source size and
    `cam` / `face` the camera box and face as in LayoutPlan. `game` (a templates.GAMES id) adds its HUD.
    `confidence` is the camera detection's (None: given by the user, or not measured).
    Source boxes are [x, y, w, h] fractions; canvas boxes are [x0, y0, x1, y1] pixels of `canvas`."""
    if plan is None:
        if src is None:
            raise ValueError("reframe_boxes needs a plan or the source size")
        sw, sh = src
        whole = (0.0, 0.0, float(sw), float(sh))
        plan = LayoutPlan(requested="original", layout="original", scene="gameplay_cam" if cam else "gameplay",
                          aspect="", size=(sw, sh), panels=(Panel("source", whole, (0, 0, sw, sh)),),
                          cam=tuple(cam) if cam else None, face=tuple(face) if face else None,
                          head=tuple(_xyxy(head_box(face, sw, sh))) if face else None, source=(sw, sh))
    sw, sh = plan.source or src or (0, 0)
    if not sw or not sh:
        raise ValueError("reframe_boxes needs the source size: a plan from compose, or `src`")
    ow, oh = plan.size
    panels = [{"role": "camera" if p.kind == "camera" else "gameplay", "out": _xyxy(p.out)} for p in plan.panels]
    keep_out: list[list[int]] = []
    head = [int(round(v)) for v in plan.head] if plan.head else None
    if head:
        keep_out.append(head)
    facecam = None
    if plan.cam:
        cam_out = None
        for p in plan.panels:
            if p.kind == "camera":
                cam_out = _xyxy(p.out)
                if p.border:               # an inset over the gameplay: no text on any of it
                    keep_out.append(cam_out)
        if cam_out is None:                # the camera is part of a gameplay picture, where the streamer put it
            shown = _shown(cam_px(plan.cam, sw, sh), plan.panels)
            if shown:
                cam_out = _xyxy(shown)
                keep_out.append(cam_out)
        facecam = {"src": [round(v, 4) for v in plan.cam], "out": cam_out,
                   "confidence": None if confidence is None else round(float(confidence), 3)}
    hud = []
    for kind, box in hud_regions(game):
        shown = _shown(cam_px(box, sw, sh), plan.panels)
        out = _xyxy(shown) if shown else None
        hud.append({"kind": kind, "src": list(box), "out": out})
        if out:
            keep_out.append(out)
    path = None
    for p in plan.panels:
        if p.kind == "gameplay" and p.path:
            path = [{"t": round(t, 3), "box": [round(r[0] / sw, 4), round(r[1] / sh, 4), round(r[2] / sw, 4),
                                                round(r[3] / sh, 4)]} for t, r in p.path]
            break
    return {"v": 1, "canvas": [ow, oh], "layout": plan.layout, "scene": plan.scene, "seam": plan.seam,
            "panels": panels, "text_span": list(plan.text_span), "facecam": facecam, "head": head, "hud": hud,
            "keep_out": keep_out, "crop_path": path}


# ---------- drawing ----------
def _scaled(out, sx: float, sy: float) -> tuple[int, int, int, int]:
    x0, y0 = even(out[0] * sx), even(out[1] * sy)
    return x0, y0, even((out[0] + out[2]) * sx) - x0, even((out[1] + out[3]) * sy) - y0


def layout_graph(plan: LayoutPlan, size: tuple[int, int] | None = None, punch: str = "1") -> str:
    """The filter graph that draws `plan` at `size` (default: the plan's own canvas). Reads [0:v], writes [v].
    `punch` is a zoom expression over time; it only ever plays on panels with no person in them."""
    ow, oh = plan.size
    tw, th = size or plan.size
    sx, sy = tw / ow, th / oh
    chains, outs = [], []
    for p in plan.panels:
        x, y, w, h = _scaled(p.out, sx, sy)
        chain = ((_moving_crop_scale(p.path, w, h) if p.path else _crop_scale(p.src, w, h))
                 + (punch_in(w, h, punch) if p.punch else ""))
        if p.border:
            chain += f",drawbox=x=0:y=0:w=iw:h=ih:color=white:t={max(2, even(p.border * sx))}"
        chains.append(chain)
        outs.append((x, y, w, h))
    covers = [o == (0, 0, tw, th) for o in outs]
    if len(chains) == 1 and covers[0]:                                        # one picture fills the frame
        return f"[0:v]{chains[0]},format=yuv420p[v]"
    if len(chains) == 1:                                                      # fit: the picture over its bars
        x, y, w, h = outs[0]
        if plan.background is None:
            return f"[0:v]{chains[0]},pad={tw}:{th}:{x}:{y}:color=black,format=yuv420p[v]"
        # Blurred at a quarter of the size: the same look for a fraction of the work.
        return (f"[0:v]split=2[a][b];"
                f"[a]{_crop_scale(plan.background, even(tw / 4), even(th / 4))},boxblur=8:2,scale={tw}:{th},"
                f"eq=brightness=-0.12,setsar=1[bg];"
                f"[b]{chains[0]}[main];"
                f"[bg][main]overlay={x}:{y},format=yuv420p[v]")
    if len(chains) == 2 and covers[0]:                                        # pip: the inset over the gameplay
        x, y, _w, _h = outs[1]
        return (f"[0:v]split=2[a][b];[a]{chains[0]}[base];[b]{chains[1]}[in];"
                f"[base][in]overlay={x}:{y},format=yuv420p[v]")
    if len(chains) == 2:                                                      # two panels, stacked or side by side
        stacked = outs[0][2] == tw
        first, second, stack = ("top", "bot", "vstack") if stacked else ("left", "right", "hstack")
        return (f"[0:v]split=2[a][b];"
                f"[a]{chains[0]}[{first}];"
                f"[b]{chains[1]}[{second}];"
                f"[{first}][{second}]{stack}=inputs=2,format=yuv420p[v]")
    if sum(w * h for _x, _y, w, h in outs) == tw * th:                         # trio, grid4: panels that tile the frame
        n = len(chains)
        return (f"[0:v]split={n}" + "".join(f"[i{k}]" for k in range(n)) + ";"
                + "".join(f"[i{k}]{chain}[p{k}];" for k, chain in enumerate(chains))
                + "".join(f"[p{k}]" for k in range(n))
                + f"xstack=inputs={n}:layout=" + "|".join(f"{x}_{y}" for x, y, _w, _h in outs) + ",format=yuv420p[v]")
    raise PipelineError("layout_unavailable", "This layout cannot be drawn.")
