"""Job worker. Claims QUEUED jobs from Postgres (FOR UPDATE SKIP LOCKED), runs the pipeline,
stores results and settles credits. Run several copies to process jobs in parallel.

    python -m app.worker
"""
import hashlib
import hmac
import json
import logging
import shutil
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import select

from . import ledger
from .ai import default_ai
from .config import get_settings
from .plans import plan_of
from .db import init_db, new_session
from .models import Account, Clip, Job, Upload, WebhookDelivery, new_id, utcnow
from .pipeline import Deadline, PipelineError, PipelineOptions, run_pipeline
from .pipeline.tools import RenderOptions, run_find, run_render
from .pipeline.transcribe import FasterWhisperTranscriber, Transcriber
from .pipeline.visual import FastembedClip
from .security import is_public_https_url
from .storage import get_storage, transcript_key, vindex_key

log = logging.getLogger("clipapi.worker")


class Canceled(Exception):
    pass


class Lost(Exception):
    """The job was finalised by someone else (e.g. the stale-job sweeper) while we were working."""


def claim_job() -> str | None:
    with new_session() as db:
        job = db.execute(select(Job).where(Job.status == "QUEUED").order_by(Job.created_at)
                         .limit(1).with_for_update(skip_locked=True)).scalar_one_or_none()
        if not job:
            return None
        job.status, job.started_at, job.heartbeat_at, job.stage = "RUNNING", utcnow(), utcnow(), "starting"
        db.commit()
        return job.id


def default_transcriber() -> Transcriber | None:
    model = get_settings().whisper_model
    return None if model.lower() == "none" else FasterWhisperTranscriber(model)


def default_indexer() -> Transcriber | None:
    """Faster, smaller model used only to build the full-video search transcript."""
    model = get_settings().whisper_index_model
    return None if model.lower() == "none" else FasterWhisperTranscriber(model, beam_size=1, words=False)


def default_embedder():
    return FastembedClip() if get_settings().visual_search else None


def _heartbeat(job_id: str, stop: threading.Event) -> None:
    """Keeps heartbeat_at fresh during long ffmpeg stages so the job isn't mistaken for a dead one."""
    while not stop.wait(30):
        try:
            with new_session() as db:
                job = db.get(Job, job_id)
                if job and job.status == "RUNNING":
                    job.heartbeat_at = utcnow()
                    db.commit()
        except Exception:
            log.exception("heartbeat failed for %s", job_id)


def clip_text(r) -> str:
    """Words spoken in a rendered clip (from its captions file), else the matched text."""
    if r.captions_path and r.captions_path.exists():
        try:
            return " ".join(w["text"] for w in json.loads(r.captions_path.read_text())["words"])
        except (ValueError, KeyError):
            pass
    return str(r.features.get("text", ""))


