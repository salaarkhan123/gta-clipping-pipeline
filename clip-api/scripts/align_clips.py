"""Find where clips cut from a long video came from, by their audio. For scoring another tool's clips (Wayin)
against the eval set: see `label_moments.py wayin` and eval/README.md.

Audio is decoded at 16 kHz mono and turned into 24 log band energies every 20 ms. A probe window of the clip
(WINDOW seconds) is slid along the source and compared band by band (Pearson correlation, averaged over the bands):
the best place is where the probe came from, and the correlation there is the match's confidence.

A clip's start and end are aligned separately, because the other tool trims dead air: a clip can be several source
pieces, so its source span is longer than the clip. Each end tries up to PROBES windows, stepping inward, in case
the clip opens or closes on something added (an intro, a sound effect). A match is refused, never guessed, when:
- the confidence is under MIN_CONFIDENCE (0.85, chosen from the measurements below), or another place
  more than 3 s away scores within MIN_MARGIN of it
  (repetitive audio: music loops, silence);
- the start lands after the end, or the span is more than 3x the clip plus 60 s (the two ends are not one moment),
  or shorter than the clip minus 1 s (the source cannot be shorter than what was cut from it).
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.ff import SAFE_IN, PipelineError, run_bytes  # noqa: E402

RATE, HOP, NFFT, BANDS = 16000, 320, 1024, 24       # 50 frames a second
FPS = RATE / HOP
WINDOW, PROBES = 6.0, 3
# Measured 2026-11-17 on the two local test sources (a 78-minute reaction stream, the 2-hour GTA Online benchmark):
# 6 s probes from the other video reached at most 0.76 (95th percentile 0.63 to 0.67, 80 probes); pieces cut out of
# the right video and re-encoded (AAC, loudness-normalised, +6 dB, a 15 s gap removed) matched at 0.97 to 1.00.
MIN_CONFIDENCE, MIN_MARGIN = 0.85, 0.1
EXCLUDE = 3.0                                        # seconds around the best place that the runner-up may not use


def decode(path: Path, cap: float = 1800.0) -> np.ndarray:
    raw = run_bytes(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", *SAFE_IN, "-i", path, "-vn",
                     "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"], cap=cap)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _band_matrix() -> np.ndarray:
    freqs = np.fft.rfftfreq(NFFT, 1 / RATE)
    edges = np.geomspace(100.0, 7000.0, BANDS + 1)
    return np.stack([(freqs >= lo) & (freqs < hi) for lo, hi in zip(edges, edges[1:])], axis=1).astype(np.float32)


def features(samples: np.ndarray) -> np.ndarray:
    """(frames, BANDS) log band energies, one frame every 20 ms."""
    n = max(0, (len(samples) - NFFT) // HOP + 1)
    out = np.empty((n, BANDS), dtype=np.float32)
    bands, win = _band_matrix(), np.hanning(NFFT).astype(np.float32)
    step = 20000
    for a in range(0, n, step):
        b = min(n, a + step)
        idx = (np.arange(a, b) * HOP)[:, None] + np.arange(NFFT)[None, :]
        spec = np.abs(np.fft.rfft(samples[idx] * win, axis=1)) ** 2
        out[a:b] = np.log10(spec.astype(np.float32) @ bands + 1e-9)
    return out


class Source:
    """A long video's features, with what sliding a probe along them needs computed once."""

    def __init__(self, feats: np.ndarray):
        self.feats = feats.astype(np.float64)
        self.n = len(feats)
        self.size = 1 << int(np.ceil(np.log2(max(2, self.n + int(WINDOW * FPS)))))
        self.spec = np.fft.rfft(self.feats.T, n=self.size, axis=1)
        zero = np.zeros((1, BANDS))
        self.c1 = np.concatenate([zero, np.cumsum(self.feats, axis=0)])
        self.c2 = np.concatenate([zero, np.cumsum(self.feats ** 2, axis=0)])

    @classmethod
    def of(cls, path: Path) -> "Source":
        return cls(features(decode(path)))

    def locate(self, probe: np.ndarray) -> tuple[int, float, float]:
        """(frame, confidence, runner-up) of the probe's best place in the source."""
        m = len(probe)
        if m < 10 or self.n < m:
            return 0, 0.0, 0.0
        q = probe.astype(np.float64)
        q_std = q.std(axis=0)
        use = q_std > 1e-3                                   # flat bands (silence, a cut-off filter) say nothing
        if not use.any():
            return 0, 0.0, 0.0
        qz = (q[:, use] - q[:, use].mean(axis=0)) / q_std[use]
        dots = np.fft.irfft(self.spec[use] * np.conj(np.fft.rfft(qz.T, n=self.size, axis=1)), n=self.size, axis=1)
        offsets = self.n - m + 1
        dots = dots[:, :offsets]
        s1 = self.c1[m:m + offsets, use] - self.c1[:offsets, use]
        s2 = self.c2[m:m + offsets, use] - self.c2[:offsets, use]
        var = np.maximum(s2 / m - (s1 / m) ** 2, 0.0)
        std = np.sqrt(var)
        corr = np.where(std.T > 1e-3, dots / (m * np.maximum(std.T, 1e-9)), 0.0).mean(axis=0)
        best = int(np.argmax(corr))
        ex = int(EXCLUDE * FPS)
        rest = np.concatenate([corr[:max(0, best - ex)], corr[best + ex + 1:]])
        return best, float(corr[best]), float(rest.max()) if len(rest) else -1.0


