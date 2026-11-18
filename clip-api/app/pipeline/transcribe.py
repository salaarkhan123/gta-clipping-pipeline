"""Speech-to-text on candidate windows only (keeps cost per source minute low)."""
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .ff import SAFE_IN, Deadline, PipelineError, run

EXCLAMATIONS = ("oh my god", "oh my gosh", "no way", "what the", "let's go", "lets go", "holy",
                "are you kidding", "clip that", "clip it", "wtf", "omg", "get out", "i can't believe")


@dataclass
class Transcript:
    words: list[tuple[float, float, str]] = field(default_factory=list)      # (start, end, word)
    segments: list[tuple[float, float, str]] = field(default_factory=list)   # sentence-ish chunks
    # (start, end, speaker) when the transcriber identified who speaks; None when it does not (never guessed)
    turns: list[tuple[float, float, str]] | None = None


class Transcriber(Protocol):
    def transcribe(self, wav: Path) -> Transcript: ...


MIN_SPEECH_SEC = 3.0      # less speech than this in a sample says nothing about the language


def in_language(transcriber, language: str | None):
    """(languages, agent F) The transcriber to use for speech in `language`: the same one, unless it knows a better
    one (the local Whisper model hands over its multilingual counterpart). No language: no change."""
    pick = getattr(transcriber, "for_language", None)
    return pick(language) if pick is not None and language else transcriber


class FasterWhisperTranscriber:
    """Lazy-loaded faster-whisper model, CPU int8. One model per process.

    `language` is the language it transcribes: English unless told otherwise, as it always was. `multilingual` is
    the name of the model to use for any other language (None: there is none, and every request stays here)."""
    _lock = threading.Lock()
    _models: dict = {}
    workers = 1      # transcriptions one model runs at once (set before first use; see TRANSCRIBE_PARALLEL)

    def __init__(self, model_name: str, beam_size: int = 5, words: bool = True, language: str = "en",
                 multilingual: str | None = None):
        self.model_name, self.beam_size, self.words = model_name, beam_size, words
        self.language, self.multilingual = language, multilingual
        self._others: dict[str, "FasterWhisperTranscriber"] = {}

    def _load(self, name: str | None = None):
        name = name or self.model_name
        with self._lock:
            if name not in self._models:
                from faster_whisper import WhisperModel
                try:
                    self._models[name] = WhisperModel(name, device="cpu", compute_type="int8",
                                                      num_workers=max(1, FasterWhisperTranscriber.workers))
                except Exception as e:
                    if name.endswith(".en"):
                        raise                    # the English models: as before
                    raise PipelineError("language_unavailable", "The speech model for this language could not be "
                                        "loaded on this server. Try again later, or use English.") from e
        return self._models[name]

    def for_language(self, language: str | None) -> "FasterWhisperTranscriber":
        """The transcriber for speech in `language`: this one for its own language (English stays on the model and
        the options it always had), otherwise the multilingual model with the same settings."""
        if not language or language == self.language or not self.multilingual:
            return self
        if language not in self._others:
            self._others[language] = FasterWhisperTranscriber(self.multilingual, self.beam_size, self.words,
                                                              language=language, multilingual=self.multilingual)
        return self._others[language]

    def timing_words(self) -> "FasterWhisperTranscriber":
        """The same model, language and settings, timing every word (what a stored whole transcript needs)."""
        if self.words:
            return self
        out = FasterWhisperTranscriber(self.model_name, self.beam_size, True, self.language, self.multilingual)
        out._others = {code: t.timing_words() for code, t in self._others.items()}
        return out

    def options(self) -> dict:
        """What the model is asked to do. For English this is exactly what it was before languages existed."""
        return {"language": self.language, "word_timestamps": self.words, "vad_filter": True,
                "beam_size": self.beam_size, "condition_on_previous_text": False}

    def language_probs(self, wav: Path) -> dict[str, float] | None:
        """How likely each language is for the speech in this WAV (the first 30 s of it), by the multilingual
        model. None when there is no such model or too little speech to tell."""
        if not self.multilingual:
            return None
        import numpy as np
        from faster_whisper.vad import get_speech_timestamps
        audio = read_wav(wav)
        spoken = get_speech_timestamps(audio)
        if sum(c["end"] - c["start"] for c in spoken) < MIN_SPEECH_SEC * 16000:
            return None
        speech = np.concatenate([audio[c["start"]:c["end"]] for c in spoken])
        _lang, _prob, probs = self._load(self.multilingual).detect_language(speech)
        return {code: float(p) for code, p in probs}

    def transcribe(self, wav: Path) -> Transcript:
        # Feed raw samples instead of a path: faster-whisper's own decoder (PyAV) breaks across versions.
        segments, _ = self._load().transcribe(read_wav(wav), **self.options())
        out = Transcript()
        for seg in segments:
            text = (seg.text or "").strip()
            if not text or text.startswith(("[", "(")):
                continue  # skip [Music], (laughs) and similar
            if (seg.no_speech_prob or 0) > 0.6 or (seg.avg_logprob or 0) < -1.0:
                continue  # likely music lyrics or background chatter, not the streamer
            out.segments.append((float(seg.start), float(seg.end), text))
            for w in seg.words or []:
                word = (w.word or "").strip()
                if word:
                    out.words.append((float(w.start), float(w.end), word))
        return out


