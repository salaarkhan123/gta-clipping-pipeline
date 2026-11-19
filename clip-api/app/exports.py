"""Re-export (POST /v1/clips/export) and the editor's saved decisions (`clips.edit`): the database side.

The rendering itself is app/pipeline/tools.py run_export. Owned by the rendering agent (docs/CONTRACTS.md).

What a clip is rendered from: its edit (`clips.edit`, ClipEditDoc) when it has one, else what its own job rendered
(`features["edit"]`: segments, flash-forward, zooms), else its start and end.
"""
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Clip, Export, Job, new_id
from .pipeline.captions import Word
from .pipeline.edit import remap_words, source_words
from .pipeline.tools import ExportItem, planned_seconds
from .render_options import LayoutOptions

MIN_EDIT_SEC = 1.0          # the shortest an edited clip may be
MAX_EDIT_SEC = 300.0        # the longest (the longest clip-length bucket)
HOOK_MAX = 60


class Trim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class CaptionLine(BaseModel):
    """A caption line as the user wrote it, in source seconds."""
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(max_length=200)


EMOJI = re.compile(r"^[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF\u2300-\u23FF"
                   r"\uFE0F\u200D\U0001F3FB-\U0001F3FF]{1,8}$")


class EditWord(BaseModel):
    """One caption word in the text-based editor (captions agent), in SOURCE seconds like the rest of the edit.

    - `text`: the word as it is shown (edit words); its time stays the spoken word's.
    - `hidden`: remove the caption only; the video keeps the moment.
    - `cut`: remove the caption and its stretch of video (the word's [start, end] joins the edit's cuts).
    - `highlight`: this word in a colour (#RRGGBB) of the user's choosing.
    - `emoji`: up to two emoji drawn after the word.
    - `break_before`: a new caption starts at this word (split).
    """
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=60)
    hidden: bool = False
    cut: bool = False
    highlight: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    emoji: str | None = Field(default=None, max_length=16)
    break_before: bool = False

    @field_validator("text")
    @classmethod
    def one_word(cls, value):
        value = " ".join(value.split())
        if not value or "{" in value or "}" in value or "\\" in value:
            raise ValueError("a caption word is plain text")
        return value

    @field_validator("emoji")
    @classmethod
    def only_emoji(cls, value):
        if value is not None and not EMOJI.match(value):
            raise ValueError("emoji takes emoji only")
        return value

    @model_validator(mode="after")
    def check_times(self):
        if self.end <= self.start:
            raise ValueError("a word ends after it starts")
        return self


