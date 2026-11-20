"""Re-export: render chosen clips of a finished job again with new options and the editor's edits.

POST /v1/clips/export/quote  what an export would cost; nothing is reserved or rendered
POST /v1/clips/export        the export itself: a job (tool "export") to poll like any other

The editor saves an edit with PATCH /v1/clips/{clip_id} (`edit`, exports.ClipEditDoc), free.

PRICE (approved by the owner, PR #136): one credit per started minute of the seconds an export renders, all its
clips together. The quote and the export use the same plan (export_plan), so the quote is what is reserved, and
a successful export is charged that amount for the clips it rendered: exactly the quote unless a clip was deleted
before its turn. A failed or cancelled export is refunded in full. Never charged:
- a clip that already has a full render with the same options and edit: its file is handed back (`existing`);
- the same request again while an equal export is queued or running: that job is handed back;
- a request repeated with the same Idempotency-Key: the job it started is handed back, as for POST /v1/clips.
"""
import json
from dataclasses import dataclass, field
from typing import Literal

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .exports import ClipEditDoc, clip_cut, complete_edit, export_spec
from .models import Clip, Export, Job, Upload
from .pipeline.render import output_size, resolution_name
from .pipeline.tools import planned_seconds
from .plans import plan_of
from .render_options import LayoutOptions, refused_layout
from .routes_media import ACTIVE, credits_for, job_json, own_job, replayed, submit_job
from .storage import get_storage

router = APIRouter()

MAX_EXPORT_CLIPS = 50
EXPORTABLE = ("clips", "find", "render")        # the job tools whose clips can be exported
NOTE = ("The exact price: a successful export is charged this, less only when a clip is deleted before it is "
        "rendered. Refunded in full if the render fails.")
FREE_NOTE = "Already rendered with these settings: the files are handed back free."


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


def _options(job: Job, sent: dict, hook: bool) -> dict:
    """The job's own render options with the ones the request sent on top, checked together."""
    own = {k: v for k, v in (job.options or {}).items() if k in LayoutOptions.model_fields}
    sent = {k: v for k, v in sent.items() if k in LayoutOptions.model_fields}
    try:
        merged = LayoutOptions(**{**own, **sent})
    except ValidationError as e:
        refused = refused_layout(e.errors())
        if refused:
            raise ApiError(400, *refused) from None
        raise ApiError(422, "bad_options", e.errors()[0]["msg"]) from None
    out = merged.model_dump()
    out.pop("render", None)
    out["hook_overlay"] = hook
    return out


def own_render_spec(job: Job) -> dict | None:
    """What the clips of a clip job that rendered in full look like, as export_spec says it, or None (a preview,
    no video, or another tool's render, which an export does not reproduce)."""
    opts = job.options or {}
    if opts.get("tool", "clips") != "clips" or opts.get("render", "full") != "full":
        return None
    try:
        return export_spec(_options(job, {}, bool(opts.get("hook_overlay", True))), None)
    except ApiError:
        return None                     # options that are no longer offered: nothing to match


def existing_render(db: Session, clip: Clip, spec: dict, own: dict | None) -> str | None:
    """The storage key of a full render of `clip` that looks like `spec`, else None."""
    if clip.export_key:
        row = db.execute(select(Export).where(Export.clip_id == clip.id, Export.storage_key == clip.export_key)
                         ).scalars().first()
        if row is not None and row.options == spec:
            return clip.export_key
    if clip.video_key and own is not None and own == spec:
        return clip.video_key
    return None


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


def check_edit(db: Session, clip: Clip, edit: ClipEditDoc) -> ClipEditDoc:
    """An edit must stay inside its clip's video. Returns it as it is stored (exports.complete_edit)."""
    upload = db.get(Upload, db.get(Job, clip.job_id).upload_id)
    if upload is not None and edit.trim.end > upload.duration_sec + 0.5:
        raise ApiError(422, "bad_segment", f"The trim must fall inside the video (0 to {upload.duration_sec:.0f} s).")
    try:
        return complete_edit(clip, edit)
    except ValidationError as e:
        raise ApiError(422, "bad_edit", e.errors()[0]["msg"]) from None


def rendered_resolution(db: Session, job: Job, options: dict, max_side: int | None) -> str:
    """The resolution an export with these options renders (render.output_size, as run_export draws it): the one
    asked for, never above the source's own nor the plan's cap `max_side`. What the quote and the clip report."""
    upload = db.get(Upload, job.upload_id)
    size = output_size(upload.width, upload.height, options.get("vertical", True), options.get("aspect", "9:16"),
                       options.get("resolution"), max_side=max_side)
    return resolution_name(*size)


@dataclass
class ExportPlan:
    """What an export request renders, reserves and hands back. The quote shows it; the export stores it."""
    job: Job
    clips: list[Clip]                   # every clip asked for, in order
    options: dict                       # the render options (the job's, with the sent ones on top)
    edits: dict                         # clip id: the edit it renders (a dict) or None
    resolution: str = "1080"            # what the files are: the request's, after the plan's cap and the source's size
    todo: list[Clip] = field(default_factory=list)      # the clips rendered and charged
    seconds: dict = field(default_factory=dict)         # clip id: the seconds it renders
    free: list[dict] = field(default_factory=list)      # clips with this render already: handed back free

    @property
    def total(self) -> float:
        return round(sum(self.seconds[c.id] for c in self.todo), 3)

    @property
    def cost(self) -> int:
        return credits_for(self.total) if self.todo else 0

    def stored(self) -> dict:
        """The export job's options: what the worker renders, and what an equal request is compared on."""
        ids = [c.id for c in self.todo]
        return json.loads(json.dumps({
            "tool": "export", "charge_basis": "rendered", "source_job": self.job.id, "clips": ids, **self.options,
            "edits": {i: self.edits[i] for i in ids}, "seconds": {i: self.seconds[i] for i in ids}}, sort_keys=True))


