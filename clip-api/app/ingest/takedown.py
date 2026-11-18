"""Takedown: remove everything that came from a source URL, or from all of one account's link imports.

    python scripts/admin.py takedown --url <source url> [--dry-run]
    python scripts/admin.py takedown --account <account id or email> [--dry-run]

For each imported upload it finds: jobs still waiting are cancelled and refunded, running jobs are told to stop
(the worker cancels and refunds them at its next step), every clip is marked deleted and its files removed, and
the upload's file, transcript and search index are removed and the upload marked deleted, the same way expired
files are (worker.sweep_expired). The import log is kept: it is the record of who imported what.
Running it again changes nothing. Files are removed before the rows are marked, so a run that is interrupted can
simply be repeated.
"""
from dataclasses import dataclass, field

from sqlalchemy import select

from .. import ledger
from ..db import new_session
from ..models import Account, Clip, Export, ImportLog, Job, Upload, utcnow
from ..storage import get_storage, transcript_key, vindex_key
from ..thumbnail_jobs import thumbnail_keys
from .sources import canonical

TAKEN_DOWN = ("taken_down", "This video was removed after a takedown request. Any credits held for this job "
                            "were returned.")


@dataclass
class Removed:
    upload_id: str
    account_id: str
    source_url: str
    platform: str | None
    upload_removed: bool = False            # the upload itself was live and is now deleted
    files: list[str] = field(default_factory=list)
    clips: int = 0
    cancelled: list[tuple[str, int]] = field(default_factory=list)     # (job id, credits returned)
    stopping: list[str] = field(default_factory=list)                  # running jobs told to stop
    still_stopping: list[str] = field(default_factory=list)            # told on an earlier run, not finished yet

    @property
    def changed(self) -> bool:
        return bool(self.upload_removed or self.files or self.clips or self.cancelled or self.stopping)


@dataclass
class Report:
    target: str
    dry_run: bool
    log_rows: int
    removed: list[Removed]

    def lines(self) -> list[str]:
        verb = "would remove" if self.dry_run else "removed"
        out = [f"Takedown for {self.target}" + (" (dry run: nothing is changed)" if self.dry_run else "")]
        changed = [r for r in self.removed if r.changed]
        for r in changed:
            out.append(f"  {r.upload_id}  account {r.account_id}  {r.platform or '-'}  {r.source_url}")
            if r.upload_removed:
                out.append(f"    upload {verb}")
            if r.clips:
                out.append(f"    {r.clips} clip(s) {verb}")
            if r.files:
                out.append(f"    {len(r.files)} stored file(s) {verb}")
            for job_id, credits in r.cancelled:
                out.append(f"    job {job_id} {'would be ' if self.dry_run else ''}cancelled, {credits} credit(s) returned")
            for job_id in r.stopping:
                out.append(f"    job {job_id} is running: {'would be ' if self.dry_run else ''}told to stop "
                           "(the worker cancels and refunds it at its next step)")
        for r in self.removed:
            for job_id in r.still_stopping:
                out.append(f"  job {job_id} on {r.upload_id} is still stopping: run this again in a minute to confirm")
        if not changed:
            out.append("  Nothing to remove.")
        else:
            out.append(f"Total: {sum(r.upload_removed for r in changed)} upload(s), {sum(r.clips for r in changed)} "
                       f"clip(s), {sum(len(r.files) for r in changed)} file(s) {verb}; "
                       f"{sum(len(r.cancelled) for r in changed)} job(s) cancelled, "
                       f"{sum(c for r in changed for _j, c in r.cancelled)} credit(s) returned; "
                       f"{sum(len(r.stopping) for r in changed)} running job(s) told to stop.")
        out.append(f"Import log: {self.log_rows} row(s) for this target, kept.")
        return out


def find_account(db, who: str) -> Account:
    account = db.get(Account, who) or db.execute(
        select(Account).where(Account.email == who.strip().lower())).scalar_one_or_none()
    if account is None:
        raise LookupError(f"No account with id or email {who}")
    return account


