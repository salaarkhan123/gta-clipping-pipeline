"""Action-aware crop: where the subject of each moment of a clip is, and a calm crop path that follows it.

    track(src, start, end, ...) -> Track                    subject positions sampled over a clip, and its hard cuts
    follow(samples, crop_w, src_w, length, cuts) -> path    the crop's left edge over time, or None (hold still)
    crop_path(plan, track, length) -> LayoutPlan            the plan with its gameplay panel moving along the path

The subject of a gaming frame is, in order: a face that stays put for a moment (dialogue, cutscenes, RP), then
what moves differently from the camera (a car or a character the game camera is not centred on), then the middle
(where FPS crosshairs and third-person cameras put the action). The path is what a camera operator would do: hold
still while the subject stays near the middle of the crop, pan just enough when it leaves (never faster than
MAX_PAN), and cut at once at a hard cut instead of sweeping across it.
"""
import logging
import time
from dataclasses import dataclass, replace

import numpy as np

from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout, run_bytes

log = logging.getLogger("clipapi.action")

STEP = 0.5            # seconds between the path's points
DEAD_ZONE = 0.20      # the subject may sit this share of the crop's width either side of its centre before it pans
MAX_PAN = 0.30        # the crop pans at most this share of the source width per second
MIN_MOVE = 0.02       # a path that never moves more than this share of the source width is drawn still
FPS = 4.0             # subject samples per second of clip
SIZE = (320, 180)     # the size the samples are analysed at
CUT_LEVEL = 40.0      # mean change (0-255) between two samples a quarter second apart that is a hard cut
MIN_RESIDUAL = 1.0    # mean change (0-255) left after taking out the camera's pan, below which nothing moves on its own
CENTRE_PULL = 0.35   # with no clear subject, the target drifts back to the middle (FPS crosshair, chase cameras)
GAMES_CENTRED = ("valorant", "cs2", "ow2", "apex", "fortnite")   # crosshair games: the action is the middle


@dataclass(frozen=True)
class Track:
    times: tuple[float, ...]      # seconds from the clip start
    xs: tuple[float, ...]         # the subject's centre x at each time, as a fraction of the source width
    kinds: tuple[str, ...]        # "face" | "motion" | "centre": what each position came from
    cuts: tuple[float, ...]       # hard cuts, seconds from the clip start
    seconds: float = 0.0          # how long the analysis took


