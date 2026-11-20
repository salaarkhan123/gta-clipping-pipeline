"""Job worker. Claims QUEUED jobs from Postgres (FOR UPDATE SKIP LOCKED), runs the pipeline,
stores results and settles credits. WORKER_CONCURRENCY jobs run at once in one process (default 1);
several worker processes can also share one queue: a job is claimed by exactly one of them.

    python -m app.worker
"""
import hashlib
import hmac
import json
import logging
import math
import shutil
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import select, update

from . import ledger
from . import languages
from . import log_redact
from .ai import default_ai
from .config import get_settings
from .plan_grants import sweep_yearly_grants
from .plans import plan_of
from .db import init_db, new_session
from .models import Account, Clip, Job, Upload, WebhookDelivery, new_id, utcnow
from .pipeline import Deadline, PipelineError, PipelineOptions, Timer, run_pipeline
from .pipeline.tools import RenderOptions, run_export, run_find, run_render
from .exports import export_items, finish_export, new_export_id
from .pipeline.heard import Heard
from .pipeline.stt import complete, extract_audio, provider_for
from .pipeline.thumbs import canvas_of, write_thumbnail
from .pipeline.transcribe import FasterWhisperTranscriber, Transcriber, Transcript, in_language
from .pipeline.translate import detect_language, run_text_job, transcript_language, translate_captions
from .pipeline.visual import FastembedClip
from .security import is_public_https_url
from .storage import get_storage, transcript_key, transcript_parts_key, vindex_key
from .thumbnail_jobs import PREFIX as THUMB_PREFIX, is_thumbnail_job, run_thumbnail_job, thumbnail_keys
from .thumbnails import frame_key_of, words_for

log = logging.getLogger("clipapi.worker")


class Canceled(Exception):
    pass


class Lost(Exception):
    """The job was finalised by someone else (e.g. the stale-job sweeper) while we were working."""


def credits_of(seconds: float) -> int:
    """Credits for a number of seconds: one per started minute (the same rule as routes_media.credits_for)."""
    return max(1, math.ceil(seconds / 60))

def claim_job(prefix: str | None = None) -> str | None:
    """Claim the oldest QUEUED job for this caller only. The conditional UPDATE decides the winner, so two
    claimers never get the same job on any database (SKIP LOCKED only keeps Postgres claimers from waiting).
    `prefix`: only jobs whose id starts with it (the premium thumbnail slot claims `thm_` jobs only)."""
    with new_session() as db:
        for _ in range(5):
            q = select(Job.id).where(Job.status == "QUEUED")
            if prefix:
                q = q.where(Job.id.startswith(prefix, autoescape=True))
            job_id = db.execute(q.order_by(Job.created_at).limit(1).with_for_update(skip_locked=True)).scalar_one_or_none()
            if not job_id:
                return None
            now = utcnow()
            won = db.execute(update(Job).where(Job.id == job_id, Job.status == "QUEUED")
                             .values(status="RUNNING", started_at=now, heartbeat_at=now, stage="starting")).rowcount
            db.commit()
            if won:
                return job_id
        return None


def default_transcriber() -> Transcriber | None:
    model = get_settings().whisper_model
    if model.lower() == "none":
        return None
    other = languages.caption_model()          # (languages) for speech that is not English
    return FasterWhisperTranscriber(model, multilingual=None if other.lower() in ("none", model) else other)


def default_indexer() -> Transcriber | None:
    """Faster, smaller model used only to build the full-video search transcript."""
    model = get_settings().whisper_index_model
    if model.lower() == "none":
        return None
    other = languages.index_model()            # (languages) for speech that is not English
    return FasterWhisperTranscriber(model, beam_size=1, words=False,
                                    multilingual=None if other.lower() in ("none", model) else other)


