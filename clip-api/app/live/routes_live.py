"""Public /v1/live/* routes — 404 while LIVE_CLIPPING is off.

When the flag is on this exposes a **scaffold / mock** surface only: no MediaMTX, no credits, no
preview files, no dashboard success chrome. FE must stay Soon until a measured path exists.
"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ..deps import ApiError, Principal, current_principal
from .buffer import RollingSegmentBuffer
from .detect import DetectorConfig, HighlightDetector
from .flags import live_clipping_enabled, require_live_clipping
from .ingest import FileSegmentHook, IngestHooks
from .jobs import LIVE_CLIP_TOOL
from .mock_pipeline import run_mock_live_pipeline

router = APIRouter(tags=["live"])

_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rights_confirmed: bool = False
    max_minutes: int = Field(default=60, ge=1, le=480)
    mode: str = Field(default="mock", pattern="^(mock|scaffold)$")


class SegmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_sec: float = Field(ge=0)
    duration_sec: float = Field(default=2.0, gt=0, le=30)
    rms_db: list[float] = Field(default_factory=list)
    # Path is accepted only for local/dev scaffolding; production will pass server-side paths only.
    path: str | None = None


def listing() -> dict | None:
    """What GET /v1/options may include: None while the flag is off."""
    if not live_clipping_enabled():
        return None
    return {
        "available": True,
        "mode": "scaffold",
        "tool": LIVE_CLIP_TOOL,
        "note": ("Live clipping is scaffold-only: mock detect and timings, no measured real-time claim, "
                 "no creator ingest server in this build."),
        "credits": None,  # price not set; LIVE_BILLING off
    }


@router.get("/v1/live/status", summary="Live clipping flag and scaffold honesty")
def live_status():
    """Public. Always answers: when off, `enabled: false` (not a 404) so the site can keep Soon honest."""
    enabled = live_clipping_enabled()
    body: dict[str, Any] = {
        "enabled": enabled,
        "tool": LIVE_CLIP_TOOL,
        "measured_realtime": False,
        "note": ("Live clipping is off." if not enabled else
                 "Scaffold only — mock pipeline; do not treat timings as product latency."),
    }
    if enabled:
        body["listing"] = listing()
    return body


@router.post("/v1/live/sessions", status_code=201, summary="Start a scaffold live session")
def create_session(body: SessionCreate, principal: Principal = Depends(current_principal)):
    require_live_clipping()
    if not body.rights_confirmed:
        raise ApiError(422, "rights_required",
                       "Confirm you own the stream or have permission to clip it (rights_confirmed).")
    sid = f"ls_{secrets.token_hex(8)}"
    buf = RollingSegmentBuffer()
    det = HighlightDetector(DetectorConfig(warm_sec=30, threshold=1.2, refractory_sec=20.0))
    hooks = IngestHooks(on_publish_auth=lambda key: key == sid)  # placeholder key == session id
    with _LOCK:
            _SESSIONS[sid] = {
            "id": sid,
            "account_id": principal.account.id,
            "state": "LIVE",
            "mode": body.mode,
            "max_minutes": body.max_minutes,
            "rights_confirmed": True,
            "created_at": time.time(),
            "buffer": buf,
            "detector": det,
            "hooks": hooks,
            "file_hook": FileSegmentHook(buffer=buf, hooks=hooks),
            "candidates": [],
            "timings_ms": {},
        }
    return {
        "id": sid,
        "state": "LIVE",
        "mode": body.mode,
        "tool": LIVE_CLIP_TOOL,
        "ingest": {
            "status": "scaffold",
            "note": "No RTMP/SRT endpoint in this build. Push segments via POST .../segments or run mock.",
            "stream_key_hint": "not issued — MediaMTX wiring is residual",
        },
        "measured_realtime": False,
    }


@router.get("/v1/live/sessions/{session_id}", summary="Scaffold session state")
def get_session(session_id: str, principal: Principal = Depends(current_principal)):
    require_live_clipping()
    sess = _own_session(session_id, principal.account.id)
    buf: RollingSegmentBuffer = sess["buffer"]
    det: HighlightDetector = sess["detector"]
    return {
        "id": sess["id"],
        "state": sess["state"],
        "mode": sess["mode"],
        "seconds_buffered": buf.covered_sec,
        "segments": len(buf),
        "triggers": len(det.triggers),
        "candidates": sess["candidates"],
        "timings_ms": sess["timings_ms"],
        "measured_realtime": False,
    }


@router.post("/v1/live/sessions/{session_id}/segments", summary="Ingest hook: closed segment")
def post_segment(session_id: str, body: SegmentIn, principal: Principal = Depends(current_principal)):
    require_live_clipping()
    sess = _own_session(session_id, principal.account.id)
    hook: FileSegmentHook = sess["file_hook"]
    from pathlib import Path
    path = Path(body.path) if body.path else None
    t0 = time.perf_counter()
    seg = hook.on_segment_complete(
        path,
        start_sec=body.start_sec,
        duration_sec=body.duration_sec,
        rms_db=body.rms_db,
    )
    det: HighlightDetector = sess["detector"]
    new_triggers = det.push_batch(body.rms_db) if body.rms_db else []
    sess["timings_ms"]["last_segment_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
    return {
        "segment": {"index": seg.index, "start_sec": seg.start_sec, "end_sec": seg.end_sec},
        "new_triggers": [{"at_sec": t.at_sec, "score": t.score, "audio_z": t.audio_z, "chat_z": t.chat_z}
                         for t in new_triggers],
        "measured_realtime": False,
    }


@router.post("/v1/live/sessions/{session_id}/mock", summary="Run local mock pipeline into this session")
def run_mock(session_id: str, principal: Principal = Depends(current_principal)):
    require_live_clipping()
    sess = _own_session(session_id, principal.account.id)
    result = run_mock_live_pipeline(session_id=session_id, rights_confirmed=True)
    sess["candidates"] = [
        {"start_sec": c.start_sec, "end_sec": c.end_sec, "score": c.score, "rank": c.rank}
        for c in result.candidates
    ]
    sess["timings_ms"] = result.timings_ms
    sess["state"] = "LIVE"
    # Also feed the session detector from the mock so GET shows trigger count.
    det: HighlightDetector = sess["detector"]
    det.reset()
    for t in result.triggers:
        det.triggers.append(t)
    return result.as_dict()


@router.post("/v1/live/mock", summary="One-shot mock live pipeline (no session persistence)")
def one_shot_mock(principal: Principal = Depends(current_principal)):
    require_live_clipping()
    _ = principal  # auth required; no credits charged
    return run_mock_live_pipeline().as_dict()


def _own_session(session_id: str, account_id: str) -> dict[str, Any]:
    with _LOCK:
        sess = _SESSIONS.get(session_id)
    if sess is None or sess["account_id"] != account_id:
        raise ApiError(404, "not_found", "Live session not found.")
    return sess
