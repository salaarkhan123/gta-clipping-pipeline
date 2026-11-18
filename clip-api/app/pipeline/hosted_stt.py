"""Hosted speech-to-text behind TRANSCRIPTION_PROVIDER: Groq (Whisper large-v3 / turbo), Deepgram (Nova-3) and
AssemblyAI. Each turns the job's 16 kHz mono WAV into the Transcript the local model gives: absolute seconds, every
word with its start and end, and speaker turns when the service identifies speakers.

- Audio leaves the server as FLAC (lossless, about half the WAV), so a 2-hour recording is one request for
  Deepgram and AssemblyAI. Groq takes at most 25 MB (free) / 100 MB (developer) per request, so its file is cut
  into chunks at quiet seconds (stt.chunk_bounds), sent several at once, and put back on one timeline.
- Every request has a timeout, and is retried on 429, 5xx and network errors (Retry-After honoured, capped).
- A failure never ends the job by itself: `WithFallback` hands the file to the local model, logs it and records
  it in the job's stages. Only when there is no local model either does the job fail, and a failed job is
  refunded by the worker like any other.
- API keys come from Settings only (the worker passes them in), are sent in headers, never in URLs, messages or
  logs.

Docs read 2026-11-18 (prices and limits: docs/transcription/provider-comparison.md):
  Groq        https://console.groq.com/docs/speech-to-text
  Deepgram    https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded
  AssemblyAI  https://www.assemblyai.com/docs/api-reference/transcripts/submit
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout, run
from .stt import chunk_bounds, slice_wav, wav_duration
from .timing import Timer
from .transcribe import Transcript

log = logging.getLogger("clipapi.stt")

# Pay-as-you-go USD per audio hour, from the pages above (read 2026-11-18). Deepgram lists $/minute: x 60.
PRICE_PER_HOUR = {
    ("groq", "whisper-large-v3"): 0.111, ("groq", "whisper-large-v3-turbo"): 0.04,
    ("deepgram", "nova-3"): 0.0043 * 60,
    ("assemblyai", "assemblyai-stt-3-7"): 0.21, ("assemblyai", "universal-2"): 0.15,
}
ASSEMBLYAI_DIARIZE_PER_HOUR = 0.02     # standard diarization add-on (https://www.assemblyai.com/pricing)
GROQ_MIN_BILLED_SEC = 10.0             # Groq bills at least 10 s per request
RETRY_AFTER_CAP = 30.0


class ProviderFailed(PipelineError):
    """The service could not transcribe the file. Safe to show; never contains a key."""
    def __init__(self, provider: str, why: str):
        super().__init__("transcription_provider_failed", f"{provider}: {why}")
        self.provider = provider


@dataclass(frozen=True)
class HostedConfig:
    api_key: str = field(repr=False)
    model: str
    language: str = "en"
    timeout_sec: float = 900.0         # the whole file, per provider attempt
    retries: int = 3                   # extra attempts per request on 429 / 5xx / network errors
    diarize: bool = True
    region: str = "us"                 # AssemblyAI: "eu" sends audio to its EU servers
    chunk_sec: float = 600.0           # Groq: 10 minutes of FLAC is about 10 MB, inside the 25 MB free limit
    parallel: int = 4                  # Groq: chunks sent at once
    poll_sec: float = 3.0              # AssemblyAI: wait between status checks
    mip_opt_out: bool = True           # Deepgram: keep our users' audio out of its Model Improvement Program


@dataclass
class Usage:
    """What one transcription cost and how it went: for the benchmark and the job's counts."""
    billed_sec: float = 0.0
    requests: int = 0
    retries: int = 0
    errors: list[str] = field(default_factory=list)


def to_flac(wav: Path, dest: Path, deadline: Deadline | None = None) -> Path:
    run(["ffmpeg", "-loglevel", "error", "-y", *SAFE_IN, "-i", wav, "-c:a", "flac", dest], deadline, cap=900)
    return dest


