"""Link import: `POST /v1/imports {url, consent: true}` turns a public video link into an upload.

An import is a Job row (id `imp_...`, tool `import`, no credits) on a hidden placeholder upload, so the existing
queue and worker run it. The log row is written here, before anything is fetched. When the import succeeds its
`upload_id` works exactly like the id of an uploaded file. See app/ingest/ for the rules and the downloaders.
"""
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ledger
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .ingest import UPLOAD_INSTEAD, Refused
from .ingest.fetch import check_hop
from .ingest.runner import IMPORT_PREFIX
from .ingest.sources import SOURCES, classify
from .models import Account, ImportLog, Job, Upload, new_id, utcnow
from .routes_media import ACTIVE, ALLOWED_EXT, iso, upload_json

router = APIRouter()
BULK_MAX = 10               # links per bulk request. One number for everyone: plan limits are the owner's call.
MAX_ACTIVE_IMPORTS = 10     # imports one account may have waiting or running at once
CONSENT_TEXT = "I own this content or have permission to clip it."
_IS_IMPORT = Job.id.like(f"{IMPORT_PREFIX}\\_%", escape="\\")


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")       # url and consent only: no option reaches a downloader
    url: str
    consent: Any = None


class BulkImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urls: list[str]
    consent: Any = None


def require_consent(consent: Any) -> None:
    if consent is not True:
        raise ApiError(422, "consent_required",
                       "consent must be true: confirm that you own this content or have permission to clip it. "
                       "Nothing is imported without it.")


def require_enabled(p: Principal) -> None:
    if not get_settings().imports_enabled:
        raise ApiError(503, "imports_disabled", f"Link import is switched off for now. {UPLOAD_INSTEAD}")
    if not p.account.email_verified:
        raise ApiError(403, "email_not_verified", "Confirm your email address before importing links.")


def import_json(db: Session, job: Job) -> dict:
    placeholder = db.get(Upload, job.upload_id)
    upload_id = (job.result or {}).get("upload_id") if job.status == "SUCCEEDED" else None
    upload = db.get(Upload, upload_id) if upload_id else None
    if upload is not None and (upload.deleted_at or upload.expires_at <= utcnow()):
        upload = None                               # expired or taken down since
    return {"import_id": job.id, "status": job.status, "stage": job.stage, "progress": job.progress,
            "url": placeholder.source_url, "platform": placeholder.source_platform,
            "upload_id": upload.id if upload else None, "upload": upload_json(upload) if upload else None,
            "reused": bool((job.result or {}).get("reused")),
            "error": {"code": job.error_code, "message": job.error_message} if job.error_code else None,
            "created_at": iso(job.created_at), "finished_at": iso(job.finished_at)}


def create_import(db: Session, account: Account, url: str) -> tuple[Job, bool]:
    """Validate, log, queue. Returns (job, created); `created` is False when the same link is already being
    imported for this account. Raises Refused (a 422) or ApiError. Nothing is fetched here."""
    source = classify(url)
    if source.platform == "direct":
        check_hop(source.fetch_url)         # a name lookup only; the worker checks again and pins the address
    s = get_settings()
    ledger.lock_account(db, account.id)     # serialise this account's imports (Postgres row lock)
    active = db.execute(select(Job).where(Job.account_id == account.id, _IS_IMPORT,
                                          Job.status.in_(ACTIVE))).scalars().all()
    for job in active:
        if db.get(Upload, job.upload_id).source_url == source.url:
            return job, False
    if len(active) >= MAX_ACTIVE_IMPORTS:
        raise ApiError(429, "too_many_imports", f"{MAX_ACTIVE_IMPORTS} imports are already waiting or running. "
                                                "Wait for one to finish before adding more.")
    now = utcnow()
    expires = now + timedelta(days=s.retention_days)
    # The log row: who asked for which link, and that they confirmed their rights. Written before any fetch.
    db.add(ImportLog(account_id=account.id, source_url=source.url, platform=source.platform, consent=True,
                     created_at=now))
    # A placeholder upload, hidden (deleted_at set) until the file is stored: no job can run on it before then.
    placeholder = Upload(id=new_id("upl"), account_id=account.id, filename="import", storage_key="", size_bytes=0,
                         duration_sec=0.0, width=0, height=0, has_audio=False, source_url=source.url,
                         source_platform=source.platform, created_at=now, expires_at=expires, deleted_at=now)
    db.add(placeholder)
    db.flush()
    job = Job(id=new_id(IMPORT_PREFIX), account_id=account.id, upload_id=placeholder.id,
              options={"tool": "import", "url": source.url, "platform": source.platform},
              duration_sec=0.0, credits_reserved=0, expires_at=expires)       # an import costs nothing
    db.add(job)
    db.commit()
    return job, True