def spoken_language(upload_id: str, asked: str | None, has_audio: bool, src: Path, duration: float, work: Path,
                    deadline, detectors, starting=lambda: None) -> tuple[str | None, bool]:
    """(languages, agent F) The language a job transcribes in, and whether it was detected just now.
    The one asked for; else the one detected on this upload before; else, with detection on, the one detected now
    (stored on the upload). None: unknown, and the English models are used as they always were."""
    if asked:
        return asked, False
    with new_session() as db:
        known = db.get(Upload, upload_id).language
    if known:
        return known, False
    probe_with = next((d.language_probs for d in detectors
                       if d is not None and getattr(d, "language_probs", None) is not None
                       and getattr(d, "multilingual", True)), None)
    if not (get_settings().language_detect and has_audio and probe_with is not None):
        return None, False
    starting()
    found, _sure = detect_language(src, duration, probe_with, work, deadline)
    if found:
        with new_session() as db:
            db.get(Upload, upload_id).language = found
            db.commit()
    return found, found is not None


def timing_words(transcriber):
    """The transcriber that makes a stored whole transcript: the same model, timing every word."""
    timed = getattr(transcriber, "timing_words", None)
    return timed() if timed is not None else transcriber


def _read_json(storage, key: str, dest: Path) -> dict | None:
    if not storage.exists(key):
        return None
    storage.fetch(key, dest)
    try:
        return json.loads(dest.read_text())
    finally:
        dest.unlink(missing_ok=True)


def _read_parts(storage, upload_id: str, work: Path) -> dict | None:
    """The stored pieces, or None. They are only a saving: a file that cannot be read is treated as missing."""
    try:
        return _read_json(storage, transcript_parts_key(upload_id), work / "transcript-parts.json")
    except ValueError:
        log.warning("unreadable transcript pieces for %s; transcribing again", upload_id)
        return None


def load_heard(storage, upload_id: str, language: str, work: Path) -> tuple[Heard, dict | None]:
    """(U1) What this upload already has transcribed in `language`: its whole transcript and the pieces earlier
    clip jobs transcribed. Also returns the whole transcript as stored (None when there is none)."""
    whole = _read_json(storage, transcript_key(upload_id), work / "transcript.json")
    parts = _read_parts(storage, upload_id, work)
    try:
        return Heard.load(language, whole, parts), whole
    except (KeyError, TypeError, ValueError):
        log.warning("malformed transcript pieces for %s; transcribing again", upload_id)
        return Heard.load(language, whole, None), whole


def save_parts(storage, upload_id: str, heard: Heard, work: Path) -> None:
    """Add the pieces this job transcribed to the ones stored for the upload. The stored file is read again first,
    so pieces another job saved meanwhile are kept (a piece lost to a race is only transcribed again later).
    Keeping them is only a saving for later jobs, so a failure here never fails the job."""
    if not heard.added:
        return
    try:
        stored = Heard.load(heard.language, None, _read_parts(storage, upload_id, work))
        for p in heard.added:
            stored.add(p.start, p.end, p.model, p.transcript)
        (work / "transcript-parts.json").write_text(json.dumps(stored.parts_doc()))
        storage.put(transcript_parts_key(upload_id), work / "transcript-parts.json")
    except Exception:
        log.exception("could not keep the transcript pieces of %s", upload_id)


def game_weights(template_id: str | None, configured: str) -> tuple[dict | None, str]:
    """The sub-score weights for a job: those of its template's game, else its genre, else the default, from
    SCORE_WEIGHTS. (None, "equal") when nothing is configured, the job has no template, or the setting is unreadable
    (ranking then uses the plain mean; a bad setting never fails a job)."""
    from .pipeline.ranking import weights_for
    from .templates import TEMPLATES
    try:
        table = json.loads(configured) if configured.strip() else {}
    except ValueError:
        log.warning("SCORE_WEIGHTS is not valid JSON; ranking by the plain mean")
        table = {}
    template = TEMPLATES.get(template_id or "") or {}
    return weights_for(template.get("game"), template.get("genre"), table if isinstance(table, dict) else {})


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