def sentences(words: list[tuple[float, float, str]], gap: float = 1.0) -> list[tuple[float, float, str]]:
    """Words grouped into sentence-ish segments: a break after . ? ! or a pause longer than `gap`."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or w[2].endswith((".", "?", "!")) or nxt[0] - w[1] > gap:
            out.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)))
            cur = []
    return out


def merged_turns(spoken: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """(start, end, speaker) runs, consecutive runs of the same speaker joined."""
    out: list[tuple[float, float, str]] = []
    for s, e, who in spoken:
        if out and out[-1][2] == who:
            out[-1] = (out[-1][0], e, who)
        else:
            out.append((s, e, who))
    return out


class _Hosted:
    name = "hosted"
    price_key: tuple[str, str]

    def __init__(self, cfg: HostedConfig, client: httpx.Client | None = None):
        self.cfg, self._client = cfg, client
        self.usage = Usage()
        self._lock = threading.Lock()
        self._sleep = time.sleep

    @property
    def model(self) -> str:
        """The name the transcript is kept under: provider and model, e.g. groq:whisper-large-v3-turbo."""
        return f"{self.name}:{self.cfg.model}"

    def price_per_hour(self) -> float | None:
        price = PRICE_PER_HOUR.get((self.name, self.cfg.model))
        if price is not None and self.name == "assemblyai" and self.cfg.diarize:
            price += ASSEMBLYAI_DIARIZE_PER_HOUR
        return price

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=httpx.Timeout(self.cfg.timeout_sec, connect=15.0))

    def _bill(self, seconds: float) -> None:
        with self._lock:
            self.usage.billed_sec += seconds

    def _call(self, http: httpx.Client, method: str, url: str, deadline: Deadline | None, **kw) -> httpx.Response:
        """One request, retried on 429, 5xx and network errors. Raises ProviderFailed (never with the key)."""
        for attempt in range(self.cfg.retries + 1):
            timeout = deadline.remaining(self.cfg.timeout_sec) if deadline else self.cfg.timeout_sec
            with self._lock:
                self.usage.requests += 1
            try:
                r = http.request(method, url, timeout=httpx.Timeout(timeout, connect=15.0), **kw)
            except httpx.HTTPError as e:
                why, wait = f"network error ({type(e).__name__})", 2.0 ** attempt
            else:
                if r.status_code < 400:
                    return r
                if r.status_code != 429 and r.status_code < 500:
                    why = f"HTTP {r.status_code}"
                    with self._lock:
                        self.usage.errors.append(why)
                    raise ProviderFailed(self.name, f"the request was refused ({why})")
                why = f"HTTP {r.status_code}"
                try:
                    wait = min(RETRY_AFTER_CAP, float(r.headers.get("retry-after", "")))
                except ValueError:
                    wait = 2.0 ** attempt
            with self._lock:
                self.usage.errors.append(why)
            if attempt == self.cfg.retries:
                raise ProviderFailed(self.name, f"no answer after {attempt + 1} attempts ({why})")
            with self._lock:
                self.usage.retries += 1
            if deadline:
                deadline.remaining()
            self._sleep(wait)
        raise AssertionError("unreachable")


class GroqProvider(_Hosted):
    """Groq's OpenAI-compatible Whisper endpoint, chunk by chunk (its file size limit)."""
    name = "groq"
    URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    def transcribe_file(self, wav: Path, work_dir: Path, deadline: Deadline | None = None,
                        on_progress: Callable[[int, int], None] | None = None) -> Transcript:
        bounds = chunk_bounds(wav, self.cfg.chunk_sec)
        http, done = self._http(), [0]

        def one(item: tuple[int, tuple[float, float]]) -> Transcript:
            i, (a, b) = item
            piece, flac = work_dir / f"groq{i}.wav", work_dir / f"groq{i}.flac"
            try:
                slice_wav(wav, a, b - a, piece)
                data = to_flac(piece, flac, deadline).read_bytes()
                r = self._call(http, "POST", self.URL, deadline,
                               headers={"Authorization": f"Bearer {self.cfg.api_key}"},
                               files={"file": (flac.name, data, "audio/flac")},
                               data={"model": self.cfg.model, "response_format": "verbose_json",
                                     "timestamp_granularities[]": ["word", "segment"],
                                     "language": self.cfg.language, "temperature": "0"})
            finally:
                piece.unlink(missing_ok=True)
                flac.unlink(missing_ok=True)
            self._bill(max(GROQ_MIN_BILLED_SEC, b - a))
            part = parse_groq(_json(r, self.name))
            with self._lock:
                done[0] += 1
                if on_progress:
                    on_progress(done[0], len(bounds))
            return Transcript(words=[(round(s + a, 3), round(e + a, 3), w) for s, e, w in part.words],
                              segments=[(round(s + a, 3), round(e + a, 3), x) for s, e, x in part.segments])

        try:
            with ThreadPoolExecutor(max(1, self.cfg.parallel)) as pool:
                parts = list(pool.map(one, enumerate(bounds)))
        finally:
            if self._client is None:
                http.close()
        out = Transcript()
        for p in parts:
            out.words += p.words
            out.segments += p.segments
        return out


