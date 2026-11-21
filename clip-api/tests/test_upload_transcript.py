"""U1: one transcript per upload. Every job on an upload reads what earlier jobs transcribed and adds what it
transcribes, so nothing is transcribed twice; words carry their times; speakers appear only when the provider
identified them."""
import json

import pytest

from app import worker
from app.config import get_settings
from app.pipeline import PipelineError, PipelineOptions, Timer, run_pipeline
from app.pipeline.heard import Heard, doc_of, model_of
from app.pipeline.stt import wav_duration
from app.pipeline.transcribe import FasterWhisperTranscriber, Transcript
from app.storage import get_storage, transcript_key, transcript_parts_key
from tests.test_api import balance, upload
from tests.test_launch import FakeAI, three_bursts  # noqa: F401
from tests.test_punchier_clips import Talker


class Recording(Talker):
    """Talker that remembers how many seconds it was asked to transcribe."""
    def __init__(self):
        self.seconds: list[float] = []

    def transcribe(self, wav) -> Transcript:
        self.seconds.append(wav_duration(wav))
        return super().transcribe(wav)


class Diarizing(Recording):
    """A transcriber that also says who speaks: two speakers taking turns every 10 s."""
    def transcribe(self, wav) -> Transcript:
        t = super().transcribe(wav)
        t.turns = [(float(k), k + 10.0, "A" if k % 20 == 0 else "B") for k in range(0, 60, 10)]
        return t


def stored(upload_id: str, key=transcript_key) -> dict | None:
    storage = get_storage()
    if not storage.exists(key(upload_id)):
        return None
    return json.loads(storage.path(key(upload_id)).read_text())


def clip_job(client, headers, upload_id, **options):
    r = client.post("/v1/clips", json={"upload_id": upload_id, "options": {"max_clips": 1, "clip_length": 10,
                                                                         **options}}, headers=headers)
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def finished(client, headers, job_id) -> dict:
    return client.get(f"/v1/jobs/{job_id}", headers=headers).json()


# ---------- the model ----------

def test_a_window_is_read_only_when_it_was_transcribed_and_the_first_piece_owns_overlapping_time():
    heard = Heard()
    heard.add(0.0, 20.0, "base.en", Transcript(words=[(1.0, 1.5, "a"), (15.0, 15.5, "b")],
                                               segments=[(1.0, 1.5, "a"), (15.0, 15.5, "b")]))
    heard.add(10.0, 30.0, "small.en", Transcript(words=[(15.1, 15.6, "B"), (25.0, 25.5, "c")],
                                                 segments=[(15.1, 15.6, "B"), (25.0, 25.5, "c")]))
    t, offset = heard.window(10.0, 30.0)
    assert offset == 10.0 and [w[2] for w in t.words] == ["b", "c"]          # 15 s belongs to the first piece
    assert t.words[0][:2] == (5.0, 5.5)                                     # times from the window's start
    assert heard.window(10.0, 31.0) is None                                 # 30-31 s was never transcribed
    assert heard.window(5.0, 15.0, "small.en") is None                      # the caption model only did 10-30 s
    assert [w[2] for w in heard.window(12.0, 28.0, "small.en")[0].words] == ["B", "c"]
    assert heard.gaps(0.0, 40.0) == [(30.0, 40.0)]


def test_pieces_survive_a_round_trip_and_other_languages_are_not_read():
    heard = Heard("es")
    heard.add(5.0, 9.0, "small", Transcript(words=[(6.0, 6.5, "hola")], segments=[(6.0, 6.5, "hola")]))
    doc = json.loads(json.dumps(heard.parts_doc()))
    back = Heard.load("es", None, doc)
    assert back.window(5.0, 9.0, "small")[0].words == [(1.0, 1.5, "hola")] and back.added == []
    assert Heard.load("en", None, doc).pieces == []
    whole = {**doc_of(Transcript(words=[(1.0, 1.2, "x")], segments=[(1.0, 1.2, "x")]), 30.0, "base.en"), "language": "es"}
    assert Heard.load("es", whole).complete(30.0) and not Heard.load("en", whole).pieces


def test_model_names_say_whether_words_are_timed():
    assert model_of(FasterWhisperTranscriber("small.en")) == "small.en"
    assert model_of(FasterWhisperTranscriber("base.en", beam_size=1, words=False)) == "base.en:beam1:nowords"
    assert model_of(FasterWhisperTranscriber("base.en", beam_size=1, words=False).timing_words()) == "base.en:beam1"
    assert model_of(Talker()) == "Talker"


# ---------- Clip Maker ----------

