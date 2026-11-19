"""S3: the audio is decoded once, pieces are cut from it without ffmpeg, and a provider transcribes whole files."""
import threading
import wave

import numpy as np
import pytest
from pydantic import ValidationError

import app.pipeline as pipeline
from app import worker
from app.config import Settings
from app.pipeline import PipelineError, PipelineOptions, PipelineTimeout, Timer, run_pipeline
from app.pipeline.ff import Deadline, probe
from app.pipeline.signals import audio_rms_db
from app.pipeline.stt import LocalProvider, chunk_bounds, extract_audio, provider_for, slice_wav, wav_duration, window
from app.pipeline.transcribe import Transcript
from tests.test_api import upload
from tests.test_launch import FakeAI, three_bursts  # noqa: F401
from tests.test_punchier_clips import Talker


def tone(path, seconds, quiet=(), rate=16000):
    """A WAV of noise at talking level with one-second quiet spots at the given seconds."""
    rng = np.random.default_rng(1)
    x = (rng.normal(0, 3000, int(seconds * rate))).astype(np.int16)
    for q in quiet:
        x[int(q * rate):int((q + 1) * rate)] //= 100
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(x.tobytes())
    return path


def test_one_decode_gives_the_wav_and_the_same_levels_as_before(video, tmp_path):
    got = extract_audio(video, tmp_path / "a.wav")
    levels = got.levels
    assert got.path == tmp_path / "a.wav"
    with wave.open(str(tmp_path / "a.wav"), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
    assert wav_duration(tmp_path / "a.wav") == pytest.approx(probe(video).duration, abs=0.2)
    old = audio_rms_db(video)
    assert len(levels) == len(old) and max(abs(a - b) for a, b in zip(levels, old)) < 0.01     # the same measurement
    assert max(levels[20:24]) > max(levels[5:15]) + 20                                        # the loud burst at 20-24 s


def test_slices_are_cut_from_the_file_exactly_and_clipped_at_the_end(tmp_path):
    src = tone(tmp_path / "s.wav", 10)
    assert slice_wav(src, 2.0, 3.0, tmp_path / "p.wav") == 3.0
    with wave.open(str(src), "rb") as a, wave.open(str(tmp_path / "p.wav"), "rb") as b:
        a.setpos(2 * 16000)
        assert b.readframes(b.getnframes()) == a.readframes(3 * 16000)
    assert slice_wav(src, 8.5, 5.0, tmp_path / "e.wav") == 1.5 and wav_duration(tmp_path / "e.wav") == 1.5
    assert slice_wav(src, 99.0, 5.0, tmp_path / "n.wav") == 0.0


def test_chunks_are_cut_at_quiet_seconds_cover_the_file_and_leave_no_sliver(tmp_path):
    bounds = chunk_bounds(tone(tmp_path / "long.wav", 700, quiet=(292, 588)), chunk_sec=300)
    assert bounds == [(0.0, 292.5), (292.5, 588.5), (588.5, 700.0)]                # each cut in the quiet second near 300 and 592
    assert chunk_bounds(tone(tmp_path / "short.wav", 360), chunk_sec=300) == [(0.0, 360.0)]
    two = chunk_bounds(tone(tmp_path / "two.wav", 620), chunk_sec=300)
    assert len(two) == 2 and two[0][0] == 0.0 and two[-1][1] == 620.0 and two[1][1] - two[1][0] > 300   # no 20 s tail chunk
    assert all(a[1] == b[0] for a, b in zip(bounds, bounds[1:]))


class Counting:
    """Says one word a second into every piece it is given, and remembers what it was asked."""
    def __init__(self):
        self.pieces, self.threads, self.lock = [], set(), threading.Lock()

    def transcribe(self, wav) -> Transcript:
        with self.lock:
            self.pieces.append(wav_duration(wav))
            self.threads.add(threading.current_thread().name)
        return Transcript(words=[(1.0, 1.4, "word")], segments=[(1.0, 1.4, "word")])


def test_local_provider_transcribes_every_chunk_once_with_absolute_times_in_order(tmp_path):
    wav, t, progress = tone(tmp_path / "long.wav", 700, quiet=(292, 588)), Counting(), []
    out = LocalProvider(t, chunk_sec=300, parallel=3).transcribe_file(wav, tmp_path, on_progress=lambda k, n: progress.append((k, n)))
    assert [w[0] for w in out.words] == [1.0, 293.5, 589.5] and [s[2] for s in out.segments] == ["word"] * 3
    assert sum(t.pieces) == pytest.approx(700.0, abs=0.01) and len(t.pieces) == 3      # the whole file, nothing twice
    assert sorted(progress) == [(1, 3), (2, 3), (3, 3)] and len(t.threads) >= 2         # really in parallel
    assert not list(tmp_path.glob("stt*.wav"))                                          # the pieces are cleaned up
    one = Counting()
    LocalProvider(one, chunk_sec=300).transcribe_file(wav, tmp_path)
    assert len(one.threads) == 1                                                        # the default: one at a time


def test_provider_stops_at_the_deadline_and_unknown_providers_are_refused(tmp_path):
    wav = tone(tmp_path / "long.wav", 700)
    gone = Deadline(0.001)
    import time
    time.sleep(0.01)
    with pytest.raises(PipelineTimeout):
        LocalProvider(Counting(), chunk_sec=300).transcribe_file(wav, tmp_path, deadline=gone)
    with pytest.raises(PipelineError, match="'whisperx' is not available"):
        provider_for("whisperx", Counting())
    assert provider_for("local", None) is None and isinstance(provider_for("local", Counting(), 120, 2), LocalProvider)
    for bad in (0, 9):
        with pytest.raises(ValidationError):
            Settings(transcribe_parallel=bad)
    assert Settings.model_fields["transcription_provider"].default == "local" and Settings.model_fields["transcribe_parallel"].default == 1


def test_window_reads_a_candidate_out_of_a_whole_transcript():
    full = Transcript(words=[(5.0, 5.4, "a"), (12.0, 12.4, "b"), (30.0, 30.4, "c")], segments=[(5.0, 5.4, "a"), (12.0, 30.4, "b c")])
    t, offset = window(full, 10.0, 25.0)
    assert offset == 10.0 and t.words == [(2.0, pytest.approx(2.4), "b")] and t.segments == [(2.0, pytest.approx(20.4), "b c")]


def test_given_the_audio_the_pipeline_reads_everything_from_it(video, transcriber, tmp_path, monkeypatch):
    audio = extract_audio(video, tmp_path / "a.wav")

    def no_ffmpeg(*a, **k):
        raise AssertionError("the source was decoded again")
    monkeypatch.setattr(pipeline, "extract_wav", no_ffmpeg)
    monkeypatch.setattr(pipeline, "audio_rms_db", no_ffmpeg)
    clips = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False), tmp_path / "o", transcriber=transcriber,
                         source_audio=audio)
    assert len(clips) == 1 and 10 <= clips[0].start <= 24 and clips[0].captions_path.exists()
    assert (tmp_path / "a.wav").exists()                                    # the caller's file: the pipeline leaves it alone


