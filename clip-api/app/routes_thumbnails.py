"""A clip's thumbnails: the free one its job made, premium AI ones (#140, paid), and which one the clip uses.

Free, always on:
  GET   /v1/clips/{clip_id}/thumbnails                     the gallery: the original and every premium one
  POST  /v1/clips/{clip_id}/thumbnails/{thumb_id}/select   use this one (`original` is the job's own); switching
                                                           back and forth is free
  PATCH /v1/clips/{clip_id}/thumbnails/{thumb_id}          edit the text or turn it off; redrawn by our renderer

Paid, behind PREMIUM_THUMBNAILS (off: 404 `premium_thumbnails_off`):
  POST  /v1/clips/{clip_id}/thumbnails/premium/quote       the exact price; reserves nothing
  POST  /v1/clips/{clip_id}/thumbnails/premium             confirm: reserves the price and queues the job

PRICE (owner OK 2026-11-17, #140): PREMIUM_THUMB_CREDITS, 25 by default, from server config only. A request must
send `confirm: true` (and may send back the quoted `credits`, refused with 409 when the price changed). The first
premium thumbnail of a clip also needs `likeness_consent: true` (logged in likeness_consents). One Idempotency-Key
gives one job; an identical request while the first is still queued or running gets that job back.
"""
import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger
from . import thumbnail_jobs as tj
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .imagegen import style_look
from .imagegen.prompts import MAX_INSTRUCTION, InstructionRefused, clean_instruction
from .models import Clip, ClipThumbnail, Job, LikenessConsent, new_id
from .pipeline.thumbs import Canvas, write_thumbnail
from .routes_media import ACTIVE, iso, job_json
from .storage import get_storage

router = APIRouter()
log = logging.getLogger("clipapi.thumbnails")
ORIGINAL = "original"


class PremiumQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: str = Field(max_length=40)
    instruction: str | None = Field(default=None, max_length=MAX_INSTRUCTION * 2)   # cleaned, then at most 200


class PremiumRequest(PremiumQuote):
    confirm: bool = False                 # true: the user saw the price and confirmed it
    credits: int | None = None            # the price the user saw; 409 when it is not the price now
    likeness_consent: bool = False        # needed before the clip's first premium thumbnail


class ThumbText(BaseModel):
    """Send only what changes. `text` null: the clip's own hook."""
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=tj.TEXT_MAX)
    show_text: bool | None = None

    @field_validator("text")
    @classmethod
    def tidy(cls, value):
        return (" ".join(value.split()) or None) if isinstance(value, str) else value


def own_clip(db: Session, p: Principal, clip_id: str) -> tuple[Clip, Job]:
    clip = db.get(Clip, clip_id)
    job = db.get(Job, clip.job_id) if clip is not None else None
    if clip is None or clip.deleted_at is not None or job is None or job.account_id != p.account.id:
        raise ApiError(404, "not_found", "No such clip.")
    return clip, job


def _checked(clip: Clip, body: PremiumQuote) -> tuple[str, str | None]:
    """(style, cleaned instruction), or ApiError. Nothing is reserved or sent before this passes."""
    if style_look(get_settings(), body.style) is None:
        names = ", ".join(s["id"] for s in tj.styles())
        raise ApiError(422, "unknown_style", f"Pick one of these styles: {names}.")
    try:
        instruction = clean_instruction(body.instruction)
    except InstructionRefused as e:
        raise ApiError(422, "instruction_not_allowed", str(e)) from None
    if not clip.frame_key:
        raise ApiError(409, "no_clean_frame", "This clip was made before premium thumbnails. Make the clip again "
                                              "to use one.")
    return body.style, instruction


def _consented(db: Session, account_id: str, clip_id: str) -> bool:
    return db.execute(select(LikenessConsent.id).where(LikenessConsent.account_id == account_id,
                                                       LikenessConsent.clip_id == clip_id,
                                                       LikenessConsent.consent.is_(True)).limit(1)).first() is not None


@router.post("/v1/clips/{clip_id}/thumbnails/premium/quote")
def premium_quote(clip_id: str, body: PremiumQuote, p: Principal = Depends(current_principal),
                  db: Session = Depends(get_db)):
    """What a premium thumbnail of this clip costs, exactly. Nothing is reserved, stored or sent."""
    tj.require_enabled()
    clip, _job = own_clip(db, p, clip_id)
    style, instruction = _checked(clip, body)
    return {"credits_reserved": tj.price(), "credits": tj.price(), "style": style, "instruction": instruction,
            "note": tj.NOTE, "likeness_consent_required": not _consented(db, p.account.id, clip.id),
            "consent": tj.CONSENT_TEXT, "balance": ledger.balance(db, p.account.id)}


