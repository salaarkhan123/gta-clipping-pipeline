"""Wave B1: parallel clip encodes behind RENDER_WORKERS / PipelineOptions.render_workers."""
import threading
import time
from pathlib import Path

from app import worker
from app.config import get_settings
from app.db import new_session
from app.models import Job
from app.pipeline import ClipResult, PipelineOptions, Timer, run_pipeline
from app.pipeline.render import render_clip
from tests.test_progressive import OPTS, rising  # noqa: F401 — fixture
from tests.test_api import upload
from tests.test_upload_transcript import Recording, clip_job, finished


def test_default_render_workers_is_serial_best_first(rising, tmp_path):
    """workers=1 (default) keeps the historical score-ordered on_clip hand-off."""
    seen, timer = [], Timer()

    def on_clip(r):
        seen.append((r.index, r.start))

    clips = run_pipeline(rising, PipelineOptions(**OPTS), tmp_path / "o", timer=timer, on_clip=on_clip)
    assert [r.index for r in clips] == [1, 2, 3]
    by_score = [r.index for r in sorted(clips, key=lambda r: -r.score)]
    assert [i for i, _ in seen] == by_score
    assert 0 < timer.as_dict()["counts"]["first_clip_sec"]


def test_parallel_render_returns_video_order_and_hands_every_clip(rising, tmp_path):
    """workers>1 may finish out of score order; return value stays index order and every clip is handed over."""
    seen, timer = [], Timer()

    def on_clip(r):
        assert r.video_path is None or r.video_path.exists()
        seen.append(r.index)

    clips = run_pipeline(rising, PipelineOptions(**OPTS, render_workers=3), tmp_path / "p",
                         timer=timer, on_clip=on_clip)
    assert [r.index for r in clips] == [1, 2, 3]
    assert sorted(seen) == [1, 2, 3]
    assert timer.as_dict()["counts"]["clips"] == 3
    assert 0 < timer.as_dict()["counts"]["first_clip_sec"]


def test_parallel_render_overlaps_encode_calls(rising, tmp_path, monkeypatch):
    """With render_workers>1, more than one render_clip is in flight at once."""
    active, peak, lock = 0, 0, threading.Lock()
    real = render_clip

    def slow_render(*a, **k):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.2)
            return real(*a, **k)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr("app.pipeline.render_clip", slow_render)
    run_pipeline(rising, PipelineOptions(**OPTS, render_workers=3, render="preview"), tmp_path / "q")
    assert peak >= 2, f"expected overlapping encodes, peak concurrency was {peak}"


def test_worker_applies_settings_render_workers_not_client_options(client, user, video, monkeypatch):
    """RENDER_WORKERS from Settings wins; a job body cannot raise encode concurrency."""
    monkeypatch.setattr(get_settings(), "render_workers", 2)
    headers, _ = user
    up = upload(client, headers, video)
    seen = {}

    def capturing_pipeline(src, options, out_dir, progress_cb=None, transcriber=None, deadline=None,
                           timer=None, on_clip=None, transcript=None, source_audio=None, **kw):
        seen["workers"] = options.render_workers
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = out_dir / "clip-1.mp4"
        video_path.write_bytes(b"\x00")
        clip = ClipResult(start=20.0, end=30.0, score=1.0, signals={"audio": 1.0}, features={},
                          video_path=video_path, thumb_path=None, captions_path=None, meta={}, index=1)
        if on_clip:
            on_clip(clip)
        return [clip]

    job_id = clip_job(client, headers, up["upload_id"], max_clips=1, clip_length=10)
    # Even if a client stuffed render_workers into stored options, the worker overwrites from Settings.
    with new_session() as db:
        j = db.get(Job, job_id)
        j.options = {**(j.options or {}), "render_workers": 8}
        db.commit()
    assert worker.run_once(Recording(), pipeline=capturing_pipeline) == "SUCCEEDED"
    assert seen["workers"] == 2
    finished(client, headers, job_id)