def parse_groq(d: dict) -> Transcript:
    """verbose_json with word and segment timestamps -> Transcript. Segments the local model would skip (bracketed
    sound tags, likely non-speech, very unsure text) are skipped here too, with their words."""
    kept = []
    for seg in d.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text or text.startswith(("[", "(")):
            continue
        if (seg.get("no_speech_prob") or 0) > 0.6 or (seg.get("avg_logprob") or 0) < -1.0:
            continue
        kept.append((float(seg["start"]), float(seg["end"]), text))
    words = [(float(w["start"]), float(w["end"]), (w.get("word") or "").strip()) for w in d.get("words") or []]
    words = [w for w in words if w[2]]
    if d.get("segments") is not None:
        words = [w for w in words if any(s - 0.2 <= (w[0] + w[1]) / 2 <= e + 0.2 for s, e, _x in kept)]
    return Transcript(words=words, segments=kept)


class DeepgramProvider(_Hosted):
    """Deepgram pre-recorded: the whole file in one request (limit 2 GB, 10 minutes of processing)."""
    name = "deepgram"
    URL = "https://api.deepgram.com/v1/listen"

    def transcribe_file(self, wav: Path, work_dir: Path, deadline: Deadline | None = None,
                        on_progress: Callable[[int, int], None] | None = None) -> Transcript:
        flac = work_dir / "deepgram.flac"
        params = {"model": self.cfg.model, "smart_format": "true", "punctuate": "true", "utterances": "true",
                  "language": self.cfg.language}
        if self.cfg.diarize:
            params["diarize"] = "true"
        if self.cfg.mip_opt_out:
            params["mip_opt_out"] = "true"
        http = self._http()
        try:
            data = to_flac(wav, flac, deadline).read_bytes()
            r = self._call(http, "POST", self.URL, deadline, params=params, content=data,
                           headers={"Authorization": f"Token {self.cfg.api_key}", "Content-Type": "audio/flac"})
        finally:
            flac.unlink(missing_ok=True)
            if self._client is None:
                http.close()
        d = _json(r, self.name)
        self._bill(float((d.get("metadata") or {}).get("duration") or wav_duration(wav)))
        if on_progress:
            on_progress(1, 1)
        return parse_deepgram(d)


def parse_deepgram(d: dict) -> Transcript:
    try:
        alt = d["results"]["channels"][0]["alternatives"][0]
    except (KeyError, IndexError, TypeError):
        raise ProviderFailed("deepgram", "the answer had no transcript") from None
    raw = alt.get("words") or []
    words = [(float(w["start"]), float(w["end"]), (w.get("punctuated_word") or w.get("word") or "").strip())
             for w in raw]
    words = [w for w in words if w[2]]
    utts = (d.get("results") or {}).get("utterances")
    segments = ([(float(u["start"]), float(u["end"]), (u.get("transcript") or "").strip()) for u in utts
                 if (u.get("transcript") or "").strip()] if utts else sentences(words))
    turns = None
    if raw and all(w.get("speaker") is not None for w in raw):
        turns = merged_turns([(float(w["start"]), float(w["end"]), f"speaker {w['speaker']}") for w in raw])
    return Transcript(words=words, segments=segments, turns=turns)


