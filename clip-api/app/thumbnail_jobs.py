"""Premium AI thumbnails (#140): the paid job, the worker's side, and what the routes share.

A premium thumbnail is a Job row (id `thm_...`, tool `premium_thumbnail`, no video seconds) on the clip's source
upload, so it is claimed, heartbeated, cancelled, swept and refunded like every other job:
- reserved once when the user confirms (`reserve:<job_id>`, the price from PREMIUM_THUMB_CREDITS only);
- settled once (`settle:<job_id>`): committed when the picture is stored, released (a full refund) on every other
  ending: provider error or timeout after the one retry, safety block, the face lost, cancel, the clip deleted,
  a crash here, or the worker dying (the stale-job sweeper);
- the new thumbnail is added to the clip's gallery; it is never chosen for the user.

The frame comes from the clip's stored `frame_key` (the free thumbnail's frame without text); the text is the
clip's hook, drawn with our renderer (thumbs.write_thumbnail), so spelling is exact.
"""
import hashlib
import json
import logging
import shutil
import tempfile
import threading
from pathlib import Path

from sqlalchemy import select

from . import ledger
from .config import get_settings
from .db import new_session
from .deps import ApiError
from .imagegen import GenerationFailed, editors_from, generate, style_look
from .imagegen.prompts import MAX_INSTRUCTION
from .models import Clip, ClipThumbnail, Job, new_id, utcnow
from .pipeline.thumbs import Canvas, canvas_of, thumb_text
from .storage import get_storage

log = logging.getLogger("clipapi.thumbnails")
PREFIX = "thm"
TOOL = "premium_thumbnail"
MAX_ACTIVE = 3                  # premium thumbnails one account may have queued or running at once
TEXT_MAX = 80
CONSENT_TEXT = ("I am the streamer shown in this clip, or I have their permission to have their likeness "
                "edited by AI.")
NOTE = "Shown before you confirm. Refunded in full if it fails."
FAILED_MESSAGE = {
    "provider_error": "The image service had a problem.",
    "provider_timeout": "The image service took too long.",
    "safety_block": "The image service declined this picture.",
    "no_image": "The image service returned no picture.",
    "face_lost": "The result lost the streamer's face, so it was not kept.",
    "fallback_unavailable": "The image service had a problem.",
    "clip_gone": "The clip was deleted.",
}


class Canceled(Exception):
    pass


class Lost(Exception):
    """The job was finalised elsewhere (the stale-job sweeper, a takedown) while it ran."""


def is_thumbnail_job(job_id: str) -> bool:
    return job_id.startswith(PREFIX + "_")


# ---------- shared with the routes ----------
def enabled() -> bool:
    return bool(get_settings().premium_thumbnails)


def require_enabled() -> None:
    """404 while the feature flag is off; 503 when it is on but no provider key is set."""
    s = get_settings()
    if not s.premium_thumbnails:
        raise ApiError(404, "premium_thumbnails_off", "Premium thumbnails are not available yet.")
    if not editors_from(s):
        raise ApiError(503, "premium_thumbnails_unavailable", "Premium thumbnails are not set up on this server.")


def price() -> int:
    return int(get_settings().premium_thumb_credits)


def styles() -> list[dict]:
    return [{"id": x["id"], "name": x.get("name") or x["id"]} for x in get_settings().thumb_styles]


def listing() -> dict | None:
    """What GET /v1/options says about premium thumbnails: None (not listed) while the flag is off."""
    if not enabled():
        return None
    return {"credits": price(), "styles": styles(), "instruction_max": MAX_INSTRUCTION,
            "consent": CONSENT_TEXT, "note": NOTE}


def fingerprint(clip_id: str, style: str, instruction: str | None) -> str:
    return hashlib.sha256(json.dumps([clip_id, style, instruction or ""]).encode()).hexdigest()[:32]


def hook_of(clip: Clip, job: Job | None) -> str | None:
    """The words a clip's thumbnail carries: the editor's hook, else the AI's hook or title (swears masked when the
    clip's job had `censor` on)."""
    edit_hook = (clip.edit or {}).get("hook_text") if isinstance(clip.edit, dict) else None
    meta = {**(clip.meta or {}), **({"hook": edit_hook} if edit_hook else {})}
    return thumb_text(meta, bool(((job.options if job else None) or {}).get("censor")))


def canvas_for_clip(clip: Clip) -> Canvas | None:
    return canvas_of((clip.features or {}).get("thumbnail"))


def accent_of(job: Job | None) -> str | None:
    return ((job.options if job else None) or {}).get("caption_accent")


def ensure_original(db, clip: Clip) -> ClipThumbnail:
    """The row standing for the thumbnail the clip's job made, created the first time anything else is added or
    chosen, so the free original is always kept and can be chosen again."""
    row = db.execute(select(ClipThumbnail).where(ClipThumbnail.clip_id == clip.id, ClipThumbnail.kind == "original",
                                                 ClipThumbnail.deleted_at.is_(None))).scalar_one_or_none()
    if row is None:
        job = db.get(Job, clip.job_id)
        row = ClipThumbnail(id=new_id("thb"), clip_id=clip.id, account_id=job.account_id, kind="original",
                            clean_key=clip.frame_key or clip.thumb_key or "", image_key=clip.thumb_key or "",
                            text=None, show_text=True)
        db.add(row)
        db.flush()
    return row


