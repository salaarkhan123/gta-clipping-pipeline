"""Recoverable per-clip render failures must not wipe the job or already-handed-over clips."""
import subprocess

import pytest

from app.pipeline import PipelineError, PipelineOptions, PipelineTimeout, Timer, run_pipeline
from app.pipeline import render as render_mod


@pytest.fixture(scope="module")
def rising(tmp_path_factory):
    out = tmp_path_factory.mktemp("v") / "rising.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
                    "-af", "volume='if(between(t,10,13),0.5,if(between(t,30,33),0.7,if(between(t,48,51),1.0,0.02)))':eval=frame",
                    "-t", "60", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(out)], check=True)
    return out


OPTS = {"max_clips": 3, "clip_length": 10, "tighten": False, "punch_zoom": False}


def test_one_clip_media_error_is_skipped_and_others_still_render(rising, tmp_path, monkeypatch):
    calls = [0]
    real = render_mod.render_clip

    def flaky(*a, **k):
        calls[0] += 1
        if calls[0] == 1:
            raise PipelineError("media_error", "Could not process this video (Invalid data).")
        return real(*a, **k)

    monkeypatch.setattr(render_mod, "render_clip", flaky)
    monkeypatch.setattr("app.pipeline.render_clip", flaky)
    timer = Timer()
    clips = run_pipeline(rising, PipelineOptions(**OPTS), tmp_path / "o", timer=timer)
    assert len(clips) == 2
    assert timer.as_dict()["counts"].get("render_failed") == 1
    assert all(c.video_path and c.video_path.exists() for c in clips)


def test_all_clip_renders_failing_raises_render_failed(rising, tmp_path, monkeypatch):
    def always_fail(*a, **k):
        raise PipelineError("media_error", "Could not process this video (boom).")

    monkeypatch.setattr(render_mod, "render_clip", always_fail)
    monkeypatch.setattr("app.pipeline.render_clip", always_fail)
    with pytest.raises(PipelineError) as ei:
        run_pipeline(rising, PipelineOptions(**OPTS), tmp_path / "o")
    assert ei.value.code == "render_failed"


def test_job_timeout_during_render_still_propagates(rising, tmp_path, monkeypatch):
    def timed_out(*a, **k):
        raise PipelineTimeout()

    monkeypatch.setattr(render_mod, "render_clip", timed_out)
    monkeypatch.setattr("app.pipeline.render_clip", timed_out)
    with pytest.raises(PipelineTimeout):
        run_pipeline(rising, PipelineOptions(**OPTS), tmp_path / "o")
