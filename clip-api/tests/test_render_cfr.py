"""Every render path writes constant 30 fps: the same number of frames for the same length, evenly spaced, with
the sound kept in step across cuts. ffmpeg 7.1 (the production image) times the frames after a concat unevenly
unless the output is made constant; ffmpeg 6.1 did not, so r_frame_rate alone hid it."""
import json
import subprocess

import pytest

from app.pipeline.ff import probe
from app.pipeline.render import OUT_FPS, render_clip


@pytest.fixture(scope="module")
def src60(tmp_path_factory):
    """20 s at 60 fps with a tone: a source that has to be brought down to 30 fps."""
    out = tmp_path_factory.mktemp("cfr") / "src60.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=60:duration=20",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


def frame_times(video) -> list[float]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout
    return sorted(float(p["pts_time"]) for p in json.loads(out)["packets"])


def stream(video, kind: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", f"{kind}:0", "-show_entries",
                          "stream=r_frame_rate,avg_frame_rate,duration", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def assert_cfr(video, seconds: float, audio: bool = True) -> None:
    times = frame_times(video)
    steps = [b - a for a, b in zip(times, times[1:])]
    assert len(times) == pytest.approx(seconds * OUT_FPS, abs=2)                  # 30 frames for every second
    assert max(abs(d - 1 / OUT_FPS) for d in steps) < 0.002                       # and evenly spaced
    v = stream(video, "v")
    assert v["r_frame_rate"] == v["avg_frame_rate"] == f"{OUT_FPS}/1"
    assert float(v["duration"]) == pytest.approx(seconds, abs=0.1)
    if audio:
        assert float(stream(video, "a")["duration"]) == pytest.approx(float(v["duration"]), abs=0.1)   # in step


CUTS = [(12.0, 13.5), (2.0, 5.2), (6.0, 9.4)]       # a flash-forward, then the moment with a dead-air cut


@pytest.mark.parametrize("vertical,segments,seconds", [
    (True, CUTS, 8.1),               # the dead-air path (segments_graph): reframed
    (False, CUTS, 8.1),              # ... and in the source's own frame
    (True, None, 6.0),               # one piece: reframed
    (False, None, 6.0),              # ... and in the source's own frame
])
def test_every_render_path_is_constant_30_fps(src60, tmp_path, vertical, segments, seconds):
    info = probe(src60)
    out = tmp_path / "c.mp4"
    render_clip(src60, 2.0, 8.0, out, src_w=info.width, src_h=info.height, vertical=vertical, zoom=1.0, chat="none",
                words=[(0.2, 0.6, "hello"), (0.7, 1.2, "world")], font="DejaVu Sans", layout="fill", segments=segments)
    assert_cfr(out, seconds)


def test_a_preview_with_cuts_is_constant_30_fps(src60, tmp_path):
    info = probe(src60)
    out = tmp_path / "p.mp4"
    render_clip(src60, 2.0, 9.4, out, src_w=info.width, src_h=info.height, vertical=True, zoom=1.0, chat="none",
                words=[], font="DejaVu Sans", layout="fill", segments=CUTS, preview=True, resolution="1080", flash=True)
    assert_cfr(out, 8.1)


def test_a_silent_source_with_cuts_is_constant_30_fps(src60, tmp_path):
    silent = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src60), "-an", "-c:v", "copy", str(silent)], check=True)
    info = probe(silent)
    out = tmp_path / "s.mp4"
    render_clip(silent, 2.0, 9.4, out, src_w=info.width, src_h=info.height, vertical=True, zoom=1.0, chat="none",
                words=[], font="DejaVu Sans", layout="fill", segments=CUTS, has_audio=False)
    assert_cfr(out, 8.1, audio=False)
