"""Premium AI thumbnails (#140): restyle a clip's thumbnail frame with an image-edit model, then draw the hook text
with our own renderer (app/pipeline/thumbs.py), so the words are always spelled exactly.

`generate` is the whole step, used by the worker (app/thumbnail_jobs.py) and the benchmark
(scripts/premium_thumb_bench.py). It touches no database, storage or credits: it reads a frame from disk and
writes two JPEGs, or raises GenerationFailed with every attempt it made.

Attempts: the primary provider, then one retry on the fallback (the primary again when there is no fallback).
A call fails on a provider error, a timeout, a safety block, an answer without an image, or when the streamer's
face is gone from the output (faces.face_kept).
"""
import logging
import time
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable

from .base import FACE_LOST, PROVIDER_ERROR, EditRequest, ImageEditor, ProviderFailed
from .faces import face_kept, faces, reference_crop
from .prompts import build_prompt

log = logging.getLogger("clipapi.imagegen")
MAX_SHORT_SIDE = 1080          # a premium thumbnail is at most 1080 on its short side
JPEG_QUALITY = 90
ASPECTS = {"9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1.0, "16:9": 16 / 9, "3:4": 3 / 4, "4:3": 4 / 3, "2:3": 2 / 3,
           "3:2": 3 / 2}


@dataclass
class Attempt:
    provider: str
    model: str
    ok: bool
    code: str | None
    message: str | None
    seconds: float
    cost_usd: float | None
    cost_source: str = ""


@dataclass
class Generated:
    clean: Path                # the restyled picture, no text
    image: Path                # with the hook text drawn on it (the clean picture when there is no text)
    text_drawn: bool
    provider: str
    model: str
    attempts: list[Attempt] = field(default_factory=list)
    face_check: str = "no_face_in_frame"      # kept | no_face_in_frame

    def info(self) -> dict:
        return {"provider": self.provider, "model": self.model, "face_check": self.face_check,
                "attempts": [asdict(a) for a in self.attempts],
                "cost_usd": round(sum(a.cost_usd or 0 for a in self.attempts), 6)}


class GenerationFailed(Exception):
    def __init__(self, code: str, message: str, attempts: list[Attempt]):
        super().__init__(message)
        self.code, self.message, self.attempts = code, message, attempts


def aspect_of(size: tuple[int, int]) -> str:
    r = size[0] / size[1]
    return min(ASPECTS, key=lambda a: abs(ASPECTS[a] - r))


def _fit(picture, size: tuple[int, int]):
    """The provider's picture cut to the frame's exact shape (centre crop) at most MAX_SHORT_SIDE on its short side."""
    from PIL import Image
    w, h = size
    short = min(MAX_SHORT_SIDE, max(min(w, h), min(picture.size)))   # the provider's detail, never below the frame
    k = short / min(w, h)
    tw, th = max(2, round(w * k)), max(2, round(h * k))
    pw, ph = picture.size
    scale = max(tw / pw, th / ph)
    resized = picture.convert("RGB").resize((max(tw, round(pw * scale)), max(th, round(ph * scale))), Image.LANCZOS)
    left, top = (resized.size[0] - tw) // 2, (resized.size[1] - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def generate(frame: Path, out_dir: Path, *, look: str, instruction: str | None, text: str | None, canvas,
             accent: str | None, editors: list[ImageEditor], timeout: float,
             between: Callable[[], None] = lambda: None) -> Generated:
    """Restyle `frame` (the clip's thumbnail frame, no text) with `look` and the cleaned `instruction`, then draw
    `text` on it laid out on `canvas` (thumbs.Canvas of the frame). `editors`: [primary, fallback]; the first
    is tried, then one retry on the next (or the same one when it is alone). `between()` runs before each
    attempt and may raise (a cancel). Raises GenerationFailed when no attempt gave a usable picture."""
    from PIL import Image

    from ..pipeline.thumbs import write_thumbnail
    if not editors:
        raise GenerationFailed(PROVIDER_ERROR, "No image provider is configured.", [])
    with Image.open(frame) as im:
        source = im.convert("RGB")
    found = faces(source)
    face = found[0] if found else None
    reference = reference_crop(source, face) if face else None
    frame_jpeg = BytesIO()
    source.save(frame_jpeg, "JPEG", quality=92)
    aspect = aspect_of(source.size)
    order = [editors[0], editors[1] if len(editors) > 1 else editors[0]]
    attempts: list[Attempt] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for editor in order:
        between()
        request = EditRequest(build_prompt(look, instruction, reference is not None), frame_jpeg.getvalue(), aspect,
                              reference)
        t0 = time.monotonic()
        try:
            result = editor.edit(request, timeout)
            try:
                with Image.open(BytesIO(result.image)) as im:
                    im.load()
                    picture = _fit(im, source.size)
            except Exception:
                raise ProviderFailed(PROVIDER_ERROR, "The provider's image could not be opened.", result.cost_usd) from None
            if face is not None and not face_kept(face, picture.resize(source.size)):
                raise ProviderFailed(FACE_LOST, "The streamer's face was lost in the output.", result.cost_usd)
        except ProviderFailed as e:
            attempts.append(Attempt(editor.name, editor.model, False, e.code, e.message[:300],
                                    round(time.monotonic() - t0, 2), e.cost_usd))
            log.warning("premium thumbnail attempt on %s failed: %s %s", editor.name, e.code, e.message[:200])
            continue
        attempts.append(Attempt(editor.name, editor.model, True, None, None, round(time.monotonic() - t0, 2),
                                result.cost_usd, result.cost_source))
        clean, image = out_dir / "premium.clean.jpg", out_dir / "premium.jpg"
        picture.save(clean, "JPEG", quality=JPEG_QUALITY, optimize=True)
        drawn = write_thumbnail(clean, image, text, canvas, accent)
        return Generated(clean, image, drawn, editor.name, editor.model, attempts,
                         "kept" if face is not None else "no_face_in_frame")
    last = attempts[-1]
    raise GenerationFailed(last.code or PROVIDER_ERROR, last.message or "The thumbnail could not be made.", attempts)


def editors_from(settings) -> list[ImageEditor]:
    """[primary, fallback] from the settings: Gemini when GEMINI_API_KEY is set, then BFL when BFL_API_KEY is."""
    from .bfl import BflEditor
    from .gemini import GeminiEditor
    out: list[ImageEditor] = []
    if settings.gemini_api_key:
        out.append(GeminiEditor(settings.gemini_api_key, settings.gemini_image_model, settings.gemini_image_size))
    if settings.bfl_api_key:
        out.append(BflEditor(settings.bfl_api_key))
    return out


def style_look(settings, style: str) -> str | None:
    """The look prompt of a named style from the server's config, or None for an unknown style."""
    return next((s["prompt"] for s in settings.thumb_styles if s.get("id") == style), None)
