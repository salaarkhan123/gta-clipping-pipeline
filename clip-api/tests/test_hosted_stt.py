"""Hosted transcription (Groq, Deepgram, AssemblyAI) on mocked HTTP in the documented response shapes, the local
fallback, and that a job whose transcription cannot be done at all is failed and refunded."""
import json
import logging

import httpx
import pytest

from app import config, worker
from app.pipeline import PipelineTimeout, Timer
from app.pipeline import hosted_stt
from app.pipeline.ff import Deadline
from app.pipeline.hosted_stt import (AssemblyAIProvider, DeepgramProvider, GroqProvider, HostedConfig, ProviderFailed,
                                     WithFallback)
from app.pipeline.stt import LocalProvider, provider_for
from app.pipeline.transcribe import Transcript
from tests.test_api import balance, upload
from tests.test_stt import tone

KEY = "sk-test-secret-0123456789"


def cfg(**kw) -> HostedConfig:
    return HostedConfig(**{"api_key": KEY, "model": "m", "retries": 2, "poll_sec": 0.0, **kw})


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def no_sleep(p):
    p._sleep = lambda s: p.slept.append(s)
    p.slept = []
    return p


def groq_answer(offset_words=0.0):
    return {"text": "oh my god no", "segments": [
        {"id": 0, "seek": 0, "start": 1.0, "end": 2.5, "text": " Oh my god.", "no_speech_prob": 0.01, "avg_logprob": -0.2},
        {"id": 1, "seek": 0, "start": 4.0, "end": 6.0, "text": " la la la", "no_speech_prob": 0.9, "avg_logprob": -0.3},
        {"id": 2, "seek": 0, "start": 7.0, "end": 8.0, "text": " [Music]", "no_speech_prob": 0.1, "avg_logprob": -0.3}],
        "words": [{"word": "Oh", "start": 1.0, "end": 1.3}, {"word": "my", "start": 1.3, "end": 1.6},
                  {"word": "god.", "start": 1.6, "end": 2.5}, {"word": "la", "start": 4.2, "end": 4.6}]}


def test_groq_sends_chunks_with_word_timestamps_and_puts_them_on_one_timeline(tmp_path):
    wav = tone(tmp_path / "a.wav", 1500, quiet=(596, 1197))
    seen = []

    def handler(req: httpx.Request):
        body = req.content.decode("latin-1")
        seen.append(body)
        assert req.url == GroqProvider.URL and req.headers["authorization"] == f"Bearer {KEY}"
        for field in ('name="model"\r\n\r\nwhisper-large-v3-turbo', 'name="response_format"\r\n\r\nverbose_json',
                      'name="timestamp_granularities[]"\r\n\r\nword', 'name="timestamp_granularities[]"\r\n\r\nsegment',
                      'name="language"\r\n\r\nen', 'filename="groq'):
            assert field in body
        return httpx.Response(200, json=groq_answer())

    p = GroqProvider(cfg(model="whisper-large-v3-turbo", chunk_sec=600, parallel=3), client(handler))
    progress = []
    t = p.transcribe_file(wav, tmp_path, on_progress=lambda k, n: progress.append((k, n)))
    assert len(seen) == 3 and progress[-1] == (3, 3)
    starts = [round(w[0] - 1.0, 1) for w in t.words if w[2] == "Oh"]      # each chunk's first word, shifted by its start
    assert starts[0] == 0.0 and 590 < starts[1] < 610 and 1190 < starts[2] < 1210
    assert [w[2] for w in t.words[:3]] == ["Oh", "my", "god."] and len(t.words) == 9     # "la" left with its segment
    assert [x for _s, _e, x in t.segments] == ["Oh my god."] * 3                         # non-speech and [Music] skipped
    assert p.usage.billed_sec == pytest.approx(1500, abs=1) and p.usage.requests == 3
    assert p.model == "groq:whisper-large-v3-turbo" and not list(tmp_path.glob("groq*"))  # pieces cleaned up


