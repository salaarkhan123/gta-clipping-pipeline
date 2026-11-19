"""Text-based caption editing: a clip's caption word by word, for the editor to start from. Owned by the captions
agent. Saving goes through PATCH /v1/clips/{id} (`edit.words`, exports.EditWord); POST /v1/clips/export renders
it. Free: nothing here renders or charges."""
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .db import get_db
from .deps import ApiError, Principal, current_principal
from .exports import edit_of, rendered_cut
from .models import Clip
from .pipeline.edit import source_words
from .routes_media import own_job
from .storage import get_storage

router = APIRouter()


@router.get("/v1/clips/{clip_id}/words")
def clip_words(clip_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """The clip's caption as words in SOURCE seconds (the times `edit.words` uses): the saved edit's words when it
    has them, else the words its job burned in. `edited` says which. A clip made without captions has none."""
    clip = db.get(Clip, clip_id)
    if not clip or clip.deleted_at:
        raise ApiError(404, "not_found", "No such clip.")
    own_job(db, p, clip.job_id)
    edit = edit_of(clip)
    if edit is not None and edit.words is not None:
        return {"clip_id": clip.id, "edited": True, "words": [w.model_dump() for w in edit.words]}
    words = []
    storage = get_storage()
    if clip.captions_key and storage.exists(clip.captions_key):
        with tempfile.TemporaryDirectory() as tmp:
            storage.fetch(clip.captions_key, Path(tmp) / "c.json")
            saved = json.loads((Path(tmp) / "c.json").read_text()).get("words") or []
        segments, flash, _z = rendered_cut(clip)
        words = source_words([(w["start"], w["end"], w["text"]) for w in saved], segments, flash)
    return {"clip_id": clip.id, "edited": False,
            "words": [{"start": s, "end": e, "text": t, "hidden": False, "cut": False, "highlight": None,
                       "emoji": None, "break_before": False} for s, e, t in words]}