def _fetch_caption_font(storage, account_id: str, options: dict, work: Path) -> None:
    """(captions) When caption_look names an uploaded font ("custom:<id>"), fetch the account's file into the job's
    work dir and hand its path to the renderer. A font that is gone fails the job (refunded) with a clear error."""
    from .routes_fonts import account_font
    font = str((options.get("caption_look") or {}).get("font") or "")
    if not font.startswith("custom:"):
        return
    row = account_font(storage, account_id, font[len("custom:"):])
    if row is None or not storage.exists(row["key"]):
        raise PipelineError("caption_font_missing", "The caption font this job uses was deleted. Choose another "
                            "font and try again.")
    dest = work / ("caption_font" + Path(row["key"]).suffix)
    storage.fetch(row["key"], dest)
    options["caption_font_file"] = str(dest)


def process_job(job_id: str, transcriber: Transcriber | None = None, pipeline=run_pipeline,
                indexer: Transcriber | None = None, embedder=None, ai=None) -> str:
    """Run one claimed job to a final state. Always settles credits. Returns the final status."""
    if job_id.startswith("imp_"):       # link import (agent E): no stored source yet; app/ingest runs it to the end
        from .ingest.runner import run_import
        return run_import(job_id)
    if is_thumbnail_job(job_id):        # premium thumbnail (#140): no video work; app/thumbnail_jobs.py runs it
        return run_thumbnail_job(job_id)
    s = get_settings()
    storage = get_storage()
    with new_session() as db:
        job = db.get(Job, job_id)
        upload = db.get(Upload, job.upload_id)
        options, duration = dict(job.options), job.duration_sec
        options["max_side"] = plan_of(db.get(Account, job.account_id)).get("max_side")
        src_key, ext, upload_id = upload.storage_key, Path(upload.storage_key).suffix, upload.id
        has_audio, video_sec = upload.has_audio, upload.duration_sec
        account_id = job.account_id

    work = Path(tempfile.mkdtemp(prefix="job_", dir=s.work_dir))
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(job_id, stop), daemon=True).start()
    status, error = "FAILED", ("processing_failed", "Something went wrong while processing this video.")
    stored: list[str] = []   # storage keys written so far, removed again if the job does not succeed
    # Two views of where the time went: `timings` follows the stage shown to the user; `timer` has the finer
    # pipeline stages and work counts used for benchmarks (scripts/job_timings.py).
    timings: dict[str, float] = {}
    timer = Timer()
    mark = [time.monotonic(), "starting"]
    t_start = mark[0]

    first_clip: list[float] = []      # seconds from the start of the run to the first clip being watchable

    def measured() -> dict:
        elapsed = time.monotonic() - t_start
        coarse = dict(timings)
        coarse[mark[1]] = coarse.get(mark[1], 0.0) + time.monotonic() - mark[0]
        return {"elapsed_sec": round(elapsed, 1), "speed_x": round(duration / max(elapsed, 0.1), 1),
                "timings": {k: round(v, 1) for k, v in coarse.items() if v >= 0.05}, **timer.as_dict(),
                **({"first_clip_sec": round(first_clip[0], 1)} if first_clip else {})}

    def waited(job: Job) -> dict:
        """Queue time and the end-to-end time a customer sees: from submitting the job to its result."""
        queue = max(0.0, (job.started_at - job.created_at).total_seconds()) if job.started_at else 0.0
        return {"queue_sec": round(queue, 1), "total_sec": round(queue + time.monotonic() - t_start, 1)}

    try:
        _fetch_caption_font(storage, account_id, options, work)    # (captions) an uploaded caption font

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
        with timer.stage("download"):
            storage.fetch(src_key, src)
        deadline = Deadline(max(900.0, duration * s.job_timeout_factor))
        tool, result = options.pop("tool", "clips"), None
        charge_basis = options.pop("charge_basis", None)   # "rendered": settle on the seconds rendered (re-runs)
        options.pop("link", None)                           # started from a link (app/url_clips.py)
        fixed_charge = options.pop("charge", None)          # a link job's first run: priced on the stored video,
                                                            # never above the quote it reserved
        render_mode = options.get("render", "full")         # (render, agent B) full | preview | none
        exported: list[tuple[str, str, str, str]] = []      # (render, agent B) export jobs: (export_id, clip_id, key, resolution)
        export_sec = 0.0                                    # (render, agent B) export jobs: quoted seconds rendered
        handed_over: set[int] = set()      # clips already stored (by object), so none is stored twice
        # (languages, agent F) The spoken language: asked for, known, or detected now. English or unknown leaves
        # the transcribers exactly as they were; any other language hands over to the multilingual models.
        asked = options.pop("source_lang", None)
        target = options.pop("target_lang", None)
        options.pop("caption_display", None)
        language, detected = asked, False
        if transcriber is not None or indexer is not None:
            language, detected = spoken_language(upload_id, asked, has_audio, src, video_sec, work, deadline,
                                                 (indexer, transcriber), lambda: progress("language", 2))
        transcriber, indexer = in_language(transcriber, language), in_language(indexer, language)
        copy_lang = target or language          # titles and hooks: asked for in this language when it is not English
        lang_ctx = {"language": copy_lang} if copy_lang and copy_lang != "en" else {}
        caption_translator = languages.translator(ai) if target and target != (language or "en") else None
        translation = {"status": None if not target or target == (language or "en")
                       else ("pending" if caption_translator else "not_configured")}

        def titled(r, meta) -> None:
            """The AI wrote this clip's hook and title after it was rendered: set them on its thumbnail now (the
            frame was chosen already; only the text is drawn). A thumbnail without text is still a thumbnail."""
            record = (getattr(r, "features", None) or {}).get("thumbnail") or {}
            frame, canvas = getattr(r, "frame_path", None), canvas_of(record)
            text = words_for(meta, options)
            if not text or record.get("text") or canvas is None or not (frame and frame.exists() and r.thumb_path):
                return
            try:
                with timer.stage("thumbnail"):
                    record["text"] = write_thumbnail(frame, r.thumb_path, text, canvas, options.get("caption_accent"))
            except Exception:
                log.exception("could not set the title on a thumbnail of %s", job_id)

        def save_clip(r, idx: int) -> None:
            """Store one finished clip and make it visible now, while the job is still running."""
            meta = getattr(r, "meta", None)             # the judge already rated it, or:
            if meta is None and ai is not None and tool in ("clips", "find"):
                with timer.stage("titles"):
                    meta = ai.clip_meta(clip_text(r), {"length": r.end - r.start, "signals": r.signals, **lang_ctx},
                                        getattr(r, "frame_path", None) or r.thumb_path)
                titled(r, meta)
            if caption_translator is not None and r.captions_path and r.captions_path.exists():
                # (languages) the clip's subtitle lines in the target language, kept in its captions file. Like the
                # AI's copy this is optional: a clip whose translation failed is still a finished clip.
                try:
                    with timer.stage("translate"):
                        caps = translate_captions(json.loads(r.captions_path.read_text()), caption_translator,
                                                  language or "en", target)
                    r.captions_path.write_text(json.dumps(caps))
                    if translation["status"] != "partial":
                        translation["status"] = "done"
                except Exception:
                    log.exception("caption translation failed for a clip of %s", job_id)
                    translation["status"] = "partial"
            # No AI, no score: a number made from loudness alone would mislead.
            clip_id = new_id("clip")
            base = f"clips/{job_id}/{clip_id}"
            thumb_key = caps_key = None
            # (render, agent B) render "preview": the video is the preview; "none": there is no video yet.
            video_key, preview_key = "", None
            with timer.stage("store"):
                if r.video_path is not None:
                    if tool == "clips" and render_mode == "preview":
                        preview_key = f"{base}.preview.mp4"
                    else:
                        video_key = f"{base}.mp4"
                    storage.put(video_key or preview_key, r.video_path)
                    stored.append(video_key or preview_key)
                if r.thumb_path and r.thumb_path.exists():
                    thumb_key = f"{base}.jpg"
                    storage.put(thumb_key, r.thumb_path)
                    stored.append(thumb_key)
                    frame = getattr(r, "frame_path", None)
                    record = (getattr(r, "features", None) or {}).get("thumbnail")
                    if frame and frame.exists() and isinstance(record, dict):
                        # The frame without text: the thumbnail is drawn again from it when the title is edited.
                        storage.put(f"{base}.frame.jpg", frame)
                        stored.append(f"{base}.frame.jpg")
                        record["frame_key"] = f"{base}.frame.jpg"
                if r.captions_path and r.captions_path.exists():
                    caps_key = f"{base}.captions.json"
                    storage.put(caps_key, r.captions_path)
                    stored.append(caps_key)
            with new_session() as db:
                job = db.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
                if job.status != "RUNNING":
                    raise Lost()
                if job.cancel_requested:
                    raise Canceled()
                db.add(Clip(id=clip_id, job_id=job_id, idx=idx, start_sec=r.start, end_sec=r.end, score=r.score,
                            signals=r.signals, features=r.features, video_key=video_key, preview_key=preview_key,
                            thumb_key=thumb_key, captions_key=caps_key, meta=meta))
                db.commit()
            if not handed_over:
                first_clip.append(time.monotonic() - t_start)
            handed_over.add(id(r))
        if tool in ("transcript", "summary"):
            # (languages, agent F) The whole video's transcript (stored once per upload, shared with Video Finder),
            # its translation, or its summary.
            tkey = transcript_key(upload_id)
            heard, cached = load_heard(storage, upload_id, language or "en", work)
            tr = timing_words(indexer or transcriber)
            stt = provider_for(s.transcription_provider, tr, s.transcribe_chunk_sec, s.transcribe_parallel)
            new_t, result = run_text_job(tool, src, video_sec, language, target, cached, stt, languages.translator(ai),
                                         languages.summarizer(ai), work / "out", progress, deadline, detected, heard)
            if new_t is not None:
                (work / "transcript.json").write_text(json.dumps(new_t))
                storage.put(tkey, work / "transcript.json")
            results = []
        elif tool == "export":
            # (render, agent B) stored clips rendered again with new options; the clips themselves change only
            # in the success transaction below (exports.finish_export).
            clip_ids = options.pop("clips")
            options.pop("source_job", None)
            edits = options.pop("edits", None)          # each clip's edit when it was priced
            quoted = options.pop("seconds", None) or {}  # each clip's seconds as quoted
            with new_session() as db:
                items = export_items(db, clip_ids, storage, work, edits)
            done = run_export(src, items, RenderOptions(caption_font=s.caption_font, moment_layout=s.provisional_layouts,
                                                        **options), work / "out",
                              progress, transcriber, deadline, timer)
            # Charged on the quoted seconds of the clips rendered: the quote exactly when every clip rendered.
            export_sec = round(sum(float(quoted.get(x.clip_id, x.seconds)) for x in done), 3)
            for x in done:
                export_id = new_export_id()
                # One file per run: a second run of the same job (picked up twice) never overwrites the first's.
                key = f"exports/{job_id}/{export_id}.mp4"
                with timer.stage("store"):
                    storage.put(key, x.video_path)
                stored.append(key)
                exported.append((export_id, x.clip_id, key, x.resolution))
            result = {"exports": [{"export_id": e, "clip_id": c, "seconds": x.seconds, "resolution": r}
                                  for (e, c, _k, r), x in zip(exported, done)]}
            results = []
        elif tool == "render":
            segments = options.pop("segments")
            results = run_render(src, segments, RenderOptions(caption_font=s.caption_font, **options),
                                 work / "out", progress, transcriber, deadline)
        elif tool == "find":
            query, max_results = options.pop("query"), options.pop("max_results")
            make_clips, clip_length = options.pop("make_clips"), options.pop("clip_length")
            mode = options.pop("mode", "auto")
            tkey, vkey, cached_v = transcript_key(upload_id), vindex_key(upload_id), None
            heard, cached_t = load_heard(storage, upload_id, language or "en", work)
            if cached_t is not None and transcript_language(cached_t) != (language or "en"):
                cached_t = None                     # (languages) made in another language: transcribe again
            if storage.exists(vkey):
                import numpy as np
                storage.fetch(vkey, work / "vindex.npz")
                with np.load(work / "vindex.npz") as z:
                    cached_v = {"emb": z["emb"], "step": float(z["step"])}
            results, result, new_t, new_v = run_find(
                src, query, max_results, make_clips, clip_length,
                RenderOptions(caption_font=s.caption_font, **options), work / "out", progress, transcriber,
                deadline, cached_t, mode=mode, embedder=embedder, vindex=cached_v, indexer=indexer,
                provider=provider_for(s.transcription_provider, timing_words(indexer or transcriber),
                                      s.transcribe_chunk_sec, s.transcribe_parallel), heard=heard)
            # Keep both indexes so later searches on this upload skip the expensive part.
            if new_t is not None:
                new_t.update(language=language or "en", language_detected=detected)
                (work / "transcript.json").write_text(json.dumps(new_t))
                storage.put(tkey, work / "transcript.json")
            if new_v is not None:
                import numpy as np
                np.savez(work / "vindex.npz", emb=new_v["emb"], step=new_v["step"])
                storage.put(vkey, work / "vindex.npz")
        else:
            weights, weights_version = game_weights(options.get("template"), s.score_weights)
            opts = PipelineOptions(caption_font=s.caption_font, source_lang=language, target_lang=target,
                                   moment_layout=s.provisional_layouts, quality_floor=s.clip_quality_floor,
                                   score_weights=weights, score_weights_version=weights_version,
                                   chat_motion_sample=s.chat_motion_sample,
                                   **options)   # (render, agent B; U4 quality floor; per-game rank weights)
            # Wave B1: encode concurrency is an ops knob (RENDER_WORKERS), not a per-job client option.
            opts.render_workers = s.render_workers
            # The pipeline's judge takes (text, frame, context); the AI client takes (text, context, frame).
            extra = ({"judge": lambda text, frame, ctx: ai.clip_meta(text, {**ctx, **lang_ctx}, frame),
                      "fast_transcriber": indexer} if ai is not None else {})
            if ai is not None and s.llm_pass and hasattr(ai, "propose_moments"):
                extra["proposer"] = ai.propose_moments          # (U3) reads the whole transcript, when there is one
            if ai is not None and hasattr(ai, "rewrite_hook"):  # (U4) a hook that repeats another clip's is rewritten
                extra["hook_writer"] = lambda text, taken, ctx: ai.rewrite_hook(text, taken, {**ctx, **lang_ctx})
            # (U1) What this upload already has transcribed (a whole transcript, pieces of earlier clip jobs) is read
            # instead of transcribed again, and what this job transcribes is kept for the next one.
            heard, whole = load_heard(storage, upload_id, language or "en", work)
            if (s.transcribe_whole and has_audio and (indexer or transcriber) is not None
                    and (whole is None or transcript_language(whole) != (language or "en"))):
                progress("transcribing", 5)
                # One decode gives the WAV for the whole transcript and the loudness the pipeline needs.
                with timer.stage("audio_signal"):
                    audio = extract_audio(src, work / "source-audio.wav", deadline)
                stt = provider_for(s.transcription_provider, timing_words(indexer or transcriber),
                                   s.transcribe_chunk_sec, s.transcribe_parallel)
                with timer.stage("transcribe_whole"):
                    doc = complete(heard, audio.path, video_sec, stt, work, deadline,
                                   lambda k, m: progress("transcribing", 5 + int(20 * k / m)))
                timer.count("transcribed_whole_sec", round(sum(min(p.end, video_sec) - p.start for p in heard.added), 1))
                doc.update(language=language or "en", language_detected=detected)
                (work / "transcript.json").write_text(json.dumps(doc))
                storage.put(transcript_key(upload_id), work / "transcript.json")
                heard, _ = load_heard(storage, upload_id, language or "en", work)     # the whole one, then the pieces
                extra["source_audio"] = audio
            results = pipeline(src, opts, work / "out", progress, transcriber, deadline, timer=timer,
                               on_clip=lambda r: save_clip(r, r.index), transcript=heard, **extra)
            save_parts(storage, upload_id, heard, work)

        progress("uploading", 99)
        for i, r in enumerate(results, 1):          # tools that hand their clips over at the end
            if id(r) not in handed_over:
                save_clip(r, r.index or i)
        with new_session() as db:
            job = db.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
            if job.status != "RUNNING":
                raise Lost()
            if job.cancel_requested:
                raise Canceled()
            if translation["status"] == "pending":
                translation["status"] = "no_captions"        # nothing had captions to translate
            spoken = {"language": language, "language_detected": detected}
            job.result = {**spoken, **(result or {}), **measured(), **waited(job),
                          **({"translation": translation["status"]} if tool not in ("transcript", "summary")
                             and translation["status"] else {})}
            if tool in ("clips", "find") or (tool in ("transcript", "summary") and charge_basis != "rendered"):
                db.get(Upload, job.upload_id).analyzed = True
            job.status, job.progress, job.stage, job.finished_at = "SUCCEEDED", 100, "done", utcnow()
            charged = fixed_charge                          # None: the whole reservation, as for a first run
            if tool == "export":                            # (render, agent B) the quoted seconds rendered
                charged = credits_of(export_sec) if export_sec > 0 else 0
            elif charge_basis == "rendered":
                rendered = float(timer.as_dict()["counts"].get("rendered_sec") or 0)
                charged = credits_of(rendered) if rendered > 0 else 0
            replaced = finish_export(db, job, exported) if tool == "export" else []
            ledger.settle(db, job, success=True, charged=charged)
            db.commit()
        status, error = "SUCCEEDED", None
        for key in replaced:            # (render, agent B) the renders the new exports replaced
            try:
                storage.delete(key)
            except Exception:
                log.exception("could not remove %s", key)
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
            # Clips stored while the job ran are gone with it: a job that did not succeed shows nothing.
            db.execute(update(Clip).where(Clip.job_id == job_id, Clip.deleted_at.is_(None)).values(deleted_at=utcnow()))
            if job.status == "RUNNING":
                job.status, job.finished_at = status, utcnow()
                if error:
                    job.error_code, job.error_message = error
                job.result = {**measured(), **waited(job)}   # where a failed or cancelled job spent its time
                ledger.settle(db, job, success=False)   # refund
                db.commit()
            else:
                status = job.status   # already finalised and settled elsewhere; leave it alone
                db.commit()           # (the clips above still go)
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
    from . import url_clips
    cutoff = utcnow() - timedelta(minutes=get_settings().stale_job_minutes)
    n, ended = 0, []
    with new_session() as db:
        stale = db.execute(select(Job).where(Job.status == "RUNNING", Job.heartbeat_at < cutoff)
                           .with_for_update(skip_locked=True)).scalars().all()
        orphans: list[str] = []
        for job in stale:
            job.status, job.finished_at = "FAILED", utcnow()
            job.error_code, job.error_message = "worker_lost", "Processing was interrupted. Your credits were refunded."
            ledger.settle(db, job, success=False)
            if job.id.startswith("imp_"):
                ended += url_clips.resolve(db, job)     # link clip jobs waiting for this import: refunded
            # Clips the dead worker had already stored: hide them and remove their files.
            for clip in db.execute(select(Clip).where(Clip.job_id == job.id, Clip.deleted_at.is_(None))).scalars():
                orphans += [k for k in (clip.video_key, clip.thumb_key, clip.captions_key, clip.preview_key,
                                        frame_key_of(clip.features)) if k]
                clip.deleted_at = utcnow()
            n += 1
        db.commit()
    storage = get_storage()
    for key in orphans:
        try:
            storage.delete(key)
        except Exception:
            log.exception("could not remove %s", key)
    url_clips.notify(ended)
    return n


