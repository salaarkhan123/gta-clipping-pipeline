"""Inventory and time existing production signals (shadow evaluation)."""
from __future__ import annotations

import resource
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SignalReport:
    source: str
    duration_sec: float
    range_sec: dict | None
    wall_sec: dict[str, float]
    peak_rss_mb: float
    series_lengths: dict[str, int]
    active_weights: dict[str, float]
    zero_weight_skipped: list[str]
    notes: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def measure_signals(
    video: Path,
    *,
    start: float = 0.0,
    length: float | None = 40.0,
    chat_region: str = "none",
) -> SignalReport:
    """Measure audio / flux / bursts / scene / optional chat on a ranged excerpt.

    Does not enable experimental sound/HUD weights. Scene remains weight 0 in production
    but is measured here as a shadow cost because WEIGHTS['scene'] == 0 skips it in-pipeline.
    """
    from app.pipeline import WEIGHTS
    from app.pipeline import signals as sig
    from app.pipeline import timeline as tl

    notes = []
    walls: dict[str, float] = {}
    lengths: dict[str, int] = {}
    rss0 = _rss_mb()

    t0 = time.perf_counter()
    levels, audio_feats = tl.audio_timeline(Path(video), start=start, length=length)
    walls["audio_timeline"] = round(time.perf_counter() - t0, 3)
    lengths["audio_rms"] = len(levels)
    for name, series in audio_feats.items():
        lengths[name] = len(series)

    t0 = time.perf_counter()
    # Shadow: scene is weight 0 in production; measure a ranged keyframe decode cost.
    span = float(length if length is not None else 0.0)
    frames = tl.keyframes(Path(video), start=start, length=max(span, 0.1)) if span > 0 else []
    lengths["scene_keyframes"] = len(frames)
    walls["scene_keyframes"] = round(time.perf_counter() - t0, 3)
    notes.append(
        "scene/keyframe decode measured in shadow mode; production WEIGHTS['scene']=0 skips this path."
    )

    if chat_region != "none":
        t0 = time.perf_counter()
        chat = sig.onscreen_chat_motion(Path(video), chat_region, start=start, length=length)
        walls["chat_motion"] = round(time.perf_counter() - t0, 3)
        lengths["chat_motion"] = 0 if chat is None else len(chat)
    else:
        walls["chat_motion"] = 0.0
        lengths["chat_motion"] = 0
        notes.append("chat_region=none (production default); chat motion not computed.")

    notes.append(
        "Named sound (YAMNet) and HUD OCR adapters are not on this research head; "
        "evaluate offline after #231/#232 integrate at weight zero."
    )
    notes.append("Transcript/judge arms require authorized ASR/judge caches (B1); not run here.")

    zero_skipped = [k for k, v in WEIGHTS.items() if float(v) <= 0]
    return SignalReport(
        source=Path(video).name,
        duration_sec=float(length or 0.0),
        range_sec={"start": start, "end": start + (length or 0.0)},
        wall_sec=walls,
        peak_rss_mb=round(max(rss0, _rss_mb()), 1),
        series_lengths=lengths,
        active_weights={k: float(v) for k, v in WEIGHTS.items() if float(v) > 0},
        zero_weight_skipped=zero_skipped,
        notes=notes,
    )
