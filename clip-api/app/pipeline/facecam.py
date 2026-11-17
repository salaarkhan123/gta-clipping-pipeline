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


def sample_gray(src, info: MediaInfo, n: int, deadline: Deadline | None = None, width: int = 640) -> list:
    h = even(width * info.height / info.width)
    frames = []
    for i in range(n):
        t = info.duration * (0.05 + 0.9 * (i + 0.5) / n)
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


def stable_face(frames: list) -> tuple[float, float, float, float] | None:
    """A face that stays in one place across the video, whatever its size, or None."""
    det, faces = _detector(), []
    for i, g in enumerate(frames):
        fh_px, fw_px = g.shape
        for (x, y, w, h) in det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=6, minSize=(24, 24)):
            faces.append((i, (x + w / 2) / fw_px, (y + h / 2) / fh_px, w / fw_px, h / fh_px))
    clusters: list[list] = []
    for f in faces:
        for c in clusters:
            _, cx, cy, w, h = c[0]
            if abs(f[1] - cx) < 0.6 * w and abs(f[2] - cy) < 0.6 * h and 0.6 < f[3] / w < 1.6:
                c.append(f)
                break
        else:
            clusters.append([f])
    best = max(clusters, key=lambda c: len({f[0] for f in c}), default=None)
    if not best or len({f[0] for f in best}) < max(3, int(0.4 * len(frames))):
        return None
    cx, cy, fw, fh = (float(np.median([f[k] for f in best])) for k in (1, 2, 3, 4))
    return cx, cy, fw, fh


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


@dataclass(frozen=True)
class Scene:
    kind: str                            # "gameplay_cam" | "camera" | "gameplay"
    cam: list[float] | None = None       # the webcam overlay [x, y, w, h] (fractions): gameplay_cam only
    face: tuple | None = None            # the person's face (centre x, centre y, w, h), when there is one


def still_share(frames: list) -> float:
    """The share of the picture that barely changes between frames sampled minutes apart, black bars left out.
    Gameplay changes everywhere; a room behind a streamer does not."""
    if len(frames) < 4:
        return 0.0
    stack = np.stack([f.astype(np.float32) for f in frames])
    change = np.abs(np.diff(stack, axis=0)).mean(axis=0)
    picture = stack.max(axis=0) >= BAR_LEVEL
    return float((change[picture] < STILL_LEVEL).mean()) if picture.any() else 0.0


def classify(frames: list) -> Scene:
    """Gameplay with a webcam overlay, a camera that fills the frame, or gameplay with no camera.

    A face that stays put is a person on camera. It is an overlay when its own rectangle can be found, or when
    the picture around it keeps changing (a cut-out camera over the game). It is the whole picture when the face
    is large or most of the frame is as still as a room."""
    face = stable_face(frames)
    if face is None:
        return Scene("gameplay")
    if face[2] > MAX_OVERLAY_FACE:
        return Scene("camera", None, face)
    rect = find_cam_rect(frames, face)
    if rect:
        return Scene("gameplay_cam", rect, face)
    if still_share(frames) >= CAMERA_STILL:
        return Scene("camera", None, face)
    return Scene("gameplay_cam", face_crop(face), face)


def detect_scene(src, info: MediaInfo, deadline: Deadline | None = None, samples: int = 12) -> Scene:
    try:
        return classify(sample_gray(src, info, samples, deadline))
    except PipelineTimeout:
        raise
    except Exception:
        log.exception("scene detection failed; continuing as gameplay with no camera")
        return Scene("gameplay")


class CamBox(list):
    """A detected camera box [x, y, w, h] that also remembers the face it was found from and the scene type.
    It is a plain list to every caller that only passes it on; render_clip reads the rest, so a face found here
    is never cut by a panel edge there."""
    face: tuple | None = None
    scene: str | None = None

    def __init__(self, box, face=None, scene=None):
        super().__init__(box)
        self.face, self.scene = face, scene


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
                           camera=getattr(options, "camera", None), split_ratio=getattr(options, "split_ratio", None))


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
        return layouts.legacy_name(plan.layout), CamBox(face_crop(plan.face), plan.face, "camera")
    return layouts.legacy_name(plan.layout), (CamBox(plan.cam, plan.face, plan.scene) if plan.cam else None)
