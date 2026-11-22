"""Live clipping (AS-3 / CPR-79): rolling buffer + detect stubs + mock pipeline.

Behind LIVE_CLIPPING (default false). Creator-push ingest only — never pull Twitch/Kick/YouTube live
video. Full design: docs/live-clipping.md and the store architecture doc. This package has no web or
database code in the core loop; routes are a thin flag gate.
"""
from .flags import live_clipping_enabled, require_live_clipping
from .jobs import LIVE_CLIP_TOOL, is_live_clip_job, live_clip_options

__all__ = [
    "LIVE_CLIP_TOOL",
    "is_live_clip_job",
    "live_clip_options",
    "live_clipping_enabled",
    "require_live_clipping",
]
