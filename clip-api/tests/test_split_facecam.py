"""Split layout: the gameplay (bottom) crop must not show the webcam overlay a second time."""
import subprocess

import numpy as np
import pytest

from app.pipeline.render import (FACECAM_REGIONS, crop_rect, gameplay_crop, layout_filter, render_clip, FULL_FRAME,
                                 _overlaps)

SRC_W, SRC_H, TW, TH = 1920, 1080, 1080, 1280      # 16:9 source, gameplay band of a 1080x1920 split frame


def crop_of(filt: str):
    """The crop=w:h:x:y in a gameplay filter, as source pixels (the last crop: the one before scale)."""
    part = filt.split("crop=")[-1].split(",")[0]
    w, h, x, y = map(int, part.split(":"))
    return x, y, w, h


def px(box):
    return box[0] * SRC_W, box[1] * SRC_H, box[2] * SRC_W, box[3] * SRC_H


def test_centred_crop_includes_the_top_right_preset_today():
    # The bug: the centred crop spans 26-74% of the width; the top-right camera starts at 70%.
    assert _overlaps(crop_rect(SRC_W, SRC_H, FULL_FRAME, TW, TH), px(FACECAM_REGIONS["top-right"]))


@pytest.mark.parametrize("preset", ["top-left", "top-right", "bottom-left", "bottom-right"])
def test_edge_camera_presets_shift_the_crop_clear_of_the_camera(preset):
    how, filt = gameplay_crop(SRC_W, SRC_H, TW, TH, 1.0, FACECAM_REGIONS[preset])
    assert how == "shifted"
    x, y, w, h = crop_of(filt)
    assert not _overlaps((x, y, w, h), px(FACECAM_REGIONS[preset]))
    assert 0 <= x and x + w <= SRC_W and (w, h) == (910, 1080)       # same size as before, still inside the frame


def test_camera_clear_of_the_crop_leaves_it_alone():
    cam = [0.0, 0.0, 0.12, 0.15]          # small top-left camera, outside the centred crop
    how, filt = gameplay_crop(SRC_W, SRC_H, TW, TH, 1.0, cam)
    centred = crop_rect(SRC_W, SRC_H, FULL_FRAME, TW, TH)
    assert how == "clear" and crop_of(filt)[0] == int(centred[0]) // 2 * 2


def test_camera_inside_the_frame_is_blurred_not_dodged():
    cam = [0.42, 0.35, 0.16, 0.25]        # overlay in the middle of the frame, touching no edge
    how, filt = gameplay_crop(SRC_W, SRC_H, TW, TH, 1.0, cam)
    assert how == "blurred" and "boxblur" in filt and "overlay" in filt


def test_only_the_split_layout_changes():
    assert "boxblur" not in layout_filter(SRC_W, SRC_H, "fill", 1.0, "none", "top-right")


def frame_rgb(video, t=0.5, w=270, h=480):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


def magenta(img) -> int:
    r, g, b = (img[..., i].astype(int) for i in range(3))
    return int(((r > 180) & (b > 180) & (g < 90)).sum())


def test_rendered_split_shows_the_camera_once(tmp_path):
    src = tmp_path / "cam.mp4"
    x, y, w, h = FACECAM_REGIONS["top-right"]
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={SRC_W}x{SRC_H}:d=2",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "2",
                    "-vf", f"drawbox=x=iw*{x}:y=ih*{y}:w=iw*{w}:h=ih*{h}:color=magenta:t=fill",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)],
                   check=True)
    out = tmp_path / "split.mp4"
    render_clip(src, 0, 1.5, out, src_w=SRC_W, src_h=SRC_H, vertical=True, zoom=1.0, chat="none", words=[],
                font="DejaVu Sans", layout="split", facecam="top-right")
    img = frame_rgb(out)
    top, bottom = img[: 480 // 3], img[480 // 3 + 4:]
    assert magenta(top) > 1000            # the camera band shows the camera
    assert magenta(bottom) == 0           # the gameplay band does not
