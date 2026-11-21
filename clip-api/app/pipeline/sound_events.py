"""Named sound events (gunshot, explosion, siren, crash, scream, laughter).

Each series is one score in [0, 1] per second of a 16 kHz mono waveform. Second i is the
second of the samples that were passed in. The pipeline adds a series to the moment score
only when its weight in WEIGHTS is above 0, and it does not call this module otherwise.
Every default weight is 0, so a job's candidates stay as they are until a weight is raised
on purpose, after the class has been measured.

YAMNet is the detector (AudioSet, Apache-2.0). TensorFlow and the model graph load on the
first call, never at import. Tests pass a detector and never download it. `heuristic_detector`
is a tiny stand-in for those tests and for a machine that has no TensorFlow. It is not
calibrated, and the pipeline does not use it.
"""
import os
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .ff import PipelineError

EVENTS = ("gunshot", "explosion", "siren", "crash", "scream", "laughter")
RATE = 16000
# YAMNet's patch window and hop (research/audioset/yamnet/params.py). A patch covers
# PATCH_WINDOW_SECONDS and the next patch starts PATCH_HOP_SECONDS later.
PATCH_HOP_SECONDS = 0.48
PATCH_WINDOW_SECONDS = 0.96
N_CLASSES = 521
YAMNET_URL = "https://tfhub.dev/google/yamnet/1"

# Column and display name in yamnet_class_map.csv. The name sits next to the index so a
# different class map cannot be applied to these columns and still look like the same event.
YAMNET_CLASSES: dict[str, tuple[tuple[int, str], ...]] = {
    "gunshot": (
        (421, "Gunshot, gunfire"),
        (422, "Machine gun"),
        (423, "Fusillade"),
        (424, "Artillery fire"),
        (425, "Cap gun"),
    ),
    "explosion": (
        (420, "Explosion"),
        (429, "Eruption"),
        (430, "Boom"),
    ),
    "siren": (
        (390, "Siren"),
        (391, "Civil defense siren"),
        (316, "Emergency vehicle"),
        (317, "Police car (siren)"),
        (318, "Ambulance (siren)"),
        (319, "Fire engine, fire truck (siren)"),
    ),
    "crash": (
        (463, "Smash, crash"),
        (464, "Breaking"),
        (306, "Skidding"),
        (307, "Tire squeal"),
    ),
    "scream": (
        (11, "Screaming"),
        (6, "Shout"),
        (9, "Yell"),
    ),
    "laughter": (
        (13, "Laughter"),
        (14, "Baby laughter"),
        (15, "Giggle"),
        (16, "Snicker"),
        (17, "Belly laugh"),
        (18, "Chuckle, chortle"),
    ),
}

Detector = Callable[[np.ndarray, int], dict[str, list[float]]]

_yamnet: "YamnetDetector | None" = None


def score_wav(path: Path, start: float = 0.0, length: float | None = None,
              detector: Detector | None = None) -> dict[str, list[float]]:
    """Scores for each event, one value per second of the 16 kHz mono WAV at `path`.

    `start` and `length` select a span of that file, in seconds. `detector` replaces YAMNet.
    """
    samples, rate = _read_wav(Path(path), start, length)
    return score_samples(samples, rate, detector)


def score_samples(samples: np.ndarray, sample_rate: int,
                  detector: Detector | None = None) -> dict[str, list[float]]:
    """Scores for each event, one value per second. Second 0 starts at the first sample."""
    if int(sample_rate) != RATE:
        raise PipelineError("media_error", "Sound events need 16 kHz audio.")
    samples = np.asarray(samples, dtype=np.float32)
    n = _seconds(len(samples), RATE)
    if n == 0:
        return {name: [] for name in EVENTS}
    det = detector if detector is not None else yamnet_detector()
    raw = det(samples, RATE)
    if not isinstance(raw, dict):
        raise PipelineError("sound_events_unavailable", "The sound-event detector returned no scores.")
    return {name: _fit(raw.get(name), n) for name in EVENTS}