def test_groq_retries_429_with_retry_after_then_gives_up_cleanly(tmp_path):
    wav = tone(tmp_path / "a.wav", 30)
    answers = [httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(503),
               httpx.Response(200, json=groq_answer())]
    p = no_sleep(GroqProvider(cfg(), client(lambda req: answers.pop(0))))
    t = p.transcribe_file(wav, tmp_path)
    assert len(t.words) == 3 and p.slept == [7.0, 2.0] and p.usage.retries == 2
    assert p.usage.billed_sec == pytest.approx(30, abs=0.1)

    p = no_sleep(GroqProvider(cfg(), client(lambda req: httpx.Response(500))))
    with pytest.raises(ProviderFailed) as e:
        p.transcribe_file(wav, tmp_path)
    assert "3 attempts" in e.value.message and KEY not in e.value.message and p.usage.requests == 3
    p = no_sleep(GroqProvider(cfg(), client(lambda req: httpx.Response(401, json={"error": {"message": KEY}}))))
    with pytest.raises(ProviderFailed) as e:
        p.transcribe_file(wav, tmp_path)
    assert "HTTP 401" in e.value.message and KEY not in e.value.message and p.usage.requests == 1   # no retry


def test_groq_minimum_billing_and_the_job_deadline(tmp_path):
    wav = tone(tmp_path / "a.wav", 4)
    p = GroqProvider(cfg(), client(lambda req: httpx.Response(200, json={"words": [], "segments": []})))
    assert p.transcribe_file(wav, tmp_path).words == [] and p.usage.billed_sec == 10.0          # billed at least 10 s
    with pytest.raises(PipelineTimeout):
        p.transcribe_file(wav, tmp_path, deadline=Deadline(0.000001))


DEEPGRAM = {
    "metadata": {"request_id": "r", "duration": 61.5, "channels": 1},
    "results": {"channels": [{"alternatives": [{"transcript": "oh my god no way", "confidence": 0.9, "words": [
        {"word": "oh", "punctuated_word": "Oh", "start": 1.0, "end": 1.2, "confidence": 0.9, "speaker": 0},
        {"word": "my", "punctuated_word": "my", "start": 1.2, "end": 1.4, "confidence": 0.9, "speaker": 0},
        {"word": "god", "punctuated_word": "god!", "start": 1.4, "end": 1.8, "confidence": 0.9, "speaker": 0},
        {"word": "no", "punctuated_word": "No", "start": 3.0, "end": 3.2, "confidence": 0.9, "speaker": 1},
        {"word": "way", "punctuated_word": "way.", "start": 3.2, "end": 3.6, "confidence": 0.9, "speaker": 1}]}]}],
        "utterances": [{"start": 1.0, "end": 1.8, "confidence": 0.9, "channel": 0, "transcript": "Oh my god!",
                        "speaker": 0, "id": "u1", "words": []},
                       {"start": 3.0, "end": 3.6, "confidence": 0.9, "channel": 0, "transcript": "No way.",
                        "speaker": 1, "id": "u2", "words": []}]}}


def test_deepgram_one_request_with_speakers_and_no_training_on_our_audio(tmp_path):
    wav = tone(tmp_path / "a.wav", 60)
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json=DEEPGRAM)
    p = DeepgramProvider(cfg(model="nova-3"), client(handler))
    t = p.transcribe_file(wav, tmp_path)
    req = seen[0]
    assert len(seen) == 1 and req.headers["authorization"] == f"Token {KEY}" and req.headers["content-type"] == "audio/flac"
    assert req.content[:4] == b"fLaC" and KEY not in str(req.url)
    q = dict(req.url.params)
    assert q["model"] == "nova-3" and q["mip_opt_out"] == "true" and q["diarize"] == "true" and q["utterances"] == "true"
    assert t.words[2] == (1.4, 1.8, "god!") and t.segments == [(1.0, 1.8, "Oh my god!"), (3.0, 3.6, "No way.")]
    assert t.turns == [(1.0, 1.8, "speaker 0"), (3.0, 3.6, "speaker 1")]
    assert p.usage.billed_sec == 61.5 and not list(tmp_path.glob("*.flac"))


def test_deepgram_without_utterances_or_speakers_still_gives_sentences(tmp_path):
    d = json.loads(json.dumps(DEEPGRAM))
    del d["results"]["utterances"]
    for w in d["results"]["channels"][0]["alternatives"][0]["words"]:
        del w["speaker"]
    t = hosted_stt.parse_deepgram(d)
    assert t.segments == [(1.0, 1.8, "Oh my god!"), (3.0, 3.6, "No way.")] and t.turns is None
    with pytest.raises(ProviderFailed):
        hosted_stt.parse_deepgram({"results": {}})


