"""A clip's thumbnail after the job: its words follow the clip's title and hook.

The frame was chosen when the clip was made (app/pipeline/thumbs.py) and is stored next to it, without text, under
`features.thumbnail.frame_key`. Setting new words only draws text on that frame again: no video is read, it takes a
fraction of a second, and it is free.
"""
import logging
import tempfile
from pathlib import Path

from .pipeline.thumbs import canvas_of, thumb_text, write_thumbnail

log = logging.getLogger("clipapi.thumbnails")


def frame_key_of(features) -> str | None:
    """The stored frame of a clip, from its features; None for a clip made before frames were kept."""
    record = features.get("thumbnail") if isinstance(features, dict) else None
    key = record.get("frame_key") if isinstance(record, dict) else None
    return key if isinstance(key, str) and key else None


def words_for(meta, options: dict | None) -> str | None:
    """The words a clip's thumbnail carries with the job's options: the hook, else the title, swears masked with
    `censor`. None when the user turned thumbnail text off (`thumbnail_text` false): the frame alone. The hook
    burned into the video (`hook_overlay`) is a separate choice and changes nothing here."""
    options = options or {}
    if options.get("thumbnail_text") is False:
        return None
    return thumb_text(meta, bool(options.get("censor")))


def redraw(clip, options: dict | None, storage) -> bool:
    """Draw the clip's current words on its stored frame and store the result over its thumbnail (same key, so a
    link already on a page shows the new picture). Returns False, changing nothing, for a clip with no stored
    frame. The clip's features record whether text was drawn."""
    features = clip.features if isinstance(clip.features, dict) else {}
    record = features.get("thumbnail") if isinstance(features.get("thumbnail"), dict) else {}
    key, canvas = frame_key_of(features), canvas_of(record)
    if not (key and canvas is not None and clip.thumb_key):
        return False
    with tempfile.TemporaryDirectory(prefix="thumb") as tmp:
        frame, out = Path(tmp) / "frame.jpg", Path(tmp) / "thumb.jpg"
        storage.fetch(key, frame)
        drawn = write_thumbnail(frame, out, words_for(clip.meta, options), canvas, (options or {}).get("caption_accent"))
        storage.put(clip.thumb_key, out)
    clip.features = {**features, "thumbnail": {**record, "text": drawn}}      # a new dict, so the JSON column is saved
    return True