def yamnet_detector() -> "YamnetDetector":
    """The process-wide YAMNet detector. The graph is loaded the first time it scores audio."""
    global _yamnet
    if _yamnet is None:
        _yamnet = YamnetDetector(os.environ.get("YAMNET_MODEL", YAMNET_URL))
    return _yamnet


class YamnetDetector:
    """YAMNet (Apache-2.0). Constructing it does not import TensorFlow or download the model."""

    def __init__(self, url: str = YAMNET_URL):
        self.url = url
        self._model = None

    def __call__(self, samples: np.ndarray, sample_rate: int) -> dict[str, list[float]]:
        if int(sample_rate) != RATE:
            raise PipelineError("media_error", "YAMNet scores 16 kHz audio.")
        if self._model is None:
            self._model = _load_yamnet(self.url)
        scores = _yamnet_matrix(self._model, samples)
        return events_from_yamnet_scores(scores, _seconds(len(samples), RATE))


def events_from_yamnet_scores(scores: np.ndarray, n_seconds: int) -> dict[str, list[float]]:
    """Map a YAMNet score matrix (frames, 521) onto one value per second for each event.

    A second's score is the loudest patch of that event whose window overlaps the second.
    """
    scores = np.asarray(scores, dtype=np.float64)
    if scores.ndim != 2 or scores.shape[1] != N_CLASSES:
        raise PipelineError("sound_events_unavailable", "YAMNet returned an unexpected class vector.")
    out = {}
    for event, rows in YAMNET_CLASSES.items():
        cols = [index for index, _name in rows]
        frame = scores[:, cols].max(axis=1) if len(scores) else np.zeros(0)
        out[event] = pool_patches(frame, n_seconds)
    return out


def pool_patches(frame_scores: np.ndarray, n_seconds: int, hop: float = PATCH_HOP_SECONDS,
                 window: float = PATCH_WINDOW_SECONDS) -> list[float]:
    """Max-pool patch scores into whole seconds. Patch i covers [i * hop, i * hop + window)."""
    frame_scores = np.asarray(frame_scores, dtype=np.float64)
    out = np.zeros(max(0, n_seconds), dtype=np.float64)
    if n_seconds <= 0 or len(frame_scores) == 0:
        return out.tolist()
    for i, score in enumerate(frame_scores):
        a = min(max(int(np.floor(i * hop)), 0), n_seconds)
        b = min(int(np.ceil(i * hop + window - 1e-9)), n_seconds)
        if b > a:
            out[a:b] = np.maximum(out[a:b], score)
    return out.tolist()