def own_import(db: Session, p: Principal, import_id: str, lock: bool = False) -> Job:
    query = select(Job).where(Job.id == import_id, Job.account_id == p.account.id, _IS_IMPORT)
    job = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if not job:
        raise ApiError(404, "not_found", "No such import.")
    return job


@router.get("/v1/imports/sources")
def import_sources():
    """What can be imported, the limits, and the confirmation every import needs. No login needed."""
    s = get_settings()
    return {"enabled": s.imports_enabled, "sources": list(SOURCES), "file_types": sorted(ALLOWED_EXT),
            "bulk_max": BULK_MAX, "consent": CONSENT_TEXT,
            "max_bytes": min(s.import_max_bytes, s.max_upload_bytes),
            "max_duration_sec": min(s.import_max_duration_sec, s.max_duration_sec)}


@router.post("/v1/imports", status_code=202)
def create(body: ImportRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Import one public video link. `consent` must be true: you own the content or have permission to clip it.
    Free. Follow `GET /v1/imports/{import_id}` until `upload_id` is set, then use it like any upload."""
    require_enabled(p)
    require_consent(body.consent)
    try:
        job, _created = create_import(db, p.account, body.url)
    except Refused as e:
        db.rollback()
        raise ApiError(422, e.code, e.message) from None
    return import_json(db, job)


@router.post("/v1/imports/bulk")
def create_bulk(body: BulkImportRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Import up to 10 links. Each link is its own import with its own log row; the answer lists every link with
    its import or the reason it was refused."""
    require_enabled(p)
    require_consent(body.consent)
    if not body.urls:
        raise ApiError(422, "no_urls", "Send at least one link in urls.")
    if len(body.urls) > BULK_MAX:
        raise ApiError(422, "too_many_urls", f"Send at most {BULK_MAX} links at once.")
    results, account_id = [], p.account.id
    for url in body.urls:
        try:
            job, _created = create_import(db, db.get(Account, account_id), url)
            results.append({"url": url, "import": import_json(db, job), "error": None})
        except (Refused, ApiError) as e:
            db.rollback()
            results.append({"url": url, "import": None, "error": {"code": e.code, "message": e.message}})
    accepted = sum(1 for r in results if r["import"])
    return {"imports": results, "accepted": accepted, "refused": len(results) - accepted}


@router.get("/v1/imports")
def list_imports(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    total = db.execute(select(func.count(Job.id)).where(Job.account_id == p.account.id, _IS_IMPORT)).scalar_one()
    jobs = db.execute(select(Job).where(Job.account_id == p.account.id, _IS_IMPORT)
                      .order_by(Job.created_at.desc(), Job.id).limit(limit).offset(offset)).scalars().all()
    return {"total": total, "imports": [import_json(db, j) for j in jobs]}


@router.get("/v1/imports/{import_id}")
def get_import(import_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return import_json(db, own_import(db, p, import_id))


@router.post("/v1/imports/{import_id}/cancel")
def cancel_import(import_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    job = own_import(db, p, import_id, lock=True)
    if job.status == "QUEUED":
        job.status, job.finished_at = "CANCELED", utcnow()
        if job.credits_reserved:
            ledger.settle(db, job, success=False)
    elif job.status == "RUNNING":
        job.cancel_requested = True     # the worker stops at its next progress update
    db.commit()
    return import_json(db, job)
