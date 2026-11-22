"""Low-latency highlight detector stub for live (trailing baseline).

CPU-only. Does not claim production quality or a measured false-positive rate — callers must
supply labelled windows before promoting thresholds. Live uses a *trailing* baseline (past only);
VOD `signals.baseline_z` is centred and is not reused here on purpose.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class Trigger:
    """A confirmed highlight fire on the stream clock (seconds from session start)."""

    at_sec: float
    score: float
    audio_z: float
    chat_z: float = 0.0


@dataclass
class DetectorConfig:
    baseline_sec: int = 300          # trailing window for median/MAD
    warm_sec: int = 60               # no triggers until baseline has this many samples
    threshold: float = 1.5           # fused score must clear this
    confirm_of: int = 3              # look at last N seconds
    confirm_need: int = 2            # need this many above threshold
    refractory_sec: float = 45.0
    audio_weight: float = 0.7
    chat_weight: float = 1.0
    mad_floor: float = 1.0


@dataclass
class HighlightDetector:
    """Stateful per-second detector. Feed one sample at a time (or a batch) as segments close."""

    config: DetectorConfig = field(default_factory=DetectorConfig)
    _audio: list[float] = field(default_factory=list)
    _chat: list[float] = field(default_factory=list)
    _last_fire_sec: float | None = None
    triggers: list[Trigger] = field(default_factory=list)

    @property
    def seconds_seen(self) -> int:
        return len(self._audio)

    def reset(self) -> None:
        self._audio.clear()
        self._chat.clear()
        self._last_fire_sec = None
        self.triggers.clear()

    def push(self, audio_rms_db: float, chat_rate: float = 0.0) -> Trigger | None:
        """Append one second of signal; maybe return a new trigger."""
        self._audio.append(float(audio_rms_db))
        self._chat.append(float(chat_rate))
        return self._maybe_fire(len(self._audio) - 1)

    def push_batch(self, audio_rms_db: Sequence[float], chat_rate: Sequence[float] | None = None) -> list[Trigger]:
        chat = list(chat_rate) if chat_rate is not None else [0.0] * len(audio_rms_db)
        if len(chat) < len(audio_rms_db):
            chat = chat + [0.0] * (len(audio_rms_db) - len(chat))
        found: list[Trigger] = []
        for a, c in zip(audio_rms_db, chat, strict=False):
            t = self.push(a, c)
            if t is not None:
                found.append(t)
        return found

    def trailing_z(self, series: Sequence[float], index: int) -> float:
        """Positive z of series[index] vs median/MAD of the trailing baseline window (past only)."""
        cfg = self.config
        start = max(0, index - cfg.baseline_sec)
        window = list(series[start:index])  # exclude current sample from baseline
        if len(window) < 2:
            return 0.0
        med = _median(window)
        mad = _median([abs(x - med) for x in window])
        scale = max(1.4826 * mad, cfg.mad_floor)
        z = (series[index] - med) / scale
        return z if z > 0.0 else 0.0

    def fused_at(self, index: int) -> tuple[float, float, float]:
        audio_z = self.trailing_z(self._audio, index)
        chat_z = self.trailing_z(self._chat, index) if any(self._chat) else 0.0
        cfg = self.config
        fused = cfg.audio_weight * audio_z + cfg.chat_weight * chat_z
        return fused, audio_z, chat_z

    def _maybe_fire(self, index: int) -> Trigger | None:
        cfg = self.config
        if index + 1 < cfg.warm_sec:
            return None
        if self._last_fire_sec is not None and (index - self._last_fire_sec) < cfg.refractory_sec:
            return None
        # Confirm: need confirm_need of the last confirm_of seconds above threshold.
        start = max(0, index - cfg.confirm_of + 1)
        hits = 0
        last_fused = last_az = last_cz = 0.0
        for i in range(start, index + 1):
            fused, az, cz = self.fused_at(i)
            if i == index:
                last_fused, last_az, last_cz = fused, az, cz
            if fused >= cfg.threshold:
                hits += 1
        if hits < cfg.confirm_need or last_fused < cfg.threshold:
            return None
        trig = Trigger(at_sec=float(index), score=round(last_fused, 4), audio_z=round(last_az, 4),
                       chat_z=round(last_cz, 4))
        self._last_fire_sec = float(index)
        self.triggers.append(trig)
        return trig


def false_positive_rate(triggers: Sequence[Trigger], highlight_intervals: Sequence[tuple[float, float]],
                        total_sec: float, *, hit_radius_sec: float = 5.0) -> dict:
    """Measure FPR when labels exist. Without labels, callers should not invent a rate.

    A trigger is a true positive if it falls within `hit_radius_sec` of any labelled highlight
    interval; otherwise a false positive. Returns `measured: false` when labels or duration missing.
    """
    if total_sec <= 0 or not highlight_intervals:
        return {
            "measured": False,
            "reason": "need labelled highlight intervals and total_sec > 0",
            "triggers": len(triggers),
        }
    tp = fp = 0
    for t in triggers:
        if any(lo - hit_radius_sec <= t.at_sec <= hi + hit_radius_sec for lo, hi in highlight_intervals):
            tp += 1
        else:
            fp += 1
    non_highlight_sec = max(total_sec - sum(max(0.0, hi - lo) for lo, hi in highlight_intervals), 1e-9)
    return {
        "measured": True,
        "true_positives": tp,
        "false_positives": fp,
        "false_positives_per_non_highlight_minute": round(fp / (non_highlight_sec / 60.0), 4),
        "triggers": len(triggers),
        "total_sec": total_sec,
    }


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])