def sweep_expired() -> int:
    """Delete stored files past their retention date."""
    storage, now, n = get_storage(), utcnow(), 0
    with new_session() as db:
        active_uploads = select(Job.upload_id).where(Job.status.in_(("WAITING", "QUEUED", "RUNNING")))
        for up in db.execute(select(Upload).where(Upload.deleted_at.is_(None), Upload.expires_at <= now,
                                                  Upload.id.not_in(active_uploads)).limit(200)).scalars():
            storage.delete(up.storage_key)
            storage.delete(transcript_key(up.id))
            storage.delete(transcript_parts_key(up.id))
            storage.delete(vindex_key(up.id))
            up.deleted_at = now
            n += 1
        expired_jobs = select(Job.id).where(Job.expires_at <= now)
        for clip in db.execute(select(Clip).where(Clip.deleted_at.is_(None),
                                                  Clip.job_id.in_(expired_jobs)).limit(500)).scalars():
            for key in dict.fromkeys([clip.video_key, clip.thumb_key, clip.captions_key, clip.preview_key,
                                      clip.export_key, frame_key_of(clip.features), *thumbnail_keys(db, [clip.id])]):
                if key:
                    storage.delete(key)
            clip.deleted_at = now
            n += 1
        db.commit()
    return n


def run_once(transcriber: Transcriber | None = None, pipeline=run_pipeline,
             indexer: Transcriber | None = None, embedder=None, ai=None, prefix: str | None = None) -> str | None:
    job_id = claim_job(prefix)
    if not job_id:
        return None
    return process_job(job_id, transcriber, pipeline, indexer, embedder, ai)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log_redact.install()
    s = get_settings()
    s.check_production()
    if s.sentry_dsn:
        log_redact.init_sentry(s.sentry_dsn)
    init_db()
    provider_for(s.transcription_provider, None)                 # an unknown provider stops the worker here, not mid-job
    FasterWhisperTranscriber.workers = s.transcribe_parallel     # before the models load
    transcriber, indexer, embedder = default_transcriber(), default_indexer(), default_embedder()
    log.info("worker started (captions: %s, search index: %s, visual search: %s)",
             s.whisper_model, s.whisper_index_model, s.visual_search)
    log.info("running up to %s job(s) at once", s.worker_concurrency)
    serve(s.worker_concurrency, threading.Event(), transcriber, indexer=indexer, embedder=embedder)


