"""Everything we hold about one account: a copy of it (`export`) and its deletion (`delete`), ticket #149.

Used by GET /v1/me/export, POST /v1/me/delete, the admin routes for requests that arrive by email
(app/routes_account.py) and `scripts/admin.py export-account | delete-account`.

Deletion keeps the rows that other records point at (the account, its uploads, jobs, clips and exports: the credit
ledger and payments reference them) and empties them of personal data. It deletes every stored object under the
account's key prefixes, so files added later under the same layout go too. What stays:

- `credit_ledger` and `payments`, untouched (append-only accounting)
- `policy_acceptances` and `likeness_consents`: proof of consent (retention: #150)
- `import_log` and `clip_feedback` (retention: #150)
- copyright and likeness cases. Canada's Copyright Act s. 41.26(1)(b) requires records that identify the person to
  be kept for 6 months to 1 year: a case younger than a year gets one `account_deleted` event holding the account id
  and the old email, so the identity survives only inside that case.

Running `delete` again is safe: it repeats the file deletion (an interrupted run left some) and changes nothing
else. Files are deleted before the caller commits the row changes.
"""
import hashlib
import hmac
import logging
from dataclasses import asdict, dataclass
from datetime import timedelta

from sqlalchemy import delete as sql_delete
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import ledger, trust
from .config import get_settings
from .models import (Account, ApiKey, CaseEvent, CaseTarget, Clip, ClipFeedback, ClipThumbnail, CreditLedger,
                     CustomTemplate, Export, ImportLog, Job, LikenessConsent, Payment, PolicyAcceptance, TrustCase,
                     Upload, WebhookDelivery, utcnow)
from .storage import get_storage
from .thumbnail_jobs import thumbnail_keys
from .thumbnails import frame_key_of
from .trust_decisions import Refused

log = logging.getLogger("clipapi.account")
OPEN_CASE = ("received", "in_review", "info_requested", "disabled", "removed", "counter_noticed")
CASE_RECORD_DAYS = 365          # Copyright Act s. 41.26(1)(b): 6 months to 1 year; we keep the longer
CONTACT = "support@clutchclips.io"
iso = trust.iso


