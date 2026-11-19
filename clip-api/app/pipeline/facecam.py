"""Automatic facecam detection: a face that stays in the same place across the video is the streamer's camera.

In-game faces move around; a webcam overlay does not. Uses OpenCV's bundled Haar face detector (no model download).
"""
import logging
import threading
from dataclasses import dataclass

import numpy as np

from . import layouts
from .ff import SAFE_IN, Deadline, MediaInfo, PipelineError, PipelineTimeout, run_bytes
from .layouts import LayoutPlan
from .render import FACECAM_REGIONS, even, resolve_layout

log = logging.getLogger("clipapi.facecam")
_local = threading.local()   # one detector per thread: a cascade is not safe to call from two jobs at once


def _detector():
    if getattr(_local, "cascade", None) is None:
        import cv2
        c = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if c.empty():
            raise RuntimeError("face detector data is missing")
        _local.cascade = c
    return _local.cascade


def _weak_detectors():
    """The looser second look: two more face detectors bundled with OpenCV (another frontal one and a profile one),
    for a streamer who looks down at the keyboard or turns away, which the first detector misses."""
    if getattr(_local, "weak", None) is None:
        import cv2
        cs = [cv2.CascadeClassifier(cv2.data.haarcascades + f)
              for f in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml")]
        if any(c.empty() for c in cs):
            raise RuntimeError("face detector data is missing")
        _local.weak = cs
    return [_detector(), *_local.weak]


def sample_gray(src, info: MediaInfo, n: int, deadline: Deadline | None = None, width: int = 640,
                span: tuple[float, float] | None = None) -> list:
    """`n` gray frames spread over the video, or over `span` (start, end seconds) when one is given."""
    h = even(width * info.height / info.width)
    a, b = span or (0.0, info.duration)
    frames = []
    for i in range(n):
        t = a + (b - a) * (0.05 + 0.9 * (i + 0.5) / n)
        try:
            raw = run_bytes(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", *SAFE_IN, "-i", src, "-frames:v", "1",
                             "-vf", f"scale={width}:{h},format=gray", "-f", "rawvideo", "-"], deadline, cap=60)
        except PipelineTimeout:
            raise
        except PipelineError:
            continue
        if len(raw) == width * h:
            frames.append(np.frombuffer(raw, np.uint8).reshape(h, width))
    return frames


MAX_OVERLAY_FACE = 0.28  # a face wider than this share of the frame is a full-screen camera, not an overlay


def find_face(frames: list) -> tuple[float, float, float, float] | None:
    """The streamer's face as (centre x, centre y, width, height) fractions: a face that stays in one place across
    the video. None if there is none, or if it fills the frame (a full-screen camera, not an overlay)."""
    face = stable_face(frames)
    return None if face is None or face[2] > MAX_OVERLAY_FACE else face


def _clusters(faces: list) -> list[list]:
    """Face hits (frame index, centre x, centre y, w, h) grouped by place and size, the group seen in the most
    frames first."""
    clusters: list[list] = []
    for f in faces:
        for c in clusters:
            _, cx, cy, w, h = c[0]
            if abs(f[1] - cx) < 0.6 * w and abs(f[2] - cy) < 0.6 * h and 0.6 < f[3] / w < 1.6:
                c.append(f)
                break
        else:
            clusters.append([f])
    return sorted(clusters, key=lambda c: -len({f[0] for f in c}))


def _median_face(cluster: list) -> tuple[float, float, float, float]:
    cx, cy, fw, fh = (float(np.median([f[k] for f in cluster])) for k in (1, 2, 3, 4))
    return cx, cy, fw, fh


def stable_face(frames: list) -> tuple[float, float, float, float] | None:
    """A face that stays in one place across the video, whatever its size, or None."""
    det, faces = _detector(), []
    for i, g in enumerate(frames):
        fh_px, fw_px = g.shape
        for (x, y, w, h) in det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=6, minSize=(24, 24)):
            faces.append((i, (x + w / 2) / fw_px, (y + h / 2) / fh_px, w / fw_px, h / fh_px))
    best = next(iter(_clusters(faces)), None)
    if not best or len({f[0] for f in best}) < max(3, int(0.4 * len(frames))):
        return None
    return _median_face(best)


WEAK_FRAMES = 2          # a loose face hit in this many frames, in one place, is worth checking for a camera box


