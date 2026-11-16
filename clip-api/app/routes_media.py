"""Uploads, clip jobs, results and credits."""
import json
import math
import re
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ledger
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .models import Clip, ClipFeedback, CreditLedger, Job, Upload, new_id, utcnow
from .pipeline import PipelineError, probe
from .security import is_public_https_url, read_token
from .storage import LocalStorage, get_storage

router = APIRouter()
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".flv", ".ts"}
ACTIVE = ("QUEUED", "RUNNING")


class LayoutOptions(BaseModel):
    """How a clip is framed and captioned. Shared by every tool."""
    model_config = ConfigDict(extra="forbid")
    vertical: bool = True
    aspect: Literal["9:16", "4:5", "1:1", "16:9"] = "9:16"
    chat_region: Literal["none", "top-right", "top-center", "top-left", "bottom-right", "bottom-left"] = "none"
    zoom: float = Field(1.0, ge=1.0, le=1.6)
    captions: bool = True
    caption_style: Literal["pop", "bold", "neon", "boxed", "clean"] = "pop"
    censor: bool = False          # mask swears in burned captions and subtitle downloads (f***ing)
    layout: Literal["auto", "split", "fill", "classic"] = "auto"
    facecam_region: Literal["auto", "top-left", "top-right", "bottom-left", "bottom-right"] | None = "auto"
    facecam_box: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def check_layout(self):
        if self.facecam_box is not None:
            x, y, w, h = self.facecam_box
            if not (0 <= x < 1 and 0 <= y < 1 and 0.05 <= w <= 1 and 0.05 <= h <= 1 and x + w <= 1 and y + h <= 1):
                raise ValueError("facecam_box must be [x, y, w, h] fractions inside the frame")
        if self.layout == "split" and not (self.facecam_box or self.facecam_region):
            raise ValueError("layout 'split' needs facecam_region or facecam_box")
        return self


class ClipOptions(LayoutOptions):
    max_clips: int = Field(3, ge=1, le=10)
    clip_length: int = Field(30, ge=10, le=60)
    tighten: bool = True          # cut silences over 0.6 s and filler words out of each clip
    punch_zoom: bool = True       # subtle punch-in zooms (max 1.15x) on the gameplay at loudness spikes
    flash_forward: bool = True    # open on 1.5 s of the clip's peak, then cut back (AI clips only)
    hook_overlay: bool = True     # burn the AI's on-screen hook text over the first 2.5 s (AI clips only)


class ClipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str
    options: ClipOptions = ClipOptions()
    webhook_url: str | None = Field(default=None, max_length=500)


class Feedback(BaseModel):
    """Send only what changes. `kept` and `reaction` accept null to clear them."""
    model_config = ConfigDict(extra="forbid")
    kept: bool | None = None
    reaction: Literal["like", "dislike"] | None = None
    bookmarked: bool | None = None

    @model_validator(mode="after")
    def _something(self):
        if not self.model_fields_set:
            raise ValueError("send at least one of kept, reaction, bookmarked")
        if "bookmarked" in self.model_fields_set and self.bookmarked is None:
            raise ValueError("bookmarked must be true or false")
        return self


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


def credits_for(duration_sec: float) -> int:
    return max(1, math.ceil(duration_sec / 60))


def upload_json(u: Upload) -> dict:
    return {"upload_id": u.id, "filename": u.filename, "size_bytes": u.size_bytes,
            "duration_sec": round(u.duration_sec, 2), "width": u.width, "height": u.height,
            "has_audio": u.has_audio, "analyzed": bool(u.analyzed), "credits_required": credits_for(u.duration_sec),
            "created_at": iso(u.created_at), "expires_at": iso(u.expires_at)}


TIERS = ((75, "top"), (55, "strong"), (35, "solid"), (0, "long_shot"))


def tier_of(meta: dict | None) -> str | None:
    """A fixed label for the AI's 0-100 score. None when the AI did not rate the clip: a score derived from
    loudness alone says how a moment compares inside its own video, not how good it is."""
    v = (meta or {}).get("virality") or {}
    if (meta or {}).get("source") == "signals" or not isinstance(v.get("score"), (int, float)):
        return None
    return next(name for floor, name in TIERS if v["score"] >= floor)


def with_ranks(db: Session, clips: list[dict]) -> list[dict]:
    """Adds rank and rank_of: each clip's position by score among the stored clips of its own run."""
    job_ids = {c["job_id"] for c in clips}
    order: dict[str, list[str]] = {}
    if job_ids:
        for clip_id, job_id in db.execute(select(Clip.id, Clip.job_id).where(
                Clip.job_id.in_(job_ids), Clip.deleted_at.is_(None)).order_by(Clip.score.desc(), Clip.idx)):
            order.setdefault(job_id, []).append(clip_id)
    return [{**c, "rank": order[c["job_id"]].index(c["id"]) + 1, "rank_of": len(order[c["job_id"]])} for c in clips]


