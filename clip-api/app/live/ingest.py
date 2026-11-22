"""Segment poll / ingest hooks for live clipping.

Production will authenticate RTMP/SRT publishes and call `on_segment_complete` when MediaMTX
closes a 2 s segment. This module defines the hook surface and a mock poller that synthesises
segments (no network, no DRM bypass). Public live URL pull is refused elsewhere (`live_channel`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .buffer import RollingSegmentBuffer, Segment


class SegmentIngest(Protocol):
    """Anything that can feed closed segments into a buffer."""

    def poll(self) -> list[Segment]:
        ...


OnSegmentComplete = Callable[[Segment], None]


@dataclass
class IngestHooks:
    """Callbacks the ingest server (or mock) invokes. Auth failure must not record bytes."""

    on_publish_auth: Callable[[str], bool] | None = None  # stream key → allow?
    on_segment_complete: OnSegmentComplete | None = None
    on_publisher_gone: Callable[[], None] | None = None

    def authorize(self, stream_key: str) -> bool:
        if self.on_publish_auth is None:
            return False
        return bool(self.on_publish_auth(stream_key))

    def segment_complete(self, segment: Segment) -> None:
        if self.on_segment_complete is not None:
            self.on_segment_complete(segment)


@dataclass
class MockSegmentPoller:
    """Synthetic segment source for local tests — no ffmpeg, no GPU, no remote fetch.

    Each poll emits one segment of `segment_sec` with optional RMS samples. Loud bursts can be
    scheduled via `loud_windows` (start_sec, end_sec, rms_db).
    """

    buffer: RollingSegmentBuffer
    hooks: IngestHooks = field(default_factory=IngestHooks)
    segment_sec: float = 2.0
    quiet_rms_db: float = -40.0
    loud_rms_db: float = -12.0
    loud_windows: list[tuple[float, float]] = field(default_factory=list)
    _t: float = 0.0
    _done: bool = False
    max_sec: float = 120.0

    def poll(self) -> list[Segment]:
        if self._done or self._t >= self.max_sec:
            self._done = True
            return []
        start = self._t
        rms = []
        for i in range(int(round(self.segment_sec))):
            sec = start + i
            level = self.quiet_rms_db
            for lo, hi in self.loud_windows:
                if lo <= sec < hi:
                    level = self.loud_rms_db
                    break
            rms.append(level)
        seg = self.buffer.append(duration_sec=self.segment_sec, path=None, rms_db=rms)
        self._t = seg.end_sec
        self.hooks.segment_complete(seg)
        return [seg]


@dataclass
class FileSegmentHook:
    """Register a closed segment file into the buffer (ingest server → API bridge)."""

    buffer: RollingSegmentBuffer
    hooks: IngestHooks = field(default_factory=IngestHooks)

    def on_segment_complete(self, path: Path | None, *, start_sec: float, duration_sec: float,
                            rms_db: list[float] | None = None) -> Segment:
        seg = Segment(
            index=self.buffer._next_index,
            start_sec=start_sec,
            duration_sec=duration_sec,
            path=Path(path) if path is not None else None,
            rms_db=tuple(rms_db or ()),
        )
        self.buffer.append(seg)
        self.hooks.segment_complete(seg)
        return seg
