"""Window selection, ported from test-tools/auto_clip.py."""
import numpy as np


def pick_windows(per_sec, length: int, count: int, duration: float) -> list[tuple[float, float, float]]:
    """Highest-scoring non-overlapping windows. Returns (start, end, mean_score), sorted by score."""
    scores = np.asarray(per_sec, dtype=float).copy()
    n = len(scores)
    if n <= length:
        return [(0.0, float(min(duration, length)), float(scores.mean()) if n else 0.0)]
    # Skip intros and outros: first 3% and last 5% (at least 10 s each) when the video is long enough.
    head, tail = max(10, int(n * 0.03)), max(10, int(n * 0.05))
    if n - head - tail > length * count:
        scores[:head] = 0.0
        scores[n - tail:] = 0.0
    csum = np.concatenate([[0.0], np.cumsum(scores)])
    sums = csum[length:] - csum[:-length]          # sums[i] = total score of window starting at i
    taken = np.zeros(len(sums), dtype=bool)
    picks = []
    for _ in range(count):
        masked = np.where(taken, -1.0, sums)
        i = int(masked.argmax())
        if masked[i] <= 0:
            break
        picks.append((float(i), float(min(i + length, duration)), float(sums[i] / length)))
        # Block nearby windows so clips are at least one clip-length apart.
        taken[max(0, i - 2 * length + 1): min(len(sums), i + 2 * length)] = True
    return picks
