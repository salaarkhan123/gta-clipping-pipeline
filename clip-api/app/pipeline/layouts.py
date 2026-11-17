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
# These need several people tracked on screen. They are not built and are never faked.
NOT_BUILT = ("trio", "grid4", "ots")
BUILT = tuple(name for name in LAYOUTS if name not in NOT_BUILT)
# The layout names from before the reframe layouts. They keep working, in every shape, with their old meaning:
# split = split2 (plain fill in 16:9), fill = full, classic = the blurred 9:16 layout with a chat panel (render.py).
LEGACY = ("split", "fill", "classic")
NEEDS_CAMERA = ("split", "split2", "pip", "screen_first", "gameplay_a", "gameplay_b")
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


def avoid_camera(src_w: int, src_h: int, tw: int, th: int, zoom: float, cam, face=None,
                 max_zoom: float = 1.0) -> tuple[str, Rect | None]:
    """The gameplay crop (target shape tw:th) with the webcam overlay kept out of it completely.

    Returns (how, rect): "clear" (the centred crop misses the camera), "shifted" (the crop moves the least
    distance that clears it), "zoomed" (it also had to zoom in, by at most `max_zoom`, to find room beside the
    camera) or ("blocked", None): the camera is in the way and cannot be stepped around. A blocked crop is never
    patched over: the caller draws a layout that shows the camera where it is instead.
    """
    pad_x, pad_y = FACECAM_PAD * src_w, FACECAM_PAD * src_h
    box = (cam[0] * src_w - pad_x, cam[1] * src_h - pad_y, cam[2] * src_w + 2 * pad_x, cam[3] * src_h + 2 * pad_y)
    if face:
        box = _union(box, head_box(face, src_w, src_h))
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
    if head is not None and (reach is None or (head[0] < reach[1] and head[2] > reach[0])):
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
        parts = _fit(c) if name == "fit" else _full(c) if name == "full" else _pip(c) if name == "pip" else _two(c, name)
        if parts is None:
            continue
        if name in ("full", "fit"):
            parts = _text_off_the_face(c, parts)
        note = None
        if name != first:
            note = _NOTES["no_camera" if scene == "gameplay" else "camera_only" if scene == "camera" else "in_the_way"]
        return LayoutPlan(requested=requested or layout, layout=name, scene=scene, aspect=aspect, size=c.size,
                          cam=c.cam, face=c.face, note=note, head=_person_on_canvas(c, parts["panels"]), **parts)
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
        chain = _crop_scale(p.src, w, h) + (punch_in(w, h, punch) if p.punch else "")
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
    raise PipelineError("layout_unavailable", "This layout cannot be drawn.")
