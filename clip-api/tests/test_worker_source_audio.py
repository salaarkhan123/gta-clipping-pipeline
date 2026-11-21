"""Clip Maker always one-shot extracts audio and passes it into run_pipeline (research A2 / S3)."""
from pathlib import Path

import pytest

from app import worker
from app.pipeline import ClipResult, PipelineOptions, run_pipeline
from app.pipeline.stt import SourceAudio, extract_audio
from tests.test_api import upload
from tests.test_upload_transcript import Recording, clip_job, finished


def test_clip_maker_passes_source_audio_even_without_whole_mode(client, user, video, monkeypatch):
    """Default Clip Maker (transcribe_whole off) still extracts once and hands the WAV to the pipeline."""
    monkeypatch.setattr(worker.get_settings(), "transcribe_whole", False)
    headers, _ = user
    up = upload(client, headers, video)
    seen: list[SourceAudio] = []
    extracts = {"n": 0}
    real_extract = extract_audio

    def counting_extract(src, dest, deadline=None):
        extracts["n"] += 1
        return real_extract(src, dest, deadline)

    def capturing_pipeline(src, options, out_dir, progress_cb=None, transcriber=None, deadline=None,
                           timer=None, on_clip=None, transcript=None, source_audio=None, **kw):
        assert source_audio is not None and isinstance(source_audio, SourceAudio)
        assert source_audio.path.exists() and source_audio.levels
        seen.append(source_audio)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = out_dir / "clip-1.mp4"
        video_path.write_bytes(b"\x00")
        clip = ClipResult(start=20.0, end=30.0, score=1.0, signals={"audio": 1.0}, features={},
                          video_path=video_path, thumb_path=None, captions_path=None, meta={}, index=1)
        if on_clip:
            on_clip(clip)
        return [clip]

    monkeypatch.setattr(worker, "extract_audio", counting_extract)
    job = clip_job(client, headers, up["upload_id"], max_clips=1, clip_length=10)
    assert worker.run_once(Recording(), pipeline=capturing_pipeline) == "SUCCEEDED"
    assert extracts["n"] == 1 and len(seen) == 1
    finished(client, headers, job)


def test_clip_maker_extracts_once_when_whole_mode_also_runs(client, user, video, monkeypatch):
    """transcribe_whole reuses the same extract; it must not decode the source audio twice."""
    monkeypatch.setattr(worker.get_settings(), "transcribe_whole", True)
    headers, _ = user
    up = upload(client, headers, video)
    extracts = {"n": 0}
    real_extract = extract_audio

    def counting_extract(src, dest, deadline=None):
        extracts["n"] += 1
        return real_extract(src, dest, deadline)

    def capturing_pipeline(src, options, out_dir, progress_cb=None, transcriber=None, deadline=None,
                           timer=None, on_clip=None, transcript=None, source_audio=None, **kw):
        assert source_audio is not None
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = out_dir / "clip-1.mp4"
        video_path.write_bytes(b"\x00")
        clip = ClipResult(start=20.0, end=30.0, score=1.0, signals={"audio": 1.0}, features={},
                          video_path=video_path, thumb_path=None, captions_path=None, meta={}, index=1)
        if on_clip:
            on_clip(clip)
        return [clip]

    monkeypatch.setattr(worker, "extract_audio", counting_extract)
    rough, final = Recording(), Recording()
    rough.model_name, final.model_name = "base.en", "small.en"
    clip_job(client, headers, up["upload_id"], max_clips=1, clip_length=10)
    assert worker.run_once(final, indexer=rough, pipeline=capturing_pipeline) == "SUCCEEDED"
    assert extracts["n"] == 1


def test_pipeline_still_does_not_extract_without_source_audio(video, transcriber, tmp_path, monkeypatch):
    """run_pipeline itself stays extract-free; only the worker supplies source_audio."""
    monkeypatch.setattr("app.pipeline.stt.extract_audio",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("pipeline extracted")))
    clips = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False),
                         tmp_path / "o", transcriber=transcriber)
    assert len(clips) == 1