@router.post("/v1/clips/{clip_id}/thumbnails/premium", status_code=202)
def premium_create(clip_id: str, body: PremiumRequest, p: Principal = Depends(current_principal),
                   db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, max_length=200)):
    """Make a premium AI thumbnail of this clip: its thumbnail frame restyled, the streamer's face kept, the hook
    drawn by ClutchClips. Poll the returned job; when it succeeds the new thumbnail is in the clip's gallery (it is
    not chosen for you). Refunded in full if it fails."""
    tj.require_enabled()
    s = get_settings()
    if not s.accept_jobs:
        raise ApiError(503, "paused", "New jobs are temporarily paused. Try again later.")
    if not p.account.email_verified:
        raise ApiError(403, "email_not_verified", "Confirm your email address before starting jobs.")
    clip, source = own_clip(db, p, clip_id)
    style, instruction = _checked(clip, body)
    cost = tj.price()
    if body.confirm is not True:
        raise ApiError(422, "confirm_required", f"A premium thumbnail costs {cost} credits. Send confirm: true to "
                                                "make it.")
    if body.credits is not None and body.credits != cost:
        raise ApiError(409, "price_changed", f"The price is now {cost} credits. Check it and confirm again.")

    ledger.lock_account(db, p.account.id)       # one submit at a time per account
    if idempotency_key:
        existing = db.execute(select(Job).where(Job.account_id == p.account.id,
                                                Job.idempotency_key == idempotency_key)).scalar_one_or_none()
        if existing is not None:
            if (existing.options or {}).get("clip_id") != clip.id or not tj.is_thumbnail_job(existing.id):
                raise ApiError(409, "idempotency_key_reused", "This Idempotency-Key was used for another request.")
            return job_json(db, existing, with_clips=False)
    mark = tj.fingerprint(clip.id, style, instruction)
    active = db.execute(select(Job).where(Job.account_id == p.account.id, Job.id.startswith(tj.PREFIX + "_"),
                                          Job.status.in_(ACTIVE))).scalars().all()
    same = next((j for j in active if (j.options or {}).get("fingerprint") == mark), None)
    if same is not None:
        return job_json(db, same, with_clips=False)        # the identical request is already on its way
    if len(active) >= tj.MAX_ACTIVE:
        raise ApiError(429, "too_many_jobs", "Wait for a premium thumbnail to finish before starting another.")
    if not _consented(db, p.account.id, clip.id):
        if body.likeness_consent is not True:
            raise ApiError(422, "likeness_consent_required", "Confirm first: " + tj.CONSENT_TEXT)
        db.add(LikenessConsent(account_id=p.account.id, clip_id=clip.id, consent=True, wording=tj.CONSENT_TEXT))
        log.info("likeness consent: account %s clip %s", p.account.id, clip.id)

    job = Job(id=new_id(tj.PREFIX), account_id=p.account.id, upload_id=source.upload_id,
              options={"tool": tj.TOOL, "clip_id": clip.id, "style": style, "instruction": instruction,
                       "fingerprint": mark},
              duration_sec=0.0, credits_reserved=cost, idempotency_key=idempotency_key,
              expires_at=source.expires_at)
    db.add(job)
    db.flush()
    try:
        ledger.reserve(db, p.account.id, job.id, cost)
    except ledger.InsufficientCredits as e:
        db.rollback()
        raise ApiError(402, "insufficient_credits",
                       f"A premium thumbnail costs {e.cost} credits and you have {e.balance}.") from None
    db.commit()
    return job_json(db, job, with_clips=False)


def _row_json(row: ClipThumbnail | None, clip: Clip, storage, selected: bool) -> dict:
    if row is None or row.kind == "original":
        key = row.image_key if row is not None else clip.thumb_key
        return {"id": ORIGINAL, "kind": "original", "style": None, "url": storage.url(key) if key else None,
                "text": row.text if row is not None else None, "show_text": row.show_text if row is not None else True,
                "editable": bool(clip.frame_key), "selected": selected, "created_at": iso(clip.created_at)}
    return {"id": row.id, "kind": row.kind, "style": row.style, "instruction": row.instruction,
            "url": storage.url(row.image_key), "text": row.text, "show_text": row.show_text, "editable": True,
            "selected": selected, "provider": (row.info or {}).get("provider"), "created_at": iso(row.created_at)}


