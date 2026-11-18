"""Uploads, clip jobs, results and credits."""
import hashlib
import json
import logging
import math
import re
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ledger
from .ai import MomentPrompt, _hook as hook_text   # the AI's own hook rules: one line, 6 words, 48 characters
from .config import get_settings
from .languages import LanguageCode, SourceLanguage
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .models import Clip, ClipFeedback, CreditLedger, Job, Upload, new_id, utcnow
from .pipeline import MIN_CLIP, PipelineError, probe
from .pipeline.moments import BUCKETS, MAX_CLIPS, kind_of
from .pipeline.translate import as_text, caption_rows
from .security import is_public_https_url, read_token
from .render_options import LayoutOptions  # noqa: F401  (re-exported: routes_tools imports it from here)
from .exports import ClipEditDoc
from .scoring import display_scores
from .storage import LocalStorage, get_storage
from .templates import TEMPLATES, with_tuning
from .thumbnails import redraw, words_for

log = logging.getLogger("clipapi.media")
router = APIRouter()
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".flv", ".ts"}
ACTIVE = ("QUEUED", "RUNNING")


RANGE_SLACK = 1.0      # a range may end this many seconds past the video (players round the length up); it is clipped


class ClipRange(BaseModel):
    """A part of the video, in seconds from its start."""
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def check_order(self):
        if self.start >= self.end:
            raise ValueError("range.start must be before range.end")
        return self


class ClipOptions(LayoutOptions):
    max_clips: int = Field(3, ge=1, le=10)
    clip_length: int = Field(30, ge=10, le=60)
    # Clip length bucket, "shortest-longest" in seconds: every clip's length falls inside it and `clip_length` is
    # not used for cutting. Absent: clips are `clip_length` long (the AI may pick 15-45 s), as before.
    duration: Literal["0-30", "0-90", "30-60", "60-90", "90-180", "180-300"] | None = None
    # How many clips to return, best first. Absent: `max_clips`; or, with `duration`, every good moment (at most 50).
    limit: int | None = Field(default=None, ge=1, le=MAX_CLIPS)
    range: ClipRange | None = None          # analyse and clip only this part of the video; clip times stay video times
    project_name: str | None = Field(default=None, max_length=120)      # your label for this run
    tighten: bool = True          # cut silences over 0.6 s and filler words out of each clip
    punch_zoom: bool = True       # subtle punch-in zooms (max 1.15x) on the gameplay at loudness spikes
    flash_forward: bool = True    # open on 1.5 s of the clip's peak, then cut back (AI clips only)
    hook_overlay: bool = True     # burn the AI's on-screen hook text over the first 2.5 s (AI clips only)
    prompt: MomentPrompt = None   # what moments to find, in your own words (max 300 characters). The AI judge
                                  # reads it as your interest; it never changes what a job costs.
    template: str | None = None   # a game template id from GET /v1/templates: tunes detection and the AI judge.
                                  # Send the template's `options` too; they are not applied for you.
    # (languages, agent F) The spoken language (null: detected), the language of titles, hooks and translated
    # subtitles (null: the spoken one), and which subtitles a download shows by default. None changes the cost.
    source_lang: SourceLanguage | None = None
    target_lang: LanguageCode | None = None
    caption_display: Literal["original", "translation", "both"] = "original"

    @field_validator("project_name")
    @classmethod
    def tidy_name(cls, value):
        return " ".join(value.split()) or None if value is not None else None

    @model_validator(mode="after")
    def check_template(self):
        if self.template is not None and self.template not in TEMPLATES:
            raise ValueError(f"unknown template; use one of: {', '.join(TEMPLATES)}")
        return self


