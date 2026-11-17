"""A moment (one candidate clip, before it is rendered) and the clip-length buckets a request can ask for.

The shapes here are shared with the renderer and the worker (docs/CONTRACTS.md). Nothing in this module
touches files, ffmpeg or the database.
"""
from dataclasses import dataclass

KINDS = ("funny", "argument", "reaction", "clutch", "fail", "story")


@dataclass
class Moment:           # one candidate clip, before rendering
    start: float        # seconds in the source
    end: float
    score: float        # 0-100 once judged; without a judge, the signal strength (0 to about 1), as ClipResult.score
    kind: str | None    # one of KINDS
    why: str | None     # one sentence from the judge
    peak: float | None  # source second where the most striking part begins, when the judge named one
    signals: dict
    features: dict
    meta: dict | None


# Clip length buckets: name -> (shortest, longest) clip in seconds, both included.
BUCKETS = {"0-30": (0, 30), "0-90": (0, 90), "30-60": (30, 60), "60-90": (60, 90), "90-180": (90, 180), "180-300": (180, 300)}

# The window length (seconds) candidates are nominated at for each bucket. A judge may then cut anywhere in the bucket.
NOMINAL = {"0-30": 20, "0-90": 45, "30-60": 45, "60-90": 75, "90-180": 120, "180-300": 240}

MAX_CLIPS = 50          # the most clips one run returns, whatever is asked for


def kind_of(value) -> str | None:
    """`value` as one of KINDS, or None."""
    kind = str(value or "").strip().lower()
    return kind if kind in KINDS else None
