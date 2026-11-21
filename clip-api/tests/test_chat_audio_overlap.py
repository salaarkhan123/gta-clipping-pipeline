"""chat_motion and audio_signal overlap when chat_region is set and the source has audio."""
import threading
import time

import pytest

import app.pipeline as pipeline
from app.pipeline import PipelineError, PipelineOptions, Timer, run_pipeline
from app.pipeline.ff import Deadline


def test_chat_and_audio_both_populate_series_and_stages(video, tmp_path):
    timer = Timer()
    clips = run_pipeline(
        video,
        PipelineOptions(max_clips=1, clip_length=10, chat_region="top-right", tighten=False, render="none"),
        tmp_path / "o",
        timer=timer,
    )
    assert clips and "chat_motion" in clips[0].signals and "audio" in clips[0].signals
    stages = timer.as_dict()["stages"]
    assert "chat_motion" in stages and "audio_signal" in stages


def test_chat_region_none_stays_serial_without_chat_stage(video, tmp_path):
    timer = Timer()
    clips = run_pipeline(
        video,
        PipelineOptions(max_clips=1, clip_length=10, chat_region="none", tighten=False, render="none"),
        tmp_path / "o",
        timer=timer,
    )
    assert clips and "audio" in clips[0].signals and "chat_motion" not in clips[0].signals
    stages = timer.as_dict()["stages"]
    assert "audio_signal" in stages and "chat_motion" not in stages


def test_overlap_wall_under_stage_sum_when_both_take_time(video, tmp_path, monkeypatch):
    """Injected sleeps prove the two stages run together: signal wall < chat + audio stage seconds."""
    started, ended = {}, {}
    lock = threading.Lock()

    def slow_chat(*a, **k):
        with lock:
            started["chat"] = time.monotonic()
        time.sleep(0.25)
        with lock:
            ended["chat"] = time.monotonic()
        vals = [0.0] * 40
        vals[20:24] = [10.0, 10.0, 10.0, 10.0]
        return vals

    def slow_audio(*a, **k):
        with lock:
            started["audio"] = time.monotonic()
        time.sleep(0.25)
        with lock:
            ended["audio"] = time.monotonic()
        levels = [-40.0] * 40
        levels[20:24] = [-10.0, -10.0, -10.0, -10.0]
        peak = [0.0] * 40
        peak[20] = 5.0
        return (levels, {"audio_flux": peak, "audio_bursts": peak})

    monkeypatch.setattr(pipeline, "onscreen_chat_motion", slow_chat)
    monkeypatch.setattr(pipeline, "audio_timeline", slow_audio)

    timer = Timer()
    clips = run_pipeline(
        video,
        PipelineOptions(max_clips=1, clip_length=10, chat_region="top-right", tighten=False, render="none"),
        tmp_path / "o",
        timer=timer,
    )
    stages = timer.as_dict()["stages"]
    chat_s, audio_s = stages["chat_motion"], stages["audio_signal"]
    signal_wall = max(ended.values()) - min(started.values())
    assert clips and "chat_motion" in clips[0].signals and "audio" in clips[0].signals
    assert abs(started["chat"] - started["audio"]) < 0.15
    assert chat_s >= 0.2 and audio_s >= 0.2
    assert signal_wall < chat_s + audio_s - 0.1
    assert signal_wall < 0.4


def test_pipeline_error_from_chat_propagates_and_expires_deadline(video, tmp_path, monkeypatch):
    seen = {"audio_entered": False}

    def boom(*a, **k):
        time.sleep(0.05)
        raise PipelineError("media_error", "chat broke")

    def slow_audio(path, deadline=None, **k):
        seen["audio_entered"] = True
        # Peer expiry sets deadline.at; poll so this thread stops instead of sleeping out the pool.
        for _ in range(40):
            if deadline is not None:
                deadline.remaining()
            time.sleep(0.05)
        return ([-20.0] * 40, {"audio_flux": [0.0] * 40, "audio_bursts": [0.0] * 40})

    monkeypatch.setattr(pipeline, "onscreen_chat_motion", boom)
    monkeypatch.setattr(pipeline, "audio_timeline", slow_audio)

    deadline = Deadline(30.0)
    t0 = time.monotonic()
    with pytest.raises(PipelineError) as ei:
        run_pipeline(
            video,
            PipelineOptions(max_clips=1, clip_length=10, chat_region="top-right", tighten=False, render="none"),
            tmp_path / "o",
            deadline=deadline,
        )
    elapsed = time.monotonic() - t0
    assert ei.value.code == "media_error" and "chat broke" in ei.value.message
    assert deadline.at is not None and deadline.at <= time.monotonic() + 0.01
    assert elapsed < 1.5
    assert seen["audio_entered"]


def test_pipeline_error_from_audio_propagates(video, tmp_path, monkeypatch):
    def ok_chat(*a, **k):
        time.sleep(0.05)
        vals = [0.0] * 40
        vals[20:24] = [10.0, 10.0, 10.0, 10.0]
        return vals

    def boom(*a, **k):
        raise PipelineError("media_error", "audio broke")

    monkeypatch.setattr(pipeline, "onscreen_chat_motion", ok_chat)
    monkeypatch.setattr(pipeline, "audio_timeline", boom)
    monkeypatch.setattr(pipeline, "audio_rms_db", boom)

    with pytest.raises(PipelineError) as ei:
        run_pipeline(
            video,
            PipelineOptions(max_clips=1, clip_length=10, chat_region="top-right",
                            tighten=False, render="none", weights={"audio_flux": 0, "audio_bursts": 0}),
            tmp_path / "o",
        )
    assert ei.value.code == "media_error" and "audio broke" in ei.value.message