@dataclass
class Match:
    file: str
    ok: bool
    why: str
    clip_seconds: float
    start: float | None = None          # source seconds
    end: float | None = None
    start_confidence: float = 0.0
    end_confidence: float = 0.0
    start_probe_at: float = 0.0         # clip seconds where the start probe that matched begins
    end_probe_at: float = 0.0           # clip seconds where the end probe that matched ends (from the clip's end)
    trimmed: float | None = None        # source span minus clip length: what was cut out of the middle

    def as_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def _probe(src: Source, clip: np.ndarray, from_end: bool) -> tuple[int, float, float, float]:
    """(source frame of the matched probe's first frame, confidence, margin, clip seconds stepped in)."""
    m = int(min(WINDOW, len(clip) / FPS / 2) * FPS)
    best = (0, 0.0, 0.0, 0.0)
    for i in range(PROBES):
        a = len(clip) - m - i * m if from_end else i * m
        if a < 0 or a + m > len(clip):
            break
        frame, conf, runner = src.locate(clip[a:a + m])
        tried = (frame, conf, conf - runner, i * m / FPS)
        if conf >= MIN_CONFIDENCE and conf - runner >= MIN_MARGIN:
            return tried
        best = max(best, tried, key=lambda t: t[1])
    return best


def align(src: Source, clip_path: Path, clip: np.ndarray | None = None) -> Match:
    clip = features(decode(clip_path)) if clip is None else clip
    length = len(clip) / FPS
    if length < 4.0:
        return Match(clip_path.name, False, "clip under 4 s: too short to align", round(length, 2))
    m = int(min(WINDOW, length / 2) * FPS)
    s_frame, s_conf, s_margin, s_in = _probe(src, clip, from_end=False)
    e_frame, e_conf, e_margin, e_in = _probe(src, clip, from_end=True)
    start = s_frame / FPS - s_in
    end = (e_frame + m) / FPS + e_in
    out = Match(clip_path.name, False, "", round(length, 2), round(start, 2), round(end, 2), s_conf, e_conf,
                s_in, e_in, round(end - start - length, 2))
    for side, conf, margin in (("start", s_conf, s_margin), ("end", e_conf, e_margin)):
        if conf < MIN_CONFIDENCE:
            out.why = f"{side} not found (confidence {conf:.2f} < {MIN_CONFIDENCE})"
            return out
        if margin < MIN_MARGIN:
            out.why = f"{side} ambiguous (another place scores within {margin:.2f})"
            return out
    span = end - start
    if span <= 0:
        out.why = "start aligns after the end"
    elif span > 3 * length + 60:
        out.why = f"start and end are {span:.0f} s apart for a {length:.0f} s clip: not one moment"
    elif span < length - 1.0:
        out.why = f"source span {span:.1f} s is shorter than the {length:.1f} s clip"
    else:
        out.ok, out.why = True, "ok"
    return out