def _rows(db: Session, clip: Clip) -> list[ClipThumbnail]:
    return db.execute(select(ClipThumbnail).where(ClipThumbnail.clip_id == clip.id, ClipThumbnail.deleted_at.is_(None))
                      .order_by(ClipThumbnail.created_at)).scalars().all()


def gallery(db: Session, clip: Clip) -> dict:
    storage, rows = get_storage(), _rows(db, clip)
    original = next((r for r in rows if r.kind == "original"), None)
    chosen = clip.thumb_id if clip.thumb_id and any(r.id == clip.thumb_id and r.kind != "original" for r in rows) else ORIGINAL
    pending = db.execute(select(Job).where(Job.id.startswith(tj.PREFIX + "_"), Job.status.in_(ACTIVE),
                                           Job.account_id == db.get(Job, clip.job_id).account_id)).scalars().all()
    return {"clip_id": clip.id, "selected": chosen, "thumb_url": storage.url(clip.thumb_key) if clip.thumb_key else None,
            "thumbnails": [_row_json(original, clip, storage, chosen == ORIGINAL)]
            + [_row_json(r, clip, storage, chosen == r.id) for r in rows if r.kind != "original"],
            "pending": [j.id for j in pending if (j.options or {}).get("clip_id") == clip.id],
            "premium": tj.listing()}


@router.get("/v1/clips/{clip_id}/thumbnails")
def list_thumbnails(clip_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """The clip's thumbnails: the original (free) first, then every premium one, and which one the clip uses."""
    clip, _job = own_clip(db, p, clip_id)
    return gallery(db, clip)


def _target(db: Session, clip: Clip, thumb_id: str) -> ClipThumbnail:
    if thumb_id == ORIGINAL:
        return tj.ensure_original(db, clip)
    row = db.get(ClipThumbnail, thumb_id)
    if row is None or row.clip_id != clip.id or row.deleted_at is not None or row.kind == "original":
        raise ApiError(404, "thumbnail_not_found", "No such thumbnail on this clip.")
    return row


@router.post("/v1/clips/{clip_id}/thumbnails/{thumb_id}/select")
def select_thumbnail(clip_id: str, thumb_id: str, p: Principal = Depends(current_principal),
                     db: Session = Depends(get_db)):
    """Use this thumbnail for the clip (`original`: the one its job made). Free; nothing is redrawn or deleted."""
    clip, _job = own_clip(db, p, clip_id)
    tj.ensure_original(db, clip)
    row = _target(db, clip, thumb_id)
    clip.thumb_id, clip.thumb_key = row.id, row.image_key
    db.commit()
    return gallery(db, clip)


@router.patch("/v1/clips/{clip_id}/thumbnails/{thumb_id}")
def edit_thumbnail(clip_id: str, thumb_id: str, body: ThumbText, p: Principal = Depends(current_principal),
                   db: Session = Depends(get_db)):
    """Change a thumbnail's text, or turn it off. Free: the picture is redrawn by ClutchClips, never by an AI."""
    clip, source = own_clip(db, p, clip_id)
    if thumb_id == ORIGINAL and not clip.frame_key:
        raise ApiError(409, "no_clean_frame", "This clip's thumbnail was made before text could be edited.")
    row = _target(db, clip, thumb_id)
    if "text" in body.model_fields_set:
        row.text = body.text
    if "show_text" in body.model_fields_set and body.show_text is not None:
        row.show_text = body.show_text
    storage = get_storage()
    words = (row.text or tj.hook_of(clip, source)) if row.show_text else None
    new_key = f"thumbs/{clip.id}/{row.id}.{uuid.uuid4().hex[:8]}.jpg"
    with tempfile.TemporaryDirectory(dir=get_settings().work_dir) as tmp:
        clean, out = Path(tmp) / "clean.jpg", Path(tmp) / "out.jpg"
        storage.fetch(row.clean_key, clean)
        from PIL import Image
        with Image.open(clean) as im:
            size = im.size
        write_thumbnail(clean, out, words, tj.canvas_for_clip(clip) or Canvas(size), tj.accent_of(source))
        storage.put(new_key, out)
    old = row.image_key
    row.image_key = new_key
    selected = clip.thumb_id == row.id or (clip.thumb_id is None and row.kind == "original")
    if selected:
        clip.thumb_id, clip.thumb_key = row.id, new_key
    db.commit()
    if old.startswith("thumbs/") and old != new_key:       # an earlier edit of ours; the job's own file stays
        try:
            storage.delete(old)
        except Exception:
            log.exception("could not remove %s", old)
    return gallery(db, clip)

