"""Per-second signal timeline (U2): what happens in each second of a recording besides how loud it is.

Every series has one value per second of the analysed part (value i is source second `start + i`). The pipeline
scores each against its own rolling baseline (signals.baseline_z) and adds it to the moment score with its weight
(pipeline.WEIGHTS). A detector with weight 0 is not computed at all, so it costs nothing.

| Signal | Made from | What it measures |
|---|---|---|
| audio_flux | the loudness decode (no second decode) | how fast the sound's spectrum changes: impacts, shouts, laughs starting |
| audio_bursts | the loudness decode | loudness pulsing 3 to 7 times a second, the rhythm of laughter |
| scene | key frames, one every 2 s (an extra decode) | how much the picture changes between key frames |
| standby | the key frames inside each candidate, and its words | seconds where nothing happens: the picture does not change and nobody speaks (starting-soon and BRB screens, an empty chair, menus left open) |

A candidate that is standby for STANDBY_REJECT of its seconds or more never becomes a clip (pipeline: its
`features.standby` is that share). `standby_share` is the one place this is decided; it takes frames from any
caller, so the thumbnail picker can use the same rule.

Each detector was checked against the labelled moments of the tuning videos in eval/; the U2 PR has the numbers and
the detectors that were tried and dropped (voice brightness for shouting, speech rate, GTA HUD colour checks).
Overlapping speakers need speaker turns, which no configured provider gives (U1), so there is no such signal.
"""
import re
import subprocess
import threading
import wave
from pathlib import Path

import numpy as np

from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout

RATE = 8000                     # samples per second of the decoded audio, as signals.audio_rms_db
AUDIO = ("audio_flux", "audio_bursts")
FRAMES = ("scene",)
SCENE_STEP = 2.0                # seconds between the frames the scene signal compares
STILL = 1.0                     # mean grey-level change (0-255) between key frames below which nothing moved
STANDBY_REJECT = 0.9            # share of a candidate's seconds that are standby at which it is never a clip
THUMB_W, THUMB_H = 160, 90      # the size key frames are compared at


def _seek(start: float, length: float | None) -> list[str]:
    return [] if length is None else ["-ss", f"{max(start, 0.0):.3f}", "-t", f"{length:.3f}"]


def audio_timeline(path: Path, deadline: Deadline | None = None, start: float = 0.0,
                   length: float | None = None) -> tuple[list[float], dict[str, list[float]]]:
    """One decode of the audio: the RMS level in dB per second, exactly as signals.audio_rms_db measures it, and the
    audio signals. The samples come through a pipe; nothing is written to disk."""
    # Two outputs of one decode, each with the `-ac 1` the level measurement always had, so its numbers are
    # signals.audio_rms_db's to the last digit: the levels go to stderr, the samples to the pipe.
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-nostdin", *_seek(start, length), *SAFE_IN,
           "-i", str(path),
           "-vn", "-ac", "1", "-af", f"aresample={RATE},asetnsamples=n={RATE},astats=metadata=1:reset=1,"
           "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=/dev/stderr", "-f", "null", "-",
           "-vn", "-ac", "1", "-af", f"aresample={RATE}", "-f", "f32le", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    err: list[bytes] = []
    reader = threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True)
    reader.start()
    killer = None
    if deadline is not None and deadline.at is not None:
        killer = threading.Timer(max(1.0, deadline.remaining()), proc.kill)     # never past the job's deadline
        killer.start()
    feats = Features()
    try:
        while True:
            buf = proc.stdout.read(RATE * 4 * 60)
            if not buf:
                break
            feats.feed(np.frombuffer(buf, dtype=np.float32))
        proc.wait()
    finally:
        if killer is not None:
            killer.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    reader.join()
    if deadline is not None:
        deadline.remaining()                       # raises when the time ran out (the kill above)
    if proc.returncode != 0:
        raise PipelineError("media_error", "Could not read this video's audio.")
    text = (err[0] if err else b"").decode("utf-8", "replace")
    vals = re.findall(r"RMS_level=(\S+)", text)
    levels = [max(-90.0, -90.0 if v in ("-inf", "inf", "nan") else float(v)) for v in vals]
    return levels, feats.done()