def check_span(options: ClipOptions, video_sec: float) -> None:
    """The range lies inside the video and is long enough to hold a clip of the chosen length. 422 otherwise."""
    start, end = 0.0, video_sec
    if options.range is not None:
        start, end = options.range.start, min(options.range.end, video_sec)
        if options.range.end > video_sec + RANGE_SLACK or start >= video_sec:
            raise ApiError(422, "bad_range", f"range must lie inside the video (0 to {video_sec:.1f} seconds).")
        if end - start < MIN_CLIP:
            raise ApiError(422, "range_too_short", f"range must be at least {MIN_CLIP:.0f} seconds long.")
    if options.duration is not None and end - start < BUCKETS[options.duration][0]:
        raise ApiError(422, "too_short_for_duration",
                       f"This video (or the chosen range) is {end - start:.0f} seconds long: shorter than the "
                       f"shortest clip of duration {options.duration}.")


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


def rerun_seconds(options: "ClipOptions", video_sec: float) -> float:
    """The most a run on an already-analysed upload can render, in seconds: what is reserved for it. The job is
    then charged for the seconds it did render and the rest is returned (worker, ledger.settle).
    Without duration, limit or range it is max_clips * clip_length, as it always was. With any of them: the number
    of clips asked for (every moment, capped at MAX_CLIPS, when a duration is set without a limit) times the
    longest clip the request allows, never more than the video or the chosen range holds."""
    if options.duration is None and options.limit is None and options.range is None:
        return options.max_clips * options.clip_length
    count = options.limit if options.limit is not None else (MAX_CLIPS if options.duration else options.max_clips)
    longest = BUCKETS[options.duration][1] if options.duration else options.clip_length
    span = video_sec
    if options.range is not None:
        span = max(0.0, min(options.range.end, video_sec) - options.range.start)
    return min(count * longest, span)