def _take_down(db, storage, upload: Upload, dry_run: bool) -> Removed:
    now = utcnow()
    out = Removed(upload.id, upload.account_id, upload.source_url or "", upload.source_platform)
    jobs = db.execute(select(Job).where(Job.upload_id == upload.id).order_by(Job.created_at)
                      .with_for_update()).scalars().all()
    for job in jobs:
        if job.status == "QUEUED":
            out.cancelled.append((job.id, job.credits_reserved))
            if not dry_run:
                job.status, job.finished_at = "CANCELED", now
                job.error_code, job.error_message = TAKEN_DOWN
                if job.credits_reserved:
                    ledger.settle(db, job, success=False)       # refund, through the same path as a cancel
        elif job.status == "RUNNING":
            if job.cancel_requested:
                out.still_stopping.append(job.id)
            else:
                out.stopping.append(job.id)
                if not dry_run:
                    job.cancel_requested = True     # the worker stops at its next step, removes its clips, refunds
    job_ids = [j.id for j in jobs]
    clips = db.execute(select(Clip).where(Clip.job_id.in_(job_ids))).scalars().all() if job_ids else []
    for clip in clips:
        if clip.deleted_at is None:
            out.clips += 1
            out.files += [k for k in (clip.video_key, clip.thumb_key, clip.captions_key, clip.preview_key,
                                      clip.export_key, clip.frame_key) if k]
            if not dry_run:
                clip.deleted_at = now
    clip_ids = [c.id for c in clips]
    out.files += thumbnail_keys(db, clip_ids)         # premium thumbnails and edited ones (#140)
    exports = db.execute(select(Export).where(Export.clip_id.in_(clip_ids), Export.storage_key.is_not(None))
                         ).scalars().all() if clip_ids else []
    for export in exports:
        out.files.append(export.storage_key)
        if not dry_run:
            export.storage_key = None               # the file is gone; the row has no deleted mark of its own
    if upload.deleted_at is None:
        out.upload_removed = True
        out.files += [k for k in (upload.storage_key, transcript_key(upload.id), vindex_key(upload.id))
                      if k and storage.exists(k)]
        if not dry_run:
            upload.deleted_at = now
    out.files = list(dict.fromkeys(out.files))
    if not dry_run:
        for key in out.files:
            storage.delete(key)
    return out


def takedown(url: str | None = None, account: str | None = None, dry_run: bool = False) -> Report:
    """Remove everything imported from `url` (any account), or everything `account` imported by link.
    Exactly one of the two. Raises LookupError for an unknown account."""
    if (url is None) == (account is None):
        raise ValueError("give exactly one of url and account")
    storage = get_storage()
    with new_session() as db:
        if url is not None:
            urls = {u for u in (url.strip(), canonical(url)) if u}
            target = f"source URL {sorted(urls, key=len)[0]}"
            where, log_where = Upload.source_url.in_(urls), ImportLog.source_url.in_(urls)
        else:
            acct = find_account(db, account)
            target = f"account {acct.id} ({acct.email}): every link import"
            where = (Upload.account_id == acct.id) & Upload.source_url.is_not(None)
            log_where = ImportLog.account_id == acct.id
        log_rows = len(db.execute(select(ImportLog.id).where(log_where)).all())
        upload_ids = db.execute(select(Upload.id).where(where).order_by(Upload.created_at, Upload.id)).scalars().all()
    removed = []
    for upload_id in upload_ids:
        with new_session() as db:                   # one upload per transaction: an interrupted run is repeatable
            upload = db.execute(select(Upload).where(Upload.id == upload_id).with_for_update()).scalar_one()
            removed.append(_take_down(db, storage, upload, dry_run))
            if dry_run:
                db.rollback()
            else:
                db.commit()
    return Report(target, dry_run, log_rows, removed)