def wav_timeline(wav: Path, start: float = 0.0, length: float | None = None) -> dict[str, list[float]]:
    """The audio signals from a 16 kHz mono WAV the caller already decoded (stt.extract_audio)."""
    feats = Features()
    with wave.open(str(wav), "rb") as w:
        rate = w.getframerate()
        step = rate // RATE                        # 16 kHz: every 2 samples averaged into one
        w.setpos(min(w.getnframes(), int(start * rate)))
        left = None if length is None else int(length * rate)
        while left is None or left > 0:
            n = rate * 60 if left is None else min(rate * 60, left)
            buf = w.readframes(n)
            if not buf:
                break
            x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
            x = x[: len(x) // step * step].reshape(-1, step).mean(axis=1)
            feats.feed(x)
            if left is not None:
                left -= n
    return feats.done()


class Features:
    """The per-second audio signals from 8 kHz mono samples, fed in chunks of any size."""

    def __init__(self):
        self.rest = np.zeros(0, dtype=np.float32)
        self.prev: np.ndarray | None = None
        f = np.fft.rfftfreq(RATE, 1 / RATE)
        self.voice = (f >= 100) & (f < 3500)
        mf = np.fft.rfftfreq(100, 1 / 100)
        self.syllable = (mf >= 3) & (mf <= 7)
        self.out: dict[str, list[float]] = {k: [] for k in AUDIO}

    def feed(self, x: np.ndarray, last: bool = False) -> None:
        x = np.concatenate([self.rest, x])
        n = len(x) // RATE
        if last and len(x) > n * RATE:             # the last part of a second, padded as the level measurement does
            x = np.concatenate([x, np.zeros(RATE - (len(x) - n * RATE), np.float32)])
            n += 1
        if n == 0:
            self.rest = x
            return
        fr = x[: n * RATE].reshape(n, RATE).astype(np.float64)
        self.rest = x[n * RATE:]
        spec = np.abs(np.fft.rfft(fr * np.hanning(RATE), axis=1)) ** 2
        logs = np.log(spec[:, self.voice] + 1e-9)
        first = 0.0 if self.prev is None else float(np.abs(logs[0] - self.prev).mean())
        self.out["audio_flux"] += [first, *np.abs(np.diff(logs, axis=0)).mean(axis=1).tolist()]
        self.prev = logs[-1]
        env = np.sqrt((fr.reshape(n, 100, RATE // 100) ** 2).mean(axis=2))     # loudness 100 times a second
        env -= env.mean(axis=1, keepdims=True)
        mod = np.abs(np.fft.rfft(env, axis=1)) ** 2
        self.out["audio_bursts"] += (mod[:, self.syllable].sum(axis=1) / (mod[:, 1:].sum(axis=1) + 1e-12)).tolist()

    def done(self) -> dict[str, list[float]]:
        if len(self.rest):
            self.feed(np.zeros(0, np.float32), last=True)
        return self.out


def scene_changes(path: Path, deadline: Deadline | None = None, start: float = 0.0,
                  length: float | None = None) -> list[float]:
    """How much the picture changes, per second: the mean grey-level difference between key frames SCENE_STEP
    apart (each value repeated for the seconds it covers)."""
    from .visual import iter_frames
    diffs, prev = [], None
    for batch in iter_frames(path, SCENE_STEP, True, deadline):
        for frame in batch:
            g = frame.astype(np.float32).mean(axis=2)
            diffs.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
            prev = g
    per_sec = np.repeat(np.asarray(diffs), int(SCENE_STEP)).tolist()
    a = int(start)
    return per_sec[a:] if length is None else per_sec[a:a + int(np.ceil(length))]


def keyframes(path: Path, start: float, length: float, deadline: Deadline | None = None) -> list[tuple[float, np.ndarray]]:
    """The key frames inside [start, start + length] as (source second, grey THUMB_W x THUMB_H array). Only key
    frames are decoded, so this costs a small part of decoding the span."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "info", "-nostdin", "-skip_frame", "nokey",
           *_seek(start, length), *SAFE_IN, "-i", str(path), "-an",
           "-vf", f"scale={THUMB_W}:{THUMB_H},format=gray,showinfo", "-fps_mode", "passthrough",
           "-f", "rawvideo", "pipe:1"]
    timeout = deadline.remaining(120.0) if deadline else 120.0
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise PipelineTimeout() from None
    if res.returncode != 0:
        return []
    times = [float(t) for t in re.findall(rb"pts_time:\s*(-?[\d.]+)", res.stderr)]
    size = THUMB_W * THUMB_H
    frames = [np.frombuffer(res.stdout[i * size:(i + 1) * size], np.uint8) for i in range(len(res.stdout) // size)]
    return [(start + t, f.reshape(THUMB_H, THUMB_W)) for t, f in zip(times, frames)]


def standby_seconds(frames: list[tuple[float, np.ndarray]], start: float, end: float,
                    speech: list[tuple[float, float]] | None = None) -> np.ndarray | None:
    """Which whole seconds of [start, end) are standby: the picture did not change between the key frames around
    them, and (when `speech`, the spoken words' (start, end) in source seconds, is known) nobody spoke. Frames are
    grey arrays of one size, any size. None when there are too few key frames to tell."""
    if len(frames) < 2:
        return None
    n = max(1, int(round(end - start)))
    times = np.array([t for t, _ in frames])
    moved = np.array([float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())
                      for (_, a), (_, b) in zip(frames, frames[1:])])
    secs = start + np.arange(n) + 0.5
    pair = np.clip(np.searchsorted(times, secs) - 1, 0, len(moved) - 1)     # the key frames around each second
    out = moved[pair] < STILL
    for a, b in speech or []:
        out[max(0, int(a - start)):max(0, int(np.ceil(b - start)))] = False
    return out


def standby_share(frames: list[tuple[float, np.ndarray]], start: float, end: float,
                  speech: list[tuple[float, float]] | None = None) -> float:
    """The share of [start, end) that is standby (0 when it cannot be told)."""
    sec = standby_seconds(frames, start, end, speech)
    return 0.0 if sec is None else round(float(sec.mean()), 3)