def sample(src, start: float, end: float, deadline: Deadline | None = None) -> np.ndarray:
    """Gray frames of [start, end] at FPS per second, SIZE: one decode of the clip's span, nothing written."""
    w, h = SIZE
    raw = run_bytes(["ffmpeg", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", *SAFE_IN,
                     "-i", str(src), "-an", "-vf", f"fps={FPS:g},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                    deadline, cap=max(60, int(4 * (end - start))))
    n = len(raw) // (w * h)
    return np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w)


def _faces(g: np.ndarray) -> list[tuple[float, float, float]]:
    """(centre x, centre y, width) fractions of the faces in one small frame, by the strict detector at 2x."""
    import cv2
    from .facecam import _detector
    big = cv2.resize(g, (g.shape[1] * 2, g.shape[0] * 2))
    H, W = big.shape
    return [((x + w / 2) / W, (y + h / 2) / H, w / W)
            for (x, y, w, h) in _detector().detectMultiScale(big, scaleFactor=1.1, minNeighbors=5, minSize=(28, 28))]


def _keep_mask(frames: np.ndarray, exclude) -> np.ndarray:
    """Pixels that can hold the subject: not a HUD that never changes over the clip, not a black bar, and not
    inside the `exclude` boxes ([x, y, w, h] fractions: the webcam)."""
    std = frames.std(axis=0)
    keep = (std > 4.0) & (frames.max(axis=0) > 20)
    h, w = keep.shape
    for box in exclude:
        x, y, bw, bh = box
        keep[int(y * h):int((y + bh) * h) + 1, int(x * w):int((x + bw) * w) + 1] = False
    return keep


def _motion_x(prev: np.ndarray, cur: np.ndarray, keep: np.ndarray) -> float | None:
    """Where in x what moves differently from the camera is, as a fraction of the width, or None. The camera's own
    pan is taken out first (phase correlation), so a whole picture sliding past is not a subject."""
    import cv2
    a, b = prev.astype(np.float32), cur.astype(np.float32)
    (dx, dy), _resp = cv2.phaseCorrelate(a, b)
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    moved = cv2.warpAffine(a, m, (a.shape[1], a.shape[0]), borderMode=cv2.BORDER_REPLICATE)
    resid = cv2.GaussianBlur(np.abs(b - moved), (9, 9), 0) * keep
    pad = int(abs(dx)) + 4                                     # the edges the shift uncovered are not motion
    resid[:, :pad] = 0
    resid[:, -pad:] = 0
    total = float(resid.sum())
    if total < MIN_RESIDUAL * keep.sum():                      # too little moves on its own: no subject
        return None
    col = resid.sum(axis=0)
    hot = col > 0.5 * col.max()
    xs = np.flatnonzero(hot)
    if len(xs) == 0 or (xs[-1] - xs[0]) > 0.6 * len(col):     # motion everywhere is the camera, not a subject
        return None
    c = np.cumsum(col * hot)
    return float(np.searchsorted(c, c[-1] / 2)) / len(col)


def track(src, start: float, end: float, *, exclude=(), game: str | None = None,
          deadline: Deadline | None = None) -> Track:
    """Where the subject is over [start, end] (seconds of the source). `exclude` are boxes to leave out (the
    webcam). In crosshair games (GAMES_CENTRED) the subject is the middle, so nothing is decoded."""
    t0 = time.time()
    length = end - start
    if game in GAMES_CENTRED or length <= 0:
        n = max(2, int(length / STEP) + 1)
        return Track(tuple(i * STEP for i in range(n)), (0.5,) * n, ("centre",) * n, (), 0.0)
    frames = sample(src, start, end, deadline)
    if len(frames) < 2:
        return Track((0.0,), (0.5,), ("centre",), (), time.time() - t0)
    keep = _keep_mask(frames, exclude)
    times, xs, kinds, cuts = [], [], [], []
    for i, g in enumerate(frames):
        t = i / FPS
        if i and float(np.abs(g.astype(np.float32) - frames[i - 1]).mean()) > CUT_LEVEL:
            cuts.append(t)
        faces = [f for f in _faces(g) if 0.03 <= f[2] <= 0.4] if i % 2 == 0 else []
        if faces:
            x, kind = max(faces, key=lambda f: f[2])[0], "face"     # the nearest face speaks most often
        else:
            mx = _motion_x(frames[i - 1], g, keep) if i and (not cuts or cuts[-1] != t) else None
            x, kind = (mx, "motion") if mx is not None else (None, "centre")
        if x is None:
            prev = xs[-1] if xs else 0.5
            x = prev + CENTRE_PULL * (0.5 - prev)                # drift back to the middle over a second or two
        times.append(t)
        xs.append(float(x))
        kinds.append(kind)
    return Track(tuple(times), tuple(xs), tuple(kinds), tuple(cuts), time.time() - t0)


def _grid(samples: list[tuple[float, float]], length: float) -> tuple[np.ndarray, np.ndarray]:
    """The subject's x on a STEP grid over [0, length]: the median of five around each sample (one bad frame
    never moves the crop), held flat before the first sample and after the last."""
    ts = np.array([t for t, _ in samples], dtype=float)
    xs = np.array([x for _, x in samples], dtype=float)
    if len(xs) >= 3:
        xs = np.array([np.median(xs[max(0, i - 2):i + 3]) for i in range(len(xs))])
    grid = np.arange(0.0, length + 1e-9, STEP)
    return grid, np.interp(grid, ts, xs)


def follow(samples: list[tuple[float, float]], crop_w: float, src_w: float, length: float,
           cuts=()) -> list[tuple[float, float]] | None:
    """The crop's left edge (source pixels) over the clip as (seconds, x) points, from `samples` of the subject's
    centre x (seconds from the clip start, source pixels). `cuts` are hard cuts (seconds): the crop may jump there.
    One point when the crop would barely move (draw it still, there). None when there is nothing to follow."""
    if not samples or crop_w >= src_w:
        return None
    grid, target = _grid(sorted(samples), length)
    half, zone = crop_w / 2, DEAD_ZONE * crop_w
    lo, hi = half, src_w - half
    step_max = MAX_PAN * src_w * STEP
    cut_at = {int(round(c / STEP)) for c in cuts if 0 < c < length}
    centre = np.empty_like(target)
    c = float(np.clip(target[0], lo, hi))
    for i, s in enumerate(target):
        if i in cut_at:                                     # a new shot: frame it at once
            c = float(np.clip(s, lo, hi))
        elif abs(s - c) > zone:                             # out of the dead zone: move just enough, never too fast
            want = s - zone if s > c else s + zone
            c += float(np.clip(want - c, -step_max, step_max))
        c = float(np.clip(c, lo, hi))
        centre[i] = c
    if centre.max() - centre.min() < MIN_MOVE * src_w:      # barely moves: one still crop, on the subject
        return [(0.0, float(np.clip(np.median(target), lo, hi) - half))]
    points = [(float(grid[0]), float(centre[0] - half))]
    for i in range(1, len(grid)):                            # keep only the points where the motion changes
        if i in cut_at:
            points.append((float(grid[i]) - 0.001, float(centre[i - 1] - half)))
        last = i == len(grid) - 1
        if last or i in cut_at or not np.isclose(centre[i + 1] - centre[i], centre[i] - centre[i - 1], atol=0.5):
            points.append((float(grid[i]), float(centre[i] - half)))
    return points


def at(points: list[tuple[float, float]], t: float) -> float:
    """The path's value at time t (straight lines between points, flat outside them), as layouts.path_expr draws it."""
    ts, xs = zip(*points)
    return float(np.interp(t, ts, xs))


def motion(points: list[tuple[float, float]] | None, length: float, fps: float = 30.0, cuts=()) -> tuple[float, float]:
    """(speed, jitter) of a crop path in source pixels per output frame: speed is the mean movement per frame,
    jitter the mean change of that movement from one frame to the next (0 for a still crop or a steady pan; a
    crop that shakes scores high even when it goes nowhere). Frames at a hard cut are left out."""
    if not points:
        return 0.0, 0.0
    t = np.arange(0.0, length, 1.0 / fps)
    v = np.diff(np.interp(t, *zip(*points)))
    keep = np.ones(len(v), bool)
    for c in cuts:
        keep[max(0, int(c * fps) - 2):int(c * fps) + 2] = False
    if keep.sum() < 2:
        return 0.0, 0.0
    a = np.abs(np.diff(v))[keep[1:] & keep[:-1]]
    return float(np.abs(v[keep]).mean()), float(a.mean()) if len(a) else 0.0


def crop_path(plan, tr: Track, length: float):
    """`plan` with its moving gameplay panel: the one panel that fills the frame (full) or the gameplay panel of a
    two-panel layout, when it is narrower than the source. A panel whose crop holds a person stays still (it was
    placed to keep them whole). Unchanged when the path would barely move."""
    sw, _sh = plan.source
    for k, p in enumerate(plan.panels):
        if p.kind != "gameplay" or not p.punch or p.src[2] >= sw - 1:
            continue
        pts = follow([(t, x * sw) for t, x in zip(tr.times, tr.xs)], p.src[2], sw, length, tr.cuts)
        if not pts:
            return plan
        if plan.cam:                                         # never slide onto the webcam
            from .layouts import _keep_out, _overlaps
            box = _keep_out(sw, plan.source[1], plan.cam, plan.face)
            if any(_overlaps((x, p.src[1], p.src[2], p.src[3]), box) for _t, x in pts):
                return plan
        if len(pts) == 1:                                    # still, but on the subject
            if abs(pts[0][1] - p.src[0]) < DEAD_ZONE * p.src[2]:
                return plan
            moved = replace(p, src=(pts[0][1], p.src[1], p.src[2], p.src[3]))
        else:
            moved = replace(p, path=tuple((t, (x, p.src[1], p.src[2], p.src[3])) for t, x in pts))
        return replace(plan, panels=plan.panels[:k] + (moved,) + plan.panels[k + 1:])
    return plan


def follow_plan(src, plan, start: float, end: float, *, game: str | None = None,
                deadline: Deadline | None = None):
    """crop_path for one clip of `src`, measured on the clip itself. Any failure keeps the still plan."""
    if plan is None or plan.source is None:
        return plan
    try:
        tr = track(src, start, end, exclude=[plan.cam] if plan.cam else (), game=game, deadline=deadline)
        return crop_path(plan, tr, end - start)
    except PipelineTimeout:
        raise
    except (PipelineError, Exception):
        log.exception("action tracking failed; the crop stays still")
        return plan
