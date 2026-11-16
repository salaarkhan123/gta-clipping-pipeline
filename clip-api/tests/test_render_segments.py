"""Rendering a clip from several source segments, and the punch-in zoom on the gameplay picture."""
import subprocess

import numpy as np
import pytest

from app.pipeline.ff import probe
from app.pipeline.render import layout_filter, punch_in, render_clip


@pytest.fixture(scope="module")
def coded(tmp_path_factory):
    """30 s where the picture tells the time: red for 0-10 s, green for 10-20 s, blue for 20-30 s. Tone throughout."""
    out = tmp_path_factory.mktemp("seg") / "coded.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=10", "-f", "lavfi", "-i", "color=c=green:s=640x360:r=30:d=10",
                    "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=30:d=10", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
                    "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


def colour_at(video, t) -> str:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-i", str(video), "-frames:v", "1",
                          "-vf", "scale=16:16", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    r, g, b = np.frombuffer(raw, np.uint8).reshape(-1, 3).mean(axis=0)
    return "red" if r > 150 and g < 90 else "green" if g > 90 and r < 90 and b < 90 else "blue" if b > 150 else "?"


def render(src, out, **kw):
    info = probe(src)
    render_clip(src, kw.pop("start", 0), kw.pop("end", 30), out, src_w=info.width, src_h=info.height, zoom=1.0, chat="none",
                words=kw.pop("words", []), font="DejaVu Sans", **kw)
    return probe(out)


def test_segments_play_back_to_back_in_the_order_given(coded, tmp_path):
    # Flash-forward of blue (24-25.5), then red 2-6, a cut, green 12-16.
    segs = [(24.0, 25.5), (2.0, 6.0), (12.0, 16.0)]
    info = render(coded, tmp_path / "v.mp4", vertical=True, layout="fill", segments=segs)
    assert info.duration == pytest.approx(9.5, abs=0.15) and (info.width, info.height) == (1080, 1920) and info.has_audio
    assert [colour_at(tmp_path / "v.mp4", t) for t in (0.7, 2.5, 5.0, 6.2, 9.0)] == ["blue", "red", "red", "green", "green"]


def test_segments_work_without_reframing_and_without_audio(coded, tmp_path):
    info = render(coded, tmp_path / "h.mp4", vertical=False, segments=[(8.0, 9.0), (21.0, 23.0)])
    assert info.duration == pytest.approx(3.0, abs=0.15) and (info.width, info.height) == (640, 360)
    assert [colour_at(tmp_path / "h.mp4", t) for t in (0.5, 2.0)] == ["red", "blue"]
    silent = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(coded), "-an", "-c:v", "copy", str(silent)], check=True)
    info = render(silent, tmp_path / "s.mp4", vertical=True, layout="fill", segments=[(1.0, 3.0), (25.0, 27.0)], has_audio=False)
    assert info.duration == pytest.approx(4.0, abs=0.15) and not info.has_audio


def test_one_whole_segment_renders_exactly_as_before(coded, tmp_path):
    a = render(coded, tmp_path / "a.mp4", start=5, end=9, vertical=True, layout="fill")
    b = render(coded, tmp_path / "b.mp4", start=5, end=9, vertical=True, layout="fill", segments=[(5, 9)])
    assert a.duration == pytest.approx(b.duration, abs=0.05) and (tmp_path / "a.mp4").stat().st_size == (tmp_path / "b.mp4").stat().st_size


def test_punch_in_zooms_the_gameplay_and_only_around_the_peak(tmp_path):
    src = tmp_path / "dot.mp4"       # black, with a white square in the middle: zooming makes the square bigger
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=8",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-vf", "drawbox=x=270:y=130:w=100:h=100:color=white:t=fill",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
    from app.pipeline.edit import zoom_expr
    render(src, tmp_path / "z.mp4", end=8, vertical=True, layout="fill", punch=zoom_expr([4.0]))

    def white(t):
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-i", str(tmp_path / "z.mp4"), "-frames:v", "1",
                              "-vf", "scale=270:480", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
        return int((np.frombuffer(raw, np.uint8) > 128).sum())
    rest, peak, after = white(1.0), white(4.2), white(6.5)
    assert peak / rest == pytest.approx(1.15 ** 2, rel=0.06)          # 1.15x in each direction at the peak
    assert after == pytest.approx(rest, rel=0.02)                     # and back to normal afterwards
    assert probe(tmp_path / "z.mp4").width == 1080                    # the frame size never changes


def test_punch_in_is_absent_when_off_and_only_on_the_gameplay_panel():
    assert punch_in(1080, 1280, "1") == ""
    split = layout_filter(1920, 1080, "split", 1.0, "none", "top-right", punch="1+0.150*min(1,max(0,1-abs(t-4.20)/0.6))")
    top, bottom = split.split("[top];")
    assert "eval=frame" not in top and "eval=frame" in bottom         # the camera panel is never zoomed
    assert "eval=frame" not in layout_filter(1920, 1080, "split", 1.0, "none", "top-right")
