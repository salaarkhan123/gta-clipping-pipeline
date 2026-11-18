"""Link import: `POST /v1/imports {url, consent: true}` turns a public video link into an upload.
`POST /v1/imports/preview {url, options?}` says what a link is, and what clipping it would cost, before anything is
imported (app/ingest/preview.py). `POST /v1/clips/from-url {url, consent: true, options}` imports a link and runs
the clip job on it in one call (app/url_clips.py).

An import is a Job row (id `imp_...`, tool `import`, no credits) on a hidden placeholder upload, so the existing
queue and worker run it. The log row is written here, before anything is fetched. When the import succeeds its
`upload_id` works exactly like the id of an uploaded file. See app/ingest/ for the rules and the downloaders.
"""
import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ledger, url_clips
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal, rate_limit
from .ingest import UPLOAD_INSTEAD, Refused
from .ingest import preview as link_preview
from .ingest.fetch import check_hop
from .ingest.runner import IMPORT_PREFIX
from .ingest.sources import SOURCES, classify
from .models import Account, ImportLog, Job, Upload, new_id, utcnow
from .plans import PLANS, plan_of
from .routes_media import (ACTIVE, ALLOWED_EXT, WAITING, ClipOptions, iso, job_json, open_job, replayed,
                           upload_json)
from .security import is_public_https_url

log = logging.getLogger("clipapi.ingest")
router = APIRouter()
BULK_MAX = PLANS[0]["bulk_import_max"]   # links per bulk request on the free plan; paid plans allow more (app/plans.py)
MAX_ACTIVE_IMPORTS = 10     # imports one account may have waiting or running at once (at least its plan's bulk size)
CONSENT_TEXT = "I own this content or have permission to clip it."
_IS_IMPORT = Job.id.like(f"{IMPORT_PREFIX}\\_%", escape="\\")


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")       # url and consent only: no option reaches a downloader
    url: str
    consent: Any = None


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    options: ClipOptions | None = None      # the clip options to price; left out: the defaults of POST /v1/clips


class UrlClipRequest(BaseModel):
    """POST /v1/clips/from-url: POST /v1/clips with a link in place of an upload, and the import's consent."""
    model_config = ConfigDict(extra="forbid")
    url: str
    consent: Any = None
    options: ClipOptions = ClipOptions()
    webhook_url: str | None = Field(default=None, max_length=500)


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
    job, created = queue_import(db, account, source)
    db.commit()
    return job, created


def log_consent(db: Session, account_id: str, source) -> None:
    """The log row: who asked for which link, and that they confirmed their rights. Written before any fetch."""
    db.add(ImportLog(account_id=account_id, source_url=source.url, platform=source.platform, consent=True,
                     created_at=utcnow()))


def queue_import(db: Session, account: Account, source, chained: bool = False) -> tuple[Job, bool]:
    """create_import without the checks of the link and without the commit: the caller commits. `chained`: the
    import is started for a link clip job (POST /v1/clips/from-url), which is the job that is counted and charged."""
    s = get_settings()
    ledger.lock_account(db, account.id)     # serialise this account's imports (Postgres row lock)
    active = db.execute(select(Job).where(Job.account_id == account.id, _IS_IMPORT,
                                          Job.status.in_(ACTIVE))).scalars().all()
    for job in active:
        if db.get(Upload, job.upload_id).source_url == source.url:
            return job, False
    most = max(MAX_ACTIVE_IMPORTS, plan_of(account)["bulk_import_max"])   # one full bulk import always fits
    if len(active) >= most:
        raise ApiError(429, "too_many_imports", f"{most} imports are already waiting or running. "
                                                "Wait for one to finish before adding more.")
    now = utcnow()
    expires = now + timedelta(days=s.retention_days)
    log_consent(db, account.id, source)
    # A placeholder upload, hidden (deleted_at set) until the file is stored: no job can run on it before then.
    placeholder = Upload(id=new_id("upl"), account_id=account.id, filename="import", storage_key="", size_bytes=0,
                         duration_sec=0.0, width=0, height=0, has_audio=False, source_url=source.url,
                         source_platform=source.platform, created_at=now, expires_at=expires, deleted_at=now)
    db.add(placeholder)
    db.flush()
    job = Job(id=new_id(IMPORT_PREFIX), account_id=account.id, upload_id=placeholder.id,
              options={"tool": "import", "url": source.url, "platform": source.platform,
                       **({"chained": True} if chained else {})},
              duration_sec=0.0, credits_reserved=0, expires_at=expires)       # an import costs nothing
    db.add(job)
    db.flush()
    return job, True