class ClipEditDoc(BaseModel):
    """`clips.edit`: one clip as the editor left it. Every time is in seconds of the SOURCE video, so an edit means
    the same thing however the clip was rendered before (the format of web-src/lib/edit.ts).

    - `trim`: where the clip starts and ends in the source (it may reach outside the clip's first cut).
    - `cuts`: parts inside the trim to leave out. The clip is rendered from the trim minus the cuts, exactly; its
      flash-forward is not kept. Left out, the cuts are the dead air its job removed inside the trim (the gaps
      between the clip's `segments`, `complete_edit`), so an edit keeps them unless it says otherwise; `[]` keeps
      every second of the trim.
    - `caption_lines`: the caption lines in the user's words; each line's time is shared evenly between its words.
      Empty: the clip's own words, moved onto the new cut.
    - `hook_text`: the on-screen hook in the user's words; null keeps the AI's.
    - `words`: the caption word by word (text-based editing, EditWord): edited text, hidden captions, highlights,
      emoji, splits, and words cut with their video. When set it replaces `caption_lines` and the clip's own words;
      each word keeps its own time.
    - `options`: the look the editor chose (POST /v1/clips option names), kept for the editor. An export renders
      with the options its request sends.
    Saving is free: nothing is rendered until POST /v1/clips/export.
    """
    model_config = ConfigDict(extra="forbid")
    trim: Trim
    cuts: list[tuple[float, float]] = Field(default_factory=list, max_length=200)
    caption_lines: list[CaptionLine] = Field(default_factory=list, max_length=1000)
    words: list[EditWord] | None = Field(default=None, max_length=3000)
    hook_text: str | None = Field(default=None, max_length=HOOK_MAX)
    options: dict = Field(default_factory=dict)

    @field_validator("hook_text")
    @classmethod
    def tidy_hook(cls, value):
        return (" ".join(value.split()) or None) if isinstance(value, str) else value

    @field_validator("options")
    @classmethod
    def check_options(cls, value):
        unknown = sorted(set(value) - set(LayoutOptions.model_fields))
        if unknown:
            raise ValueError(f"unknown option: {unknown[0]}")
        try:
            LayoutOptions(**value)
        except ValidationError as e:
            raise ValueError(e.errors()[0]["msg"]) from None
        return value

    @model_validator(mode="after")
    def check_length(self):
        if self.trim.end <= self.trim.start:
            raise ValueError("the trim must end after it starts")
        if any(e <= s for s, e in self.cuts):
            raise ValueError("each cut is [start, end] with end after start")
        kept = planned_seconds(self.segments())
        if not MIN_EDIT_SEC <= kept <= MAX_EDIT_SEC:
            raise ValueError(f"an edited clip is {MIN_EDIT_SEC:.0f} to {MAX_EDIT_SEC:.0f} seconds long")
        return self

    def segments(self) -> list[list[float]]:
        """The source parts to play, in order: the trim with the cuts taken out."""
        out, at = [], self.trim.start
        cuts = [*self.cuts, *((w.start, w.end) for w in self.words or () if w.cut)]
        for s, e in sorted((max(s, self.trim.start), min(e, self.trim.end)) for s, e in cuts):
            if e <= at:
                continue
            if s - at > 0.05:
                out.append([round(at, 3), round(s, 3)])
            at = max(at, e)
        if self.trim.end - at > 0.05:
            out.append([round(at, 3), round(self.trim.end, 3)])
        return out

    def caption_words(self) -> list[tuple[float, float, str]]:
        """The caption as timed words, in source seconds: `words` as edited (hidden and cut ones left out, each
        word's marks on its text, captions.Word), else the caption lines with their time shared evenly."""
        if self.words is not None:
            return [(w.start, w.end, Word.of(w.text, w.highlight, w.emoji, w.break_before))
                    for w in sorted(self.words, key=lambda w: w.start) if not (w.hidden or w.cut)]
        out = []
        for line in self.caption_lines:
            parts = line.text.split()
            step = (line.end - line.start) / max(1, len(parts))
            out += [(round(line.start + i * step, 3), round(line.start + (i + 1) * step, 3), w) for i, w in enumerate(parts)]
        return out


def edit_of(clip: Clip) -> ClipEditDoc | None:
    return ClipEditDoc.model_validate(clip.edit) if clip.edit else None


def dead_air(clip: Clip, start: float, end: float) -> list[list[float]]:
    """The parts between start and end that the clip's job cut out as dead air: the gaps between the source
    parts it rendered (its flash-forward left aside), in source seconds."""
    segments, flash, _z = rendered_cut(clip)
    body = sorted(segments[1:] if flash and len(segments) > 1 else segments)
    gaps = []
    for (_s0, e0), (s1, _e1) in zip(body, body[1:]):
        a, b = max(float(e0), start), min(float(s1), end)
        if b - a > 0.05:
            gaps.append([round(a, 3), round(b, 3)])
    return gaps


def complete_edit(clip: Clip, edit: ClipEditDoc) -> ClipEditDoc:
    """The edit as it is stored and rendered: without `cuts`, the clip's dead air inside the trim is cut, as its
    job cut it. Raises ValidationError when what is left is too short or too long."""
    if "cuts" in edit.model_fields_set:
        return edit
    return ClipEditDoc.model_validate({**edit.model_dump(), "cuts": dead_air(clip, edit.trim.start, edit.trim.end)})


# Keys of an export job's options that say what it is, not how it looks (export_spec leaves them out).
JOB_KEYS = ("tool", "charge_basis", "source_job", "clips", "edits", "seconds")


def export_spec(render: dict, edit: dict | None) -> dict:
    """What a full render of a clip looks like, to tell whether one exists already: its render options and its
    edit, as JSON (stored on its Export row as `options`)."""
    options = {k: v for k, v in render.items() if k not in JOB_KEYS}
    options.setdefault("resolution", "1080")
    return json.loads(json.dumps({"render": options, "edit": edit}, sort_keys=True))


