"""Rolling segment buffer for live ingest.

Holds closed segment metadata (and optional audio RMS samples) for a fixed retention window.
Does not decode or transcode — production will read fMP4 segments written by the ingest server
via file paths only (`-protocol_whitelist file,pipe` still holds).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Segment:
    """One closed ingest segment on the stream timeline."""

    index: int
    start_sec: float
    duration_sec: float
    path: Path | None = None
    # Optional per-second RMS (dB) already measured for this segment; mock poller fills these.
    rms_db: tuple[float, ...] = ()

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec


@dataclass
class RollingSegmentBuffer:
    """Ring of closed segments covering at most `retention_sec` of stream time."""

    retention_sec: float = 600.0
    segment_sec: float = 2.0
    _segments: deque[Segment] = field(default_factory=deque)
    _next_index: int = 0

    def __len__(self) -> int:
        return len(self._segments)

    @property
    def covered_sec(self) -> float:
        return sum(s.duration_sec for s in self._segments)

    @property
    def head_sec(self) -> float | None:
        return self._segments[0].start_sec if self._segments else None

    @property
    def tail_sec(self) -> float | None:
        return self._segments[-1].end_sec if self._segments else None

    def append(self, segment: Segment | None = None, *, duration_sec: float | None = None,
               path: Path | None = None, rms_db: Sequence[float] = ()) -> Segment:
        """Append a closed segment. If `segment` is omitted, allocate the next index on the timeline."""
        if segment is None:
            start = self.tail_sec if self.tail_sec is not None else 0.0
            dur = float(duration_sec if duration_sec is not None else self.segment_sec)
            segment = Segment(
                index=self._next_index,
                start_sec=start,
                duration_sec=dur,
                path=path,
                rms_db=tuple(float(x) for x in rms_db),
            )
        self._next_index = max(self._next_index, segment.index + 1)
        self._segments.append(segment)
        self._trim()
        return segment

    def extend(self, segments: Iterable[Segment]) -> None:
        for s in segments:
            self.append(s)

    def segments(self) -> list[Segment]:
        return list(self._segments)

    def rms_timeline(self) -> list[float]:
        """Concatenate per-second RMS values in stream order (gaps not invented)."""
        out: list[float] = []
        for s in self._segments:
            out.extend(s.rms_db)
        return out

    def slice_paths(self, start_sec: float, end_sec: float) -> list[Path]:
        """Paths of segments overlapping [start_sec, end_sec). Skips segments without a path."""
        paths: list[Path] = []
        for s in self._segments:
            if s.end_sec <= start_sec or s.start_sec >= end_sec:
                continue
            if s.path is not None:
                paths.append(s.path)
        return paths

    def clear(self) -> None:
        self._segments.clear()

    def _trim(self) -> None:
        while self._segments and self.covered_sec > self.retention_sec + 1e-9:
            # Drop oldest whole segments until under retention (never partial-trim a segment).
            if len(self._segments) == 1:
                break
            self._segments.popleft()
            if self.covered_sec <= self.retention_sec:
                break
        # If a single segment is somehow longer than retention, keep it (edge case for tests).
        while len(self._segments) > 1 and self.covered_sec > self.retention_sec + 1e-9:
            self._segments.popleft()
