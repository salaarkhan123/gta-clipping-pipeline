"""What an account already has from a link, so the same video is never downloaded twice.

An imported upload keeps its source link (`uploads.source_url`). Which part of the source it holds is on the import
job that made it (`jobs.upload_id` is that upload): `result.range` is the part that was taken, `[start, end]` in
seconds of the source, absent or null for the whole video.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job, Upload, utcnow
from . import Span

IMPORT_PREFIX = "imp"       # import jobs are Job rows whose id starts with this
CLOSE = 0.5                 # two ranges this close at both ends are the same range


def span_of(db: Session, upload: Upload) -> Span:
    """The part of its source that an imported upload holds."""
    made_by = db.execute(select(Job).where(Job.upload_id == upload.id, Job.id.like(f"{IMPORT_PREFIX}\\_%", escape="\\"))
                         .order_by(Job.created_at).limit(1)).scalar_one_or_none()
    if made_by is None:
        return Span()
    return Span.of((made_by.result or {}).get("range") or (made_by.options or {}).get("range"))


def same(a: Span, b: Span) -> bool:
    if (a.end is None) != (b.end is None) or abs(a.start - b.start) > CLOSE:
        return False
    return a.end is None or abs(a.end - b.end) <= CLOSE


def stored(db: Session, account_id: str, canonical_url: str) -> list[tuple[Upload, Span]]:
    """This account's stored, unexpired uploads imported from this link, newest first, each with its span."""
    uploads = db.execute(select(Upload).where(
        Upload.account_id == account_id, Upload.source_url == canonical_url, Upload.deleted_at.is_(None),
        Upload.expires_at > utcnow(), Upload.storage_key != "").order_by(Upload.created_at.desc())).scalars().all()
    return [(u, span_of(db, u)) for u in uploads]


def exact(db: Session, account_id: str, canonical_url: str, span: Span) -> Upload | None:
    """The stored upload that is exactly this part of the link."""
    return next((u for u, have in stored(db, account_id, canonical_url) if same(have, span)), None)


def holding(db: Session, account_id: str, canonical_url: str, span: Span) -> tuple[Upload, Span] | None:
    """A stored upload that contains this part of the link (a longer range, or the whole video)."""
    return next(((u, have) for u, have in stored(db, account_id, canonical_url) if have.holds(span)), None)
