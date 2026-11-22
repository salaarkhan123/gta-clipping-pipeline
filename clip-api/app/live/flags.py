"""LIVE_CLIPPING kill switch — default off.

Read from the environment only so this scaffold does not edit fenced `app/config.py` while
security #274 is open. After that lands, a follow-up may add `Settings.live_clipping` and a DEPLOY.md
row; callers should keep using these helpers.
"""
from __future__ import annotations

import os

from ..deps import ApiError

_TRUE = frozenset({"1", "true", "yes", "on"})


def live_clipping_enabled() -> bool:
    return os.environ.get("LIVE_CLIPPING", "false").strip().lower() in _TRUE


def require_live_clipping() -> None:
    """404 while the flag is off — same honesty pattern as publishing / premium thumbs."""
    if not live_clipping_enabled():
        raise ApiError(404, "live_clipping_off", "Live clipping is not available yet.")
