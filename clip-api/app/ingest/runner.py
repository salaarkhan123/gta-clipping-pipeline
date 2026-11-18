"""The worker's side of a link import: download, check, store, and turn the hidden placeholder into an upload
that behaves exactly like an uploaded file (same size, length and file-type limits, same content-hash reuse).

An import job reserves no credits, so there is normally nothing to settle. If a job does carry a reservation,
every path here settles it: a failure or a cancel ends in a refund.
"""
import hashlib
import logging
import shutil
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from .. import ledger
from ..config import get_settings
from ..db import new_session
from ..models import Job, Upload, utcnow
from ..pipeline.ff import PipelineError, probe
from ..storage import get_storage
from . import UPLOAD_INSTEAD, Refused
from .sources import DIRECT, VIDEO_EXT, classify

log = logging.getLogger("clipapi.ingest")
IMPORT_PREFIX = "imp"       # import jobs are Job rows whose id starts with this


class Canceled(Exception):
    pass


class Lost(Exception):
    """The job was finalised by someone else (the stale-job sweeper, a takedown) while we were working."""


def is_import(job_id: str) -> bool:
    return job_id.startswith(IMPORT_PREFIX + "_")


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(source, work: Path, max_bytes: int, max_duration: float, timeout: float, on_bytes):
    """(path, filename) of the downloaded file. The downloader is chosen by the allow-list, never by the caller."""
    if source.downloader == DIRECT:
        from . import fetch
        got = fetch.fetch(source.fetch_url, work, fetch.Limits(max_bytes, timeout), on_bytes)
        return got.path, got.filename
    from . import platforms
    got = platforms.download(source.platform, source.fetch_url, work,
                             platforms.Limits(max_bytes, max_duration, timeout), on_bytes)
    return got.path, got.filename


def run_import(job_id: str) -> str:
    """Run one claimed import job to a final state. Returns the final status."""
    s = get_settings()
    storage = get_storage()
    with new_session() as db:
        job = db.get(Job, job_id)
        placeholder = db.get(Upload, job.upload_id)
        account_id, upload_id, url = job.account_id, placeholder.id, placeholder.source_url or ""
    max_bytes = min(s.import_max_bytes, s.max_upload_bytes)
    max_duration = min(s.import_max_duration_sec, s.max_duration_sec)

    work = Path(tempfile.mkdtemp(prefix="imp_", dir=s.work_dir))
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(job_id, stop), daemon=True).start()
    status, error = "FAILED", ("import_failed", f"Something went wrong while importing this link. {UPLOAD_INSTEAD}")
    stored_key: str | None = None
    last = [0.0]

    def progress(stage: str, pct: int, force: bool = True) -> None:
        if not force and time.monotonic() - last[0] < 2.0:
            return
        last[0] = time.monotonic()
        with new_session() as db:
            j = db.get(Job, job_id)
            j.stage, j.progress, j.heartbeat_at = stage, max(j.progress, pct), utcnow()
            cancel, state = j.cancel_requested, j.status
            db.commit()
        if state != "RUNNING":
            raise Lost()
        if cancel:
            raise Canceled()

    def on_bytes(done: int, total: int | None) -> None:
        share = min(1.0, done / total) if total else min(0.9, done / max_bytes)
        progress("importing", 2 + int(88 * share), force=False)

    try:
        if not s.imports_enabled:
            raise Refused("imports_disabled", f"Link import is switched off. {UPLOAD_INSTEAD}")
        progress("importing", 1)
        source = classify(url)                       # checked again here: the worker trusts nothing it is handed
        path, filename = _download(source, work, max_bytes, max_duration, s.import_timeout_sec, on_bytes)

        progress("checking", 92)
        size, ext = path.stat().st_size, path.suffix.lower()
        if size > max_bytes:
            raise Refused("file_too_large", f"Maximum import size is {max_bytes // 1024 ** 2} MB.")
        if ext not in VIDEO_EXT:
            raise Refused("unsupported_type", f"This link is not a video file ({', '.join(sorted(VIDEO_EXT))}). "
                                              f"{UPLOAD_INSTEAD}")
        try:
            info = probe(path)                       # ffprobe on the saved file, never on the URL
        except PipelineError as e:
            raise Refused(e.code, f"{e.message} {UPLOAD_INSTEAD}") from None
        if info.duration > max_duration:
            raise Refused("video_too_long", f"Maximum video length is {int(max_duration // 3600)} hours.")
        if info.duration < s.min_duration_sec:
            raise Refused("video_too_short", f"Minimum video length is {s.min_duration_sec} seconds.")
        content_hash = _sha256(path)

        # The same bytes from the same link on the same account, while the first copy is still stored: hand back
        # that upload (as a second upload of the same file does). A copy that came from somewhere else is not
        # reused, so every upload has one source and a takedown of that source finds all of it.
        with new_session() as db:
            same_id = db.execute(select(Upload.id).where(
                Upload.account_id == account_id, Upload.content_hash == content_hash, Upload.size_bytes == size,
                Upload.source_url == source.url, Upload.deleted_at.is_(None), Upload.expires_at > utcnow())
                .order_by(Upload.created_at.desc()).limit(1)).scalar_one_or_none()
        if same_id is None:
            progress("storing", 95)
            stored_key = f"uploads/{account_id}/{upload_id}{ext}"
            storage.put(stored_key, path)

        with new_session() as db:
            job = db.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
            if job.status != "RUNNING":
                raise Lost()
            if job.cancel_requested:
                raise Canceled()
            if same_id is None:
                upload = db.get(Upload, upload_id)
                upload.filename, upload.storage_key, upload.size_bytes = filename[:255], stored_key, size
                upload.duration_sec, upload.width, upload.height = info.duration, info.width, info.height
                upload.has_audio, upload.content_hash = info.has_audio, content_hash
                upload.expires_at = utcnow() + timedelta(days=s.retention_days)
                upload.deleted_at = None             # visible from here on, like any upload
            job.result = {"upload_id": same_id or upload_id, "reused": same_id is not None}
            job.status, job.progress, job.stage, job.finished_at = "SUCCEEDED", 100, "done", utcnow()
            if job.credits_reserved:
                ledger.settle(db, job, success=True)
            db.commit()
        status, error = "SUCCEEDED", None
    except Canceled:
        status, error = "CANCELED", None
    except Lost:
        status, error = "LOST", None
    except Refused as e:
        error = (e.code, e.message)
        log.warning("import %s failed: %s %s", job_id, e.code, e.message)
    except Exception:
        log.exception("import %s crashed", job_id)
    finally:
        stop.set()
        shutil.rmtree(work, ignore_errors=True)

    if status != "SUCCEEDED":
        if stored_key:
            try:
                storage.delete(stored_key)
            except Exception:
                log.exception("could not remove %s", stored_key)
        with new_session() as db:
            job = db.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
            if job.status == "RUNNING":
                job.status, job.finished_at = status, utcnow()
                if error:
                    job.error_code, job.error_message = error
                if job.credits_reserved:
                    ledger.settle(db, job, success=False)   # refund
            else:
                status = job.status      # already finalised (and settled) elsewhere; leave it alone
            db.commit()
    return status
