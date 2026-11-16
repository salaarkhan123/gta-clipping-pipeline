"""Speech-to-text over a whole recording: the audio is extracted once, then a provider transcribes the file.

- `extract_audio` decodes the source's audio a single time into a 16 kHz mono WAV and, in the same pass, measures
  the loudness per second. Measured on a 2-hour recording it costs a few seconds more than measuring the levels
  alone, and cutting candidates from the WAV saves nothing over ffmpeg's seeks, so the clip pipeline does not
  extract by default: a caller that already has the audio passes it in.
- `slice_wav` cuts a piece out of that WAV by seeking in the file: no ffmpeg, no second decode.
- A provider turns the whole WAV into a `Transcript` with absolute times. `LocalProvider` runs the local Whisper
  model over chunks that are cut at quiet points, several at once when the machine has the cores for it.
  Hosted providers plug in behind the same method.
"""
import re
import wave
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from .ff import SAFE_IN, Deadline, PipelineError, run
from .transcribe import Transcriber, Transcript

RATE = 16000


@dataclass
class SourceAudio:
    """A recording's audio, decoded once: the WAV, and its loudness per second measured in the same pass."""
    path: Path
    levels: list[float]


def extract_audio(src: Path, dest: Path, deadline: Deadline | None = None) -> SourceAudio:
    """Write the source's audio to `dest` (16 kHz mono s16le WAV) and measure its RMS level in dB per second.
    One decode does both. The levels are the same measurement as signals.audio_rms_db.

    This costs more than measuring the levels alone (it writes about 115 MB per hour), so it is for callers
    that need the whole recording: a provider transcribing the file, or several passes over the audio."""
    res = run(["ffmpeg", "-hide_banner", "-nostats", "-y", *SAFE_IN, "-i", src, "-vn", "-filter_complex",
               "[0:a:0]asplit=2[w][m];"
               "[m]aresample=8000,asetnsamples=n=8000,astats=metadata=1:reset=1,"
               "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-[lv]",
               "-map", "[w]", "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", dest,
               "-map", "[lv]", "-ac", "1", "-f", "null", "-"], deadline)
    vals = re.findall(r"RMS_level=(\S+)", res.stdout)
    return SourceAudio(dest, [max(-90.0, -90.0 if v in ("-inf", "inf", "nan") else float(v)) for v in vals])


def wav_duration(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / w.getframerate()


def slice_wav(wav: Path, start: float, length: float, dest: Path) -> float:
    """Copy [start, start + length] of `wav` into `dest`. Returns the seconds actually written (the end is clipped)."""
    with wave.open(str(wav), "rb") as w:
        rate, total = w.getframerate(), w.getnframes()
        a = min(total, max(0, int(round(start * rate))))
        n = max(0, min(total - a, int(round(length * rate))))
        w.setpos(a)
        frames = w.readframes(n)
        with wave.open(str(dest), "wb") as out:
            out.setnchannels(w.getnchannels())
            out.setsampwidth(w.getsampwidth())
            out.setframerate(rate)
            out.writeframes(frames)
    return n / rate


def chunk_bounds(wav: Path, chunk_sec: float = 300.0, search: float = 15.0) -> list[tuple[float, float]]:
    """Split the recording into chunks of about `chunk_sec`, each cut moved to the quietest second within
    `search` seconds of the nominal cut, so a chunk rarely ends in the middle of a word."""
    total = wav_duration(wav)
    if total <= chunk_sec * 1.25:
        return [(0.0, total)]
    cuts, t = [0.0], chunk_sec
    with wave.open(str(wav), "rb") as w:
        rate = w.getframerate()
        while t < total - chunk_sec * 0.25:               # never leave a sliver as the last chunk
            lo = max(cuts[-1] + 1.0, t - search)
            w.setpos(int(lo * rate))
            x = np.frombuffer(w.readframes(int(min(2 * search, total - lo) * rate)), dtype=np.int16).astype(np.float32)
            step = rate // 10                                   # 0.1 s steps
            bins = len(x) // step
            if bins >= 10:
                energy = (x[: bins * step].reshape(bins, step) ** 2).mean(axis=1)
                second = np.convolve(energy, np.ones(10), mode="valid")      # every full second, sliding by 0.1 s
                cut = lo + (int(second.argmin()) + 5) * 0.1                  # the middle of the quietest one
            else:
                cut = t
            cuts.append(round(cut, 3))
            t = cut + chunk_sec
    cuts.append(total)
    return list(zip(cuts, cuts[1:]))


class TranscriptionProvider(Protocol):
    name: str

    def transcribe_file(self, wav: Path, work_dir: Path, deadline: Deadline | None = None,
                        on_progress: Callable[[int, int], None] | None = None) -> Transcript:
        """The whole recording as one Transcript, times in seconds from the start of the file."""


class LocalProvider:
    """The local Whisper model over the whole file, chunk by chunk. `parallel` chunks run at once: worth it only
    when the machine has cores to spare beyond one model's threads (see DEPLOY.md)."""
    name = "local"

    def __init__(self, transcriber: Transcriber, chunk_sec: float = 300.0, parallel: int = 1):
        self.transcriber, self.chunk_sec, self.parallel = transcriber, chunk_sec, max(1, parallel)

    def transcribe_file(self, wav: Path, work_dir: Path, deadline: Deadline | None = None,
                        on_progress: Callable[[int, int], None] | None = None) -> Transcript:
        bounds = chunk_bounds(wav, self.chunk_sec)
        done = [0]

        def one(item: tuple[int, tuple[float, float]]) -> Transcript:
            i, (a, b) = item
            if deadline:
                deadline.remaining()                       # raises once the job's time is up
            piece = work_dir / f"stt{i}.wav"
            slice_wav(wav, a, b - a, piece)
            try:
                part = self.transcriber.transcribe(piece)
            finally:
                piece.unlink(missing_ok=True)
            done[0] += 1
            if on_progress:
                on_progress(done[0], len(bounds))
            return Transcript(words=[(round(s + a, 3), round(e + a, 3), w) for s, e, w in part.words],
                              segments=[(round(s + a, 3), round(e + a, 3), x) for s, e, x in part.segments])

        with ThreadPoolExecutor(self.parallel) as pool:
            parts = list(pool.map(one, enumerate(bounds)))  # map keeps the chunks in order
        out = Transcript()
        for p in parts:
            out.words += p.words
            out.segments += p.segments
        return out


PROVIDERS = ("local",)      # hosted providers are added here with their adapters


def provider_for(name: str, transcriber: Transcriber | None, chunk_sec: float = 300.0, parallel: int = 1):
    """The configured provider, or None when there is nothing to transcribe with."""
    if name not in PROVIDERS:
        raise PipelineError("transcription_unavailable",
                            f"Transcription provider '{name}' is not available on this server (available: {', '.join(PROVIDERS)}).")
    return LocalProvider(transcriber, chunk_sec, parallel) if transcriber is not None else None


def window(full: Transcript, start: float, end: float) -> tuple[Transcript, float]:
    """The part of a whole-file transcript inside [start, end], with times relative to `start`.
    Returns (transcript, offset) in the shape the pipeline keeps per candidate."""
    return (Transcript(words=[(s - start, e - start, w) for s, e, w in full.words if start <= s < end],
                       segments=[(s - start, e - start, x) for s, e, x in full.segments if start <= s < end]), start)
