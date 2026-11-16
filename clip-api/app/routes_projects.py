"""Projects and the clip library. A project is an upload seen with its jobs and clips; nothing new is stored."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .deps import Principal, current_principal
from .models import Clip, Job, Upload, utcnow
from .routes_media import clip_json, iso, job_json, own_upload, upload_json, with_ranks
from .storage import get_storage

router = APIRouter()
ACTIVE = ("QUEUED", "RUNNING")


def _live_uploads(account_id: str):
    return select(Upload).where(Upload.account_id == account_id, Upload.deleted_at.is_(None),
                                Upload.expires_at > utcnow())


@router.get("/v1/projects")
def list_projects(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                  p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Every stored upload as a project, newest first, with how much has been made from it."""
    uploads = db.execute(_live_uploads(p.account.id).order_by(Upload.created_at.desc())
                         .limit(limit).offset(offset)).scalars().all()
    ids = [u.id for u in uploads]
    jobs = dict(db.execute(select(Job.upload_id, func.count(Job.id)).where(Job.upload_id.in_(ids))
                           .group_by(Job.upload_id)).all()) if ids else {}
    active = set(db.execute(select(Job.upload_id).where(Job.upload_id.in_(ids), Job.status.in_(ACTIVE)))
                 .scalars()) if ids else set()
    clips: dict[str, int] = {}
    thumbs: dict[str, str] = {}
    if ids:
        rows = db.execute(select(Job.upload_id, Clip.thumb_key).join(Clip, Clip.job_id == Job.id)
                          .where(Job.upload_id.in_(ids), Clip.deleted_at.is_(None))
                          .order_by(Clip.score.desc()))
        for uid, thumb_key in rows:
            clips[uid] = clips.get(uid, 0) + 1
            if thumb_key and uid not in thumbs:
                thumbs[uid] = thumb_key          # the best-scoring clip's frame stands for the project
    storage = get_storage()
    return {"projects": [{**upload_json(u), "jobs": jobs.get(u.id, 0),
                          "active": u.id in active, "clips": clips.get(u.id, 0),
                          "thumb_url": storage.url(thumbs[u.id]) if u.id in thumbs else None} for u in uploads]}


@router.get("/v1/projects/{upload_id}")
def get_project(upload_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """One project: the upload, a signed link to the source video, its jobs (newest first) and all its clips."""
    upload = own_upload(db, p, upload_id)
    storage = get_storage()
    jobs = db.execute(select(Job).where(Job.upload_id == upload.id, Job.account_id == p.account.id)
                      .order_by(Job.created_at.desc())).scalars().all()
    tool_of = {j.id: (j.options or {}).get("tool", "clips") for j in jobs}
    clips = db.execute(select(Clip).where(Clip.job_id.in_(list(tool_of)), Clip.deleted_at.is_(None))
                       .order_by(Clip.score.desc(), Clip.start_sec)).scalars().all() if tool_of else []
    return {**upload_json(upload), "source_url": storage.url(upload.storage_key),
            "jobs": [job_json(db, j, with_clips=False) for j in jobs],
            "clips": with_ranks(db, [{**clip_json(c, storage), "tool": tool_of[c.job_id],
                                      "created_at": iso(c.created_at)} for c in clips])}


SORTS = {"newest": (Clip.created_at.desc(), Clip.idx), "score": (Clip.score.desc(), Clip.created_at.desc()),
         "time": (Job.upload_id, Clip.start_sec)}
FILTERS = {"all": (), "kept": (Clip.kept.is_(True),), "discarded": (Clip.kept.is_(False),),
           "bookmarked": (Clip.bookmarked.is_(True),), "liked": (Clip.reaction == "like",)}


@router.get("/v1/clips")
def list_clips(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
               sort: Literal["newest", "score", "time"] = "newest",
               filter: Literal["all", "kept", "discarded", "bookmarked", "liked"] = "all",
               p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """The library: every stored clip on the account. sort: newest, score (highest first) or time (earliest
    moment first, grouped by video). filter: all, kept, discarded, bookmarked or liked."""
    where = (Job.account_id == p.account.id, Clip.deleted_at.is_(None), *FILTERS[filter])
    total = db.execute(select(func.count(Clip.id)).join(Job, Clip.job_id == Job.id).where(*where)).scalar_one()
    rows = db.execute(select(Clip, Job.upload_id, Upload.filename).join(Job, Clip.job_id == Job.id)
                      .join(Upload, Upload.id == Job.upload_id).where(*where)
                      .order_by(*SORTS[sort]).limit(limit).offset(offset)).all()
    storage = get_storage()
    return {"total": total, "clips": with_ranks(db, [{**clip_json(c, storage), "upload_id": upload_id,
                                                      "filename": filename, "created_at": iso(c.created_at)}
                                                     for c, upload_id, filename in rows])}
