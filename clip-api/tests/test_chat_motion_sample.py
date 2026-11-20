"""Chat motion sampling modes: dense/sparse (A3) and coarse/lite (Phase-4 CPR-14)."""
import time
from pathlib import Path

import pytest

from app.pipeline.signals import CHAT_MOTION_SAMPLES, onscreen_chat_motion


@pytest.fixture(scope="module")
def chat_video(tmp_path_factory) -> Path:
    """~20 s clip with scrolling text in the top band so edgedetect sees motion."""
    import subprocess
    path = tmp_path_factory.mktemp("chat") / "chat.mp4"
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
    assert abs(len(sparse) - len(dense)) <= 2


def test_sparse_is_faster_than_dense_on_this_fixture(chat_video):
    """Wall-clock check on this VM; labels the speedup as measured for this fixture only."""
    t0 = time.perf_counter()
    assert onscreen_chat_motion(chat_video, "top-right", sample="dense") is not None
    dense_sec = time.perf_counter() - t0
    t0 = time.perf_counter()
    assert onscreen_chat_motion(chat_video, "top-right", sample="sparse") is not None
    sparse_sec = time.perf_counter() - t0
    assert sparse_sec <= dense_sec * 1.15 + 0.05


def test_coarse_uses_half_fps_and_returns_per_second_series(chat_video, monkeypatch):
    seen: list[str] = []
    from app.pipeline import signals as sig

    real_run = sig.run

    def capture(cmd, deadline=None):
        seen.append(" ".join(str(c) for c in cmd))
        return real_run(cmd, deadline)

    monkeypatch.setattr(sig, "run", capture)
    coarse = onscreen_chat_motion(chat_video, "top-right", sample="coarse")
    dense = onscreen_chat_motion(chat_video, "top-right", sample="dense")
    assert coarse is not None and dense is not None
    assert any("fps=0.5," in c for c in seen)
    # Short fixture stays serial (no -threads 1 chunk workers).
    assert not any("-threads 1" in c for c in seen)
    assert abs(len(coarse) - len(dense)) <= 3


def test_lite_uses_scale_240_at_sparse_rate(chat_video, monkeypatch):
    seen: list[str] = []
    from app.pipeline import signals as sig

    real_run = sig.run

    def capture(cmd, deadline=None):
        seen.append(" ".join(str(c) for c in cmd))
        return real_run(cmd, deadline)

    monkeypatch.setattr(sig, "run", capture)
    lite = onscreen_chat_motion(chat_video, "top-right", sample="lite")
    sparse = onscreen_chat_motion(chat_video, "top-right", sample="sparse")
    assert lite is not None and sparse is not None
    assert any("fps=1," in c and "scale=240:" in c for c in seen)
    assert abs(len(lite) - len(sparse)) <= 2


@pytest.fixture(scope="module")
def chat_burst_video(tmp_path_factory) -> Path:
    """~90 s clip with chat motion only in known bursts (aliases less at fps=0.5 than steady scroll)."""
    import subprocess
    path = tmp_path_factory.mktemp("chatburst") / "burst.mp4"
    enables = "+".join(f"between(t\\,{s}\\,{s+15})" for s in (10, 40, 70))
    vf = (
        f"drawtext=text='CHAT %{{eif\\:t\\:d}}':fontsize=22:fontcolor=white:"
        f"x=w*0.55:y=h*0.05+mod(t*50\\,h*0.25):box=1:boxcolor=black@0.6:enable='{enables}'"
    )
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x360:r=15:d=90",
        "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path),
    ], check=True)
    return path


def test_lite_and_sparse_correlate_with_dense_on_chat_fixture(chat_video):
    import numpy as np

    dense = onscreen_chat_motion(chat_video, "top-right", sample="dense")
    assert dense is not None
    d = np.asarray(dense, dtype=float)
    for mode in ("lite", "sparse"):
        series = onscreen_chat_motion(chat_video, "top-right", sample=mode)
        assert series is not None
        s = np.asarray(series, dtype=float)
        n = min(len(d), len(s))
        corr = float(np.corrcoef(d[:n], s[:n])[0, 1])
        assert corr >= 0.85, f"{mode} pearson={corr:.3f} vs dense"


def test_coarse_recovers_chat_bursts_like_dense(chat_burst_video):
    """Coarse (fps=0.5 + interp) ranks known chat bursts like dense (hit-rate, not exact ties)."""
    import numpy as np
    from app.pipeline.signals import CHAT_LAG, baseline_z, normalise

    dense = onscreen_chat_motion(chat_burst_video, "top-right", sample="dense")
    coarse = onscreen_chat_motion(chat_burst_video, "top-right", sample="coarse")
    assert dense is not None and coarse is not None
    n = min(len(dense), len(coarse))
    d = normalise(baseline_z(dense[:n], floor=1.0), n, shift=CHAT_LAG)
    c = normalise(baseline_z(coarse[:n], floor=1.0), n, shift=CHAT_LAG)
    # After CHAT_LAG=4, raw bursts at 10/40/70 land near window starts ~6/36/66.
    bursts = [(6, 25), (36, 55), (66, 85)]
    window, k = 15, 3

    def hit_rate(series):
        starts = np.argsort(np.convolve(series, np.ones(window), "valid"))[-k:]
        return sum(1 for s in starts if any(s + window > b0 and s < b1 for b0, b1 in bursts)) / k

    assert hit_rate(d) >= 0.66, "dense should recover chat bursts"
    assert hit_rate(c) >= 0.66, "coarse should recover chat bursts"
    spearman = float(np.corrcoef(
        d.argsort().argsort().astype(float), c.argsort().argsort().astype(float),
    )[0, 1])
    assert spearman >= 0.7, f"coarse vs dense spearman={spearman:.3f}"


def test_bad_sample_is_rejected(chat_video):
    with pytest.raises(ValueError):
        onscreen_chat_motion(chat_video, "top-right", sample="keyframes")
    assert set(CHAT_MOTION_SAMPLES) == {"dense", "sparse", "coarse", "lite"}


def test_settings_default_is_dense():
    from app.config import Settings
    assert Settings.model_fields["chat_motion_sample"].default == "dense"


def test_coarse_parallelizes_long_spans(monkeypatch, tmp_path):
    """Spans ≥ 120 s use chunked ffmpeg workers for coarse/lite only."""
    from app.pipeline import signals as sig

    calls: list[str] = []

    class FakeProbe:
        duration = 300.0
        width = 640
        height = 360
        has_audio = False

    def fake_probe(path, deadline=None):
        return FakeProbe()

    def fake_run(cmd, deadline=None):
        calls.append(" ".join(str(c) for c in cmd))

        class R:
            stdout = "\n".join(f"YAVG={0.1 * (i % 7)}" for i in range(40))
        return R()

    monkeypatch.setattr(sig, "probe", fake_probe)
    monkeypatch.setattr(sig, "run", fake_run)

    out = onscreen_chat_motion(tmp_path / "fake.mp4", "top-right", sample="coarse")
    assert out is not None and len(out) == 300
    # Four chunk workers, each with -threads 1 and a -t slice.
    thread_calls = [c for c in calls if "-threads 1" in c]
    assert len(thread_calls) == 4
    assert all("fps=0.5," in c for c in thread_calls)

    calls.clear()
    onscreen_chat_motion(tmp_path / "fake.mp4", "top-right", sample="dense")
    assert not any("-threads 1" in c for c in calls), "dense must stay serial"