def clip_json(c: Clip, storage) -> dict:
    return {"id": c.id, "job_id": c.job_id, "index": c.idx, "start_sec": c.start_sec, "end_sec": c.end_sec,
            "tier": tier_of(c.meta),
            "score": c.score, "signals": c.signals, "kept": c.kept, "reaction": c.reaction,
            "bookmarked": bool(c.bookmarked),
            **{k: (c.meta or {}).get(k) for k in ("title", "description", "hashtags", "virality", "reason")},
            "titles": (c.meta or {}).get("titles") or ([c.meta["title"]] if (c.meta or {}).get("title") else []),
            "hook": (c.meta or {}).get("hook"),
            "video_url": storage.url(c.video_key),
            "thumb_url": storage.url(c.thumb_key) if c.thumb_key else None,
            "captions_url": storage.url(c.captions_key) if c.captions_key else None}


def job_json(db: Session, job: Job, with_clips: bool = True) -> dict:
    out = {"job_id": job.id, "tool": (job.options or {}).get("tool", "clips"), "status": job.status,
           "progress": job.progress, "stage": job.stage, "upload_id": job.upload_id, "options": job.options,
           "credits_reserved": job.credits_reserved, "credits_charged": job.credits_charged,
           "error": {"code": job.error_code, "message": job.error_message} if job.error_code else None,
           "created_at": iso(job.created_at), "finished_at": iso(job.finished_at), "expires_at": iso(job.expires_at)}
    if with_clips:
        storage = get_storage()
        clips = db.execute(select(Clip).where(Clip.job_id == job.id, Clip.deleted_at.is_(None))
                           .order_by(Clip.idx)).scalars()
        out["result"] = job.result
        out["clips"] = with_ranks(db, [clip_json(c, storage) for c in clips])
    return out