def weak_faces(frames: list) -> list[tuple[int, tuple[float, float, float, float]]]:
    """Places where a face shows in at least WEAK_FRAMES frames, by any of three detectors at a looser setting
    (profiles both ways): (frames seen in, face), most frames first. Many are not a streamer (game characters, a
    poster): a caller trusts one only with more evidence, such as a still camera box around it (find_cam_rect)."""
    hits = []
    for i, g in enumerate(frames):
        h_px, w_px = g.shape
        for k, det in enumerate(_weak_detectors()):
            views = ((g, False), (np.ascontiguousarray(g[:, ::-1]), True)) if k == 2 else ((g, False),)
            for img, flipped in views:
                for (x, y, w, h) in det.detectMultiScale(img, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20)):
                    if flipped:
                        x = w_px - x - w
                    hits.append((i, (x + w / 2) / w_px, (y + h / 2) / h_px, w / w_px, h / h_px))
    out = [(len({f[0] for f in c}), _median_face(c)) for c in _clusters(hits)]
    return [(n, face) for n, face in out if n >= WEAK_FRAMES]


STILL_FRACTION = 0.5     # a row or column belongs to the camera when this share of it barely changes over the video
BAR_LEVEL = 20           # a strip that never gets brighter than this (0-255) is a letterbox bar, not camera
MAX_CAM = 0.6            # an overlay wider or taller than this share of the frame is not an overlay


def find_cam_rect(frames: list, face: tuple[float, float, float, float]) -> list[float] | None:
    """The webcam overlay's own rectangle [x, y, w, h] (fractions), found from the frames, or None.

    The sampled frames are minutes apart, so gameplay pixels change completely between them while the camera's
    background (the room behind the streamer) hardly does. Starting from the face, the box grows one row or column
    at a time while the next strip is still, so it ends where the moving gameplay begins. It never grows into a
    letterbox bar (still, but black in every frame). A cut-out camera with no background has nothing still around
    the face, so this returns None and the caller falls back to a crop around the face.
    """
    if len(frames) < 4:
        return None
    stack = np.stack([f.astype(np.float32) for f in frames])
    _, H, W = stack.shape
    change = np.abs(np.diff(stack, axis=0)).mean(axis=0)                 # mean change between consecutive samples
    still = change < max(6.0, 0.35 * float(np.median(change)))
    camera = still & ~(stack.max(axis=0) < BAR_LEVEL)                    # still, and not a black bar

    cx, cy, fw, fh = face
    x0, x1 = max(0, int((cx - fw / 2) * W)), min(W, int((cx + fw / 2) * W))   # [x0, x1) x [y0, y1): starts as the face
    y0, y1 = max(0, int((cy - fh / 2) * H)), min(H, int((cy + fh / 2) * H))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    grew = True
    while grew:
        grew = False
        if x0 > 0 and camera[y0:y1, x0 - 1].mean() >= STILL_FRACTION:
            x0, grew = x0 - 1, True
        if x1 < W and camera[y0:y1, x1].mean() >= STILL_FRACTION:
            x1, grew = x1 + 1, True
        if y0 > 0 and camera[y0 - 1, x0:x1].mean() >= STILL_FRACTION:
            y0, grew = y0 - 1, True
        if y1 < H and camera[y1, x0:x1].mean() >= STILL_FRACTION:
            y1, grew = y1 + 1, True
        if (x1 - x0) > MAX_CAM * W or (y1 - y0) > MAX_CAM * H:
            return None                                                  # most of the picture is still: not an overlay
    w, h = (x1 - x0) / W, (y1 - y0) / H
    if w < 1.3 * fw or h < 1.15 * fh:
        return None                                                      # it never left the face: no rectangle here
    if not 0.4 <= (w * W) / (h * H) <= 3.0:
        return None
    return [round(v, 4) for v in (x0 / W, y0 / H, w, h)]


def face_crop(face: tuple[float, float, float, float]) -> list[float]:
    """Fallback when the overlay has no findable rectangle (a cut-out or borderless camera): head and shoulders
    only, close to the split band's shape, so as little as possible of what surrounds the camera gets in."""
    cx, cy, fw, fh = face
    cw, ch = min(1.0, 2.2 * fw), min(1.0, 1.4 * fh)
    cy += 0.1 * fh
    x, y = min(max(cx - cw / 2, 0.0), 1.0 - cw), min(max(cy - ch / 2, 0.0), 1.0 - ch)
    return [round(v, 4) for v in (x, y, cw, ch)]


def find_facecam(frames: list) -> list[float] | None:
    """Returns the webcam box [x, y, w, h] as fractions of the frame, or None when there is no facecam."""
    face = find_face(frames)
    if face is None:
        return None
    return find_cam_rect(frames, face) or face_crop(face)


def detect_facecam(src, info: MediaInfo, deadline: Deadline | None = None, samples: int = 12) -> list[float] | None:
    try:
        return find_facecam(sample_gray(src, info, samples, deadline))
    except PipelineTimeout:
        raise
    except Exception:
        log.exception("facecam detection failed; continuing without it")
        return None


