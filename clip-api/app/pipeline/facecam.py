"""Automatic facecam detection: a face that stays in the same place across the video is the streamer's camera.

In-game faces move around; a webcam overlay does not. Uses OpenCV's bundled Haar face detector (no model download).
"""
import logging
import threading

import numpy as np

from .ff import SAFE_IN, Deadline, MediaInfo, PipelineError, PipelineTimeout, run_bytes
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


def find_facecam(frames: list) -> list[float] | None:
    """Returns the webcam box [x, y, w, h] as fractions of the frame, or None."""
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
    if fw > 0.28:
        return None   # the face fills the frame: this is a full-screen camera, not an overlay
    cw, ch = min(1.0, 3.0 * fw), min(1.0, 1.9 * fh)   # a webcam frame is roughly 3 faces wide, 1.9 tall
    cy += 0.15 * fh
    x, y = min(max(cx - cw / 2, 0.0), 1.0 - cw), min(max(cy - ch / 2, 0.0), 1.0 - ch)
    return [round(v, 4) for v in (x, y, cw, ch)]


def detect_facecam(src, info: MediaInfo, deadline: Deadline | None = None, samples: int = 12) -> list[float] | None:
    try:
        return find_facecam(sample_gray(src, info, samples, deadline))
    except PipelineTimeout:
        raise
    except Exception:
        log.exception("facecam detection failed; continuing without it")
        return None


def resolve_facecam(src, info: MediaInfo, options, deadline: Deadline | None = None) -> tuple[str, object]:
    """Returns (layout, facecam) where facecam is a preset name, a box, or None."""
    region = options.facecam_region
    if region and region != "auto" and region not in FACECAM_REGIONS:
        raise PipelineError("bad_options", "Unknown facecam_region.")
    facecam = options.facecam_box
    if not facecam:
        if region == "auto":
            if options.vertical and options.layout in ("auto", "split"):
                facecam = detect_facecam(src, info, deadline)
        else:
            facecam = region
    layout = resolve_layout(options.layout, facecam)
    if layout == "split" and not facecam:
        if region != "auto":
            raise PipelineError("bad_options", "The split layout needs facecam_region or facecam_box.")
        layout = "fill"   # asked for auto-detection and no camera was found
    return layout, facecam