def own_job(db: Session, p: Principal, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.account_id != p.account.id:
        raise ApiError(404, "not_found", "No such job.")
    return job


def own_upload(db: Session, p: Principal, upload_id: str) -> Upload:
    upload = db.get(Upload, upload_id)
    if not upload or upload.account_id != p.account.id or upload.deleted_at or upload.expires_at <= utcnow():
        raise ApiError(404, "upload_not_found", "No such upload (uploads expire after a few days).")
    return upload


def submit_job(db: Session, p: Principal, upload_id: str, webhook_url: str | None, idempotency_key: str | None,
               plan: Callable[[Upload], tuple[dict, float, int]]) -> dict:
    """Shared by every tool. `plan(upload)` returns (options, seconds_processed, credit_cost) or raises ApiError."""
    s = get_settings()
    if not s.accept_jobs:
        raise ApiError(503, "paused", "New jobs are temporarily paused. Try again later.")
    if not p.account.email_verified:
        raise ApiError(403, "email_not_verified", "Confirm your email address before starting jobs.")
    if webhook_url and not is_public_https_url(webhook_url):
        raise ApiError(422, "bad_webhook_url", "webhook_url must be a public https URL.")

    ledger.lock_account(db, p.account.id)  # serialise this account's submits (Postgres row lock)
    if idempotency_key:
        existing = db.execute(select(Job).where(Job.account_id == p.account.id,
                                                Job.idempotency_key == idempotency_key)).scalar_one_or_none()
        if existing:
            return job_json(db, existing, with_clips=False)

    upload = own_upload(db, p, upload_id)
    options, processed_sec, cost = plan(upload)

    active = db.execute(select(func.count()).select_from(Job).where(
        Job.account_id == p.account.id, Job.status.in_(ACTIVE))).scalar_one()
    if active >= s.max_concurrent_jobs_per_account:
        raise ApiError(429, "too_many_jobs", "Wait for a running job to finish before starting another.")

    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    used_sec = db.execute(select(func.coalesce(func.sum(Job.duration_sec), 0)).where(
        Job.created_at >= day_start, Job.status.in_(("QUEUED", "RUNNING", "SUCCEEDED")))).scalar_one()
    if (used_sec + processed_sec) / 60 > s.daily_minutes_cap:
        raise ApiError(503, "capacity", "The service is at capacity for today. Try again tomorrow.")

    job = Job(id=new_id("job"), account_id=p.account.id, upload_id=upload.id, options=options,
              duration_sec=processed_sec, credits_reserved=cost, webhook_url=webhook_url,
              idempotency_key=idempotency_key, expires_at=utcnow() + timedelta(days=s.retention_days))
    db.add(job)
    db.flush()
    try:
        ledger.reserve(db, p.account.id, job.id, cost)
    except ledger.InsufficientCredits as e:
        db.rollback()
        raise ApiError(402, "insufficient_credits",
                       f"This job needs {e.cost} credits and you have {e.balance}.") from None
    db.commit()
    return job_json(db, job, with_clips=False)


@router.post("/v1/uploads", status_code=201)
async def create_upload(request: Request, filename: str = Query("upload.mp4", max_length=255),
                        p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Send the video as the raw request body (e.g. `curl -T video.mp4`). Streamed to disk with a size cap."""
    s = get_settings()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > s.max_upload_bytes:
        raise ApiError(413, "file_too_large", f"Maximum upload size is {s.max_upload_bytes // 1024 ** 2} MB.")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ApiError(415, "unsupported_type", f"Upload a video file ({', '.join(sorted(ALLOWED_EXT))}).")
    tmp = s.work_dir / f"up_{uuid.uuid4().hex}{ext}"
    size = 0
    try:
        with open(tmp, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > s.max_upload_bytes:
                    raise ApiError(413, "file_too_large",
                                   f"Maximum upload size is {s.max_upload_bytes // 1024 ** 2} MB.")
                fh.write(chunk)
        if size == 0:
            raise ApiError(422, "empty_body", "The request body was empty. Send the video file as the body.")
        try:
            info = await run_in_threadpool(probe, tmp)
        except PipelineError as e:
            raise ApiError(415, e.code, e.message) from None
        if info.duration > s.max_duration_sec:
            raise ApiError(413, "video_too_long", f"Maximum video length is {s.max_duration_sec // 3600} hours.")
        if info.duration < s.min_duration_sec:
            raise ApiError(422, "video_too_short", f"Minimum video length is {s.min_duration_sec} seconds.")
        upload_id = new_id("upl")
        key = f"uploads/{p.account.id}/{upload_id}{ext}"
        await run_in_threadpool(get_storage().put, key, tmp)
    finally:
        tmp.unlink(missing_ok=True)
    safe_name = re.sub(r"[^\w.\- ]+", "_", Path(filename).name)[:255] or "upload" + ext
    upload = Upload(id=upload_id, account_id=p.account.id, filename=safe_name, storage_key=key, size_bytes=size,
                    duration_sec=info.duration, width=info.width, height=info.height, has_audio=info.has_audio,
                    expires_at=utcnow() + timedelta(days=s.retention_days))
    db.add(upload)
    db.commit()
    return upload_json(upload)


@router.get("/v1/uploads")
def list_uploads(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rows = db.execute(select(Upload).where(Upload.account_id == p.account.id, Upload.deleted_at.is_(None),
                                           Upload.expires_at > utcnow())
                      .order_by(Upload.created_at.desc()).limit(limit).offset(offset)).scalars()
    return {"uploads": [upload_json(u) for u in rows]}


@router.post("/v1/clips", status_code=202)
def create_job(body: ClipRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
               idempotency_key: str | None = Header(default=None, max_length=200)):
    """AI Clip Maker: find the best moments in an upload and render them."""
    def plan(upload: Upload):
        if not upload.has_audio and body.options.chat_region == "none":
            raise ApiError(422, "no_signal",
                           "This video has no audio track. Set chat_region so on-screen chat can be used.")
        s = get_settings()
        if upload.analyzed and s.charge_once_per_upload:   # already paid for once: charge only what is rendered
            cost = credits_for(body.options.max_clips * body.options.clip_length)
        else:
            cost = credits_for(upload.duration_sec)
        return {"tool": "clips", **body.options.model_dump()}, upload.duration_sec, cost
    return submit_job(db, p, body.upload_id, body.webhook_url, idempotency_key, plan)


@router.get("/v1/jobs/{job_id}")
def get_job(job_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return job_json(db, own_job(db, p, job_id))


@router.get("/v1/jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
              p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    jobs = db.execute(select(Job).where(Job.account_id == p.account.id)
                      .order_by(Job.created_at.desc()).limit(limit).offset(offset)).scalars()
    return {"jobs": [job_json(db, j, with_clips=False) for j in jobs]}


@router.post("/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    job = db.execute(select(Job).where(Job.id == job_id, Job.account_id == p.account.id)
                     .with_for_update()).scalar_one_or_none()
    if not job:
        raise ApiError(404, "not_found", "No such job.")
    if job.status == "QUEUED":
        job.status, job.finished_at = "CANCELED", utcnow()
        ledger.settle(db, job, success=False)
    elif job.status == "RUNNING":
        job.cancel_requested = True  # the worker stops at the next stage boundary and refunds
    db.commit()
    return job_json(db, job, with_clips=False)


@router.post("/v1/clips/{clip_id}/feedback")
def clip_feedback(clip_id: str, body: Feedback, p: Principal = Depends(current_principal),
                  db: Session = Depends(get_db)):
    clip = db.get(Clip, clip_id)
    if not clip:
        raise ApiError(404, "not_found", "No such clip.")
    own_job(db, p, clip.job_id)
    for field in sorted(body.model_fields_set):
        value = getattr(body, field)
        if getattr(clip, field) == value:
            continue                      # no change: nothing to log
        setattr(clip, field, value)
        logged = None if value is None else (str(value).lower() if isinstance(value, bool) else value)
        db.add(ClipFeedback(clip_id=clip.id, account_id=p.account.id, kind=field, value=logged))
    db.commit()
    return {"id": clip.id, "kept": clip.kept, "reaction": clip.reaction, "bookmarked": bool(clip.bookmarked)}


class ClipEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)


@router.patch("/v1/clips/{clip_id}")
def edit_clip(clip_id: str, body: ClipEdit, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Choose the clip's title: one of its `titles`, or your own words. Free: nothing is re-rendered."""
    clip = db.get(Clip, clip_id)
    if not clip or clip.deleted_at:
        raise ApiError(404, "not_found", "No such clip.")
    own_job(db, p, clip.job_id)
    title = " ".join(body.title.split())
    if not title:
        raise ApiError(422, "validation_error", "The title is empty.")
    clip.meta = {**(clip.meta or {}), "title": title}      # a new dict, so the JSON column is saved
    db.commit()
    return with_ranks(db, [clip_json(clip, get_storage())])[0]


def _stamp(t: float, sep: str) -> str:
    ms = int(round(max(t, 0) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def subtitle_cues(words: list[dict], max_words: int = 7, max_chars: int = 42, gap: float = 0.6) -> list[tuple]:
    cues, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > gap
                    or len(" ".join(x["text"] for x in cur)) + len(w["text"]) + 1 > max_chars):
            cues.append(cur)
            cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    return [(c[0]["start"], max(c[-1]["end"], c[0]["start"] + 0.2), " ".join(x["text"].strip() for x in c)) for c in cues]


@router.get("/v1/clips/{clip_id}/subtitles", response_class=PlainTextResponse)
def clip_subtitles(clip_id: str, format: Literal["srt", "vtt", "txt"] = "srt",
                   p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Subtitle file for a clip that was rendered with captions. Times are relative to the clip."""
    clip = db.get(Clip, clip_id)
    if not clip or clip.deleted_at:
        raise ApiError(404, "not_found", "No such clip.")
    own_job(db, p, clip.job_id)
    if not clip.captions_key:
        raise ApiError(404, "no_captions", "This clip has no captions (it was rendered with captions off, or has no speech).")
    tmp = get_settings().work_dir / f"cap_{uuid.uuid4().hex}.json"
    try:
        get_storage().fetch(clip.captions_key, tmp)
        cues = subtitle_cues(json.loads(tmp.read_text()).get("words", []))
    finally:
        tmp.unlink(missing_ok=True)
    if format == "txt":
        body = " ".join(c[2] for c in cues) + "\n"
    elif format == "vtt":
        body = "WEBVTT\n\n" + "\n".join(f"{_stamp(a, '.')} --> {_stamp(b, '.')}\n{t}\n" for a, b, t in cues)
    else:
        body = "\n".join(f"{i}\n{_stamp(a, ',')} --> {_stamp(b, ',')}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))
    return PlainTextResponse(body, headers={"content-disposition": f'attachment; filename="{clip.id}.{format}"'})


@router.get("/v1/credits")
def credits(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rows = db.execute(select(CreditLedger).where(CreditLedger.account_id == p.account.id,
                                                 CreditLedger.kind != "commit")
                      .order_by(CreditLedger.id.desc()).limit(50)).scalars()
    return {"balance": ledger.balance(db, p.account.id),
            "history": [{"delta": r.delta, "kind": r.kind, "job_id": r.job_id, "note": r.note,
                         "created_at": iso(r.created_at)} for r in rows]}


@router.get("/v1/files/{token}")
def get_file(token: str):
    """Signed download for local-disk storage. With S3/R2 the URLs point straight at the bucket."""
    data = read_token(token, "file")
    storage = get_storage()
    if not data or not isinstance(storage, LocalStorage):
        raise ApiError(404, "not_found", "This link is invalid or has expired.")
    path = storage.path(data["k"])
    if not path.is_file():
        raise ApiError(404, "not_found", "This file has been deleted.")
    return FileResponse(path, filename=path.name)
