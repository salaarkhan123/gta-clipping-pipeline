"""The cheap likeness checks around a premium thumbnail, with the free thumbnail's face detector (OpenCV Haar,
app/pipeline/facecam.py).

- reference_crop: a close-up of the biggest face in the frame (head and shoulders), sent as a second image so the
  model keeps the streamer recognisable.
- face_kept: the output still shows a face where the frame had one, about the same size. This catches the face
  being dropped, covered or moved; it cannot tell whether the face is the same person (Haar finds faces, it does
  not recognise them), so a human check of outputs is still needed (see the PR's benchmark sheet).
A frame where no face is found is not checked (gameplay with no camera).
"""
from io import BytesIO

import numpy as np

DETECT_ROWS = 720           # faces are looked for at this height
MIN_FACE = 0.04             # of the short side: smaller "faces" are noise
NEAR = 0.75                 # the output face's centre within this many face sizes of the frame's
SIZE_RANGE = (0.4, 2.5)     # the output face's area against the frame's
CROP_PAD = 1.1              # face sizes of room around the face in the close-up
CROP_SIDE = 512


def _gray(image) -> np.ndarray:
    import cv2
    rgb = np.asarray(image.convert("RGB"))
    k = DETECT_ROWS / rgb.shape[0]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if abs(k - 1) > 0.05:
        gray = cv2.resize(gray, (max(8, int(rgb.shape[1] * k)), DETECT_ROWS),
                          interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
    return gray


def faces(image) -> list[tuple[float, float, float, float]]:
    """Faces in a PIL image as (x, y, w, h) fractions, biggest first."""
    from ..pipeline.facecam import _detector
    gray = _gray(image)
    h, w = gray.shape
    small = max(20, int(MIN_FACE * min(h, w)))
    found = _detector().detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(small, small))
    out = [(x / w, y / h, fw / w, fh / h) for x, y, fw, fh in found]
    return sorted(out, key=lambda f: f[2] * f[3], reverse=True)


def reference_crop(image, face) -> bytes:
    """JPEG close-up of `face` ((x, y, w, h) fractions) in `image`, square, CROP_SIDE pixels."""
    W, H = image.size
    cx, cy = (face[0] + face[2] / 2) * W, (face[1] + face[3] / 2) * H
    half = max(face[2] * W, face[3] * H) * (0.5 + CROP_PAD)
    box = (int(max(0, cx - half)), int(max(0, cy - half)), int(min(W, cx + half)), int(min(H, cy + half)))
    crop = image.convert("RGB").crop(box)
    side = max(crop.size)
    crop = crop.resize((max(1, round(crop.size[0] * CROP_SIDE / side)), max(1, round(crop.size[1] * CROP_SIDE / side))))
    buf = BytesIO()
    crop.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def face_kept(source_face, output) -> bool:
    """Whether `output` (a PIL image of the same framing) still has a face near `source_face`, about its size."""
    sx, sy, sw, sh = source_face
    scx, scy = sx + sw / 2, sy + sh / 2
    for f in faces(output):
        cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
        ratio = (f[2] * f[3]) / max(1e-6, sw * sh)
        if abs(cx - scx) <= NEAR * sw and abs(cy - scy) <= NEAR * sh and SIZE_RANGE[0] <= ratio <= SIZE_RANGE[1]:
            return True
    return False
