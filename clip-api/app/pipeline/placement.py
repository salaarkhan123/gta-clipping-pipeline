"""Where a clip's captions and hook sit: on the row the caption position asks for, moved the least distance that
keeps them off everything in the clip's keep-out boxes (the streamer's head, a webcam in the picture, the game's
HUD) and inside the frame's safe rows. The boxes come from layouts.reframe_boxes ("Reframe boxes v1" in
docs/CONTRACTS.md); this module only reads them. No file, network or database code.
"""
from .ff import PipelineError

CAPTION_POSITIONS = ("auto", "seam", "lower", "center")
LOWER_THIRD = 0.70               # where a caption sits when there is no line between panels to sit on
# A caption stays between these shares of the height: clear of the apps' own buttons and a player's controls.
SAFE_ROWS = (0.05, 0.92)
FACE_GAP = 14                    # pixels kept between text and a keep-out box, on a 1920-high canvas
HOOK_ROOM = 200                  # pixels a hook may take from its top on the 1080 canvas: two lines and the box
HOOK_PAD = 14                    # the hook's box reaches this far above its top (its border), 1080 canvas
TEXT_GAP = 16                    # pixels kept between the hook and a caption
STEP_GAP = 24                    # pixels a hook moved off a caption keeps from it
HOOK_LOW = 0.94                  # the lowest a hook's box may reach, as a share of the height


def _blocked(keep_out, reach: tuple[float, float] | None) -> list[tuple[float, float]]:
    """(y0, y1) of every keep-out box that reaches into the columns `reach` (x0, x1) covers."""
    return [(b[1], b[3]) for b in keep_out if reach is None or (b[0] < reach[1] - 1 and b[2] > reach[0] + 1)]


def _nearest(want: float, lo: float, hi: float, bands: list[tuple[float, float]]) -> float:
    """The value in [lo, hi] nearest `want` that is in none of `bands` (open intervals). With none free, the
    edge of the frame farthest from the middle of the bands."""
    def free(v):
        return lo <= v <= hi and not any(a < v < b for a, b in bands)
    if free(want):
        return want
    ways = [v for a, b in bands for v in (a, b) if free(v)]
    if ways:
        return min(ways, key=lambda v: abs(v - want))
    middle = sum(a + b for a, b in bands) / (2 * len(bands)) if bands else want
    return max((lo, hi), key=lambda v: abs(v - middle))


def caption_row(oh: int, position: str, half: float, *, seam: int | None = None, keep_out=(),
                reach: tuple[float, float] | None = None, want: float | None = None) -> int:
    """The row (pixels from the top of a frame `oh` tall) of the middle of a one-line caption `half` pixels tall
    above and below it.

    "seam": on the line between two stacked panels (`seam`), or the lower third when there is no such line;
    "lower": the lower third; "center": the middle of the frame; "auto": the seam when there is one, else the
    lower third. From there it moves the least distance that keeps it FACE_GAP clear of every `keep_out` box
    (x0, y0, x1, y1) in the columns `reach` (x0, x1) the widest caption covers, inside the safe rows."""
    if position not in CAPTION_POSITIONS:
        raise PipelineError("bad_options", f"Unknown caption_position. Use one of: {', '.join(CAPTION_POSITIONS)}.")
    chosen = want
    want = oh * (0.5 if position == "center" else LOWER_THIRD)
    if position in ("auto", "seam") and seam is not None:
        want = seam
    if chosen is not None:                     # a row the user chose (caption_look.y): still never on a box
        want = chosen
    lo, hi = SAFE_ROWS[0] * oh, SAFE_ROWS[1] * oh
    gap = FACE_GAP * oh / 1920
    bands = [(y0 - gap - half, y1 + gap + half) for y0, y1 in _blocked(keep_out, reach)]
    lo, hi = lo + half, hi - half
    return int(round(_nearest(min(max(want, lo), hi), lo, hi, bands)))


def hook_row(oh: int, want: int, caption: tuple[float, float] | None, *, keep_out=(),
             reach: tuple[float, float] | None = None, k: float = 1.0) -> int:
    """The hook's top: `want`, or the nearest top at which its box (HOOK_PAD above the top to HOOK_ROOM below,
    scaled by `k`) is clear of the caption band `caption` (y0, y1) and of every keep-out box in its columns."""
    room, pad, gap = HOOK_ROOM * k, HOOK_PAD * k, FACE_GAP * oh / 1920
    lo, hi = 20 * k, HOOK_LOW * oh - room
    bands, ways = [], []
    for y0, y1 in _blocked(keep_out, reach):
        bands.append((y0 - gap - room, y1 + gap + pad))
        ways += [y1 + gap + pad, y0 - gap - room]
    if caption:
        top, bottom = caption[0] - TEXT_GAP * k, caption[1] + TEXT_GAP * k
        bands.append((top - room, bottom + pad))
        ways += [bottom + STEP_GAP * k, top - STEP_GAP * k - room]      # moved off it, a little more room
    def free(v):
        return lo <= v <= hi and not any(a < v < b for a, b in bands)
    if free(want):
        return int(want)
    found = [v for v in ways if free(v)]
    return int(min(found, key=lambda v: abs(v - want))) if found else int(want)


def place(boxes: dict, position: str, half: float, fill: float, hook_want: int, k: float = 1.0,
          below_video: int | None = None, want: float | None = None) -> tuple[int, int]:
    """(the row of the middle of an impact caption, the hook's top) on the canvas of `boxes` (a reframe_boxes
    dict). `fill` is the share of the text span the widest caption covers; `hook_want` is where the hook would
    sit. `below_video` (the classic layout) is the row the caption goes to when it has no seam or lower third."""
    ow, oh = boxes["canvas"]
    span = boxes.get("text_span") or (0.0, 1.0)
    mid, width = (span[0] + span[1]) / 2 * ow, (span[1] - span[0]) * ow
    keep = [tuple(b) for b in boxes.get("keep_out") or ()]
    seam = boxes.get("seam") if below_video is None else int(below_video + half)
    center = caption_row(oh, position, half, seam=seam, keep_out=keep, reach=(mid - width * fill / 2, mid + width * fill / 2),
                         want=want)
    hook = hook_row(oh, hook_want, (center - half, center + half), keep_out=keep,
                    reach=(span[0] * ow + 90 * k, span[1] * ow - 90 * k), k=k)
    return center, hook