def own_import(db: Session, p: Principal, import_id: str, lock: bool = False) -> Job:
    query = select(Job).where(Job.id == import_id, Job.account_id == p.account.id, _IS_IMPORT)
    job = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if not job:
        raise ApiError(404, "not_found", "No such import.")
    return job


@router.get("/v1/imports/sources")
def import_sources(request: Request, db: Session = Depends(get_db)):
    """What can be imported, the limits, and the confirmation every import needs. No login needed: without one,
    `bulk_max` is the Free plan's. Signed in (session or API key), it is your plan's links per bulk import."""
    s = get_settings()
    bulk_max = BULK_MAX
    if request.headers.get("authorization"):          # a bad token is a 401, never a silent Free answer
        bulk_max = plan_of(current_principal(request, db).account)["bulk_import_max"]
    return {"enabled": s.imports_enabled, "sources": list(SOURCES), "file_types": sorted(ALLOWED_EXT),
            "bulk_max": bulk_max, "consent": CONSENT_TEXT,
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


def look_up(p: Principal, source) -> tuple[dict, bool]:
    """(the preview of a classified link, whether it came from the cache). Lookups that reach the site count
    against the account's limit; cached answers do not."""
    hit = link_preview.cached(source.url)
    if hit is not None:
        return hit, True
    rate_limit(f"preview:{p.account.id}", link_preview.LOOKUPS_PER_MINUTE, 60)
    return link_preview.look(source), False


@router.post("/v1/imports/preview")
def preview(body: PreviewRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """What a link is (platform, title, channel, length, thumbnail) and whether it can be imported. Free, and
    nothing is imported or stored, so no consent is needed. When `supported` is false, `refusal` says why and
    what to do instead. Lookups that reach the site are limited to 10 a minute per account; answers are cached
    for 5 minutes per link (1 minute when the site refused).
    `estimate`: what POST /v1/clips/from-url with these `options` (default: those of POST /v1/clips) would
    reserve, from the same price as POST /v1/clips/quote, with your balance. Nothing is reserved. Null when the
    link is not supported or its length is unknown before a download (import it first, then clip the upload)."""
    require_enabled(p)
    cached, source = False, None
    try:
        source = classify(body.url)
    except Refused as e:
        result = link_preview.answer(body.url, None, refusal=e)
    else:
        result, cached = look_up(p, source)
    refusal = result["refusal"]
    log.info("import preview: account=%s platform=%s url=%r supported=%s refusal=%s cached=%s", p.account.id,
             result["platform"], result["url"][:200], result["supported"], refusal and refusal["code"], cached)
    estimate = None
    if source is not None and result["supported"]:
        upload = url_clips.reusable_upload(db, p.account.id, source.url)
        try:
            plan = url_clips.plan_for(body.options or ClipOptions(), result, upload)
        except ApiError as e:
            if e.code != url_clips.NO_LENGTH[0]:
                raise                       # options that do not fit this video: a 422, as from the quote
        else:
            estimate = url_clips.estimate_json(db, p.account.id, plan)
    return {**result, "estimate": estimate}


@router.post("/v1/clips/from-url", status_code=202)
def clips_from_url(body: UrlClipRequest, response: Response, p: Principal = Depends(current_principal),
                   db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, max_length=200)):
    """Clips from a link in one call: the server imports the video and runs the clip job on it. `consent` must be
    true. The quoted credits (the preview's `estimate`) are reserved now, before anything is imported; the job is
    never charged more, less if the video is shorter, and refunded in full if the import or the job fails or is
    cancelled. Follow `GET /v1/jobs/{job_id}`: status WAITING (stage "importing", `import.progress`), then the
    clip job's stages and its clips. 200 instead of 202 when the same request is already waiting or running (that
    job is returned); a repeated Idempotency-Key returns the job it started."""
    require_enabled(p)
    require_consent(body.consent)
    if not get_settings().accept_jobs:
        raise ApiError(503, "paused", "New jobs are temporarily paused. Try again later.")
    if body.webhook_url and not is_public_https_url(body.webhook_url):
        raise ApiError(422, "bad_webhook_url", "webhook_url must be a public https URL.")
    prior = replayed(db, p, idempotency_key)
    if prior:
        return prior
    try:
        source = classify(body.url)
    except Refused as e:
        raise ApiError(422, e.code, e.message) from None
    account_id, request = p.account.id, body.options.model_dump(mode="json")
    same = url_clips.equal_request(db, account_id, source.url, request)
    if same is not None:                    # a double click: nothing is looked up, logged or reserved again
        response.status_code = 200
        return job_json(db, same, with_clips=False)
    upload = url_clips.reusable_upload(db, account_id, source.url)
    info = None
    if upload is None:                      # metadata only, outside the account lock: never a download
        info, _cached = look_up(p, source)
        if info["refusal"]:
            raise ApiError(422, info["refusal"]["code"], info["refusal"]["message"])
    plan = url_clips.plan_for(body.options, info, upload)

    account = ledger.lock_account(db, account_id)   # serialise this account's submits: a double click waits here
    prior = replayed(db, p, idempotency_key)
    if prior:
        return prior
    same = url_clips.equal_request(db, account_id, source.url, request)
    if same is not None:
        response.status_code = 200
        return job_json(db, same, with_clips=False)
    link = {"url": source.url, "platform": source.platform, "request": request, "import_id": None,
            "quoted_sec": round(plan.seconds, 3), "quoted": plan.cost}
    try:
        if plan.upload is not None:         # the account has this video already: nothing is imported
            log_consent(db, account_id, source)
            job = open_job(db, p, plan.upload.id, {**plan.options, url_clips.LINK: link}, plan.seconds, plan.cost,
                           body.webhook_url, idempotency_key)
        else:
            imp, created = queue_import(db, account, source, chained=True)
            if not created:                 # joins an import of this link already on its way: log this consent
                log_consent(db, account_id, source)
            link["import_id"] = imp.id
            job = open_job(db, p, imp.upload_id, {**plan.options, url_clips.LINK: link}, plan.seconds, plan.cost,
                           body.webhook_url, idempotency_key, status=WAITING, stage="importing")
    except ApiError:
        db.rollback()                       # nothing is logged, queued or reserved
        raise
    if body.options.project_name:
        job.name = body.options.project_name
    db.commit()
    log.info("clips from url: account=%s job=%s import=%s platform=%s url=%r credits=%s", account_id, job.id,
             link["import_id"], source.platform, source.url[:200], plan.cost)
    return job_json(db, job, with_clips=False)


@router.post("/v1/imports/bulk")
def create_bulk(body: BulkImportRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Import several links at once: up to the plan's `bulk_import_max` (Free and Starter 10, Pro 30, Scale 50).
    Each link is its own import with its own log row; the answer lists every link with its import or the reason it
    was refused."""
    require_enabled(p)
    require_consent(body.consent)
    if not body.urls:
        raise ApiError(422, "no_urls", "Send at least one link in urls.")
    plan = plan_of(p.account)
    if len(body.urls) > plan["bulk_import_max"]:
        raise ApiError(422, "too_many_urls", f"The {plan['name']} plan imports at most {plan['bulk_import_max']} "
                                             "links at once.")
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
        url_clips.resolve(db, job)          # clip jobs waiting for it are cancelled and refunded
    elif job.status == "RUNNING":
        job.cancel_requested = True     # the worker stops at its next progress update
    db.commit()
    return import_json(db, job)
