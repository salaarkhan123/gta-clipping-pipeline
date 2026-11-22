"""Job typing for live clipping without a schema migration.

A live session's clip-making work is an ordinary Job row whose `options.tool` is `live_clip`
(same pattern as `premium_thumbnail` / `export`). No new column; additive `live_session_id` on Clip
waits for a coordinated Alembic revision after security `0012`.
"""
from __future__ import annotations

from typing import Any

LIVE_CLIP_TOOL = "live_clip"


def is_live_clip_job(options: dict | None) -> bool:
    return bool(options) and options.get("tool") == LIVE_CLIP_TOOL


def live_clip_options(
    *,
    session_id: str,
    mode: str = "mock",
    max_minutes: int | None = None,
    rights_confirmed: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical options blob for a live_clip job. Credits are not reserved here (billing off)."""
    out: dict[str, Any] = {
        "tool": LIVE_CLIP_TOOL,
        "live_session_id": session_id,
        "mode": mode,  # mock | scaffold | production (production not wired)
        "rights_confirmed": bool(rights_confirmed),
    }
    if max_minutes is not None:
        out["max_minutes"] = int(max_minutes)
    if extra:
        out.update(extra)
    return out