def assemblyai_handler(statuses, calls, transcript=None):
    transcript = transcript or {
        "id": "t1", "status": "completed", "audio_duration": 61, "text": "Oh my god. No way.",
        "words": [{"text": "Oh", "start": 1000, "end": 1200, "confidence": 0.9, "speaker": "A"},
                  {"text": "my", "start": 1200, "end": 1400, "confidence": 0.9, "speaker": "A"},
                  {"text": "god.", "start": 1400, "end": 1800, "confidence": 0.9, "speaker": "A"},
                  {"text": "No", "start": 3000, "end": 3200, "confidence": 0.9, "speaker": "B"},
                  {"text": "way.", "start": 3200, "end": 3600, "confidence": 0.9, "speaker": "B"}],
        "utterances": [{"speaker": "A", "start": 1000, "end": 1800, "text": "Oh my god.", "confidence": 0.9, "words": []},
                       {"speaker": "B", "start": 3000, "end": 3600, "text": "No way.", "confidence": 0.9, "words": []}]}

    def handler(req: httpx.Request):
        calls.append((req.method, req.url.path))
        assert req.headers["authorization"] == KEY
        if req.url.path == "/v2/upload":
            assert req.content[:4] == b"fLaC"
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/upload/x"})
        if req.method == "POST" and req.url.path == "/v2/transcript":
            body = json.loads(req.content)
            assert body["audio_url"].endswith("/upload/x") and body["speech_models"] == ["assemblyai-stt-3-7"]
            assert body["speaker_labels"] is True and body["language_code"] == "en"
            return httpx.Response(200, json={"id": "t1", "status": "queued"})
        if req.url.path == "/v2/transcript/t1/sentences":
            return httpx.Response(200, json={"sentences": [{"text": "Oh my god.", "start": 1000, "end": 1800},
                                                           {"text": "No way.", "start": 3000, "end": 3600}]})
        if req.method == "GET":
            s = statuses.pop(0)
            return httpx.Response(200, json=transcript if s == "completed" else {"id": "t1", "status": s,
                                                                                    **({"error": "bad audio"} if s == "error" else {})})
        if req.method == "DELETE":
            return httpx.Response(200, json={"id": "t1", "status": "completed"})
        raise AssertionError(req)
    return handler


def test_assemblyai_uploads_polls_reads_seconds_and_deletes_its_copy(tmp_path):
    wav = tone(tmp_path / "a.wav", 60)
    calls = []
    p = AssemblyAIProvider(cfg(model="assemblyai-stt-3-7"), client(assemblyai_handler(["queued", "processing", "completed"], calls)))
    t = p.transcribe_file(wav, tmp_path)
    assert t.words[0] == (1.0, 1.2, "Oh") and t.segments == [(1.0, 1.8, "Oh my god."), (3.0, 3.6, "No way.")]
    assert t.turns == [(1.0, 1.8, "speaker A"), (3.0, 3.6, "speaker B")]
    assert ("DELETE", "/v2/transcript/t1") == calls[-1] and [c for c in calls if c[0] == "GET"][:3] == [("GET", "/v2/transcript/t1")] * 3
    assert p.usage.billed_sec == 61 and p.price_per_hour() == pytest.approx(0.23)            # model + diarization
    assert AssemblyAIProvider(cfg(region="eu")).base == "https://api.eu.assemblyai.com"


def test_assemblyai_error_status_fails_the_attempt_and_still_deletes(tmp_path):
    wav = tone(tmp_path / "a.wav", 20)
    calls = []
    p = AssemblyAIProvider(cfg(model="assemblyai-stt-3-7"), client(assemblyai_handler(["processing", "error"], calls)))
    with pytest.raises(ProviderFailed):
        p.transcribe_file(wav, tmp_path)
    assert calls[-1] == ("DELETE", "/v2/transcript/t1")
    calls = []
    slow = AssemblyAIProvider(cfg(model="assemblyai-stt-3-7", timeout_sec=0.0),
                              client(assemblyai_handler(["processing"] * 5, calls)))
    with pytest.raises(ProviderFailed, match="no transcript after"):
        slow.transcribe_file(wav, tmp_path)


class Local:
    name, model = "local", "local:base.en"

    def __init__(self):
        self.files = 0

    def transcribe_file(self, wav, work_dir, deadline=None, on_progress=None):
        self.files += 1
        return Transcript(words=[(0.0, 0.5, "local")], segments=[(0.0, 0.5, "local")])


class Broken:
    name, model = "groq", "groq:m"

    def __init__(self, exc):
        self.exc = exc

    def transcribe_file(self, *a, **k):
        raise self.exc


