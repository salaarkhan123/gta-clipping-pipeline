"""The worker's side of a link import: download, check, store, and turn the hidden placeholder into an upload
that behaves exactly like an uploaded file (same size, length and file-type limits, same content-hash reuse).

An import job reserves no credits, so there is normally nothing to settle. If a job does carry a reservation,
every path here settles it: a failure or a cancel ends in a refund. Clip jobs started from the link
(POST /v1/clips/from-url) wait for the import and are queued or refunded in its final transaction (url_clips.resolve).
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

from .. import ledger, url_clips
from ..config import get_settings
from ..db import new_session
from ..models import Job, Upload, utcnow
from ..pipeline.ff import Deadline, PipelineError, probe
from ..storage import get_storage
from . import SPAN_SLACK, UPLOAD_INSTEAD, Refused, Span, copies, fit_span
from .copies import IMPORT_PREFIX
from .sources import DIRECT, VIDEO_EXT, classify

log = logging.getLogger("clipapi.ingest")


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


def fetched_json(mode: str, bytes_: int = 0, seconds: float | None = 0.0, full_bytes: int | None = None,
                 full_seconds: float | None = None, estimated: bool = False) -> dict:
    """What an import brought over the network, apart from what it stored or what the job costs. `mode`:
    "segments" (only the segments that hold the chosen part), "whole_file" (the whole video, cut afterwards when a
    part was chosen), "stored_copy" (cut from a copy the account already had: nothing downloaded) or "none" (the
    stored upload was handed back). `bytes` and `seconds`: what was downloaded. `full_bytes` and `full_seconds`:
    the whole video in the same streams, for comparison: the size the site gives, or, when it gives none
    (`full_bytes_estimated`), the downloaded part's rate over the whole length; null when neither is known."""
    return {"mode": mode, "bytes": int(bytes_), "seconds": None if seconds is None else round(float(seconds), 3),
            "full_bytes": full_bytes, "full_seconds": None if full_seconds is None else round(float(full_seconds), 3),
            "full_bytes_estimated": bool(estimated)}


def _download(source, work: Path, s, span: Span, on_bytes, on_stage):
    """(path, filename, the part of the source that was taken, what was fetched: fetched_json). The downloader is
    chosen by the allow-list, never by the caller."""
    max_bytes = min(s.import_max_bytes, s.max_upload_bytes)
    max_duration = min(s.import_max_duration_sec, s.max_duration_sec)
    if source.downloader == DIRECT:
        from . import fetch
        on_stage("downloading")
        got = fetch.fetch(source.fetch_url, work, fetch.Limits(max_bytes, s.import_timeout_sec), on_bytes)
        size = got.path.stat().st_size
        try:
            length = probe(got.path).duration
        except PipelineError:
            length = None                   # the checks after the download refuse it
        fetched = fetched_json("whole_file", size, length, size, length)
        if span.whole:
            return got.path, got.filename, span, fetched
        on_stage("merging")
        path, span = _cut_local(got.path, span, work, s)
        return path, f"{Path(got.filename).stem}{path.suffix}", span, fetched
    from . import platforms
    got = platforms.download(source.platform, source.fetch_url, work,
                             platforms.Limits(max_bytes, max_duration, s.import_timeout_sec, s.min_duration_sec),
                             on_bytes, span, on_stage)
    return got.path, got.filename, got.span, fetched_json("segments" if got.partial else "whole_file", got.fetched_bytes,
                                                         got.fetched_sec, got.full_bytes, got.full_sec, got.full_estimated)


def _cut_local(path: Path, span: Span, work: Path, s) -> tuple[Path, Span]:
    """`span` of a video file we hold (a direct link's download, or this account's stored copy), cut with our own
    ffmpeg. The span is first fitted to the file's real length."""
    from . import platforms
    try:
        length = probe(path).duration
    except PipelineError as e:
        raise Refused(e.code, f"{e.message} {UPLOAD_INSTEAD}") from None
    span = fit_span(span, length, s.min_duration_sec, min(s.import_max_duration_sec, s.max_duration_sec))
    if span.whole:
        return path, span
    out = work / "cut"
    out.mkdir(exist_ok=True)
    return platforms.cut(path, span, out, Deadline(s.import_timeout_sec)), span