def upload_json(u: Upload) -> dict:
    return {"upload_id": u.id, "filename": u.filename, "size_bytes": u.size_bytes,
            "duration_sec": round(u.duration_sec, 2), "width": u.width, "height": u.height,
            "has_audio": u.has_audio, "analyzed": bool(u.analyzed), "credits_required": credits_for(u.duration_sec),
            "language": u.language,
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
    """Adds each clip's two positions among the stored clips of its own run, so both stay gap-free when a clip
    is deleted:
    - by score, best first: `rank_index` (from 0), with `rank` (from 1) and `rank_of` as before;
    - by where it happens in the video, earliest first: `timeline_index` (from 1). `index` is the number the
      clip was given when the run finished and never changes."""
    job_ids = {c["job_id"] for c in clips}
    by_score: dict[str, list[str]] = {}
    by_time: dict[str, list[tuple]] = {}
    if job_ids:
        for clip_id, job_id, start, idx in db.execute(select(Clip.id, Clip.job_id, Clip.start_sec, Clip.idx).where(
                Clip.job_id.in_(job_ids), Clip.deleted_at.is_(None)).order_by(Clip.score.desc(), Clip.idx)):
            by_score.setdefault(job_id, []).append(clip_id)
            by_time.setdefault(job_id, []).append((start, idx, clip_id))
    rank = {clip_id: i for ids in by_score.values() for i, clip_id in enumerate(ids)}
    timeline = {clip_id: i for rows in by_time.values() for i, (_s, _i, clip_id) in enumerate(sorted(rows), 1)}
    return [{**c, "rank": rank[c["id"]] + 1, "rank_of": len(by_score[c["job_id"]]), "rank_index": rank[c["id"]],
             "timeline_index": timeline[c["id"]]} for c in clips]


def _ai_score(meta: dict | None) -> int | float | None:
    """The AI's 0-100 score, or None when the AI did not rate the clip (the same test as tier_of)."""
    v = (meta or {}).get("virality") or {}
    if (meta or {}).get("source") == "signals" or not isinstance(v.get("score"), (int, float)):
        return None
    return v["score"]


def clip_json(c: Clip, storage) -> dict:
    return {"id": c.id, "job_id": c.job_id, "index": c.idx, "start_sec": c.start_sec, "end_sec": c.end_sec,
            "start_ms": int(round(c.start_sec * 1000)), "end_ms": int(round(c.end_sec * 1000)),
            "virality_score": _ai_score(c.meta),
            "kind": kind_of(c.kind or (c.meta or {}).get("kind")),
            "why": (c.meta or {}).get("reason") or None,
            "tier": tier_of(c.meta),
            "score": c.score, "signals": c.signals, "kept": c.kept, "reaction": c.reaction,
            "bookmarked": bool(c.bookmarked),
            **{k: (c.meta or {}).get(k) for k in ("title", "description", "hashtags", "virality", "reason")},
            "titles": (c.meta or {}).get("titles") or ([c.meta["title"]] if (c.meta or {}).get("title") else []),
            "hook": (c.meta or {}).get("hook"),
            "hook_on_screen": bool(((c.features or {}).get("edit") or {}).get("hook")),   # burned into the video
            "suggestion": (c.meta or {}).get("suggestion"),
            # (render, agent B) the best render there is: the latest export, else the job's own, else its preview.
            # null: rendered with render "none", nothing to play until it is exported.
            "video_url": storage.url(c.export_key or c.video_key or c.preview_key)
            if (c.export_key or c.video_key or c.preview_key) else None,
            "preview_url": storage.url(c.preview_key) if c.preview_key else None,
            "export_url": storage.url(c.export_key) if c.export_key else None,
            "export_res": c.export_res,
            "rendered": "full" if (c.export_key or c.video_key) else "preview" if c.preview_key else "none",
            "edit": c.edit,                                     # the editor's edit (exports.ClipEditDoc) or null
            # the source parts the clip was rendered from, in playing order (a flash-forward first)
            "segments": ((c.features or {}).get("edit") or {}).get("segments") or [[c.start_sec, c.end_sec]],
            "thumb_url": storage.url(c.thumb_chosen_key or c.thumb_key) if (c.thumb_chosen_key or c.thumb_key) else None,
            "captions_url": storage.url(c.captions_key) if c.captions_key else None}


def with_display_scores(db: Session, clips: list[dict]) -> list[dict]:
    """Adds display_score: the AI's raw score calibrated across the clips of the same run (scoring.display_scores;
    the best clip of a run shows 90 to 99). Worked out on every read and never stored. None for a clip the AI did
    not rate. The raw numbers (`score`, `virality`) are left as they are.

    The scale is set by the run's stored clips only, the same set `rank` counts: a deleted clip no longer takes
    part, so after the best or the weakest clip is deleted the others are spread over what remains, and while a
    job is still running it covers the clips stored so far."""
    job_ids = {c["job_id"] for c in clips}
    raw: dict[str, dict[str, int | float | None]] = {}
    if job_ids:
        for clip_id, job_id, meta in db.execute(select(Clip.id, Clip.job_id, Clip.meta).where(
                Clip.job_id.in_(job_ids), Clip.deleted_at.is_(None))):
            raw.setdefault(job_id, {})[clip_id] = _ai_score(meta)
    shown: dict[str, int | None] = {}
    for scores in raw.values():                       # one run at a time: each has its own scale
        shown.update(zip(scores, display_scores(list(scores.values()))))
    return [{**c, "display_score": shown.get(c["id"])} for c in clips]


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
        out["clips"] = with_display_scores(db, with_ranks(db, [clip_json(c, storage) for c in clips]))
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


def replayed(db: Session, p: Principal, idempotency_key: str | None) -> dict | None:
    """The job an earlier request with this Idempotency-Key started, as that request returned it, else None.
    The caller holds the account lock (ledger.lock_account)."""
    if not idempotency_key:
        return None
    existing = db.execute(select(Job).where(Job.account_id == p.account.id,
                                            Job.idempotency_key == idempotency_key)).scalar_one_or_none()
    return job_json(db, existing, with_clips=False) if existing else None


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
    existing = replayed(db, p, idempotency_key)
    if existing:
        return existing

    upload = own_upload(db, p, upload_id)
    options, processed_sec, cost = plan(upload)

    active = db.execute(select(func.count()).select_from(Job).where(      # premium thumbnails (thm_) have their own cap
        Job.account_id == p.account.id, Job.status.in_(ACTIVE), ~Job.id.startswith("thm_", autoescape=True))).scalar_one()
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
async def create_upload(request: Request, response: Response, filename: str = Query("upload.mp4", max_length=255),
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
    size, digest = 0, hashlib.sha256()
    try:
        with open(tmp, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                digest.update(chunk)
                if size > s.max_upload_bytes:
                    raise ApiError(413, "file_too_large",
                                   f"Maximum upload size is {s.max_upload_bytes // 1024 ** 2} MB.")
                fh.write(chunk)
        if size == 0:
            raise ApiError(422, "empty_body", "The request body was empty. Send the video file as the body.")
        content_hash = digest.hexdigest()
        # The same bytes from the same account, while the first copy is still stored: hand back that upload.
        # Nothing new is stored, and jobs on it are priced as on any upload that was already analysed.
        same = db.execute(select(Upload).where(
            Upload.account_id == p.account.id, Upload.content_hash == content_hash, Upload.size_bytes == size,
            Upload.deleted_at.is_(None), Upload.expires_at > utcnow()).order_by(Upload.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if same is not None:
            response.status_code = 200
            return {**upload_json(same), "reused": True}
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
                    content_hash=content_hash, expires_at=utcnow() + timedelta(days=s.retention_days))
    db.add(upload)
    db.commit()
    return {**upload_json(upload), "reused": False}


@router.get("/v1/uploads")
def list_uploads(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rows = db.execute(select(Upload).where(Upload.account_id == p.account.id, Upload.deleted_at.is_(None),
                                           Upload.expires_at > utcnow())
                      .order_by(Upload.created_at.desc()).limit(limit).offset(offset)).scalars()
    return {"uploads": [upload_json(u) for u in rows]}


def clip_plan(body: "ClipRequest"):
    """What POST /v1/clips stores, processes and reserves for `body` (submit_job's `plan`)."""
    def plan(upload: Upload):
        if not upload.has_audio and body.options.chat_region == "none":
            raise ApiError(422, "no_signal",
                           "This video has no audio track. Set chat_region so on-screen chat can be used.")
        check_span(body.options, upload.duration_sec)
        s = get_settings()
        basis = {}
        if upload.analyzed and s.charge_once_per_upload:   # already paid for once: charge only what is rendered
            cost = credits_for(rerun_seconds(body.options, upload.duration_sec))     # the worst case is reserved
            basis = {"charge_basis": "rendered"}           # and the job settles on the seconds it rendered
        else:
            cost = credits_for(upload.duration_sec)
        return {"tool": "clips", **basis, **with_tuning(body.options.model_dump())}, upload.duration_sec, cost
    return plan


@router.post("/v1/clips/quote")
def quote_job(body: ClipRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """(render, agent B) What POST /v1/clips with the same body would reserve. Nothing is reserved or started."""
    options, _sec, cost = clip_plan(body)(own_upload(db, p, body.upload_id))
    rendered = options.get("charge_basis") == "rendered"
    return {"credits_reserved": cost,
            "note": ("This video was analysed before: charged for the seconds rendered, never more than this."
                     if rendered else "One credit per started minute of the video.")}


@router.post("/v1/clips", status_code=202)
def create_job(body: ClipRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
               idempotency_key: str | None = Header(default=None, max_length=200)):
    """AI Clip Maker: find the best moments in an upload and render them."""
    out = submit_job(db, p, body.upload_id, body.webhook_url, idempotency_key, clip_plan(body))
    if body.options.project_name:
        job = db.get(Job, out["job_id"])
        if job is not None and job.name is None:       # a replayed request (Idempotency-Key) keeps its first name
            job.name = body.options.project_name
            db.commit()
    return out


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
    title: str | None = Field(default=None, min_length=1, max_length=80)
    hook: str | None = Field(default=None, min_length=1, max_length=48)   # (U7) the thumbnail's words (one line)
    # (render, agent B) the editor's edit (app/exports.py ClipEditDoc: source seconds); null forgets it
    edit: ClipEditDoc | None = None

    @model_validator(mode="after")
    def check(self):
        if not self.model_fields_set & {"title", "hook", "edit"}:
            raise ValueError("send title, hook, edit or any of them together")
        for name in ("title", "hook"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


@router.patch("/v1/clips/{clip_id}")
def edit_clip(clip_id: str, body: ClipEdit, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Choose the clip's title (one of its `titles`, or your own words) and its hook, and save the editor's `edit`.
    Free: nothing is re-rendered; POST /v1/clips/export renders the edit. When the words the thumbnail carries
    change, it is drawn again on its stored frame now (a fraction of a second). A hook already burned into the
    video stays as it is there."""
    clip = db.get(Clip, clip_id)
    if not clip or clip.deleted_at:
        raise ApiError(404, "not_found", "No such clip.")
    job = own_job(db, p, clip.job_id)
    if "edit" in body.model_fields_set:
        stored = None
        if body.edit is not None:
            from .routes_export import check_edit
            stored = check_edit(db, clip, body.edit).model_dump()     # without cuts: the job's dead air is cut
        clip.edit = stored
    changes = {}
    if body.title is not None:
        changes["title"] = " ".join(body.title.split())
        if not changes["title"]:
            raise ApiError(422, "validation_error", "The title is empty.")
    if body.hook is not None:
        changes["hook"] = hook_text(body.hook)
        if not changes["hook"]:
            raise ApiError(422, "validation_error", "The hook is empty.")
    options = job.options if isinstance(job.options, dict) else {}
    before = words_for(clip.meta, options)
    if changes:
        clip.meta = {**(clip.meta or {}), **changes}        # a new dict, so the JSON column is saved
    storage = get_storage()
    if words_for(clip.meta, options) != before:
        try:
            redraw(clip, options, storage)
        except Exception:                                   # the words are saved either way
            log.exception("could not draw the thumbnail of %s again", clip.id)
    db.commit()
    return with_display_scores(db, with_ranks(db, [clip_json(clip, storage)]))[0]


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
                   caption_display: Literal["original", "translation", "both"] | None = None,
                   p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Subtitle file for a clip that was rendered with captions. Times are relative to the clip.
    `caption_display`: the spoken words (`original`), their translation into the job's `target_lang`
    (`translation`), or both, original first. Left out: the job's own `caption_display` option."""
    clip = db.get(Clip, clip_id)
    if not clip or clip.deleted_at:
        raise ApiError(404, "not_found", "No such clip.")
    job = own_job(db, p, clip.job_id)
    if not clip.captions_key:
        raise ApiError(404, "no_captions", "This clip has no captions (it was rendered with captions off, or has no speech).")
    display = caption_display or (job.options or {}).get("caption_display") or "original"
    tmp = get_settings().work_dir / f"cap_{uuid.uuid4().hex}.json"
    try:
        get_storage().fetch(clip.captions_key, tmp)
        captions = json.loads(tmp.read_text())
        cues = subtitle_cues(captions.get("words", []))
    finally:
        tmp.unlink(missing_ok=True)
    if display != "original":           # (languages, agent F)
        rows = caption_rows(captions)
        if rows is None:
            raise ApiError(409, "no_translation", "This clip's captions have no translation. Run the job with "
                                                  "target_lang set on a server where translation is configured.")
        lang = (captions.get("translation") or {}).get("language") or "translated"
        suffix = lang if display == "translation" else f"{captions.get('language') or 'orig'}-{lang}"
        return PlainTextResponse(as_text(rows, display, format, joined=True), headers={
            "content-disposition": f'attachment; filename="{clip.id}.{suffix}.{format}"'})
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