def test_a_rerun_on_the_same_upload_transcribes_nothing_and_gives_the_same_clips(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    tr = Recording()
    first = clip_job(client, headers, up["upload_id"])
    assert worker.run_once(tr) == "SUCCEEDED"
    made = len(tr.seconds)
    assert made >= 1
    parts = stored(up["upload_id"], transcript_parts_key)
    assert parts["version"] == 2 and parts["language"] == "en" and len(parts["pieces"]) == made
    assert all(w[0] < w[1] for p in parts["pieces"] for w in p["words"])  # every word has a start before its end
    assert stored(up["upload_id"]) is None              # pieces only: no whole transcript claimed (Finder pricing)

    second = clip_job(client, headers, up["upload_id"])
    assert worker.run_once(tr) == "SUCCEEDED"
    assert len(tr.seconds) == made                                          # nothing transcribed again
    a, b = finished(client, headers, first), finished(client, headers, second)
    assert b["result"]["counts"]["transcript_reused"] >= 1 and "transcribe_rough" not in b["result"]["stages"]
    assert b["result"]["counts"].get("transcript_transcribed", 0) == 0
    assert b["result"]["counts"]["heard_pieces"] >= 1
    key = lambda c: (c["start_sec"], c["end_sec"], c["score"])  # noqa: E731
    assert [key(c) for c in a["clips"]] == [key(c) for c in b["clips"]]
    caps = [client.get(f"/v1/clips/{j['clips'][0]['id']}/subtitles?format=txt", headers=headers).text for j in (a, b)]
    assert caps[0] == caps[1] and caps[0].strip()


def test_with_a_judge_both_passes_are_read_on_a_rerun(client, user, three_bursts):  # noqa: F811
    headers, _ = user
    up = upload(client, headers, three_bursts)
    rough, final = Recording(), Recording()
    rough.model_name, final.model_name = "base.en", "small.en"
    for _ in range(2):
        clip_job(client, headers, up["upload_id"], clip_length=20)
        assert worker.run_once(final, indexer=rough, ai=FakeAI()) == "SUCCEEDED"
        if _ == 0:
            made = (len(rough.seconds), len(final.seconds))
    assert made[0] >= 1 and made[1] >= 1 and (len(rough.seconds), len(final.seconds)) == made


def test_captions_never_come_from_another_models_text(three_bursts, tmp_path):  # noqa: F811
    heard = Heard()
    t = Transcript(words=[(float(k), k + 0.5, "index") for k in range(60)], segments=[(0.0, 60.0, "index")])
    heard.add(0.0, 61.0, "base.en", t)
    heard.added.clear()
    final = Recording()
    final.model_name = "small.en"
    clips = run_pipeline(three_bursts, PipelineOptions(max_clips=1, clip_length=20, tighten=False), tmp_path / "o",
                         transcriber=final, transcript=heard)
    words = {w["text"] for w in json.loads(clips[0].captions_path.read_text())["words"]}
    assert final.seconds and words == {"oh", "no"}                          # the caption model ran; its words burned
    assert [p.model for p in heard.added] == ["small.en"] * len(final.seconds)


def test_unreadable_pieces_are_transcribed_again(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    path = get_storage().path(transcript_parts_key(up["upload_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    tr = Recording()
    clip_job(client, headers, up["upload_id"])
    assert worker.run_once(tr) == "SUCCEEDED" and tr.seconds
    assert stored(up["upload_id"], transcript_parts_key)["pieces"]          # replaced by good pieces


def test_a_failed_save_of_the_pieces_does_not_fail_the_job(client, user, video, monkeypatch):
    headers, _ = user

    def broken_put(key, src, put=get_storage().put):
        if key.endswith(".parts.json"):
            raise OSError("disk full")
        put(key, src)
    monkeypatch.setattr(get_storage(), "put", broken_put)
    up = upload(client, headers, video)
    job = clip_job(client, headers, up["upload_id"])
    assert worker.run_once(Recording()) == "SUCCEEDED" and finished(client, headers, job)["clips"]


# ---------- whole transcripts (Video Finder, Transcripts, Clip Maker's whole mode) ----------

def test_video_finder_after_a_clip_job_transcribes_only_what_the_clip_job_did_not(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    tr, index = Recording(), Recording()
    tr.model_name, index.model_name = "small.en", "base.en"
    clip_job(client, headers, up["upload_id"])
    assert worker.run_once(tr) == "SUCCEEDED"
    covered = sum(tr.seconds)
    client.post("/v1/find", json={"upload_id": up["upload_id"], "query": "oh no", "make_clips": False}, headers=headers)
    assert worker.run_once(tr, indexer=index) == "SUCCEEDED"
    assert sum(index.seconds) == pytest.approx(40.0 - covered, abs=1.5)    # only the rest of the 40 s video
    doc = stored(up["upload_id"])
    assert doc["version"] == 2 and doc["model"] == "mixed" and doc["language"] == "en"
    assert doc["words"] and all(w[0] < w[1] for w in doc["words"]) and "speakers" not in doc
    assert all("speaker" not in s for s in doc["segments"])


def test_speakers_are_kept_when_the_provider_gives_them(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/transcripts", json={"upload_id": up["upload_id"]}, headers=headers)
    assert r.status_code == 202, r.text
    assert worker.run_once(Diarizing()) == "SUCCEEDED"
    doc = stored(up["upload_id"])
    assert doc["speakers"]["turns"][:2] == [[0.0, 10.0, "A"], [10.0, 20.0, "B"]]
    rows = client.get(f"/v1/transcripts/{up['upload_id']}", headers=headers).json()["segments"]
    assert rows[0]["speaker"] == "A" and {r["speaker"] for r in rows} == {"A", "B"}


def test_without_speakers_from_the_provider_none_are_made_up(client, user, video):
    headers, _ = user
    up2 = upload(client, headers, video)
    client.post("/v1/transcripts", json={"upload_id": up2["upload_id"]}, headers=headers)
    assert worker.run_once(Recording()) == "SUCCEEDED"
    assert "speakers" not in stored(up2["upload_id"])
    assert {r["speaker"] for r in client.get(f"/v1/transcripts/{up2['upload_id']}", headers=headers).json()["segments"]} == {None}


def test_whole_mode_makes_the_transcript_first_and_every_candidate_reads_it(client, user, three_bursts, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "transcribe_whole", True)
    headers, _ = user
    up = upload(client, headers, three_bursts)
    rough, final = Recording(), Recording()
    rough.model_name, final.model_name = "base.en", "small.en"
    job = clip_job(client, headers, up["upload_id"], clip_length=20)
    assert worker.run_once(final, indexer=rough, ai=FakeAI()) == "SUCCEEDED"
    result = finished(client, headers, job)["result"]
    assert sum(rough.seconds) == pytest.approx(60.0, abs=1.0)              # the whole video, once
    assert "transcribe_rough" not in result["stages"] and result["stages"]["transcribe_whole"] >= 0
    assert result["counts"]["transcript_reused"] >= result["counts"]["candidates"]
    doc = stored(up["upload_id"])
    assert doc["model"] == "base.en" and doc["words"] and all(w[0] < w[1] for w in doc["words"])
    assert final.seconds                                                    # captions: still the caption model
    # A second job reuses the whole transcript: no transcribe_whole stage, counter set.
    again = clip_job(client, headers, up["upload_id"], clip_length=20)
    made = (len(rough.seconds), len(final.seconds))
    assert worker.run_once(final, indexer=rough, ai=FakeAI()) == "SUCCEEDED"
    second = finished(client, headers, again)["result"]
    assert (len(rough.seconds), len(final.seconds)) == made
    assert "transcribe_whole" not in second["stages"]
    assert second["counts"]["transcript_whole_reused"] == 1
    assert second["counts"]["transcript_reused"] >= second["counts"]["candidates"]


def test_whole_mode_failure_refunds(client, user, three_bursts, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "transcribe_whole", True)
    headers, _ = user
    up = upload(client, headers, three_bursts)
    before = balance(client, headers)

    class Broken(Recording):
        def transcribe(self, wav):
            raise PipelineError("transcription_unavailable", "down")
    job = clip_job(client, headers, up["upload_id"])
    assert worker.run_once(Recording(), indexer=Broken(), ai=FakeAI()) == "FAILED"
    assert finished(client, headers, job)["error"]["code"] == "transcription_unavailable"
    assert balance(client, headers) == before and stored(up["upload_id"]) is None


def test_expired_and_taken_down_uploads_lose_their_pieces_too(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    clip_job(client, headers, up["upload_id"])
    assert worker.run_once(Recording()) == "SUCCEEDED"
    assert stored(up["upload_id"], transcript_parts_key)
    from datetime import timedelta
    from app.db import new_session
    from app.models import Job, Upload, utcnow
    with new_session() as db:
        db.get(Upload, up["upload_id"]).expires_at = utcnow() - timedelta(days=1)
        for j in db.query(Job).filter(Job.upload_id == up["upload_id"]):
            j.expires_at = utcnow() - timedelta(days=1)
        db.commit()
    worker.sweep_expired()
    assert stored(up["upload_id"], transcript_parts_key) is None


def test_a_first_run_is_unchanged_by_an_empty_transcript(video, tmp_path):
    opts = PipelineOptions(max_clips=1, clip_length=10, tighten=False)
    plain = run_pipeline(video, opts, tmp_path / "a", transcriber=Recording(), timer=Timer())
    known = run_pipeline(video, opts, tmp_path / "b", transcriber=Recording(), transcript=Heard())
    assert [(c.start, c.end, c.score) for c in plain] == [(c.start, c.end, c.score) for c in known]
