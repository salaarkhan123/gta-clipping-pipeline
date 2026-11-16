"""Per-stage timing for one pipeline run, so every change to speed reports a number.

    timer = Timer()
    with timer.stage("render"):
        ...
    timer.count("clips", 3)
    timer.as_dict()  ->  {"stages": {"render": 12.3}, "counts": {"clips": 3}}

Stages may repeat (the time adds up) and may be entered from several threads. Nesting is allowed but the times
then overlap, so the pipeline keeps its stages flat: they add up to (almost) the whole run.
"""
import threading
import time
from contextlib import contextmanager


class Timer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.stages: dict[str, float] = {}
        self.counts: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        start = time.monotonic()
        try:
            yield
        finally:      # a stage that fails still took the time it took
            self.add(name, time.monotonic() - start)

    def add(self, name: str, seconds: float) -> None:
        with self._lock:
            self.stages[name] = self.stages.get(name, 0.0) + seconds

    def count(self, name: str, n: float = 1) -> None:
        with self._lock:
            self.counts[name] = self.counts.get(name, 0) + n

    def as_dict(self) -> dict:
        with self._lock:
            return {"stages": {k: round(v, 2) for k, v in self.stages.items()},
                    "counts": {k: round(v, 2) if isinstance(v, float) else v for k, v in self.counts.items()}}