def process_job(job_id: str, transcriber: Transcriber | None = None, pipeline=run_pipeline,
                indexer: Transcriber | None = None, embedder=None, ai=None) -> str:
    """Run one claimed job to a final state. Always settles credits. Returns the final status."""
    s = get_settings()
    storage = get_storage()
    with new_session() as db:
        job = db.get(Job, job_id)
        upload = db.get(Upload, job.upload_id)
        options, duration = dict(job.options), job.duration_sec
        options["max_side"] = plan_of(db.get(Account, job.account_id)).get("max_side")
        src_key, ext, upload_id = upload.storage_key, Path(upload.storage_key).suffix, upload.id

    work = Path(tempfile.mkdtemp(prefix="job_", dir=s.work_dir))
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(job_id, stop), daemon=True).start()
    status, error = "FAILED", ("processing_failed", "Something went wrong while processing this video.")
    stored: list[str] = []   # storage keys written so far, removed again if the job does not succeed
    try:
        timings: dict[str, float] = {}
        mark = [time.monotonic(), "starting"]
        t_start = mark[0]

        def progress(stage: str, pct: int) -> None:
            if stage != mark[1]:
                now = time.monotonic()
                timings[mark[1]] = timings.get(mark[1], 0.0) + now - mark[0]
                mark[0], mark[1] = now, stage
            with new_session() as db:
                j = db.get(Job, job_id)
                j.stage, j.progress, j.heartbeat_at = stage, max(j.progress, pct), utcnow()
                cancel = j.cancel_requested
                db.commit()
            if cancel:
                raise Canceled()

        progress("downloading", 1)
        src = work / f"source{ext}"
        storage.fetch(src_key, src)
        deadline = Deadline(max(900.0, duration * s.job_timeout_factor))
        tool, result = options.pop("tool", "clips"), None
        if tool == "render":
            segments = options.pop("segments")
            results = run_render(src, segments, RenderOptions(caption_font=s.caption_font, **options),
                                 work / "out", progress, transcriber, deadline)
        elif tool == "find":
            query, max_results = options.pop("query"), options.pop("max_results")
            make_clips, clip_length = options.pop("make_clips"), options.pop("clip_length")
            mode = options.pop("mode", "auto")
            tkey, vkey, cached_t, cached_v = transcript_key(upload_id), vindex_key(upload_id), None, None
            if storage.exists(tkey):
                storage.fetch(tkey, work / "transcript.json")
                cached_t = json.loads((work / "transcript.json").read_text())
            if storage.exists(vkey):
                import numpy as np
                storage.fetch(vkey, work / "vindex.npz")
                with np.load(work / "vindex.npz") as z:
                    cached_v = {"emb": z["emb"], "step": float(z["step"])}
            results, result, new_t, new_v = run_find(
                src, query, max_results, make_clips, clip_length,
                RenderOptions(caption_font=s.caption_font, **options), work / "out", progress, transcriber,
                deadline, cached_t, mode=mode, embedder=embedder, vindex=cached_v, indexer=indexer)
            # Keep both indexes so later searches on this upload skip the expensive part.
            if new_t is not None:
                (work / "transcript.json").write_text(json.dumps(new_t))
                storage.put(tkey, work / "transcript.json")
            if new_v is not None:
                import numpy as np
                np.savez(work / "vindex.npz", emb=new_v["emb"], step=new_v["step"])
                storage.put(vkey, work / "vindex.npz")
        else:
            opts = PipelineOptions(caption_font=s.caption_font, **options)
            # The pipeline's judge takes (text, frame, context); the AI client takes (text, context, frame).
            extra = ({"judge": lambda text, frame, ctx: ai.clip_meta(text, ctx, frame), "fast_transcriber": indexer}
                     if ai is not None else {})
            results = pipeline(src, opts, work / "out", progress, transcriber, deadline, **extra)

        metas = [None] * len(results)
        if tool in ("clips", "find"):
            if ai is not None:
                progress("writing_titles", 98)
            for k, r in enumerate(results):
                if getattr(r, "meta", None) is not None:   # the judge already rated this clip
                    metas[k] = r.meta
                    continue
                meta = ai.clip_meta(clip_text(r), {"length": r.end - r.start, "signals": r.signals},
                                    r.thumb_path) if ai is not None else None
                metas[k] = meta   # no AI, no score: a number made from loudness alone would mislead

        progress("uploading", 99)
        rows = []
        for i, r in enumerate(results, 1):
            clip_id = new_id("clip")
            base = f"clips/{job_id}/{clip_id}"
            storage.put(f"{base}.mp4", r.video_path)
            stored.append(f"{base}.mp4")
            thumb_key = caps_key = None
            if r.thumb_path and r.thumb_path.exists():
                thumb_key = f"{base}.jpg"
                storage.put(thumb_key, r.thumb_path)
                stored.append(thumb_key)
            if r.captions_path and r.captions_path.exists():
                caps_key = f"{base}.captions.json"
                storage.put(caps_key, r.captions_path)
                stored.append(caps_key)
            rows.append(Clip(id=clip_id, job_id=job_id, idx=i, start_sec=r.start, end_sec=r.end, score=r.score,
                             signals=r.signals, features=r.features, video_key=f"{base}.mp4",
                             thumb_key=thumb_key, captions_key=caps_key, meta=metas[i - 1]))
        with new_session() as db:
            job = db.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
            if job.status != "RUNNING":
                raise Lost()
            if job.cancel_requested:
                raise Canceled()
            db.add_all(rows)
            elapsed = time.monotonic() - t_start
            timings[mark[1]] = timings.get(mark[1], 0.0) + time.monotonic() - mark[0]
            job.result = {**(result or {}), "elapsed_sec": round(elapsed, 1),
                          "speed_x": round(duration / max(elapsed, 0.1), 1),
                          "timings": {k: round(v, 1) for k, v in timings.items() if v >= 0.05}}
            if tool in ("clips", "find"):
                db.get(Upload, job.upload_id).analyzed = True
            job.status, job.progress, job.stage, job.finished_at = "SUCCEEDED", 100, "done", utcnow()
            ledger.settle(db, job, success=True)
            db.commit()
        status, error = "SUCCEEDED", None
    except Canceled:
        status, error = "CANCELED", None
    except Lost:
        status, error = "LOST", None
    except PipelineError as e:
        error = (e.code, e.message)
        log.warning("job %s failed: %s %s", job_id, e.code, e.message)
    except Exception:
        log.exception("job %s crashed", job_id)
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
                ledger.settle(db, job, success=False)   # refund
                db.commit()
            else:
                status = job.status   # already finalised and settled elsewhere; leave it alone
    send_webhook(job_id)
    return status


