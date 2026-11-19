"""Clips from a link: `POST /v1/clips/from-url {url, consent: true, options}` (routes_ingest.py) imports the video
and runs the clip job on it, with no further step from the client.

States of the one job the customer follows (`job_...`):

    WAITING (stage "importing")  the link is being imported by a normal import job (`imp_...`, `link.import_id`)
      -> QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELED     as any clip job, once the import stored the video
      -> FAILED | CANCELED                                      the import failed, was refused, timed out or was
                                                                cancelled, or the job was cancelled while waiting

Money: the clip job reserves the quoted credits on its own id (`reserve:<job_id>`) when it is created, before
anything is imported, and is settled once (`settle:<job_id>`) like every job. The import itself holds nothing.
- The quote comes from price_clips (routes_media), the function POST /v1/clips/quote uses, on the length the
  link's public metadata gives (the preview) or, when this account already has the video, on that upload.
- When the import finishes, `resolve` runs in the import's own final transaction: it re-prices the job on the
  stored video and queues it, never above the quote (the reservation caps the charge) and lower when the video is
  shorter (`charge`, read by the worker), or fails or cancels it with a full refund.
- A job left WAITING by a crash is finished by `sweep_waiting` (worker); every step checks the job is still
  WAITING under its row lock and the settle key is unique, so each job ends with one reservation and one settle.
"""
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger
from .db import new_session
from .deps import ApiError
from .ingest import UPLOAD_INSTEAD, Span, copies
from .models import Job, Upload, utcnow
from .routes_media import ACTIVE, WAITING, ClipOptions, price_clips

log = logging.getLogger("clipapi.ingest")

LINK = "link"               # the job option that marks a job started from a link (popped by the worker)
CHARGE = "charge"           # the job option with the credits a first run is charged, when below the reservation
REFUNDED = "Your credits were returned."
NO_LENGTH = ("duration_unknown", "This link's length cannot be read before it is downloaded, so it cannot be priced. "
                                 "Import it with POST /v1/imports, then start clips on the upload.")


AUTO_DURATION = "0-90"      # automatic discovery: every moment that passes, 0 to 90 s each, at most MAX_CLIPS


def with_defaults(options: ClipOptions | None) -> ClipOptions:
    """Owner, 2026-11-18: automatic clip discovery is the default, with no 3-clip limit. Options that name a count
    or a length bucket (`max_clips`, `limit`, `duration`) are kept as sent."""
    options = options or ClipOptions()
    if options.model_fields_set & {"max_clips", "limit", "duration"}:
        return options
    return options.model_copy(update={"duration": AUTO_DURATION})


@dataclass
class Plan:
    """What a clip job from a link stores, processes and reserves."""
    options: dict               # the job's stored options (price_clips), without `link`
    seconds: float              # the length it is priced on
    cost: int                   # the credits reserved: the quote
    basis: str                  # "source_minutes" (one credit per started minute) | "rendered" (analysed before)
    upload: Upload | None       # this account's stored copy of the link, when there is one: nothing is imported


def reusable_upload(db: Session, account_id: str, canonical_url: str, span: Span | None = None) -> Upload | None:
    """This account's newest stored, unexpired upload that is exactly this part of the link (`span`; left out:
    the whole video). A stored copy that only contains the part is not handed back here: the import cuts the
    part out of it, without a download (app/ingest/runner.py)."""
    return copies.exact(db, account_id, canonical_url, span or Span())


def plan_for(options: ClipOptions, preview: dict | None, upload: Upload | None, span: Span | None = None) -> Plan:
    """The quote, from the one price function (price_clips). On the stored upload when there is one, else on the
    length the import will bring in: the chosen part (`span`) of the preview's length, or all of it. 422
    duration_unknown when neither gives a length; 422 for options that do not fit the video (as POST
    /v1/clips/quote)."""
    span = span or Span()
    if upload is not None:
        stored, seconds, cost = price_clips(options, upload.duration_sec, upload.has_audio, bool(upload.analyzed))
    else:
        seconds = (preview or {}).get("duration_sec")
        if span.end is not None:
            seconds = span.end - span.start
        elif isinstance(seconds, (int, float)):
            seconds = seconds - span.start
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            raise ApiError(422, *NO_LENGTH)
        stored, seconds, cost = price_clips(options, float(seconds))
    basis = "rendered" if stored.get("charge_basis") == "rendered" else "source_minutes"
    return Plan(stored, seconds, cost, basis, upload)