def email_hash(email: str) -> str:
    """Keyed hash of an email address, the same for any capitalisation."""
    return hmac.new(get_settings().secret_key.encode(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


def was_deleted_before(db: Session, email: str) -> bool:
    """True when an account with this email was deleted (it already had its free sign-up grant)."""
    return db.execute(select(Account.id).where(Account.status == "deleted",
                                               Account.deleted_email_hash == email_hash(email))).first() is not None


# ---------- export ----------

def _all(db: Session, query) -> list:
    return list(db.execute(query).scalars())


def export(db: Session, account: Account) -> dict:
    """Everything we hold about the account as plain JSON. Never the password hash or the webhook secret."""
    a = account
    uploads = _all(db, select(Upload).where(Upload.account_id == a.id).order_by(Upload.created_at, Upload.id))
    jobs = _all(db, select(Job).where(Job.account_id == a.id).order_by(Job.created_at, Job.id))
    job_ids = [j.id for j in jobs]
    clips = _all(db, select(Clip).where(Clip.job_id.in_(job_ids)).order_by(Clip.job_id, Clip.idx)) if job_ids else []
    case_ids = select(CaseTarget.case_id).where(CaseTarget.account_id == a.id)
    cases = _all(db, select(TrustCase).where(TrustCase.id.in_(case_ids)).order_by(TrustCase.created_at))
    mine = _all(db, select(CaseTarget).where(CaseTarget.account_id == a.id).order_by(CaseTarget.id))
    return {
        "exported_at": iso(utcnow()),
        "profile": {"id": a.id, "email": a.email, "email_verified": a.email_verified, "plan": a.plan or "free",
                    "status": a.status, "created_at": iso(a.created_at), "signup_ip": a.signup_ip,
                    "stripe_customer_id": a.stripe_customer_id, "stripe_subscription_id": a.stripe_subscription_id,
                    "subscription_status": a.subscription_status,
                    "subscription_cancel_at": iso(a.subscription_cancel_at),
                    "subscription_updated_at": iso(a.subscription_event_at)},
        "api_keys": [{"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": iso(k.created_at),
                      "last_used_at": iso(k.last_used_at), "revoked_at": iso(k.revoked_at)}
                     for k in _all(db, select(ApiKey).where(ApiKey.account_id == a.id).order_by(ApiKey.created_at))],
        "policy_acceptances": [{"policy": p.policy, "version": p.version, "source": p.source,
                                "accepted_at": iso(p.accepted_at)}
                               for p in _all(db, select(PolicyAcceptance).where(PolicyAcceptance.account_id == a.id)
                                             .order_by(PolicyAcceptance.id))],
        "uploads": [{"id": u.id, "filename": u.filename, "size_bytes": u.size_bytes, "duration_sec": u.duration_sec,
                     "width": u.width, "height": u.height, "language": u.language, "source_url": u.source_url,
                     "source_platform": u.source_platform, "created_at": iso(u.created_at),
                     "expires_at": iso(u.expires_at), "deleted_at": iso(u.deleted_at)} for u in uploads],
        "jobs": [{"id": j.id, "upload_id": j.upload_id, "name": j.name, "status": j.status, "options": j.options,
                  "duration_sec": j.duration_sec, "credits_reserved": j.credits_reserved,
                  "credits_charged": j.credits_charged, "webhook_url": j.webhook_url, "error_code": j.error_code,
                  "created_at": iso(j.created_at), "finished_at": iso(j.finished_at)} for j in jobs],
        "clips": [{"id": c.id, "job_id": c.job_id, "index": c.idx, "start": c.start_sec, "end": c.end_sec,
                   "score": c.score, "kind": c.kind, "meta": c.meta, "edit": c.edit, "kept": c.kept,
                   "reaction": c.reaction, "bookmarked": c.bookmarked, "created_at": iso(c.created_at),
                   "deleted_at": iso(c.deleted_at)} for c in clips],
        "clip_feedback": [{"clip_id": f.clip_id, "kind": f.kind, "value": f.value, "created_at": iso(f.created_at)}
                          for f in _all(db, select(ClipFeedback).where(ClipFeedback.account_id == a.id)
                                        .order_by(ClipFeedback.id))],
        "exports": [{"id": e.id, "clip_id": e.clip_id, "resolution": e.resolution, "status": e.status,
                     "options": e.options, "created_at": iso(e.created_at)}
                    for e in _all(db, select(Export).where(Export.account_id == a.id).order_by(Export.created_at))],
        "templates": [{"id": t.id, "name": t.name, "options": t.options, "created_at": iso(t.created_at),
                       "updated_at": iso(t.updated_at), "deleted_at": iso(t.deleted_at)}
                      for t in _all(db, select(CustomTemplate).where(CustomTemplate.account_id == a.id)
                                    .order_by(CustomTemplate.created_at))],
        "credit_ledger": [{"id": r.id, "delta": r.delta, "kind": r.kind, "job_id": r.job_id, "note": r.note,
                           "created_at": iso(r.created_at)}
                          for r in _all(db, select(CreditLedger).where(CreditLedger.account_id == a.id)
                                        .order_by(CreditLedger.id))],
        "payments": [{"kind": p.kind, "amount_cents": p.amount_cents, "credits": p.credits,
                      "credits_removed": p.credits_removed, "status": p.status, "created_at": iso(p.created_at)}
                     for p in _all(db, select(Payment).where(Payment.account_id == a.id).order_by(Payment.id))],
        "import_log": [{"source_url": i.source_url, "platform": i.platform, "consent": i.consent,
                        "created_at": iso(i.created_at)}
                       for i in _all(db, select(ImportLog).where(ImportLog.account_id == a.id).order_by(ImportLog.id))],
        "webhook_deliveries": [{"job_id": w.job_id, "url": w.url, "status_code": w.status_code, "attempt": w.attempt,
                                "created_at": iso(w.created_at)}
                               for w in (_all(db, select(WebhookDelivery).where(WebhookDelivery.job_id.in_(job_ids))
                                              .order_by(WebhookDelivery.id)) if job_ids else [])],
        "cases": [trust.my_case_json(c, [t for t in mine if t.case_id == c.id]) for c in cases],
        "premium_thumbnails": [{"id": t.id, "clip_id": t.clip_id, "kind": t.kind, "style": t.style,
                                "instruction": t.instruction, "text": t.text, "created_at": iso(t.created_at),
                                "deleted_at": iso(t.deleted_at)}
                               for t in _all(db, select(ClipThumbnail).where(ClipThumbnail.account_id == a.id)
                                             .order_by(ClipThumbnail.created_at))],
        "likeness_consents": [{"clip_id": c.clip_id, "consent": c.consent, "wording": c.wording,
                               "created_at": iso(c.created_at)}
                              for c in _all(db, select(LikenessConsent).where(LikenessConsent.account_id == a.id)
                                            .order_by(LikenessConsent.id))],
    }


# ---------- delete ----------

@dataclass
class Report:
    account_id: str
    dry_run: bool = False
    already_deleted: bool = False
    old_email: str = ""
    jobs_cancelled: int = 0
    credits_refunded: int = 0
    files_deleted: int = 0
    uploads: int = 0
    jobs: int = 0
    clips: int = 0
    exports: int = 0
    api_keys: int = 0
    templates: int = 0
    webhook_deliveries: int = 0
    thumbnails: int = 0
    case_records: int = 0

    def counts(self) -> dict:
        out = asdict(self)
        for private in ("account_id", "dry_run", "already_deleted", "old_email"):
            out.pop(private)
        return out

    def lines(self) -> list[str]:
        verb = "would be" if self.dry_run else "were"
        head = f"Delete account {self.account_id}" + (" (dry run: nothing is changed)" if self.dry_run else "")
        if self.already_deleted:
            head += " (already deleted: repeating the file deletion)"
        return [head,
                f"  {self.files_deleted} file(s) {verb} deleted",
                f"  {self.jobs_cancelled} queued job(s) {verb} cancelled, {self.credits_refunded} credit(s) returned",
                f"  emptied: {self.uploads} upload(s), {self.jobs} job(s), {self.clips} clip(s), {self.exports} "
                f"export(s)",
                f"  deleted rows: {self.api_keys} API key(s), {self.templates} template(s), {self.webhook_deliveries} "
                f"webhook delivery(ies), {self.thumbnails} thumbnail(s)",
                f"  {self.case_records} case record(s) keep the identity (Copyright Act s. 41.26(1)(b))",
                "  kept: credit ledger, payments, policy acceptances, likeness consents, import log, clip feedback"]


def _refuse_if_blocked(db: Session, a: Account, jobs: list[Job]) -> list[TrustCase]:
    if a.stripe_subscription_id and a.subscription_status not in (None, "canceled"):
        raise Refused("subscription_active", "Your paid plan is still active. Cancel it first in Billing (Manage "
                                             "billing), then delete your account once it shows as canceled.")
    case_ids = select(CaseTarget.case_id).where(CaseTarget.account_id == a.id)
    cases = _all(db, select(TrustCase).where(TrustCase.id.in_(case_ids)).order_by(TrustCase.created_at))
    if any(c.status in OPEN_CASE for c in cases):
        raise Refused("case_open", "A copyright or likeness report about your content is still open, so the "
                                   f"account cannot be deleted yet. Email {CONTACT} and we will help.")
    if any(j.status == "RUNNING" for j in jobs):
        raise Refused("job_running", "A job is still running. Wait for it to finish or cancel it, then try again.")
    return cases


def _stored_files(db: Session, a: Account, uploads: list[Upload], jobs: list[Job], clips: list[Clip],
                  exports: list[Export], dry_run: bool) -> int:
    """Delete every object under the account's prefixes, plus any key a row names outside them."""
    storage = get_storage()
    prefixes = [f"uploads/{a.id}/",
                *(p for u in uploads for p in (f"transcripts/{u.id}", f"index/{u.id}")),
                *(p for j in jobs for p in (f"clips/{j.id}/", f"exports/{j.id}/")),
                *(f"thumbs/{c.id}/" for c in clips)]
    named = [*(u.storage_key for u in uploads),
             *(k for c in clips for k in (c.video_key, c.thumb_key, c.captions_key, c.preview_key, c.export_key,
                                          c.thumb_chosen_key, frame_key_of(c.features))),
             *(e.storage_key for e in exports), *thumbnail_keys(db, [c.id for c in clips])]
    outside = [k for k in dict.fromkeys(named) if k and not k.startswith(tuple(prefixes))]
    n = 0
    for prefix in prefixes:
        n += len(storage.keys(prefix)) if dry_run else storage.delete_prefix(prefix)
    for key in outside:
        if storage.exists(key):
            n += 1
            if not dry_run:
                storage.delete(key)
    return n


def delete(db: Session, account: Account, actor: str, dry_run: bool = False) -> Report:
    """Delete the account's personal data and files; see the module docstring. Raises Refused (and changes
    nothing) while a paid subscription is live, a case about its content is open or one of its jobs is running.
    `actor`: who asked ("self" or "admin:<id>"), for the log. The caller commits (or rolls back a dry run)."""
    now = utcnow()
    a = ledger.lock_account(db, account.id)
    report = Report(a.id, dry_run=dry_run, already_deleted=a.status == "deleted", old_email=a.email)
    jobs = _all(db, select(Job).where(Job.account_id == a.id).order_by(Job.created_at).with_for_update())
    cases = _refuse_if_blocked(db, a, jobs)

    for job in jobs:                                         # c. queued jobs: cancelled and refunded
        if job.status == "QUEUED":
            job.status, job.finished_at, job.error_code = "CANCELED", now, "account_deleted"
            report.jobs_cancelled += 1
            if job.credits_reserved and ledger.settle(db, job, success=False):
                report.credits_refunded += job.credits_reserved
    db.flush()

    job_ids = [j.id for j in jobs]
    uploads = _all(db, select(Upload).where(Upload.account_id == a.id))
    clips = _all(db, select(Clip).where(Clip.job_id.in_(job_ids))) if job_ids else []
    clip_ids = [c.id for c in clips]
    exports = _all(db, select(Export).where(or_(Export.account_id == a.id, Export.clip_id.in_(clip_ids))))
    report.files_deleted = _stored_files(db, a, uploads, jobs, clips, exports, dry_run)   # d. before the commit

    for u in uploads:                                        # e. rows the ledger and payments point at: emptied
        u.deleted_at = u.deleted_at or now
        u.filename, u.source_url, u.source_platform, u.content_hash, u.storage_key = "deleted", None, None, None, ""
    for j in jobs:
        j.options = {"tool": (j.options or {}).get("tool", "clips")}
        j.name = j.webhook_url = j.result = j.error_message = j.idempotency_key = None
    for c in clips:
        c.deleted_at = c.deleted_at or now
        c.meta = c.edit = None
        c.features, c.signals = {}, {}
        c.video_key = ""
        c.thumb_key = c.captions_key = c.preview_key = c.export_key = c.thumb_chosen_key = c.thumb_id = None
    for e in exports:
        e.options, e.storage_key = {}, None
    report.uploads, report.jobs, report.clips, report.exports = len(uploads), len(jobs), len(clips), len(exports)

    def gone(model, *where) -> int:                          # f. rows that only hold the account's data
        return db.execute(sql_delete(model).where(*where).execution_options(synchronize_session=False)).rowcount
    report.api_keys = gone(ApiKey, ApiKey.account_id == a.id)
    report.templates = gone(CustomTemplate, CustomTemplate.account_id == a.id)
    report.webhook_deliveries = gone(WebhookDelivery, WebhookDelivery.job_id.in_(job_ids)) if job_ids else 0
    report.thumbnails = gone(ClipThumbnail, or_(ClipThumbnail.account_id == a.id, ClipThumbnail.clip_id.in_(clip_ids)))

    cutoff = now - timedelta(days=CASE_RECORD_DAYS)          # h. the identity, kept inside recent cases only
    for case in [c for c in cases if c.created_at >= cutoff]:
        done = any((e.data or {}).get("account_id") == a.id for e in db.execute(select(CaseEvent).where(
            CaseEvent.case_id == case.id, CaseEvent.action == "account_deleted")).scalars())
        if not done and not report.already_deleted:
            db.add(CaseEvent(case_id=case.id, actor_kind="system", action="account_deleted", created_at=now,
                             data={"account_id": a.id, "email": a.email}))
            report.case_records += 1

    if not report.already_deleted:                           # i. the account itself
        a.deleted_email_hash = email_hash(a.email)
        a.deleted_at = now
    a.email = f"deleted+{a.id}@deleted.invalid"
    a.password_hash = a.webhook_secret = ""
    a.email_verified = a.is_admin = False
    a.signup_ip = a.stripe_customer_id = a.stripe_subscription_id = None
    a.subscription_status = a.subscription_cancel_at = a.subscription_event_at = None
    a.plan, a.status = "free", "deleted"
    db.flush()
    if not dry_run:
        log.warning("account %s deleted by %s: %s", a.id, actor, report.counts())
    return report
