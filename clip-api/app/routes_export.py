"""Re-export: render chosen clips of a finished job again with new options and the editor's edits.

POST /v1/clips/export/quote  what an export would reserve; nothing is reserved or rendered
POST /v1/clips/export        the export itself: a job (tool "export") to poll like any other

The editor saves an edit with PATCH /v1/clips/{clip_id} (`edit`, exports.ClipEditDoc), free.

PRICE (needs the owner's OK, docs/CONTRACTS.md "Money paths"): an export reserves credits_for(the seconds it will
render, all its clips together), one credit per started minute, and is charged for the seconds it did render (the
approved re-run rule, `charge_basis` "rendered"). A failed or cancelled export is refunded in full.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .exports import ClipEditDoc, planned
from .models import Clip, Job, Upload
from .plans import plan_of
from .render_options import LayoutOptions
from .routes_media import credits_for, own_job, submit_job

router = APIRouter()

MAX_EXPORT_CLIPS = 50
EXPORTABLE = ("clips", "find", "render")        # the job tools whose clips can be exported
NOTE = "Charged for the seconds rendered, never more than this. Refunded in full if the render fails."


class ExportOptions(LayoutOptions):
    """The render options of POST /v1/clips. The ones sent replace the job's own; the rest stay as the job had
    them. An export is always a full render."""
    render: Literal["full"] = "full"
    hook: bool = True           # burn the hook: the edit's `hook_text`, else the AI's


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    clips: list[str] | None = Field(default=None, min_length=1, max_length=MAX_EXPORT_CLIPS)   # null: every clip
    options: ExportOptions = ExportOptions()
    # One clip only: its edit (trim, cuts, caption lines, hook text), saved on the clip and rendered.
    edit: ClipEditDoc | None = None
    webhook_url: str | None = Field(default=None, max_length=500)


def _options(job: Job, body: ExportRequest) -> dict:
    """The job's own render options with the ones the request sent on top, checked together."""
    own = {k: v for k, v in (job.options or {}).items() if k in LayoutOptions.model_fields}
    sent = {k: v for k, v in body.options.model_dump(exclude_unset=True).items() if k in LayoutOptions.model_fields}
    try:
        merged = LayoutOptions(**{**own, **sent})
    except ValidationError as e:
        raise ApiError(422, "bad_options", e.errors()[0]["msg"]) from None
    out = merged.model_dump()
    out.pop("render", None)
    out["hook_overlay"] = body.options.hook
    return out


def _clips(db: Session, job: Job, ids: list[str] | None) -> list[Clip]:
    rows = {c.id: c for c in db.execute(select(Clip).where(Clip.job_id == job.id, Clip.deleted_at.is_(None))
                                        .order_by(Clip.idx)).scalars()}
    if ids is None:
        if not rows:
            raise ApiError(422, "no_clips", "This job has no clips to export.")
        return list(rows.values())
    missing = [i for i in dict.fromkeys(ids) if i not in rows]
    if missing:
        raise ApiError(404, "clip_not_found", f"No such clip in this job: {missing[0]}.")
    return [rows[i] for i in dict.fromkeys(ids)]


def check_edit(db: Session, clip: Clip, edit: ClipEditDoc) -> None:
    """An edit must stay inside its clip's video."""
    upload = db.get(Upload, db.get(Job, clip.job_id).upload_id)
    if upload is not None and edit.trim.end > upload.duration_sec + 0.5:
        raise ApiError(422, "bad_segment", f"The trim must fall inside the video (0 to {upload.duration_sec:.0f} s).")


def _quote(db: Session, p: Principal, body: ExportRequest) -> tuple[Job, list[Clip], dict, float]:
    job = own_job(db, p, body.job_id)
    if (job.options or {}).get("tool", "clips") not in EXPORTABLE:
        raise ApiError(422, "not_exportable", "Only clip, Video Finder, Reframe and Captions jobs have clips to export.")
    if job.status != "SUCCEEDED":
        raise ApiError(409, "job_not_finished", "The job has to finish before its clips can be exported.")
    clips = _clips(db, job, body.clips)
    if body.edit is not None:
        if len(clips) != 1:
            raise ApiError(422, "one_clip_per_edit", "Send an edit with exactly one clip in `clips`.")
        check_edit(db, clips[0], body.edit)
    options = _options(job, body)
    total = round(sum(planned(c, body.edit) for c in clips), 3)
    s, plan = get_settings(), plan_of(p.account)
    cap = min(s.max_render_sec, plan["max_render_min"] * 60 if plan.get("max_render_min") else s.max_render_sec)
    if total > cap:
        raise ApiError(413, "range_too_long", f"The {plan['name']} plan renders up to {cap // 60} minutes per job. "
                                              "Export fewer clips at a time or upgrade.")
    return job, clips, options, total


@router.post("/v1/clips/export/quote")
def export_quote(body: ExportRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """What POST /v1/clips/export with the same body would reserve. Nothing is reserved, saved or rendered."""
    _job, clips, options, total = _quote(db, p, body)
    return {"credits_reserved": credits_for(total), "seconds": total, "note": NOTE,
            "resolution": options.get("resolution", "1080"),
            "clips": [{"clip_id": c.id, "seconds": planned(c, body.edit)} for c in clips]}


@router.post("/v1/clips/export", status_code=202)
def export_clips(body: ExportRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
                 idempotency_key: str | None = Header(default=None, max_length=200)):
    """Render chosen clips of a finished job again: new resolution, layout, captions or hook placement, and each
    clip's edit. Poll the returned job; when it succeeds each clip of the source job has an `export_url`."""
    def plan(upload: Upload):
        job, clips, options, total = _quote(db, p, body)
        if body.edit is not None:
            clips[0].edit = body.edit.model_dump()     # committed with the job (submit_job)
        return ({"tool": "export", "charge_basis": "rendered", "source_job": job.id, "clips": [c.id for c in clips],
                 **options}, total, credits_for(total))
    return submit_job(db, p, own_job(db, p, body.job_id).upload_id, body.webhook_url, idempotency_key, plan)
