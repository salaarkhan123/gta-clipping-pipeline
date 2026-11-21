"""Text-based caption editing: a clip's caption word by word, for the editor to start from. Owned by the captions
agent. Saving goes through PATCH /v1/clips/{id} (`edit.words`, exports.EditWord); POST /v1/clips/export renders
it. Free: nothing here renders or charges."""
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .db import get_db
from .deps import Principal, current_principal
from .exports import edit_of, rendered_cut
from .pipeline.edit import source_words
from .routes_media import own_clip
from .storage import get_storage

router = APIRouter()
MIN_WORD_SEC = 0.01        # the length a word timed with none is given


@router.get("/v1/clips/{clip_id}/words")
def clip_words(clip_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """The clip's caption as words in SOURCE seconds (the times `edit.words` uses): the saved edit's words when it
    has them, else the words its job burned in. `edited` says which. A clip made without captions has none."""
    clip, _job = own_clip(db, p, clip_id)          # someone else's clip and a missing one are the same 404
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
    # Whisper can time a short word with no length ("I" at 10.22-10.22). An edit's word must end after it starts
    # (exports.EditWord), so such a word gets the shortest length, 10 ms; otherwise the editor could not save back
    # the words this route gave it.
    return {"clip_id": clip.id, "edited": False,
            "words": [{"start": s, "end": max(e, round(s + MIN_WORD_SEC, 3)), "text": t, "hidden": False, "cut": False,
                       "highlight": None, "emoji": None, "break_before": False} for s, e, t in words]}