def send_webhook(job_id: str) -> None:
    with new_session() as db:
        job = db.get(Job, job_id)
        if not job or not job.webhook_url:
            return
        account = db.get(Account, job.account_id)
        url, secret = job.webhook_url, account.webhook_secret
        body = json.dumps({"job_id": job.id, "status": job.status, "credits_charged": job.credits_charged,
                           "error_code": job.error_code}, separators=(",", ":"))
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    for attempt in (1, 2, 3):
        code = None
        try:
            if is_public_https_url(url):   # re-checked at send time (SSRF guard)
                resp = httpx.post(url, content=body, timeout=10, follow_redirects=False, headers={
                    "content-type": "application/json", "x-clipapi-signature": f"sha256={sig}"})
                code = resp.status_code
        except httpx.HTTPError:
            pass
        with new_session() as db:
            db.add(WebhookDelivery(job_id=job_id, url=url, status_code=code, attempt=attempt))
            db.commit()
        if code is not None and 200 <= code < 300:
            return
        time.sleep(2 * attempt)


def sweep_stale_jobs() -> int:
    """RUNNING jobs whose worker died (no heartbeat) are failed and refunded."""
    cutoff = utcnow() - timedelta(minutes=get_settings().stale_job_minutes)
    n = 0
    with new_session() as db:
        stale = db.execute(select(Job).where(Job.status == "RUNNING", Job.heartbeat_at < cutoff)
                           .with_for_update(skip_locked=True)).scalars().all()
        for job in stale:
            job.status, job.finished_at = "FAILED", utcnow()
            job.error_code, job.error_message = "worker_lost", "Processing was interrupted. Your credits were refunded."
            ledger.settle(db, job, success=False)
            n += 1
        db.commit()
    return n


def sweep_expired() -> int:
    """Delete stored files past their retention date."""
    storage, now, n = get_storage(), utcnow(), 0
    with new_session() as db:
        active_uploads = select(Job.upload_id).where(Job.status.in_(("QUEUED", "RUNNING")))
        for up in db.execute(select(Upload).where(Upload.deleted_at.is_(None), Upload.expires_at <= now,
                                                  Upload.id.not_in(active_uploads)).limit(200)).scalars():
            storage.delete(up.storage_key)
            storage.delete(transcript_key(up.id))
            storage.delete(vindex_key(up.id))
            up.deleted_at = now
            n += 1
        expired_jobs = select(Job.id).where(Job.expires_at <= now)
        for clip in db.execute(select(Clip).where(Clip.deleted_at.is_(None),
                                                  Clip.job_id.in_(expired_jobs)).limit(500)).scalars():
            for key in (clip.video_key, clip.thumb_key, clip.captions_key):
                if key:
                    storage.delete(key)
            clip.deleted_at = now
            n += 1
        db.commit()
    return n


def run_once(transcriber: Transcriber | None = None, pipeline=run_pipeline,
             indexer: Transcriber | None = None, embedder=None, ai=None) -> str | None:
    job_id = claim_job()
    if not job_id:
        return None
    return process_job(job_id, transcriber, pipeline, indexer, embedder, ai)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = get_settings()
    s.check_production()
    if s.sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=s.sentry_dsn, traces_sample_rate=0.0)
    init_db()
    transcriber, indexer, embedder = default_transcriber(), default_indexer(), default_embedder()
    log.info("worker started (captions: %s, search index: %s, visual search: %s)",
             s.whisper_model, s.whisper_index_model, s.visual_search)
    last_sweep = 0.0
    while True:
        try:
            if time.monotonic() - last_sweep > 60:
                last_sweep = time.monotonic()
                stale, expired = sweep_stale_jobs(), sweep_expired()
                if stale or expired:
                    log.info("sweep: %s stale jobs refunded, %s expired files deleted", stale, expired)
            if run_once(transcriber, indexer=indexer, embedder=embedder, ai=default_ai()) is None:
                time.sleep(s.worker_poll_sec)
        except Exception:
            log.exception("worker loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()