def export_plan(db: Session, p: Principal, body: ExportRequest) -> ExportPlan:
    """The one plan behind the quote and the export, so the quote is exactly what the export reserves."""
    job = own_job(db, p, body.job_id)
    if (job.options or {}).get("tool", "clips") not in EXPORTABLE:
        raise ApiError(422, "not_exportable", "Only clip, Video Finder, Reframe and Captions jobs have clips to export.")
    if job.status != "SUCCEEDED":
        raise ApiError(409, "job_not_finished", "The job has to finish before its clips can be exported.")
    clips = _clips(db, job, body.clips)
    edits = {c.id: c.edit for c in clips}
    if body.edit is not None:
        if len(clips) != 1:
            raise ApiError(422, "one_clip_per_edit", "Send an edit with exactly one clip in `clips`.")
        edits[clips[0].id] = check_edit(db, clips[0], body.edit).model_dump()
    # `hook` not sent: the export keeps what the job chose (its hook_overlay), so a clip made with the hook off
    # is not exported with one.
    hook = body.options.hook if "hook" in body.options.model_fields_set else bool((job.options or {}).get("hook_overlay", True))
    options = _options(job, body.options.model_dump(exclude_unset=True), hook)
    s, account_plan = get_settings(), plan_of(p.account)
    plan = ExportPlan(job=job, clips=clips, options=options, edits=edits,
                      resolution=rendered_resolution(db, job, options, account_plan.get("max_side")))
    storage, own = get_storage(), own_render_spec(job)
    for c in clips:
        doc = ClipEditDoc.model_validate(edits[c.id]) if edits[c.id] else None
        seconds = planned_seconds(clip_cut(c, doc)[0])
        key = existing_render(db, c, export_spec(options, edits[c.id]), own)
        if key:
            plan.free.append({"clip_id": c.id, "video_url": storage.url(key), "seconds": seconds,
                              "resolution": plan.resolution})
        else:
            plan.todo.append(c)
            plan.seconds[c.id] = seconds
    cap = min(s.max_render_sec, account_plan["max_render_min"] * 60 if account_plan.get("max_render_min")
              else s.max_render_sec)
    if plan.total > cap:
        raise ApiError(413, "range_too_long", f"The {account_plan['name']} plan renders up to {cap // 60} minutes per "
                                              "job. Export fewer clips at a time or upgrade.")
    return plan


def equal_export(db: Session, p: Principal, stored: dict) -> Job | None:
    """An export of this account, queued or running, that renders exactly what `stored` would."""
    for job in db.execute(select(Job).where(Job.account_id == p.account.id, Job.status.in_(ACTIVE))
                          .order_by(Job.created_at)).scalars():
        if (job.options or {}).get("tool") == "export" and json.loads(json.dumps(job.options, sort_keys=True)) == stored:
            return job
    return None


@router.post("/v1/clips/export/quote")
def export_quote(body: ExportRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """What POST /v1/clips/export with the same body would reserve: the same plan. Nothing is reserved, saved or
    rendered. `existing` lists the clips whose render is handed back free."""
    plan = export_plan(db, p, body)
    todo = {c.id for c in plan.todo}
    return {"credits_reserved": plan.cost, "seconds": plan.total, "note": NOTE if plan.todo else FREE_NOTE,
            "resolution": plan.resolution,
            "clips": [{"clip_id": c.id, "seconds": plan.seconds[c.id] if c.id in todo else 0.0, "free": c.id not in todo}
                      for c in plan.clips],
            "existing": plan.free}


@router.post("/v1/clips/export", status_code=202)
def export_clips(body: ExportRequest, response: Response, p: Principal = Depends(current_principal),
                 db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, max_length=200)):
    """Render chosen clips of a finished job again: new resolution, layout, captions or hook placement, and each
    clip's edit. Poll the returned job; when it succeeds each clip of the source job has an `export_url`.
    200 instead of 202 when nothing is started: every clip already has this render (`job_id` null, `existing`
    holds the files), or an equal export is already queued or running (that job is returned)."""
    source = own_job(db, p, body.job_id)
    ledger.lock_account(db, p.account.id)       # serialise this account's submits: a double click waits here
    prior = replayed(db, p, idempotency_key)
    if prior:
        return prior
    plan = export_plan(db, p, body)
    if body.edit is not None:
        plan.clips[0].edit = plan.edits[plan.clips[0].id]      # saved free, committed with whatever follows
    if not plan.todo:
        db.commit()
        response.status_code = 200
        return {"job_id": None, "status": "SUCCEEDED", "credits_reserved": 0, "credits_charged": 0,
                "existing": plan.free}
    stored = plan.stored()
    same = equal_export(db, p, stored)
    if same is not None:
        db.commit()
        response.status_code = 200
        return {**job_json(db, same, with_clips=False), "existing": plan.free}
    out = submit_job(db, p, source.upload_id, body.webhook_url, idempotency_key,
                     lambda _upload: (stored, plan.total, plan.cost))
    return {**out, "existing": plan.free}