# ---------- scene type: what kind of picture this source is ----------
CAMERA_STILL = 0.5       # this share of the frame barely changing over the video: the camera is the whole picture
STILL_LEVEL = 10.0       # mean change (0-255) between samples minutes apart below which a pixel counts as still


ROOM_CHANGE = 28.0       # median change (0-255) between samples minutes apart below which the picture is a room, not a game
CAMERA_FRAMES = 0.5      # a face in this share of the frames, in one place, with no overlay box: the person is the picture
# How sure each way of finding the camera is (Scene.confidence); docs/REFRAME_EVAL.md has the eval set behind them.
CONFIDENCE = {"rect": 0.9, "weak_rect": 0.75, "face_crop": 0.6, "camera": 0.8, "weak_camera": 0.6}


@dataclass(frozen=True)
class Scene:
    kind: str                            # "gameplay_cam" | "camera" | "gameplay"
    cam: list[float] | None = None       # the webcam overlay [x, y, w, h] (fractions): gameplay_cam only
    face: tuple | None = None            # the person's face (centre x, centre y, w, h), when there is one
    confidence: float | None = None      # 0-1, how sure the camera is (CONFIDENCE); None for "gameplay" or a given box


def still_share(frames: list) -> float:
    """The share of the picture that barely changes between frames sampled minutes apart, black bars left out.
    Gameplay changes everywhere; a room behind a streamer does not."""
    if len(frames) < 4:
        return 0.0
    stack = np.stack([f.astype(np.float32) for f in frames])
    change = np.abs(np.diff(stack, axis=0)).mean(axis=0)
    picture = stack.max(axis=0) >= BAR_LEVEL
    return float((change[picture] < STILL_LEVEL).mean()) if picture.any() else 0.0


def median_change(frames: list) -> float:
    """The median change (0-255) of a pixel between frames sampled minutes apart: 35 and up for gameplay, about
    20 for a room on camera, whatever moves in it."""
    if len(frames) < 2:
        return 255.0
    stack = np.stack([f.astype(np.float32) for f in frames])
    return float(np.median(np.abs(np.diff(stack, axis=0)).mean(axis=0)))


def classify(frames: list) -> Scene:
    """Gameplay with a webcam overlay, a camera that fills the frame, or gameplay with no camera.

    A face that stays put is a person on camera. It is an overlay when its own rectangle can be found, or when
    the picture around it keeps changing (a cut-out camera over the game). It is the whole picture when the face
    is large or most of the frame is as still as a room.

    When the strict face detector finds no overlay box, a looser look (weak_faces) tries again: a streamer looking
    down at the keyboard is often seen in only a few frames, or only in profile. A loose face is trusted only when
    a still camera box grows around it, so a game character never becomes a camera. With no box, a face in most
    frames over a picture that changes like a room is a person filling the frame (a react or just-chatting video)."""
    face = stable_face(frames)
    if face is not None and face[2] > MAX_OVERLAY_FACE:
        return Scene("camera", None, face, CONFIDENCE["camera"])
    rect = find_cam_rect(frames, face) if face else None
    if rect:
        return Scene("gameplay_cam", rect, face, CONFIDENCE["rect"])
    weak = [(n, f) for n, f in weak_faces(frames) if f[2] <= MAX_OVERLAY_FACE] if len(frames) >= 4 else []
    for _n, loose in weak:
        rect = find_cam_rect(frames, loose)
        if rect:
            return Scene("gameplay_cam", rect, face or loose, CONFIDENCE["weak_rect"])
    if face is not None:
        if still_share(frames) >= CAMERA_STILL:
            return Scene("camera", None, face, CONFIDENCE["camera"])
        return Scene("gameplay_cam", face_crop(face), face, CONFIDENCE["face_crop"])
    if weak and weak[0][0] >= CAMERA_FRAMES * len(frames) and median_change(frames) < ROOM_CHANGE:
        return Scene("camera", None, weak[0][1], CONFIDENCE["weak_camera"])
    return Scene("gameplay")


def detect_scene(src, info: MediaInfo, deadline: Deadline | None = None, samples: int = 12) -> Scene:
    try:
        return classify(sample_gray(src, info, samples, deadline))
    except PipelineTimeout:
        raise
    except Exception:
        log.exception("scene detection failed; continuing as gameplay with no camera")
        return Scene("gameplay")


class CamBox(list):
    """A detected camera box [x, y, w, h] that also remembers the face it was found from, the scene type and how
    sure the detection is (Scene.confidence). It is a plain list to every caller that only passes it on;
    render_clip reads the rest, so a face found here is never cut by a panel edge there."""
    face: tuple | None = None
    scene: str | None = None
    confidence: float | None = None

    def __init__(self, box, face=None, scene=None, confidence=None):
        super().__init__(box)
        self.face, self.scene, self.confidence = face, scene, confidence