def read_wav(path: Path):
    """16 kHz mono s16le WAV -> float32 numpy array in [-1, 1]."""
    import wave
    import numpy as np
    with wave.open(str(path), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def extract_wav(src: Path, start: float, length: float, dest: Path, deadline: Deadline | None = None) -> None:
    run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{max(start, 0):.3f}", "-t", f"{length:.3f}",
         *SAFE_IN, "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dest], deadline)


def exclamation_hits(text: str) -> int:
    low = text.lower()
    return sum(low.count(p) for p in EXCLAMATIONS)


def snap_to_speech(start: float, end: float, segments: list[tuple[float, float, str]],
                   lo: float, hi: float, min_len: float, max_len: float, tol: float = 4.0) -> tuple[float, float]:
    """Move clip edges to the nearest sentence boundary within `tol` seconds so clips don't cut mid-sentence."""
    if not segments:
        return start, end
    s_near = min((seg[0] for seg in segments), key=lambda t: abs(t - start))
    e_near = min((seg[1] for seg in segments), key=lambda t: abs(t - end))
    new_s = max(lo, s_near - 0.15) if abs(s_near - start) <= tol else start
    new_e = min(hi, e_near + 0.25) if abs(e_near - end) <= tol else end
    if not (min_len <= new_e - new_s <= max_len):
        return start, end
    return new_s, new_e


# (U4) Cuts on whole sentences.
SENTENCE_END = (".", "?", "!", "…")
SENTENCE_PAUSE = 0.8          # a silence this long between two words ends a sentence too (speech without punctuation)


def sentences(words: list[tuple[float, float, str]]) -> list[tuple[float, float]]:
    """The sentences of a run of timed words (sorted), as (start, end): a sentence ends on a word ending in . ? ! or
    before a pause of SENTENCE_PAUSE seconds."""
    out: list[tuple[float, float]] = []
    start = last = None
    for s, e, w in words:
        if start is not None and s - last >= SENTENCE_PAUSE:
            out.append((start, last))
            start = None
        if start is None:
            start = s
        last = e
        if str(w).strip().endswith(SENTENCE_END):
            out.append((start, e))
            start = None
    if start is not None:
        out.append((start, last))
    return out


def snap_to_sentences(start: float, end: float, words: list[tuple[float, float, str]], lo: float, hi: float,
                      min_len: float, max_len: float, tol: float = 4.0) -> tuple[float, float] | None:
    """Clip edges on whole sentences: the start moves back to the start of the sentence it falls in (or to the
    nearest sentence start), the end forward to the end of its sentence (or the nearest end), each by at most
    `tol` seconds. None when there are no timed words or the snapped clip would leave [min_len, max_len]."""
    spans = sentences(words)
    if not spans:
        return None

    def edge(t: float, inside, points: list[float]) -> float | None:
        if inside is not None and abs(inside - t) <= tol:
            return inside
        near = [p for p in points if abs(p - t) <= tol]
        return min(near, key=lambda p: abs(p - t)) if near else None

    s = edge(start, next((a for a, b in spans if a <= start < b), None), [a for a, _b in spans])
    e = edge(end, next((b for a, b in spans if a < end <= b), None), [b for _a, b in spans])
    new_s = max(lo, s - 0.15) if s is not None else start
    new_e = min(hi, e + 0.25) if e is not None else end
    return (new_s, new_e) if min_len <= new_e - new_s <= max_len else None
