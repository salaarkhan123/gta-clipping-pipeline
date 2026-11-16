"""Window selection, ported from test-tools/auto_clip.py."""
import numpy as np

SPREAD_PARTS = 4              # pick_spread guarantees candidates from each quarter of the video
SPREAD_MIN_DURATION = 1200    # ... on videos of 20 minutes or more; shorter ones use the plain ranking


def _window_sums(per_sec, length: int, count: int) -> np.ndarray:
    """sums[i] = total score of the window starting at second i, with intro and outro zeroed."""
    scores = np.asarray(per_sec, dtype=float).copy()
    n = len(scores)
    # Skip intros and outros: first 3% and last 5% (at least 10 s each) when the video is long enough.
    head, tail = max(10, int(n * 0.03)), max(10, int(n * 0.05))
    if n - head - tail > length * count:
        scores[:head] = 0.0
        scores[n - tail:] = 0.0
    csum = np.concatenate([[0.0], np.cumsum(scores)])
    return csum[length:] - csum[:-length]


def _greedy(sums: np.ndarray, taken: np.ndarray, length: int, count: int, lo: int = 0, hi: int | None = None) -> list[int]:
    """Start seconds of the best `count` free windows in [lo, hi), best first. Marks them and their surroundings taken."""
    hi = len(sums) if hi is None else hi
    picks = []
    for _ in range(count):
        masked = np.where(taken[lo:hi], -1.0, sums[lo:hi])
        if not len(masked):
            break
        i = lo + int(masked.argmax())
        if sums[i] <= 0 or taken[i]:
            break
        picks.append(i)
        # Block nearby windows so clips are at least one clip-length apart.
        taken[max(0, i - 2 * length + 1): min(len(sums), i + 2 * length)] = True
    return picks


def _windows(starts: list[int], sums: np.ndarray, length: int, duration: float) -> list[tuple[float, float, float]]:
    out = [(float(i), float(min(i + length, duration)), float(sums[i] / length)) for i in starts]
    return sorted(out, key=lambda w: w[2], reverse=True)


def pick_windows(per_sec, length: int, count: int, duration: float) -> list[tuple[float, float, float]]:
    """Highest-scoring non-overlapping windows. Returns (start, end, mean_score), sorted by score."""
    n = len(per_sec)
    if n <= length:
        return [(0.0, float(min(duration, length)), float(np.mean(per_sec)) if n else 0.0)]
    sums = _window_sums(per_sec, length, count)
    return _windows(_greedy(sums, np.zeros(len(sums), dtype=bool), length, count), sums, length, duration)


def pick_spread(per_sec, length: int, count: int, duration: float, floor: int | None = None) -> list[tuple[float, float, float]]:
    """pick_windows, but each quarter of a long video first gets `floor` windows (default count // 6) before
    the rest go to the strongest moments anywhere. Same count, same spacing, same return shape.

    Loudness is scored against a rolling baseline, so a part of the video that is spikier against its own
    baseline can take nearly every slot (the 0.2e coverage check: 23 of 30 candidates from the second hour).
    This is for nominating candidates to a judge that then decides; a quarter with no signal gets nothing.
    """
    n = len(per_sec)
    floor = count // 6 if floor is None else floor
    if n <= length or floor < 1 or duration < SPREAD_MIN_DURATION:
        return pick_windows(per_sec, length, count, duration)
    sums = _window_sums(per_sec, length, count)
    taken = np.zeros(len(sums), dtype=bool)
    starts: list[int] = []
    for k in range(SPREAD_PARTS):
        lo, hi = k * len(sums) // SPREAD_PARTS, (k + 1) * len(sums) // SPREAD_PARTS
        starts += _greedy(sums, taken, length, floor, lo, hi)
    starts += _greedy(sums, taken, length, count - len(starts))
    return _windows(starts, sums, length, duration)