def estimate_json(db: Session, account_id: str, plan: Plan) -> dict:
    have = ledger.balance(db, account_id)
    note = ("You already have this video: charged for the seconds rendered, never more than this."
            if plan.basis == "rendered" else
            f"One credit per started minute of the video ({plan.seconds / 60:.1f} minutes). Never more than this; "
            "less if the video turns out shorter.")
    return {"credits": plan.cost, "basis": plan.basis, "duration_sec": round(plan.seconds, 2), "balance": have,
            "enough": have >= plan.cost, "note": note}


def request_of(job: Job) -> dict:
    return ((job.options or {}).get(LINK) or {}).get("request") or {}


def range_json(value) -> dict | None:
    span = Span.of(value)
    return None if span.whole else {"start_sec": span.start, "end_sec": span.end}


def transfer_json(imp: Job) -> dict:
    """How far an import is, beyond `stage` and `progress`: the bytes downloaded so far of the bytes expected
    (null when the site does not say), and the part of the video it takes (null: all of it)."""
    result = imp.result or {}
    return {"bytes_done": result.get("bytes_done"), "bytes_total": result.get("bytes_total"),
            "range": range_json(result.get("range") or (imp.options or {}).get("range"))}


def link_json(db: Session, job: Job) -> dict:
    """The `import` part of a job started from a link."""
    link = (job.options or {}).get(LINK) or {}
    imp = db.get(Job, link["import_id"]) if link.get("import_id") else None
    if imp is None:                     # the account had the video already: nothing was imported
        return {"import_id": None, "status": "SUCCEEDED", "stage": "done", "progress": 100, "url": link.get("url"),
                "platform": link.get("platform"), "reused": True, "bytes_done": None, "bytes_total": None,
                "range": range_json(link.get("range")),
                "upload_id": job.upload_id, "error": None}
    ready = job.status != WAITING and imp.status == "SUCCEEDED"
    return {"import_id": imp.id, "status": imp.status, "stage": imp.stage, "progress": imp.progress,
            **transfer_json(imp),
            "url": link.get("url"), "platform": link.get("platform"),
            "reused": bool((imp.result or {}).get("reused")),
            "upload_id": job.upload_id if ready else None,
            "error": {"code": imp.error_code, "message": imp.error_message} if imp.error_code else None}


def equal_request(db: Session, account_id: str, url: str, request: dict, asked: list | None = None) -> Job | None:
    """A job of this account, waiting, queued or running, started from the same link with the same options and
    the same range (`asked`: the request's start and end, None for the whole video)."""
    for job in db.execute(select(Job).where(Job.account_id == account_id, Job.status.in_((WAITING, *ACTIVE)))
                          .order_by(Job.created_at)).scalars():
        link = (job.options or {}).get(LINK) or {}
        if link.get("url") == url and link.get("request") == request and link.get("asked") == asked:
            return job
    return None


def _waiting_on(db: Session, imp: Job) -> list[Job]:
    jobs = db.execute(select(Job).where(Job.account_id == imp.account_id, Job.status == WAITING)
                      .order_by(Job.created_at).with_for_update()).scalars().all()
    return [j for j in jobs if ((j.options or {}).get(LINK) or {}).get("import_id") == imp.id]


def _end(job: Job, status: str, error: tuple[str, str] | None, db: Session) -> None:
    job.status, job.finished_at, job.stage = status, utcnow(), None
    if error:
        job.error_code, job.error_message = error
    ledger.settle(db, job, success=False)               # a full refund


