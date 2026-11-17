"""The score a clip shows: the AI's raw 0-100 rating, calibrated across the clips of one job.

Pure functions, no database and no web code. The formula is the one in docs/CONTRACTS.md, "Score calibration (A)":
the best clip of a job shows 90 to 99 (higher when its raw score is higher), the weakest sits up to 40 points
below it and never under 55, and the others are spread between the two in proportion to their raw scores.
Nothing here is stored: the display score is worked out each time clips are read. The raw numbers are untouched.
"""
import math
from typing import Sequence

TOP_MIN, TOP_MAX = 90, 99      # what the best clip of a job shows
RAW_LOW, RAW_SPAN = 40, 50     # a best raw score of 40 or less shows TOP_MIN; 90 or more shows TOP_MAX
FLOOR, SPREAD = 55, 40         # the lowest score ever shown; how far below the top the weakest clip sits


def ai_score(meta: dict | None) -> int | float | None:
    """The AI's raw 0-100 score from a clip's stored meta, or None when the AI did not rate the clip. The same
    test as the tier (routes_media.tier_of), so a clip has a display score exactly when it has a tier: a number
    made from loudness alone (source "signals") is not a rating."""
    virality = (meta or {}).get("virality") or {}
    if (meta or {}).get("source") == "signals" or not isinstance(virality.get("score"), (int, float)):
        return None
    return virality["score"]


def display_scores(raw: Sequence[int | float | None]) -> list[int | None]:
    """One job's raw AI scores in, the score each clip shows out, in the same order. None stays None.

    With hi and lo the highest and lowest raw score among the rated clips:
        top     = 90 + 9 * clamp((hi - 40) / 50, 0, 1)
        floor   = max(55, top - 40)
        display = round(floor + (top - floor) * (s - lo) / (hi - lo))      # halves round up
    One rated clip, or all equal: every rated clip shows `top`. The result is a whole number from 55 to 99 and
    the best clip always shows 90 to 99. A higher raw score never shows a lower number and equal raw scores
    show the same number; two raw scores close together can round to the same number.

    Pass the scores of the job's stored (not deleted) clips: the scale runs from the best to the weakest clip
    that is still there, the same set the rank is counted over. Deleting a clip in the middle changes nothing
    for the others; deleting the best or the weakest one moves the scale to the clips that remain.
    """
    rated = [s for s in raw if s is not None]
    if not rated:
        return [None] * len(raw)
    hi, lo = max(rated), min(rated)
    top = TOP_MIN + (TOP_MAX - TOP_MIN) * min(1.0, max(0.0, (hi - RAW_LOW) / RAW_SPAN))
    floor = max(float(FLOOR), top - SPREAD)

    def shown(s: int | float) -> int:
        value = top if hi == lo else floor + (top - floor) * (s - lo) / (hi - lo)
        return int(math.floor(value + 0.5))

    return [None if s is None else shown(s) for s in raw]