def resolve_plan(src, info: MediaInfo, options, deadline: Deadline | None = None) -> LayoutPlan | None:
    """The layout plan for a job's options (layout, aspect, facecam_region, facecam_box, zoom, and the two-panel
    controls camera and split_ratio when the options have them), detecting the scene when the camera is not
    given. None when the clip is not reframed or uses the old classic layout.
    Raises PipelineError for a layout the aspect does not offer, or one that is not built (trio, grid4, ots)."""
    region = options.facecam_region
    if region and region != "auto" and region not in FACECAM_REGIONS:
        raise PipelineError("bad_options", "Unknown facecam_region.")
    if not options.vertical:
        return None
    aspect = getattr(options, "aspect", "9:16")
    name = layouts.check_layout(options.layout, aspect)
    if name == "classic":
        return None
    box = options.facecam_box or (FACECAM_REGIONS[region] if region and region != "auto" else None)
    if box:
        scene = Scene("gameplay_cam", list(box))
    elif region == "auto":
        scene = detect_scene(src, info, deadline)
    else:
        scene = Scene("gameplay")
    if options.layout in layouts.NEEDS_CAMERA and scene.kind == "gameplay" and region != "auto":
        raise PipelineError("bad_options", f"The {options.layout} layout needs facecam_region or facecam_box.")
    return layouts.compose(info.width, info.height, name, aspect, scene=scene.kind, cam=scene.cam, face=scene.face,
                           zoom=getattr(options, "zoom", 1.0), requested=options.layout,
                           camera=getattr(options, "camera", None), split_ratio=getattr(options, "split_ratio", None),
                           confidence=scene.confidence)


MOMENT_SAMPLES = 4      # frames looked at inside each moment when the layout is auto


def moment_scene(frames: list, facecam) -> tuple[str, tuple | None] | None:
    """What one moment shows, from frames sampled inside it, when the video as a whole has a camera (`facecam`,
    what resolve_facecam found): ("gameplay", None) when no face stays put in it (the camera is hidden or
    switched off), ("camera", face) when the person fills the frame, None when it looks like the rest of the
    video. Too few frames, or no camera in the video: None. It never finds a camera the video did not have.
    A camera whose face was never seen (a box the user gave, a face the detector misses) is kept as it is:
    no face in a moment would then say nothing about that moment."""
    if (not facecam or getattr(facecam, "scene", None) != "gameplay_cam" or getattr(facecam, "face", None) is None
            or len(frames) < 2):
        return None
    face = stable_face(frames)
    if face is None:
        return "gameplay", None
    return ("camera", face) if face[2] > MAX_OVERLAY_FACE else None


def moment_facecam(src, info: MediaInfo, start: float, end: float, layout: str, facecam,
                   deadline: Deadline | None = None) -> tuple[str, object]:
    """The (layout, facecam) render_clip draws one moment of an auto-layout job with: the job's own, unless the
    moment shows something else (moment_scene). A moment with the camera hidden fills the frame with gameplay; one
    where the person fills the frame is framed on them."""
    try:
        scene = moment_scene(sample_gray(src, info, MOMENT_SAMPLES, deadline, span=(start, end)), facecam)
    except PipelineTimeout:
        raise
    except Exception:
        log.exception("moment scene check failed; keeping the video's layout")
        return layout, facecam
    if scene is None:
        return layout, facecam
    kind, face = scene
    return ("fill", None) if kind == "gameplay" else ("fill", CamBox(face_crop(face), face, "camera"))


def resolve_facecam(src, info: MediaInfo, options, deadline: Deadline | None = None) -> tuple[str, object]:
    """Returns (layout, facecam) for render_clip: the layout that will be drawn, and the camera (a CamBox, or
    None). The layout is the old name where there is one ("split", "fill"), so callers that know only those
    still recognise it. Callers that want the whole decision use resolve_plan and pass render_clip(plan=...)."""
    plan = resolve_plan(src, info, options, deadline)
    if plan is None:        # not reframed, or classic: the camera is passed through and nothing is detected
        facecam = options.facecam_box or (options.facecam_region if options.facecam_region != "auto" else None)
        layout = resolve_layout(options.layout, facecam)
        if layout == "split" and not facecam:
            if options.facecam_region != "auto":
                raise PipelineError("bad_options", "The split layout needs facecam_region or facecam_box.")
            layout = "fill"
        return layout, facecam
    if plan.scene == "camera":      # the person is the picture: pass the head and shoulders as the box to hold
        return layouts.legacy_name(plan.layout), CamBox(face_crop(plan.face), plan.face, "camera", plan.confidence)
    return layouts.legacy_name(plan.layout), (CamBox(plan.cam, plan.face, plan.scene, plan.confidence)
                                              if plan.cam else None)