@pytest.mark.parametrize("exc", [ProviderFailed("groq", "HTTP 500"), KeyError("words"), httpx.ConnectError("down")])
def test_any_failure_of_the_service_falls_back_to_the_local_model_and_is_recorded(tmp_path, caplog, exc):
    local, timer = Local(), Timer()
    p = WithFallback(Broken(exc), local, timer)
    with caplog.at_level(logging.WARNING):
        t = p.transcribe_file(tmp_path / "a.wav", tmp_path)
    assert t.words == [(0.0, 0.5, "local")] and local.files == 1 and p.model == "local:base.en"
    d = timer.as_dict()
    assert d["counts"]["stt_fallback"] == 1 and "transcribe_hosted" in d["stages"] and "transcribe_fallback" in d["stages"]
    assert "groq failed" in caplog.text and KEY not in caplog.text


def test_the_job_deadline_is_not_a_provider_failure(tmp_path):
    local = Local()
    with pytest.raises(PipelineTimeout):
        WithFallback(Broken(PipelineTimeout()), local).transcribe_file(tmp_path / "a.wav", tmp_path)
    assert local.files == 0


def test_provider_for_picks_the_service_only_with_its_settings():
    class Tr:
        language = "en"

        def transcribe(self, wav):
            return Transcript()
    assert isinstance(provider_for("local", Tr()), LocalProvider)
    assert isinstance(provider_for("groq", Tr()), LocalProvider)                     # no key: the local model
    assert provider_for("deepgram", None) is None
    p = provider_for("deepgram", Tr(), hosted=cfg(model="nova-3"))
    assert isinstance(p, WithFallback) and isinstance(p.primary, DeepgramProvider) and isinstance(p.fallback, LocalProvider)
    assert p.model == "deepgram:nova-3" and KEY not in repr(p.primary.cfg)
    assert isinstance(provider_for("assemblyai", None, hosted=cfg()).primary, AssemblyAIProvider)
    s = config.Settings(transcription_provider="groq", groq_api_key=KEY)
    assert KEY not in repr(s)
    h = worker.hosted_config(s, Tr())
    assert h.api_key == KEY and h.model == "whisper-large-v3-turbo" and h.language == "en"
    assert worker.hosted_config(config.Settings(transcription_provider="groq"), Tr()) is None
    assert worker.hosted_config(config.Settings(), Tr()) is None
    assert config.Settings.model_fields["transcription_provider"].default == "local"


@pytest.fixture
def groq_on(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    config.get_settings.cache_clear()
    yield
    monkeypatch.delenv("TRANSCRIPTION_PROVIDER")
    monkeypatch.delenv("GROQ_API_KEY")
    config.get_settings.cache_clear()


def failing_service(monkeypatch):
    real = httpx.Client
    monkeypatch.setattr(hosted_stt.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(
        lambda req: httpx.Response(500)), **kw))
    monkeypatch.setattr(hosted_stt._Hosted, "__init__", _no_wait_init(hosted_stt._Hosted.__init__))


def _no_wait_init(init):
    def wrapped(self, *a, **k):
        init(self, *a, **k)
        self._sleep = lambda s: None
    return wrapped


def test_a_job_whose_service_fails_succeeds_on_the_local_model_and_says_so(client, user, video, transcriber,
                                                                           groq_on, monkeypatch):
    failing_service(monkeypatch)
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/find", json={"upload_id": up["upload_id"], "query": "no way", "make_clips": False}, headers=headers)
    assert worker.run_once(transcriber) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert job["result"]["counts"]["stt_fallback"] == 1 and "transcribe_hosted" in job["result"]["stages"]
    assert [m["kind"] for m in job["result"]["matches"]][:1] == ["speech"]


def test_a_job_with_no_service_and_no_local_model_fails_and_is_refunded(client, user, video, groq_on, monkeypatch):
    failing_service(monkeypatch)
    headers, _ = user
    before = balance(client, headers)
    up = upload(client, headers, video)
    r = client.post("/v1/transcripts", json={"upload_id": up["upload_id"]}, headers=headers)
    assert r.status_code == 202, r.text
    # The local model is there for the job's own work, but this provider has none behind it.
    monkeypatch.setattr(worker, "transcription_provider",
                        lambda s, tr, timer=None: provider_for("groq", None, hosted=worker.hosted_config(s, tr), timer=timer))
    assert worker.run_once(Local()) == "FAILED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert job["error"]["code"] == "transcription_unavailable"
    assert balance(client, headers) == before                                         # refunded