def _queue(db: Session, job: Job, upload: Upload) -> None:
    """Price the job again on the stored video and queue it. Raises ApiError when the options do not fit it."""
    stored, seconds, cost = price_clips(ClipOptions(**request_of(job)), upload.duration_sec, upload.has_audio,
                                        bool(upload.analyzed))
    link = {**job.options[LINK], "upload_id": upload.id, "real_sec": round(upload.duration_sec, 3)}
    options = {**stored, LINK: link}
    if stored.get("charge_basis") != "rendered":
        options[CHARGE] = min(cost, job.credits_reserved)   # never more than the quote; less for a shorter video
    job.upload_id, job.duration_sec, job.options = upload.id, seconds, options
    job.status, job.stage, job.progress = "QUEUED", None, 0


def settle_waiting(db: Session, job: Job, imp: Job | None) -> bool:
    """Queue or end one WAITING job now that its import is final. False if it was not waiting any more. The
    caller holds the job's row lock and commits."""
    if job.status != WAITING or (imp is not None and imp.status in ACTIVE):
        return False                    # settled already, or the import is still waiting or running
    if imp is not None and imp.status == "SUCCEEDED":
        upload_id = (imp.result or {}).get("upload_id")
        upload = db.get(Upload, upload_id) if upload_id else None
        if upload is None or upload.deleted_at is not None or upload.expires_at <= utcnow():
            _end(job, "FAILED", ("import_failed", f"The imported video is no longer stored. {REFUNDED}"), db)
            return True
        try:
            _queue(db, job, upload)
        except ApiError as e:
            _end(job, "FAILED", (e.code, f"{e.message} {REFUNDED}"), db)
    elif imp is not None and imp.status == "CANCELED":
        _end(job, "CANCELED", (imp.error_code, imp.error_message) if imp.error_code else None, db)
    else:                               # failed, refused, timed out, lost, or missing
        code = (imp.error_code if imp is not None else None) or "import_failed"
        message = (imp.error_message if imp is not None else None) or f"The link could not be imported. {UPLOAD_INSTEAD}"
        _end(job, "FAILED", (code, message if "credits" in message else f"{message} {REFUNDED}"), db)
    return True


def resolve(db: Session, imp: Job) -> list[str]:
    """Settle every job waiting for this import, which has just reached its final state in this transaction.
    Returns the ids of the jobs that ended (failed or cancelled) here."""
    ended = []
    for job in _waiting_on(db, imp):
        settle_waiting(db, job, imp)
        if job.status != "QUEUED":
            ended.append(job.id)
    return ended


def cancel_waiting(db: Session, job: Job) -> None:
    """Cancel a WAITING job (the caller holds its row lock): refunded now. Its import is stopped too when it was
    started for a link clip job and no other job waits for it."""
    _end(job, "CANCELED", None, db)
    link = (job.options or {}).get(LINK) or {}
    imp = db.execute(select(Job).where(Job.id == link.get("import_id")).with_for_update()
                     ).scalar_one_or_none() if link.get("import_id") else None
    if imp is None or not (imp.options or {}).get("chained") or _waiting_on(db, imp):
        return
    if imp.status == "QUEUED":
        imp.status, imp.finished_at = "CANCELED", utcnow()
    elif imp.status == "RUNNING":
        imp.cancel_requested = True     # the import stops at its next progress update


def sweep_waiting() -> int:
    """WAITING jobs whose import is final (or gone) but that were not settled with it, for example after a crash
    between the two: queued or refunded now. Safe to run any number of times."""
    n, ended = 0, []
    with new_session() as db:
        for job in db.execute(select(Job).where(Job.status == WAITING).order_by(Job.created_at)
                              .with_for_update(skip_locked=True)).scalars().all():
            link = (job.options or {}).get(LINK) or {}
            imp = db.get(Job, link["import_id"]) if link.get("import_id") else None
            if imp is not None and imp.status in ACTIVE:
                continue
            if settle_waiting(db, job, imp):
                n += 1
                if job.status != "QUEUED":
                    ended.append(job.id)
        db.commit()
    notify(ended)
    return n


def notify(job_ids: list[str]) -> None:
    """The webhook of each job that ended without reaching a worker."""
    if job_ids:
        from .worker import send_webhook
        for job_id in job_ids:
            send_webhook(job_id)
