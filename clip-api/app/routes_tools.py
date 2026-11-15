"""Single-purpose tools: Reframe, Captions and Video Finder. They share uploads, jobs and credits with /v1/clips."""
import json
import uuid

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .models import Upload
from .plans import plan_of
from .pipeline.tools import search_transcript
from .routes_media import LayoutOptions, credits_for, own_upload, submit_job
from typing import Literal

from .storage import get_storage, transcript_key, vindex_key

router = APIRouter()


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def check(self):
        if self.end - self.start < 1:
            raise ValueError("each segment must be at least 1 second long")
        return self


class ReframeOptions(LayoutOptions):
    vertical: bool = True
    captions: bool = False


class CaptionOptions(LayoutOptions):
    vertical: bool = False      # keep the source framing by default; set true to reframe as well
    captions: bool = True


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str
    segments: list[Segment] | None = Field(default=None, min_length=1, max_length=10)
    webhook_url: str | None = Field(default=None, max_length=500)


class ReframeRequest(RenderRequest):
    options: ReframeOptions = ReframeOptions()


class CaptionRequest(RenderRequest):
    options: CaptionOptions = CaptionOptions()


class FindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str
    query: str = Field(min_length=1, max_length=200)
    mode: Literal["auto", "speech", "visual"] = "auto"
    max_results: int = Field(5, ge=1, le=10)
    make_clips: bool = True
    clip_length: int = Field(30, ge=10, le=60)
    options: LayoutOptions = LayoutOptions()
    webhook_url: str | None = Field(default=None, max_length=500)


def _render_plan(body: RenderRequest, need_audio: bool, account):
    def plan(upload: Upload):
        s = get_settings()
        if need_audio and not upload.has_audio:
            raise ApiError(422, "no_audio", "This video has no audio track, so there is nothing to caption.")
        segs = [[x.start, x.end] for x in body.segments] if body.segments else [[0.0, upload.duration_sec]]
        for seg in segs:
            if seg[0] >= upload.duration_sec or seg[1] > upload.duration_sec + 0.5:
                raise ApiError(422, "bad_segment",
                               f"Segments must fall inside the video (0 to {upload.duration_sec:.0f} s).")
            seg[1] = min(seg[1], upload.duration_sec)
        total = sum(b - a for a, b in segs)
        plan = plan_of(account)
        cap = min(s.max_render_sec, plan["max_render_min"] * 60 if plan.get("max_render_min") else s.max_render_sec)
        if total > cap:
            raise ApiError(413, "range_too_long",
                           f"The {plan['name']} plan renders up to {cap // 60} minutes per job. "
                           "Pass shorter segments or upgrade.")
        return {"tool": "render", "segments": segs, **body.options.model_dump()}, total, credits_for(total)
    return plan


@router.post("/v1/reframe", status_code=202)
def reframe(body: ReframeRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
            idempotency_key: str | None = Header(default=None, max_length=200)):
    """AI Reframe: turn a whole video, or chosen segments, into 9:16 with the chosen layout. No detection."""
    return submit_job(db, p, body.upload_id, body.webhook_url, idempotency_key, _render_plan(body, False, p.account))


@router.post("/v1/captions", status_code=202)
def captions(body: CaptionRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
             idempotency_key: str | None = Header(default=None, max_length=200)):
    """AI Caption Generator: burn word-highlight captions into a whole video or chosen segments."""
    return submit_job(db, p, body.upload_id, body.webhook_url, idempotency_key, _render_plan(body, True, p.account))


@router.post("/v1/find", status_code=202)
def find(body: FindRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
         idempotency_key: str | None = Header(default=None, max_length=200)):
    """AI Video Finder: find moments by what was said and (optionally) cut a clip around each match.

    Searches speech (transcript) and what is on screen (visual index); `mode` picks one or both.
    A video is charged 1 credit per minute once, by whichever of Clip Maker or Video Finder runs on it first.
    After that, searches cost only the clips they render, and GET /v1/uploads/{id}/search is free.
    """
    def plan(upload: Upload):
        s, storage = get_settings(), get_storage()
        speech_ok = upload.has_audio and body.mode in ("auto", "speech")
        visual_ok = s.visual_search and body.mode in ("auto", "visual")
        if not speech_ok and not visual_ok:
            if body.mode == "visual":
                raise ApiError(422, "visual_unavailable", "Visual search is turned off on this server.")
            raise ApiError(422, "no_audio", "This video has no audio track to search.")
        opts = {"tool": "find", "query": body.query.strip(), "mode": body.mode, "max_results": body.max_results,
                "make_clips": body.make_clips, "clip_length": body.clip_length, **body.options.model_dump()}
        needs_index = ((speech_ok and not storage.exists(transcript_key(upload.id)))
                       or (visual_ok and not storage.exists(vindex_key(upload.id))))
        render_sec = max(60.0, body.max_results * body.clip_length if body.make_clips else 0.0)
        processed = upload.duration_sec if needs_index else render_sec
        paid = upload.analyzed and s.charge_once_per_upload
        cost = credits_for(upload.duration_sec) if needs_index and not paid else credits_for(render_sec)
        return opts, processed, cost
    return submit_job(db, p, body.upload_id, body.webhook_url, idempotency_key, plan)


@router.get("/v1/uploads/{upload_id}/search")
def search_upload(upload_id: str, q: str = Query(min_length=1, max_length=200),
                  limit: int = Query(5, ge=1, le=20),
                  p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Instant, free search of an upload that has already been transcribed by POST /v1/find."""
    upload = own_upload(db, p, upload_id)
    storage, key = get_storage(), transcript_key(upload.id)
    if not storage.exists(key):
        raise ApiError(409, "not_transcribed",
                       "This upload has not been transcribed yet. Run POST /v1/find on it once first.")
    tmp = get_settings().work_dir / f"tr_{uuid.uuid4().hex}.json"
    try:
        storage.fetch(key, tmp)
        transcript = json.loads(tmp.read_text())
    finally:
        tmp.unlink(missing_ok=True)
    return {"upload_id": upload.id, "query": q, "matches": search_transcript(transcript, q, limit)}