class AssemblyAIProvider(_Hosted):
    """AssemblyAI async: upload the file, start a transcript, poll it, read its sentences, then delete it there."""
    name = "assemblyai"

    @property
    def base(self) -> str:
        return "https://api.eu.assemblyai.com" if self.cfg.region == "eu" else "https://api.assemblyai.com"

    def transcribe_file(self, wav: Path, work_dir: Path, deadline: Deadline | None = None,
                        on_progress: Callable[[int, int], None] | None = None) -> Transcript:
        flac, auth = work_dir / "assemblyai.flac", {"authorization": self.cfg.api_key}
        http, tid = self._http(), None
        try:
            try:
                data = to_flac(wav, flac, deadline).read_bytes()
            finally:
                flac.unlink(missing_ok=True)
            up = _json(self._call(http, "POST", f"{self.base}/v2/upload", deadline, content=data,
                                  headers={**auth, "content-type": "application/octet-stream"}), self.name)
            body = {"audio_url": up["upload_url"], "speech_models": [self.cfg.model],
                    "language_code": self.cfg.language, "punctuate": True, "format_text": True,
                    "speaker_labels": self.cfg.diarize}
            tid = _json(self._call(http, "POST", f"{self.base}/v2/transcript", deadline, json=body, headers=auth),
                        self.name)["id"]
            started = time.monotonic()
            while True:
                d = _json(self._call(http, "GET", f"{self.base}/v2/transcript/{tid}", deadline, headers=auth), self.name)
                if d.get("status") == "completed":
                    break
                if d.get("status") == "error":
                    raise ProviderFailed(self.name, "the service could not transcribe this audio")
                if time.monotonic() - started > self.cfg.timeout_sec:
                    raise ProviderFailed(self.name, f"no transcript after {int(self.cfg.timeout_sec)} s")
                if deadline:
                    deadline.remaining()
                self._sleep(self.cfg.poll_sec)
            sents = _json(self._call(http, "GET", f"{self.base}/v2/transcript/{tid}/sentences", deadline,
                                     headers=auth), self.name).get("sentences")
            self._bill(float(d.get("audio_duration") or wav_duration(wav)))
            if on_progress:
                on_progress(1, 1)
            return parse_assemblyai(d, sents)
        except KeyError:
            raise ProviderFailed(self.name, "the answer was not in the documented shape") from None
        finally:
            if tid is not None:          # keep nothing there: the transcript lives in our storage only
                try:
                    http.request("DELETE", f"{self.base}/v2/transcript/{tid}", headers=auth, timeout=30.0)
                except httpx.HTTPError:
                    log.warning("assemblyai: could not delete transcript %s; it expires on its own", tid)
            if self._client is None:
                http.close()


def parse_assemblyai(d: dict, sents: list[dict] | None = None) -> Transcript:
    """Times are milliseconds there."""
    raw = d.get("words") or []
    words = [(w["start"] / 1000, w["end"] / 1000, (w.get("text") or "").strip()) for w in raw]
    words = [w for w in words if w[2]]
    segments = ([(s["start"] / 1000, s["end"] / 1000, (s.get("text") or "").strip()) for s in sents
                 if (s.get("text") or "").strip()] if sents else sentences(words))
    turns = None
    if d.get("utterances"):
        turns = merged_turns([(u["start"] / 1000, u["end"] / 1000, f"speaker {u['speaker']}") for u in d["utterances"]])
    return Transcript(words=words, segments=segments, turns=turns)


def _json(r: httpx.Response, provider: str) -> dict:
    try:
        d = r.json()
    except ValueError:
        raise ProviderFailed(provider, "the answer was not JSON") from None
    if not isinstance(d, dict):
        raise ProviderFailed(provider, "the answer was not in the documented shape")
    return d


HOSTED = {"groq": GroqProvider, "deepgram": DeepgramProvider, "assemblyai": AssemblyAIProvider}


class WithFallback:
    """A hosted provider with the local model behind it. Whatever goes wrong with the service (refused, timed
    out, unusable answer, a bug in parsing it) the local model transcribes the file instead, and the job's stages
    say so (`transcribe_hosted`, `transcribe_fallback`, count `stt_fallback`). Only the job's own deadline, or
    having no local model, ends the job, which the worker then fails and refunds."""

    def __init__(self, primary, fallback=None, timer: Timer | None = None):
        self.primary, self.fallback, self.timer = primary, fallback, timer or Timer()
        self.name, self.used = primary.name, primary

    @property
    def model(self) -> str:
        """The model that made the last transcript (the local one after a fallback)."""
        return getattr(self.used, "model", self.used.name)

    def transcribe_file(self, wav: Path, work_dir: Path, deadline: Deadline | None = None,
                        on_progress: Callable[[int, int], None] | None = None) -> Transcript:
        try:
            with self.timer.stage("transcribe_hosted"):
                t = self.primary.transcribe_file(wav, work_dir, deadline, on_progress)
            self.used = self.primary
            usage = getattr(self.primary, "usage", None)
            if usage is not None:
                self.timer.count("stt_hosted_billed_sec", round(usage.billed_sec, 1))
            return t
        except PipelineTimeout:
            raise
        except Exception as e:       # noqa: BLE001 -- any failure of the service falls back
            why = getattr(e, "code", None) or type(e).__name__
            log.warning("transcription: %s failed (%s); the local model transcribes this file", self.name, why)
            self.timer.count("stt_fallback")
            if self.fallback is None:
                raise PipelineError("transcription_unavailable",
                                    "Speech could not be transcribed right now. Please try again later.") from None
            self.used = self.fallback
            with self.timer.stage("transcribe_fallback"):
                return self.fallback.transcribe_file(wav, work_dir, deadline, on_progress)
