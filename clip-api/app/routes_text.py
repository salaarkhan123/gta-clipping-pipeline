"""Language tools (agent F): the languages list, whole-video transcripts (with an optional translation) and video
summaries. Transcripts and summaries are jobs on an upload, priced like Video Finder's index: a video's minutes
once, by whichever whole-video tool runs on it first; after that the re-run rule (reserve, charge what was rendered,
which here is nothing). Translation and summaries themselves cost nothing extra; both are off until the owner turns
a provider on (see the PR's money questions)."""
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import languages
from .ai import default_ai
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .languages import LanguageCode, SourceLanguage
from .models import Upload
from .pipeline.translate import as_text, segment_rows, stored_translation, transcript_language
from .routes_media import credits_for, own_upload, submit_job
from .storage import get_storage, transcript_key

router = APIRouter()


class TranscriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str
    source_lang: SourceLanguage | None = None      # null: detected (or the language detected before)
    target_lang: LanguageCode | None = None        # translate every segment into this language, when configured
    webhook_url: str | None = Field(default=None, max_length=500)


class SummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str
    source_lang: SourceLanguage | None = None
    target_lang: LanguageCode | None = None        # the summary's language; null: the spoken one
    webhook_url: str | None = Field(default=None, max_length=500)


@router.get("/v1/languages")
def list_languages():
    """Every language code the API knows, with its English name, whether speech in it can be transcribed on this
    server, and whether translation and summaries are configured. Public, no key needed."""
    can = set(languages.source_languages())
    ai = default_ai()
    return {"languages": [{"code": c, "name": n, "transcribe": c in can} for c, n in languages.LANGUAGES.items()],
            "translation": languages.translator(ai) is not None, "summaries": languages.summarizer(ai) is not None,
            "speakers": False}


def _plan(tool: str, body):
    def plan(upload: Upload):
        s = get_settings()
        if not upload.has_audio:
            raise ApiError(422, "no_audio", "This video has no audio track, so there is nothing to transcribe.")
        if tool == "summary" and languages.summarizer(default_ai()) is None:
            raise ApiError(503, "not_configured", "Video summaries are not configured on this server.")
        options = {"tool": tool, "source_lang": body.source_lang, "target_lang": body.target_lang}
        if upload.analyzed and s.charge_once_per_upload:
            # Already paid for once: the re-run rule. One credit is held and the job is charged for what it
            # rendered, which is nothing, so it all goes back when the job settles.
            return {**options, "charge_basis": "rendered"}, 60.0, credits_for(60)
        return options, upload.duration_sec, credits_for(upload.duration_sec)
    return plan


@router.post("/v1/transcripts", status_code=202)
def create_transcript(body: TranscriptRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
                      idempotency_key: str | None = Header(default=None, max_length=200)):
    """Video Transcripts: the whole video's speech as timed segments, with a translation of each segment when
    `target_lang` differs from the spoken language and translation is configured on this server. The transcript
    is kept with the upload (Video Finder uses the same one): read it with GET /v1/transcripts/{upload_id}.

    Cost: the video's minutes, once, like Video Finder's index; on an upload that was already analysed nothing."""
    return submit_job(db, p, body.upload_id, body.webhook_url, idempotency_key, _plan("transcript", body))


@router.post("/v1/summaries", status_code=202)
def create_summary(body: SummaryRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
                   idempotency_key: str | None = Header(default=None, max_length=200)):
    """Video Summary: a title, a summary, tags and timed highlights, written from the transcript (made first when
    the upload has none). The result is in the job (`result.summary`) and GET /v1/summaries/{upload_id}."""
    return submit_job(db, p, body.upload_id, body.webhook_url, idempotency_key, _plan("summary", body))


def _stored(db: Session, p: Principal, upload_id: str) -> tuple[Upload, dict]:
    upload = own_upload(db, p, upload_id)
    storage, key = get_storage(), transcript_key(upload.id)
    if not storage.exists(key):
        raise ApiError(409, "not_transcribed", "This upload has no transcript yet. Run POST /v1/transcripts first.")
    tmp = get_settings().work_dir / f"tr_{uuid.uuid4().hex}.json"
    try:
        storage.fetch(key, tmp)
        return upload, json.loads(tmp.read_text())
    finally:
        tmp.unlink(missing_ok=True)


def _rows(transcript: dict, target: str | None, display: str) -> list[dict]:
    if display != "original" and target is None:
        raise ApiError(422, "validation_error", "caption_display translation or both needs target_lang.")
    if target is not None and stored_translation(transcript, target) is None:
        if display != "original":
            raise ApiError(409, "no_translation", f"This transcript has no translation into {target}. Run "
                                                  "POST /v1/transcripts with that target_lang first.")
        target = None
    return segment_rows({**transcript, "language": transcript_language(transcript)}, target)


@router.get("/v1/transcripts/{upload_id}")
def get_transcript(upload_id: str, target_lang: LanguageCode | None = None,
                   p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """The upload's transcript as JSON: segments {start, end, text, language, speaker}, plus `translation` on each
    when `target_lang` is given and that translation was made. `speaker` is null: no speaker-identification
    method is configured on this server."""
    upload, transcript = _stored(db, p, upload_id)
    target = target_lang
    has = target is not None and stored_translation(transcript, target) is not None
    return {"upload_id": upload.id, "language": transcript_language(transcript),
            "language_detected": bool(transcript.get("language_detected")), "duration": transcript.get("duration"),
            "target_lang": target, "translated": has,
            "translations": sorted((transcript.get("translations") or {}).keys()),
            "segments": segment_rows({**transcript, "language": transcript_language(transcript)}, target if has else None)}


@router.get("/v1/transcripts/{upload_id}/download", response_class=PlainTextResponse)
def download_transcript(upload_id: str, format: Literal["txt", "srt", "vtt"] = "txt",
                        caption_display: Literal["original", "translation", "both"] = "original",
                        target_lang: LanguageCode | None = None,
                        p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """The transcript as a TXT, SRT or VTT file: the spoken words, the translation into `target_lang`, or both."""
    upload, transcript = _stored(db, p, upload_id)
    rows = _rows(transcript, target_lang, caption_display)
    spoken = transcript_language(transcript)
    suffix = {"original": spoken, "translation": target_lang, "both": f"{spoken}-{target_lang}"}[caption_display]
    return PlainTextResponse(as_text(rows, caption_display, format), headers={
        "content-disposition": f'attachment; filename="{upload.id}.{suffix}.{format}"'})


@router.get("/v1/summaries/{upload_id}")
def get_summary(upload_id: str, target_lang: LanguageCode | None = None,
                p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """A summary made before by POST /v1/summaries, in `target_lang` (default: the spoken language)."""
    upload, transcript = _stored(db, p, upload_id)
    lang = target_lang or transcript_language(transcript)
    summary = (transcript.get("summaries") or {}).get(lang)
    if not summary:
        raise ApiError(404, "no_summary", f"This upload has no summary in {lang} yet. Run POST /v1/summaries first.")
    return {"upload_id": upload.id, "language": lang, **{k: summary.get(k) for k in ("title", "summary", "tags",
                                                                                     "highlights")}}
