"""Speech-to-text on candidate windows only (keeps cost per source minute low)."""
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .ff import SAFE_IN, Deadline, run

EXCLAMATIONS = ("oh my god", "oh my gosh", "no way", "what the", "let's go", "lets go", "holy",
                "are you kidding", "clip that", "clip it", "wtf", "omg", "get out", "i can't believe")


@dataclass
class Transcript:
    words: list[tuple[float, float, str]] = field(default_factory=list)      # (start, end, word)
    segments: list[tuple[float, float, str]] = field(default_factory=list)   # sentence-ish chunks


class Transcriber(Protocol):
    def transcribe(self, wav: Path) -> Transcript: ...


class FasterWhisperTranscriber:
    """Lazy-loaded faster-whisper model, CPU int8. One model per process."""
    _lock = threading.Lock()
    _models: dict = {}
    workers = 1      # transcriptions one model runs at once (set before first use; see TRANSCRIBE_PARALLEL)

    def __init__(self, model_name: str, beam_size: int = 5, words: bool = True):
        self.model_name, self.beam_size, self.words = model_name, beam_size, words

    def _load(self):
        with self._lock:
            if self.model_name not in self._models:
                from faster_whisper import WhisperModel
                self._models[self.model_name] = WhisperModel(self.model_name, device="cpu", compute_type="int8",
                                                             num_workers=max(1, FasterWhisperTranscriber.workers))
        return self._models[self.model_name]

    def transcribe(self, wav: Path) -> Transcript:
        # Feed raw samples instead of a path: faster-whisper's own decoder (PyAV) breaks across versions.
        segments, _ = self._load().transcribe(read_wav(wav), language="en", word_timestamps=self.words, vad_filter=True,
                                               beam_size=self.beam_size, condition_on_previous_text=False)
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