def heuristic_detector(samples: np.ndarray, sample_rate: int) -> dict[str, list[float]]:
    """A stand-in detector with no model.

    A short impulse scores as a gunshot, a low rumble as an explosion, a steady mid tone as a
    siren, a high tone as a scream, broadband noise as a crash, and a 3 to 7 Hz loudness pulse
    as laughter. The numbers are not a measurement of those sounds. They only give tests a
    detector that reads the samples.
    """
    if int(sample_rate) != RATE:
        raise PipelineError("media_error", "Sound events need 16 kHz audio.")
    x = np.asarray(samples, dtype=np.float32)
    n = _seconds(len(x), RATE)
    if n == 0:
        return {name: [] for name in EVENTS}
    pad = n * RATE - len(x)
    if pad:
        x = np.concatenate([x, np.zeros(pad, np.float32)])
    frames = x.reshape(n, RATE)
    window = np.hanning(RATE).astype(np.float32)
    power = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    freqs = np.fft.rfftfreq(RATE, 1.0 / RATE)
    total = power[:, 1:].sum(axis=1) + 1e-12

    def band(lo: float, hi: float) -> np.ndarray:
        mask = (freqs >= lo) & (freqs < hi)
        return power[:, mask].sum(axis=1) / total

    low = band(0, 200)
    siren_band = band(500, 1800)
    scream_band = band(1800, 4500)
    usable = power[:, 1:] + 1e-12
    flat = np.exp(np.mean(np.log(usable), axis=1)) / np.mean(usable, axis=1)
    tonal = 1.0 - flat
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    peak = np.max(np.abs(frames), axis=1)
    crest = peak / (rms + 1e-8)
    hop = RATE // 100
    env = np.sqrt(np.mean(frames.reshape(n, 100, hop) ** 2, axis=2))
    env -= env.mean(axis=1, keepdims=True)
    mod = np.abs(np.fft.rfft(env, axis=1)) ** 2
    mf = np.fft.rfftfreq(100, 0.01)
    syllable = (mf >= 3) & (mf <= 7)
    bursts = mod[:, syllable].sum(axis=1) / (mod[:, 1:].sum(axis=1) + 1e-12)
    loud = np.clip(rms / 0.05, 0.0, 1.0)
    sustained = np.clip((6.0 - crest) / 4.0, 0.0, 1.0)
    scores = {
        "gunshot": np.clip((crest - 8.0) / 12.0, 0.0, 1.0) * np.clip(peak / 0.4, 0.0, 1.0),
        "explosion": np.clip(low - 0.55, 0.0, 1.0) * loud * np.clip((10.0 - crest) / 6.0, 0.0, 1.0),
        "siren": np.clip(tonal - 0.55, 0.0, 1.0) * np.clip(siren_band - 0.4, 0.0, 1.0) * loud * sustained,
        "scream": np.clip(tonal - 0.55, 0.0, 1.0) * np.clip(scream_band - 0.4, 0.0, 1.0) * loud * sustained,
        "crash": (np.clip(flat - 0.35, 0.0, 1.0) * loud * np.clip((12.0 - crest) / 8.0, 0.0, 1.0)
                  * np.clip(1.0 - low, 0.0, 1.0)),
        "laughter": np.clip((bursts - 0.25) / 0.4, 0.0, 1.0) * loud,
    }
    return {name: np.clip(scores[name], 0.0, 1.0).tolist() for name in EVENTS}


def _load_yamnet(url: str):
    try:
        import tensorflow_hub as hub
    except ImportError as exc:
        raise PipelineError(
            "sound_events_unavailable",
            "Named sound events need tensorflow-hub and the YAMNet model, which are not installed.") from exc
    return hub.load(url)


def _yamnet_matrix(model, samples: np.ndarray) -> np.ndarray:
    import tensorflow as tf
    waveform = tf.constant(np.asarray(samples, dtype=np.float32))
    scores, _embeddings, _spectrogram = model(waveform)
    return np.asarray(scores)


def _read_wav(path: Path, start: float, length: float | None) -> tuple[np.ndarray, int]:
    try:
        handle = wave.open(str(path), "rb")
    except (wave.Error, EOFError, FileNotFoundError) as exc:
        raise PipelineError("media_error", "Sound events need a 16 kHz mono WAV.") from exc
    with handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2 or handle.getframerate() != RATE:
            raise PipelineError("media_error", "Sound events need a 16 kHz mono WAV.")
        total = handle.getnframes()
        begin = min(total, max(0, int(start * RATE)))
        handle.setpos(begin)
        count = total - begin if length is None else max(0, int(length * RATE))
        count = min(count, total - begin)
        raw = handle.readframes(count)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0, RATE


def _seconds(n_samples: int, rate: int) -> int:
    if n_samples <= 0:
        return 0
    return int(np.ceil(n_samples / rate))


def _fit(vals, n: int) -> list[float]:
    if not vals:
        return [0.0] * n
    out = [float(v) for v in list(vals)[:n]]
    if len(out) < n:
        out.extend([0.0] * (n - len(out)))
    return out
