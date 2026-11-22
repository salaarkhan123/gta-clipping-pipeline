"""One-click Generate Highlights: how many clips automatic discovery aims for.

Used when a duration bucket is set and the caller did not set `limit` (JobSetup "Auto",
url_clips.with_defaults). The quality floor still decides which moments become clips — this is
only the upper bound, so a short VOD is not treated like a 2-hour run, and a 2-hour VOD still
aims at the SPEC §14 band (30–50) without inventing filler to hit a quota.
"""
from .moments import MAX_CLIPS

# ~1 slot per three minutes of analysed source. 2 h → 40 (inside 30–50); short VODs stay small.
SEC_PER_SLOT = 180.0
MIN_WANT = 3


def suggest_want(span_sec: float) -> int:
    """Upper bound for automatic discovery from analysed length (seconds). Clamped to [MIN_WANT, MAX_CLIPS]."""
    if span_sec <= 0:
        return MIN_WANT
    return max(MIN_WANT, min(MAX_CLIPS, round(span_sec / SEC_PER_SLOT)))
