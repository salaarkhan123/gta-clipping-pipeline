"""Production readiness: no blur patch when a small step clears the camera, consistent loudness without
clipping, and a flash-forward that reads as intended."""
import re
import subprocess

import numpy as np
import pytest

from app.pipeline.ff import probe
from app.pipeline.render import MAX_DODGE, _overlaps, crop_rect, gameplay_crop, render_clip, FULL_FRAME
from tests.test_split_facecam import SRC_H, SRC_W, TH, TW, crop_of, px


def test_a_camera_just_inside_the_crop_is_stepped_around_not_blurred():
    cam = [0.172, 0.786, 0.186, 0.210]                 # the benchmark stream: a cut-out camera, bottom, left of centre
    assert _overlaps(crop_rect(SRC_W, SRC_H, FULL_FRAME, TW, TH), px(cam))      # the centred crop does include it
    how, filt = gameplay_crop(SRC_W, SRC_H, TW, TH, 1.0, cam)
    assert how == "shifted" and "boxblur" not in filt
    x, y, w, h = crop_of(filt)
    assert not _overlaps((x, y, w, h), px(cam)) and 0 <= x and x + w <= SRC_W
    centred = crop_rect(SRC_W, SRC_H, FULL_FRAME, TW, TH)
    assert abs(x - centred[0]) <= MAX_DODGE * w                                 # a small step: the middle of the game stays in view


def test_a_camera_in_the_middle_of_the_frame_is_still_covered_because_no_small_step_clears_it():
    how, filt = gameplay_crop(SRC_W, SRC_H, TW, TH, 1.0, [0.42, 0.35, 0.16, 0.25])
    assert how == "blurred"


def loudness(path) -> tuple[float, float]:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1]), float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", out)[-1])


@pytest.fixture(scope="module")
def loud_and_quiet(tmp_path_factory):
    """Two 20 s recordings of the same pink noise: one far too hot (clipping), one much too quiet."""
    d = tmp_path_factory.mktemp("lufs")
    for name, gain in (("hot", "12dB"), ("quiet", "-12dB")):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15:duration=20",
                        "-f", "lavfi", "-i", "anoisesrc=color=pink:duration=20:amplitude=0.5", "-af", f"volume={gain}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / f"{name}.mp4")], check=True)
    return d


def clip(src, out, **kw):
    info = probe(src)
    render_clip(src, kw.pop("start", 0), kw.pop("end", 20), out, src_w=info.width, src_h=info.height, vertical=True, zoom=1.0,
                chat="none", words=[], font="DejaVu Sans", layout="fill", **kw)
    return out


def test_every_clip_leaves_at_the_same_loudness_with_headroom(loud_and_quiet, tmp_path):
    before = {n: loudness(loud_and_quiet / f"{n}.mp4") for n in ("hot", "quiet")}
    assert before["hot"][0] - before["quiet"][0] > 12                           # more than 12 LU apart going in
    after = {n: loudness(clip(loud_and_quiet / f"{n}.mp4", tmp_path / f"{n}.mp4")) for n in ("hot", "quiet")}
    for name, (lufs, peak) in after.items():
        assert -16.0 <= lufs <= -12.5, (name, lufs)                             # the platforms play at about -14
        assert peak <= -1.0, (name, peak)                                       # no clipping
    assert abs(after["hot"][0] - after["quiet"][0]) < 2.0
    assert probe(tmp_path / "hot.mp4").has_audio
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate", "-of", "csv=p=0",
                          str(tmp_path / "hot.mp4")], capture_output=True, text=True).stdout.strip()
    assert out == "48000"                                                       # not loudnorm's internal 192 kHz


def test_loudness_also_applies_to_cut_clips_and_can_be_switched_off(loud_and_quiet, tmp_path):
    cut = loudness(clip(loud_and_quiet / "hot.mp4", tmp_path / "cut.mp4", segments=[(1.0, 8.0), (10.0, 19.0)]))
    assert -16.0 <= cut[0] <= -12.5 and cut[1] <= -1.0
    raw = loudness(clip(loud_and_quiet / "hot.mp4", tmp_path / "raw.mp4", loudness=False))
    assert raw[0] > cut[0] + 2.0                                                # untouched: still louder than the target


def test_a_silent_clip_renders_and_is_left_alone(tmp_path):
    src = tmp_path / "silent.mp4"       # digital silence broke the one-pass normaliser: the render itself failed
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=640x360:d=6",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "6", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)], check=True)
    from app.pipeline.render import loudness_filter, measure_loudness
    assert measure_loudness(src, 0, 6) is None and loudness_filter(None) == ""
    out = clip(src, tmp_path / "s.mp4", end=6)
    assert probe(out).duration == pytest.approx(6, abs=0.2) and probe(out).has_audio
    assert clip(src, tmp_path / "s2.mp4", end=6, segments=[(0.5, 2.5), (3.0, 5.5)]).exists()
    assert loudness_filter(-80.0).startswith("volume=20.00dB") and loudness_filter(-4.0).startswith("volume=-10.00dB")


def brightness(video, t) -> float:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=32:32",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return float(np.frombuffer(raw, np.uint8).mean())


def test_the_flash_forward_cuts_back_through_a_flash_of_white(tmp_path):
    src = tmp_path / "dark.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x202020:s=640x360:r=30:d=20",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
    segs = [(12.0, 13.5), (2.0, 10.0)]                                          # 1.5 s of the peak, then back to the start
    flashed = clip(src, tmp_path / "f.mp4", segments=segs, flash=True)
    plain = clip(src, tmp_path / "p.mp4", segments=segs)
    assert brightness(flashed, 1.47) > 150 and brightness(flashed, 1.53) > 100   # white at the cut, on both sides of it
    assert brightness(flashed, 0.7) < 60 and brightness(flashed, 2.2) < 60       # and only there
    assert brightness(plain, 1.47) < 60                                          # an ordinary cut has no flash
