"""Sparse vs dense on-screen chat motion sampling (research A3)."""
import time
from pathlib import Path

import pytest

from app.pipeline.signals import CHAT_MOTION_SAMPLES, onscreen_chat_motion


@pytest.fixture(scope="module")
def chat_video(tmp_path_factory) -> Path:
    """~20 s clip with scrolling text in the top band so edgedetect sees motion."""
    import subprocess
    path = tmp_path_factory.mktemp("chat") / "chat.mp4"
    # drawtext scrolls; top third of the frame is where chat_region top-* crops.
    vf = ("drawtext=text='chat line %{eif\\:t\\:d}':fontsize=24:fontcolor=white:x=10:"
          "y=h*0.05+mod(t*40\\,80):box=1:boxcolor=black@0.5")
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x360:r=15:d=20",
        "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path),
    ], check=True)
    return path


def test_dense_is_the_historical_default_and_returns_one_value_per_second(chat_video):
    dense = onscreen_chat_motion(chat_video, "top-right")
    assert dense is not None and 15 <= len(dense) <= 25
    assert onscreen_chat_motion(chat_video, "top-right", sample="dense") == dense


def test_sparse_returns_per_second_series_with_fewer_decoded_frames(chat_video, monkeypatch):
    """Sparse uses fps=1; the ffmpeg filter string must request fps=1, not fps=2."""
    seen: list[str] = []
    from app.pipeline import signals as sig

    real_run = sig.run

    def capture(cmd, deadline=None):
        seen.append(" ".join(str(c) for c in cmd))
        return real_run(cmd, deadline)

    monkeypatch.setattr(sig, "run", capture)
    sparse = onscreen_chat_motion(chat_video, "top-right", sample="sparse")
    dense = onscreen_chat_motion(chat_video, "top-right", sample="dense")
    assert sparse is not None and dense is not None
    assert any("fps=1," in c for c in seen)
    assert any("fps=2," in c for c in seen)
    # Same approximate length (one value per second of content).
    assert abs(len(sparse) - len(dense)) <= 2


def test_sparse_is_faster_than_dense_on_this_fixture(chat_video):
    """Wall-clock check on this VM; labels the speedup as measured for this fixture only."""
    t0 = time.perf_counter()
    assert onscreen_chat_motion(chat_video, "top-right", sample="dense") is not None
    dense_sec = time.perf_counter() - t0
    t0 = time.perf_counter()
    assert onscreen_chat_motion(chat_video, "top-right", sample="sparse") is not None
    sparse_sec = time.perf_counter() - t0
    # Sparse should not be slower; allow equal on tiny fixtures / cold cache.
    assert sparse_sec <= dense_sec * 1.15 + 0.05


def test_bad_sample_is_rejected(chat_video):
    with pytest.raises(ValueError):
        onscreen_chat_motion(chat_video, "top-right", sample="keyframes")
    assert "dense" in CHAT_MOTION_SAMPLES and "sparse" in CHAT_MOTION_SAMPLES


def test_settings_default_is_dense():
    from app.config import Settings
    assert Settings.model_fields["chat_motion_sample"].default == "dense"
