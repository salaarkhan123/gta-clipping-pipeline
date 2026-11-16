"""Facecam: crop to the webcam overlay's own rectangle, not a padded box around the face."""
import subprocess

import cv2
import numpy as np
import pytest

from app.pipeline import facecam as F
from app.pipeline.ff import probe
from app.pipeline.render import gameplay_crop, render_clip

H, W = 360, 640


def gameplay(rng):
    return np.kron(rng.integers(0, 255, (H // 8, W // 8)), np.ones((8, 8))).astype(np.uint8)


def scene(cam, n=12, cutout=False, hud=None, bar_from=None, static=False, seed=3):
    """n gray frames, minutes apart: gameplay that changes everywhere, and a camera overlay at cam = (x, y, w, h)
    whose room stays put while the streamer moves. A cut-out camera has the streamer but no room.
    Returns (frames, face)."""
    rng = np.random.default_rng(seed)
    x, y, w, h = cam
    room = np.kron(rng.integers(60, 200, (h // 10 + 1, w // 10 + 1)), np.ones((10, 10)))[:h, :w]
    first = gameplay(rng)
    head = (w // 2, int(h * 0.42))                                   # inside the camera patch
    frames = []
    for _ in range(n):
        g = first.copy() if static else gameplay(rng)
        patch = g[y:y + h, x:x + w].copy() if cutout else (room + rng.normal(0, 2, room.shape)).clip(0, 255).astype(np.uint8)
        dx, dy = (0, 0) if static else rng.integers(-5, 6, 2)
        cv2.ellipse(patch, (head[0] + dx, h + 10 + dy), (int(w * 0.33), int(h * 0.42)), 0, 0, 360, 90, -1)    # shoulders
        cv2.ellipse(patch, (head[0] + dx, head[1] + dy), (int(h * 0.17), int(h * 0.22)), 0, 0, 360, 170, -1)  # head
        g[y:y + h, x:x + w] = patch
        if hud:
            hx, hy, hw, hh = hud
            g[hy:hy + hh, hx:hx + hw] = 235                           # a static HUD icon
        if bar_from is not None:
            g[:, bar_from:] = 0                                       # letterbox bar to the right edge
        frames.append(g)
    return frames, ((x + head[0]) / W, (y + head[1]) / H, 2 * h * 0.17 / W, 2 * h * 0.22 / H)


def px(box):
    return [round(box[0] * W), round(box[1] * H), round(box[2] * W), round(box[3] * H)]


def close(box, cam, tol=2):
    return box is not None and all(abs(a - b) <= tol for a, b in zip(px(box), cam))


def test_finds_the_overlay_rectangle_not_a_box_around_the_face():
    cam = (400, 60, 180, 120)
    frames, face = scene(cam)
    box = F.find_cam_rect(frames, face)
    assert close(box, cam), (box and px(box), cam)
    # The old guess (3 faces wide, 1.9 tall) for the same face: a different shape that takes in gameplay.
    assert not close([face[0] - 1.5 * face[2], face[1] - 0.8 * face[3], 3 * face[2], 1.9 * face[3]], cam, tol=6)


def test_overlay_in_a_corner_touching_the_frame_edges():
    cam = (W - 200, H - 130, 200, 130)
    frames, face = scene(cam)
    assert close(F.find_cam_rect(frames, face), cam)


def test_static_hud_beside_the_camera_stays_out():
    cam = (300, 200, 180, 120)
    frames, face = scene(cam, hud=(250, 230, 44, 44))            # an icon 6 px left of the camera
    assert close(F.find_cam_rect(frames, face), cam)


def test_letterbox_bar_against_the_camera_stays_out():
    cam = (360, 40, 180, 120)
    frames, face = scene(cam, bar_from=540)                      # the camera sits flush against a black bar
    assert close(F.find_cam_rect(frames, face), cam)


def test_cut_out_camera_has_no_rectangle_and_falls_back_to_a_tight_face_crop(monkeypatch):
    frames, face = scene((300, 180, 180, 120), cutout=True)
    assert F.find_cam_rect(frames, face) is None
    monkeypatch.setattr(F, "find_face", lambda _frames: face)
    x, y, w, h = F.find_facecam(frames)
    assert w <= 2.2 * face[2] + 1e-3 and h <= 1.4 * face[3] + 1e-3           # tighter than the old 3 x 1.9 faces
    assert x <= face[0] - face[2] / 2 and x + w >= face[0] + face[2] / 2     # and the whole face is inside
    assert y <= face[1] - face[3] / 2 and y + h >= face[1] + face[3] / 2


def test_a_video_that_does_not_move_is_not_an_overlay():
    frames, face = scene((300, 180, 180, 120), static=True)
    assert F.find_cam_rect(frames, face) is None


def test_no_face_still_means_no_facecam():
    assert F.find_facecam(scene((300, 180, 180, 120))[0]) is None            # drawn ellipses are not a face


# ---------- on real video: detect, then render the split layout ----------
CAM = (960, 0, 320, 180)             # a green webcam box in the top-right corner of a 1280x720 stream


@pytest.fixture(scope="module")
def stream(tmp_path_factory):
    """40 s of gameplay with no green in it at all, and a pure green camera box over it."""
    out = tmp_path_factory.mktemp("cam") / "stream.mp4"
    x, y, w, h = CAM
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "mandelbrot=size=1280x720:rate=15:end_scale=0.01,format=rgb24,lutrgb=g=0,trim=duration=40",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
                    "-vf", f"drawbox=x={x}:y={y}:w={w}:h={h}:color=0x00ff00:t=fill",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
                   check=True)
    return out


def green(img) -> np.ndarray:
    r, g, b = (img[..., i].astype(int) for i in range(3))
    return (g > 150) & (r < 100) & (b < 100)


def frame_rgb(video, t=1.0, w=270, h=480):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


def test_split_layout_top_panel_is_only_camera_and_gameplay_panel_has_none(stream, tmp_path, monkeypatch):
    x, y, w, h = CAM
    monkeypatch.setattr(F, "find_face", lambda _frames: ((x + w / 2) / 1280, (y + h / 2) / 720, 0.06, 0.11))
    info = probe(stream)
    box = F.detect_facecam(stream, info)
    assert box is not None and all(abs(a - b) <= 0.006 for a, b in zip(box, (x / 1280, y / 720, w / 1280, h / 720))), box
    how, _ = gameplay_crop(info.width, info.height, 1080, 1280, 1.0, box)
    assert how == "shifted"                                                  # 0.2c: the gameplay crop moves off the camera
    out = tmp_path / "split.mp4"
    render_clip(stream, 5, 7, out, src_w=info.width, src_h=info.height, vertical=True, zoom=1.0, chat="none", words=[],
                font="DejaVu Sans", layout="split", facecam=box)
    img = frame_rgb(out)
    top, bottom = img[: 480 // 3 - 2], img[480 // 3 + 4:]
    assert green(top).mean() > 0.97          # the camera panel shows the camera and no gameplay around it
    assert green(bottom).sum() == 0          # and the gameplay panel does not show the camera again


def test_real_face_overlay_is_cropped_to_its_exact_rectangle(tmp_path):
    skdata = pytest.importorskip("skimage.data")
    cv2.imwrite(str(tmp_path / "face.png"), cv2.cvtColor(skdata.astronaut(), cv2.COLOR_RGB2BGR))
    src = tmp_path / "cam.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "mandelbrot=size=1280x720:rate=15:end_scale=0.01,format=yuv420p,trim=duration=40",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=40", "-loop", "1", "-i", str(tmp_path / "face.png"),
                    "-filter_complex", "[2:v]crop=512:288:0:20,scale=384:216[f];[0:v]drawbox=x=470:y=60:w=90:h=90:color=white:t=fill[g];"
                                       "[g][f]overlay=60:40:shortest=1[v]",
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(src)], check=True)
    box = F.detect_facecam(src, probe(src))                                  # real Haar face detection, then the rectangle
    want = (60 / 1280, 40 / 720, 384 / 1280, 216 / 720)                      # a 16:9 camera, with a HUD block to its right
    assert box is not None and all(abs(a - b) <= 0.006 for a, b in zip(box, want)), box