def test_by_default_nothing_is_extracted_up_front_and_the_result_is_the_same(video, transcriber, tmp_path, monkeypatch):
    opts = PipelineOptions(max_clips=1, clip_length=10, tighten=False)
    with_audio = run_pipeline(video, opts, tmp_path / "a", transcriber=transcriber, source_audio=extract_audio(video, tmp_path / "a.wav"))
    monkeypatch.setattr("app.pipeline.stt.extract_audio", lambda *a, **k: (_ for _ in ()).throw(AssertionError("extracted by default")))
    plain = run_pipeline(video, opts, tmp_path / "p", transcriber=transcriber)
    assert (plain[0].start, plain[0].end, plain[0].score) == (with_audio[0].start, with_audio[0].end, with_audio[0].score)
    assert not list((tmp_path / "p").glob("*.wav"))                         # no 230 MB file for a 2 h video


def full_talk(duration=60):
    t = Transcript()
    for k in range(0, duration, 2):
        t.words += [(float(k), k + 0.4, "full"), (k + 0.4, k + 0.9, "text")]
        t.segments.append((float(k), k + 0.9, "full text"))
    return t


def test_an_existing_transcript_replaces_the_rough_pass_and_captions_still_use_the_caption_model(three_bursts, tmp_path):  # noqa: F811
    rough, final, heard, timer = Counting(), Talker(), [], Timer()

    def judge(text, frame, ctx):
        heard.append(text)
        return {"title": "t", "virality": {"score": 80}}
    clips = run_pipeline(three_bursts, PipelineOptions(max_clips=1, clip_length=20, tighten=False), tmp_path / "o", transcriber=final,
                         judge=judge, fast_transcriber=rough, transcript=full_talk(), timer=timer)
    d = timer.as_dict()
    assert rough.pieces == [] and "transcribe_rough" not in d["stages"]                  # the fast model never ran
    assert d["counts"]["transcript_reused"] == d["counts"]["candidates"] >= 1
    assert heard and all("full text" in h for h in heard)                                # the judge read the stored transcript
    assert "transcribe_final" in d["stages"]
    import json
    words = {w["text"] for w in json.loads(clips[0].captions_path.read_text())["words"]}
    assert words == {"oh", "no"}                                                         # captions: the caption model's words


def test_without_a_second_pass_the_transcript_is_not_used_for_captions(three_bursts, tmp_path):  # noqa: F811
    final, timer = Talker(), Timer()
    run_pipeline(three_bursts, PipelineOptions(max_clips=1, clip_length=20, tighten=False), tmp_path / "o", transcriber=final,
                 transcript=full_talk(), timer=timer)
    assert "transcript_reused" not in timer.as_dict()["counts"] and "transcribe_rough" in timer.as_dict()["stages"]


def test_a_clip_job_reuses_the_transcript_video_finder_stored(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    index = Counting()
    client.post("/v1/find", json={"upload_id": up["upload_id"], "query": "word", "make_clips": False}, headers=headers)
    assert worker.run_once(transcriber, indexer=index) == "SUCCEEDED"
    made = len(index.pieces)
    assert made >= 1 and sum(index.pieces) == pytest.approx(40, abs=0.5)                 # the whole video, once
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                         headers=headers).json()["job_id"]
    assert worker.run_once(transcriber, indexer=index, ai=FakeAI()) == "SUCCEEDED"
    result = client.get(f"/v1/jobs/{job_id}", headers=headers).json()["result"]
    assert len(index.pieces) == made                                                     # the fast model was not run again
    assert result["counts"]["transcript_reused"] >= 1 and "transcribe_rough" not in result["stages"]