def rendered_cut(clip: Clip) -> tuple[list, bool, list]:
    """(segments, flash, zoom_at) the clip's own job rendered it from: source seconds, in playing order."""
    rendered = (clip.features or {}).get("edit") or {}
    if rendered.get("segments"):
        return ([list(x) for x in rendered["segments"]], bool(rendered.get("flash_forward")),
                list(rendered.get("zoom_at") or []))
    return [[clip.start_sec, clip.end_sec]], False, []


def clip_cut(clip: Clip, edit: ClipEditDoc | None = None) -> tuple[list, bool, list]:
    """(segments, flash, zoom_at) an export renders a clip from: its edit's, else its job's."""
    edit = edit or edit_of(clip)
    return (edit.segments(), False, []) if edit is not None else rendered_cut(clip)


def planned(clip: Clip, edit: ClipEditDoc | None = None) -> float:
    """The seconds an export of this clip renders: what it is priced on."""
    return planned_seconds(clip_cut(clip, edit)[0])


def export_items(db: Session, clip_ids: list[str], storage, work: Path, edits: dict | None = None) -> list[ExportItem]:
    """What the worker renders for an export job: one ExportItem per clip, in the order asked for. `edits` holds
    each clip's edit as it was when the export was asked for (what it was priced on); a clip missing from it
    renders its saved edit."""
    items = []
    for clip_id in clip_ids:
        clip = db.get(Clip, clip_id)
        if clip is None or clip.deleted_at is not None:
            continue                    # deleted after the export was asked for: not rendered, not charged
        if edits is not None and clip_id in edits:
            edit = ClipEditDoc.model_validate(edits[clip_id]) if edits[clip_id] else None
        else:
            edit = edit_of(clip)
        segments, flash, zooms = clip_cut(clip, edit)
        words = None
        if edit is not None and (edit.caption_lines or edit.words is not None):
            words = remap_words(edit.caption_words(), segments)
        elif clip.captions_key and storage.exists(clip.captions_key):
            storage.fetch(clip.captions_key, work / f"{clip.id}.captions.json")
            saved = json.loads((work / f"{clip.id}.captions.json").read_text()).get("words") or []
            words = [(w["start"], w["end"], w["text"]) for w in saved]
            if edit is not None:        # timed for the job's cut: moved onto the edit's
                old, old_flash, _z = rendered_cut(clip)
                words = remap_words(source_words(words, old, old_flash), segments)
        hook = (clip.meta or {}).get("hook")
        if edit is not None and edit.hook_text:
            hook = edit.hook_text
        items.append(ExportItem(clip_id=clip.id, start=clip.start_sec, end=clip.end_sec, segments=segments,
                                flash=flash, zoom_at=zooms, words=words, hook=hook))
    return items


def finish_export(db: Session, job: Job, done: list[tuple[str, str, str]], resolution: str) -> list[str]:
    """Inside the export job's success transaction: each clip's `export_key` becomes its new render and an
    Export row records it. `done` is (export_id, clip_id, storage_key). Returns the storage keys of the renders
    these replace, for the caller to delete once the transaction is committed."""
    new_keys = {key for _e, _c, key in done}
    replaced = []
    for export_id, clip_id, key in done:
        clip = db.get(Clip, clip_id)
        if clip is None:
            continue
        for old in db.execute(select(Export).where(Export.clip_id == clip_id, Export.storage_key.is_not(None))).scalars():
            replaced.append(old.storage_key)
            old.storage_key = None      # the file is deleted once this commits; the row stays as history
        if clip.export_key:
            replaced.append(clip.export_key)
        clip.export_key, clip.export_res = key, resolution
        edits = (job.options or {}).get("edits") or {}
        db.add(Export(id=export_id, clip_id=clip_id, account_id=job.account_id, resolution=resolution,
                      options=export_spec(job.options or {}, edits.get(clip_id, clip.edit)),
                      status="SUCCEEDED", storage_key=key))
    return list(dict.fromkeys(k for k in replaced if k not in new_keys))


def new_export_id() -> str:
    return new_id("exp")