def _slot(i: int, stop: threading.Event, transcriber, pipeline, indexer, embedder, ai) -> None:
    """One job at a time until stop is set. Slot 0 also runs the sweeps."""
    poll, last_sweep = get_settings().worker_poll_sec, 0.0
    while not stop.is_set():
        try:
            if i == 0 and time.monotonic() - last_sweep > 60:
                last_sweep = time.monotonic()
                from .url_clips import sweep_waiting
                stale, expired, months = sweep_stale_jobs(), sweep_expired(), sweep_yearly_grants()
                waiting = sweep_waiting()
                if stale or expired or months or waiting:
                    log.info("sweep: %s stale jobs refunded, %s expired files deleted, %s yearly-plan months granted, "
                             "%s link clip jobs settled after their import", stale, expired, months, waiting)
            if run_once(transcriber, pipeline, indexer, embedder, ai or default_ai()) is None:
                stop.wait(poll)
        except Exception:
            log.exception("worker loop error")
            stop.wait(5)


def _thumb_slot(stop: threading.Event) -> None:
    """Premium thumbnail jobs only, one at a time, so a 20-second paid job never queues behind a 2-hour VOD."""
    poll = get_settings().worker_poll_sec
    while not stop.is_set():
        try:
            if run_once(prefix=THUMB_PREFIX + "_") is None:
                stop.wait(poll)
        except Exception:
            log.exception("thumbnail slot error")
            stop.wait(5)


def serve(concurrency: int, stop: threading.Event, transcriber: Transcriber | None = None, pipeline=run_pipeline,
          indexer: Transcriber | None = None, embedder=None, ai=None) -> None:
    """Run `concurrency` job slots until stop is set; returns when every slot has finished its current job."""
    slots = [threading.Thread(target=_slot, args=(i, stop, transcriber, pipeline, indexer, embedder, ai),
                              name=f"slot-{i}") for i in range(concurrency)]
    if get_settings().premium_thumbnails:        # premium thumbnails wait on a provider, not the CPU: their own slot,
        slots.append(threading.Thread(target=_thumb_slot, args=(stop,), name="slot-thumbnails"))   # never behind a VOD
    for t in slots:
        t.start()
    for t in slots:
        t.join()


if __name__ == "__main__":
    main()
