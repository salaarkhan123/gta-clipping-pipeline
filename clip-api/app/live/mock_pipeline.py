"""Local mock live pipeline: segments → detect → ranked candidate windows.

Safe for CI: no network, no GPU, no ffmpeg required. Timings are wall clocks for the mock steps
only — they are not product latency claims. Ranking is by detector score (descending); the real
judge is not called here (fenced vs AS-1 scoring work).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from .buffer import RollingSegmentBuffer
from .detect import DetectorConfig, HighlightDetector, Trigger, false_positive_rate
from .ingest import IngestHooks, MockSegmentPoller
from .jobs import LIVE_CLIP_TOOL, live_clip_options


@dataclass(frozen=True)
class LiveCandidate:
    start_sec: float
    end_sec: float
    score: float
    trigger: Trigger
    rank: int


@dataclass
class MockLiveResult:
    session_id: str
    tool: str
    mode: str
    seconds_processed: float
    triggers: list[Trigger]
    candidates: list[LiveCandidate]
    timings_ms: dict[str, float]
    fpr: dict
    options: dict
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "tool": self.tool,
            "mode": self.mode,
            "seconds_processed": self.seconds_processed,
            "triggers": [asdict(t) for t in self.triggers],
            "candidates": [
                {
                    "start_sec": c.start_sec,
                    "end_sec": c.end_sec,
                    "score": c.score,
                    "rank": c.rank,
                    "trigger": asdict(c.trigger),
                }
                for c in self.candidates
            ],
            "timings_ms": self.timings_ms,
            "fpr": self.fpr,
            "options": self.options,
            "notes": list(self.notes),
        }


def run_mock_live_pipeline(
    *,
    session_id: str = "live_mock",
    duration_sec: float = 90.0,
    loud_windows: list[tuple[float, float]] | None = None,
    highlight_labels: list[tuple[float, float]] | None = None,
    pre_roll_sec: float = 20.0,
    post_roll_sec: float = 10.0,
    detector: HighlightDetector | None = None,
    rights_confirmed: bool = True,
) -> MockLiveResult:
    """Drive a mock poller for `duration_sec`, detect, and rank candidate windows.

    `highlight_labels` optional: when provided, FPR is measured; otherwise `fpr.measured` is false.
    """
    notes = [
        "mock pipeline only — not a measured live product latency",
        "no preview render, no Whisper, no AI judge, no credits reserved",
        "do not claim real-time from timings_ms without live_bench on real ingest",
    ]
    t0 = time.perf_counter()
    buf = RollingSegmentBuffer(retention_sec=600.0, segment_sec=2.0)
    det = detector or HighlightDetector(DetectorConfig(warm_sec=30, threshold=1.2, refractory_sec=20.0))
    windows = loud_windows if loud_windows is not None else [(40.0, 48.0), (70.0, 76.0)]
    poller = MockSegmentPoller(
        buffer=buf,
        hooks=IngestHooks(),
        segment_sec=2.0,
        loud_windows=windows,
        max_sec=duration_sec,
    )

    t_ingest = time.perf_counter()
    while True:
        segs = poller.poll()
        if not segs:
            break
        for seg in segs:
            det.push_batch(seg.rms_db)
    ingest_ms = (time.perf_counter() - t_ingest) * 1000.0

    t_rank = time.perf_counter()
    candidates: list[LiveCandidate] = []
    for trig in det.triggers:
        start = max(0.0, trig.at_sec - pre_roll_sec)
        end = trig.at_sec + post_roll_sec
        candidates.append(LiveCandidate(start_sec=start, end_sec=end, score=trig.score, trigger=trig, rank=0))
    candidates.sort(key=lambda c: c.score, reverse=True)
    ranked = [
        LiveCandidate(start_sec=c.start_sec, end_sec=c.end_sec, score=c.score, trigger=c.trigger, rank=i)
        for i, c in enumerate(candidates)
    ]
    rank_ms = (time.perf_counter() - t_rank) * 1000.0

    fpr = false_positive_rate(det.triggers, highlight_labels or [], duration_sec)
    total_ms = (time.perf_counter() - t0) * 1000.0
    opts = live_clip_options(session_id=session_id, mode="mock", rights_confirmed=rights_confirmed,
                             max_minutes=max(1, int(duration_sec // 60) + 1))

    return MockLiveResult(
        session_id=session_id,
        tool=LIVE_CLIP_TOOL,
        mode="mock",
        seconds_processed=float(buf.tail_sec or 0.0),
        triggers=list(det.triggers),
        candidates=ranked,
        timings_ms={
            "ingest_and_detect_ms": round(ingest_ms, 3),
            "rank_ms": round(rank_ms, 3),
            "total_wall_ms": round(total_ms, 3),
        },
        fpr=fpr,
        options=opts,
        notes=notes,
    )
