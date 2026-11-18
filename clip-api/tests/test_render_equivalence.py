"""The same render gives the same clip on every ffmpeg we run: development (Homebrew), CI and production (the
Debian ffmpeg of clip-api/Dockerfile). Checked here: captions show on the frame they are timed for, and the
picture and the sound stay together through cuts. tests/test_render_cfr.py checks the constant 30 fps.

The source is black and silent except for one event at 4.0-4.1 s: a white frame and a 1 kHz beep together."""
import subprocess

import numpy as np
import pytest

from app.pipeline.ff import probe
from app.pipeline.render import OUT_FPS, render_clip

RATE = 48000
EVENT = 4.0


@pytest.fixture(scope="module")
def event(tmp_path_factory):
    out = tmp_path_factory.mktemp("eq") / "event.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=60:d=10",
                    "-f", "lavfi", "-i", f"aevalsrc='if(between(t,{EVENT},{EVENT + 0.1}),0.8*sin(2*PI*1000*t),0)':s={RATE}:d=10",
                    "-vf", f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,{EVENT},{EVENT + 0.099})'",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
                   check=True)
    return out


def luma(video) -> np.ndarray:
    """Mean brightness of every frame, and of the lower half (where the captions are), as rows [whole, lower]."""
    w, h = 36, 64
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(video), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(float)
    return np.stack([frames.mean(axis=(1, 2)), frames[:, h // 2:, :].max(axis=(1, 2))], axis=1)


def beep_at(video) -> float:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(video), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    pcm = np.abs(np.frombuffer(raw, np.int16).astype(float))
    return float(np.argmax(pcm > 0.25 * pcm.max()) / RATE)


def render(src, out, segments, words=()):
    info = probe(src)
    start, end = min(s for s, _ in segments), max(e for _, e in segments)
    render_clip(src, start, end, out, src_w=info.width, src_h=info.height, vertical=True, zoom=1.0, chat="none",
                words=list(words), font="DejaVu Sans", layout="fill", style="impact", segments=segments)


@pytest.mark.parametrize("segments,expected", [
    ([(2.0, 8.0)], EVENT - 2.0),                              # one piece
    ([(1.0, 2.5), (3.0, 6.0)], 1.5 + EVENT - 3.0),            # a dead-air cut before the event
    ([(6.0, 7.0), (2.0, 3.0), (3.5, 6.0)], 1.0 + 1.0 + EVENT - 3.5),   # a tease first, then a cut
])
def test_picture_and_sound_stay_together_through_cuts(event, tmp_path, segments, expected):
    out = tmp_path / "av.mp4"
    render(event, out, segments)
    whole = luma(out)[:, 0]
    seen = float(np.argmax(whole > 128) / OUT_FPS)
    heard = beep_at(out)
    assert seen == pytest.approx(expected, abs=1 / OUT_FPS + 0.002)        # the white frame on its own frame
    assert heard == pytest.approx(expected, abs=0.015)                      # the beep within 15 ms of its time
    assert abs(seen - heard) <= 1 / OUT_FPS + 0.005                         # and together, within one frame


def test_a_caption_shows_on_the_frames_it_is_timed_for(event, tmp_path):
    out = tmp_path / "cap.mp4"
    render(event, out, [(0.5, 3.5)], words=[(1.0, 1.6, "BOOM")])            # ends before the white frame
    lower = luma(out)[:, 1]
    shown = np.flatnonzero(lower > 128)
    assert shown.size, "the caption never showed"
    first, last = shown[0] / OUT_FPS, (shown[-1] + 1) / OUT_FPS
    assert first == pytest.approx(1.0, abs=1 / OUT_FPS + 0.002)            # on the frame it starts
    assert 1.6 - 1 / OUT_FPS <= last <= 2.2                                 # and gone soon after it ends