def run_import(job_id: str) -> str:
    """Run one claimed import job to a final state. Returns the final status."""
    s = get_settings()
    storage = get_storage()
    with new_session() as db:
        job = db.get(Job, job_id)
        placeholder = db.get(Upload, job.upload_id)
        account_id, upload_id, url = job.account_id, placeholder.id, placeholder.source_url or ""
        span = Span.of((job.options or {}).get("range"))
    max_bytes = min(s.import_max_bytes, s.max_upload_bytes)
    max_duration = min(s.import_max_duration_sec, s.max_duration_sec)

    work = Path(tempfile.mkdtemp(prefix="imp_", dir=s.work_dir))
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(job_id, stop), daemon=True).start()
    status, error = "FAILED", ("import_failed", f"Something went wrong while importing this link. {UPLOAD_INSTEAD}")
    stored_key: str | None = None
    ended: list[str] = []          # link clip jobs that ended with this import (app/url_clips.py)
    last = [0.0]

    def progress(stage: str, pct: int, force: bool = True, done: int | None = None, total: int | None = None) -> None:
        """The job's stage (reading, downloading, copying, merging, checking, storing, done), percent and, while
        bytes are coming in, how many of how many. Also where a cancel or a lost job is noticed."""
        if not force and time.monotonic() - last[0] < 2.0:
            return
        last[0] = time.monotonic()
        with new_session() as db:
            j = db.get(Job, job_id)
            j.stage, j.progress, j.heartbeat_at = stage, max(j.progress, pct), utcnow()
            if done is not None:
                j.result = {"bytes_done": done, "bytes_total": total}
            cancel, state = j.cancel_requested, j.status
            db.commit()
        if state != "RUNNING":
            raise Lost()
        if cancel:
            raise Canceled()

    def on_bytes(done: int, total: int | None) -> None:
        share = min(1.0, done / total) if total else min(0.9, done / max_bytes)
        progress("downloading", 2 + int(86 * share), force=False, done=done, total=total)

    def on_stage(name: str) -> None:
        progress(name, {"downloading": 2, "merging": 90}.get(name, 2))

    try:
        if not s.imports_enabled:
            raise Refused("imports_disabled", f"Link import is switched off. {UPLOAD_INSTEAD}")
        progress("reading", 1)
        source = classify(url)                       # checked again here: the worker trusts nothing it is handed

        # Never the same video twice. This account's stored copy of exactly this part of the link is handed back
        # as it is; a stored copy that contains the part (a longer range, or the whole video) is cut here, from
        # storage. Only otherwise is anything downloaded.
        with new_session() as db:
            have = copies.exact(db, account_id, source.url, span)
            same_id = have.id if have else None
            held = None if have else copies.holding(db, account_id, source.url, span)
            held = (held[0].storage_key, held[0].filename, held[1]) if held else None
        taken, fetched = span, fetched_json("none")
        if same_id is None:
            if held is not None:
                key, name, outer = held
                progress("copying", 5)
                fetched = fetched_json("stored_copy")
                local = work / f"stored{Path(key).suffix.lower()}"
                storage.fetch(key, local)
                inner = Span(span.start - outer.start, None if span.end is None else span.end - outer.start)
                path, inner = _cut_local(local, inner, work, s)
                taken = Span(outer.start + inner.start, outer.end if inner.end is None else outer.start + inner.end)
                filename = f"{Path(name).stem}{path.suffix}"
            else:
                path, filename, taken, fetched = _download(source, work, s, span, on_bytes, on_stage)

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
            # A range is copied from the key frame before its start, so it may come out a little longer than asked.
            if info.duration > max_duration + (0 if taken.whole else SPAN_SLACK + 30):
                raise Refused("video_too_long", f"Maximum video length is {int(max_duration // 3600)} hours.")
            if info.duration < s.min_duration_sec:
                raise Refused("video_too_short", f"Minimum video length is {s.min_duration_sec} seconds.")
            content_hash = _sha256(path)

            # The same bytes from the same link on the same account, while the first copy is still stored: hand
            # back that upload (as a second upload of the same file does). A copy that came from somewhere else
            # is not reused, so every upload has one source and a takedown of that source finds all of it.
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
            job.result = {"upload_id": same_id or upload_id, "reused": same_id is not None,
                          "range": None if taken.whole else taken.as_list(),     # the part of the link it holds
                          "fetched": fetched}                                    # what came over the network
            job.status, job.progress, job.stage, job.finished_at = "SUCCEEDED", 100, "done", utcnow()
            if job.credits_reserved:
                ledger.settle(db, job, success=True)
            ended = url_clips.resolve(db, job)      # link clip jobs waiting for it: queued now, in this transaction
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
                ended = url_clips.resolve(db, job)          # link clip jobs waiting for it: refunded
            else:
                status = job.status      # already finalised (and settled) elsewhere; leave it alone
            db.commit()
    url_clips.notify(ended)
    return status