def thumbnail_keys(db, clip_ids: list[str]) -> list[str]:
    """Every stored file of these clips' extra thumbnails (for deletes, takedowns and the expiry sweep)."""
    if not clip_ids:
        return []
    rows = db.execute(select(ClipThumbnail).where(ClipThumbnail.clip_id.in_(clip_ids))).scalars().all()
    return [k for r in rows for k in (r.clean_key, r.image_key) if k]


# ---------- the worker's side ----------
def _heartbeat(job_id: str, stop: threading.Event) -> None:
    while not stop.wait(30):
        try:
            with new_session() as db:
                job = db.get(Job, job_id)
                if job and job.status == "RUNNING":
                    job.heartbeat_at = utcnow()
                    db.commit()
        except Exception:
            log.exception("heartbeat failed for %s", job_id)


def _check(job_id: str, stage: str | None = None, progress: int | None = None) -> None:
    with new_session() as db:
        job = db.get(Job, job_id)
        if job.status != "RUNNING":
            raise Lost()
        if stage:
            job.stage, job.progress, job.heartbeat_at = stage, max(job.progress, progress or 0), utcnow()
        cancel = job.cancel_requested
        db.commit()
    if cancel:
        raise Canceled()


def run_thumbnail_job(job_id: str, editors=None) -> str:
    """Run one claimed premium thumbnail job to a final state. Always settles its credits. Returns the status."""
    s, storage = get_settings(), get_storage()
    with new_session() as db:
        job = db.get(Job, job_id)
        opts = dict(job.options or {})
        clip = db.get(Clip, opts.get("clip_id"))
        source = db.get(Job, clip.job_id) if clip is not None else None
        frame_key = clip.frame_key if clip is not None and clip.deleted_at is None else None
        text, canvas, accent = (hook_of(clip, source), canvas_for_clip(clip), accent_of(source)) if clip else (None, None, None)
    work = Path(tempfile.mkdtemp(prefix="thm_", dir=s.work_dir))
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(job_id, stop), daemon=True).start()
    status, error, info, stored = "FAILED", ("processing_failed", "Something went wrong."), {}, []
    try:
        _check(job_id, "starting", 5)
        if not frame_key:
            raise GenerationFailed("clip_gone", FAILED_MESSAGE["clip_gone"], [])
        storage.fetch(frame_key, work / "frame.jpg")
        _check(job_id, "generating", 20)
        look = style_look(s, opts.get("style", "")) or ""
        if canvas is None:
            from PIL import Image
            with Image.open(work / "frame.jpg") as im:
                canvas = Canvas(im.size)
        got = generate(work / "frame.jpg", work / "out", look=look, instruction=opts.get("instruction"), text=text,
                       canvas=canvas, accent=accent, editors=editors if editors is not None else editors_from(s),
                       timeout=s.premium_thumb_timeout_sec, between=lambda: _check(job_id))
        info = got.info()
        row_id = new_id("thb")
        clean_key, image_key = f"thumbs/{clip.id}/{row_id}.clean.jpg", f"thumbs/{clip.id}/{row_id}.jpg"
        storage.put(clean_key, got.clean)
        stored.append(clean_key)
        storage.put(image_key, got.image)
        stored.append(image_key)
        with new_session() as db:
            job = db.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
            if job.status != "RUNNING":
                raise Lost()
            if job.cancel_requested:
                raise Canceled()
            row = db.get(Clip, clip.id)
            if row is None or row.deleted_at is not None:
                raise GenerationFailed("clip_gone", FAILED_MESSAGE["clip_gone"], [])
            ensure_original(db, row)
            db.add(ClipThumbnail(id=row_id, clip_id=row.id, account_id=job.account_id, kind="premium", job_id=job.id,
                                 style=opts.get("style"), instruction=opts.get("instruction"), clean_key=clean_key,
                                 image_key=image_key, text=None, show_text=True, info=info))
            job.result = {"thumbnail_id": row_id, **info}
            job.status, job.progress, job.stage, job.finished_at = "SUCCEEDED", 100, "done", utcnow()
            ledger.settle(db, job, success=True)
            db.commit()
        status, error = "SUCCEEDED", None
    except Canceled:
        status, error = "CANCELED", None
    except Lost:
        status, error = "LOST", None
    except GenerationFailed as e:
        info = {"attempts": [a.__dict__ for a in e.attempts],
                "cost_usd": round(sum(a.cost_usd or 0 for a in e.attempts), 6)}
        error = (e.code, f"{FAILED_MESSAGE.get(e.code, 'The thumbnail could not be made.')} "
                         f"Your {price()} credits were refunded.")
        log.warning("premium thumbnail %s failed: %s %s", job_id, e.code, e.message[:200])
    except Exception:
        log.exception("premium thumbnail %s crashed", job_id)
        error = ("processing_failed", f"Something went wrong. Your {price()} credits were refunded.")
    finally:
        stop.set()
        shutil.rmtree(work, ignore_errors=True)
    if status != "SUCCEEDED":
        for key in stored:
            try:
                storage.delete(key)
            except Exception:
                log.exception("could not remove %s", key)
        with new_session() as db:
            job = db.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
            if job.status == "RUNNING":
                job.status, job.finished_at = status, utcnow()
                if error:
                    job.error_code, job.error_message = error
                job.result = info or None
                ledger.settle(db, job, success=False)      # the refund
                db.commit()
            else:
                status = job.status                         # finalised and settled elsewhere
    return status
