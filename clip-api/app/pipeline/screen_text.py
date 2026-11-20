"""HUD / kill-feed OCR (#202): read on-screen text inside measured HUD regions only.

Observation mode. `hud_killfeed` and `hud_banner` sit in pipeline.WEIGHTS at 0, so the ranking path does not
compute this detector (timeline.py: a weight of 0 costs nothing). `read_hud` is the optional path for logging
and the exact-match eval sheet (`eval/labels-hud-ocr.csv`). Ranking stays off until that sheet reports 0.9.

Backend: PaddleOCR mobile PP-OCRv4 is the intended swap (code and weights Apache-2.0). The default is a stub
that returns no text. CI never constructs PaddleOCR and never downloads model weights. Set HUD_OCR_BACKEND=paddle
only on a machine that already has the wheel and the files; this module will not fetch them.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .ff import SAFE_IN, Deadline, PipelineTimeout
from .layouts import Rect, hud_regions

HUD_SIGNALS = ("hud_killfeed", "hud_banner")
# Kinds we OCR. Other HUD boxes (minimap, speedometer) are caption-avoidance only (#201).
OCR_KINDS = ("killfeed", "banner")
# Closed lexicon for the banner region. A hit is the whole line after a case fold, not a substring.
BANNER_LEXICON = frozenset({
    "wasted", "busted", "winner", "victory", "defeat", "eliminated",
    "mission passed", "mission failed",
})
SAMPLE_STEP = 4.0           # seconds between frames; slower than 1 Hz so a long VOD stays cheap
LICENSE = "Apache-2.0"      # PaddleOCR code and PP-OCRv4 mobile weights


@dataclass(frozen=True)
class TextEvent:
    text: str
    region: str
    t: float

    def as_dict(self) -> dict:
        return {"text": self.text, "region": self.region, "t": round(self.t, 3)}


class OcrBackend(Protocol):
    """Read text from one HUD crop. CPU only; CI uses StubBackend."""

    requires_gpu: bool

    def read(self, image: np.ndarray) -> list[tuple[str, float]]:
        """Lines of (text, confidence) from a cropped HUD image."""


class StubBackend:
    """No-op stand-in so tests and CI never download PP-OCRv4 weights or need a GPU."""

    requires_gpu = False
    license = LICENSE

    def read(self, image: np.ndarray) -> list[tuple[str, float]]:
        return []


class PaddleBackend:
    """PP-OCRv4 mobile via PaddleOCR. Apache-2.0. Not constructed in CI.

    Instantiating this imports paddleocr and loads local weights. It never sets a download flag: if the
    files are missing, PaddleOCR's own error stands. Callers that want the stub keep HUD_OCR_BACKEND unset.
    """

    requires_gpu = False
    license = LICENSE

    def __init__(self) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise RuntimeError("paddleocr is not installed; keep HUD_OCR_BACKEND=stub (the CI default)") from e
        # CPU path. Keyword names moved between PaddleOCR releases; never enable GPU. No download kwargs.
        try:
            self._ocr = PaddleOCR(lang="en", use_angle_cls=False, use_gpu=False, show_log=False)
        except TypeError:
            self._ocr = PaddleOCR(lang="en", device="cpu")

    def read(self, image: np.ndarray) -> list[tuple[str, float]]:
        if image.size == 0:
            return []
        bgr = image[:, :, ::-1] if image.ndim == 3 and image.shape[2] == 3 else image
        raw = self._ocr.ocr(bgr, cls=False)
        lines: list[tuple[str, float]] = []
        for page in raw or []:
            for item in page or []:
                if not item or len(item) < 2:
                    continue
                rec = item[1]
                if not rec:
                    continue
                text, conf = rec[0], float(rec[1] if len(rec) > 1 else 0.0)
                if text:
                    lines.append((str(text), conf))
        return lines


def default_backend() -> OcrBackend:
    """Stub unless HUD_OCR_BACKEND=paddle. CI leaves the env unset, so no GPU and no weight download."""
    name = (os.environ.get("HUD_OCR_BACKEND") or "stub").strip().lower()
    if name in ("paddle", "paddleocr"):
        return PaddleBackend()
    if name not in ("stub",):
        raise ValueError(f"unknown HUD_OCR_BACKEND {name!r}: stub or paddle")
    return StubBackend()


def ocr_regions(game: str | None) -> tuple[tuple[str, Rect], ...]:
    """Measured kill-feed and banner boxes for `game`. Empty when the HUD table has none: never guessed."""
    return tuple((kind, box) for kind, box in hud_regions(game) if kind in OCR_KINDS)


def banner_hit(text: str) -> str | None:
    """The lexicon token the banner line is, after a case fold, or None."""
    folded = " ".join(text.casefold().split())
    return folded if folded in BANNER_LEXICON else None


def sample_times(start: float, end: float, step: float = SAMPLE_STEP) -> list[float]:
    if end <= start or step <= 0:
        return []
    t, out = float(start), []
    while t < end:
        out.append(t)
        t += step
    return out


def series_from_events(events: list[TextEvent], n: int, base: int = 0) -> dict[str, list[float]]:
    """Per-second series for ranking, used only when a HUD weight is above 0.

    hud_killfeed is a change count (the line differed from the previous one). hud_banner is 1 on a lexicon hit.
    """
    kill = [0.0] * n
    banner = [0.0] * n
    prev = ""
    for ev in sorted(events, key=lambda e: e.t):
        i = int(ev.t) - base
        if not 0 <= i < n:
            continue
        if ev.region == "killfeed":
            if ev.text != prev:
                kill[i] += 1.0
                prev = ev.text
        elif ev.region == "banner" and banner_hit(ev.text):
            banner[i] = 1.0
    return {"hud_killfeed": kill, "hud_banner": banner}


def read_hud(path: Path, game: str | None, start: float, end: float, *,
             width: int, height: int, backend: OcrBackend | None = None,
             deadline: Deadline | None = None, step: float = SAMPLE_STEP) -> list[TextEvent]:
    """OCR measured HUD crops at sparse times. An unknown or unmeasured game returns [] and decodes nothing."""
    regions = ocr_regions(game)
    if not regions:
        return []
    backend = backend or default_backend()
    events: list[TextEvent] = []
    for t in sample_times(start, end, step):
        if deadline is not None:
            deadline.remaining()
        for kind, box in regions:
            crop = _crop_at(path, t, box, width, height, deadline)
            if crop is None:
                continue
            for text, _conf in backend.read(crop):
                text = " ".join(text.split())
                if text:
                    events.append(TextEvent(text=text, region=kind, t=t))
    return events


def _crop_at(path: Path, t: float, box: Rect, src_w: int, src_h: int,
             deadline: Deadline | None) -> np.ndarray | None:
    """One HUD crop at source time `t`. Used only after ocr_regions is non-empty."""
    x, y, bw, bh = box
    cw = max(2, int(round(bw * src_w)) // 2 * 2)
    ch = max(2, int(round(bh * src_h)) // 2 * 2)
    cx = min(max(0, int(round(x * src_w))), max(0, src_w - cw))
    cy = min(max(0, int(round(y * src_h))), max(0, src_h - ch))
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-nostdin",
           "-ss", f"{max(t, 0.0):.3f}", *SAFE_IN, "-i", str(path), "-an",
           "-vf", f"crop={cw}:{ch}:{cx}:{cy}", "-frames:v", "1",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    timeout = deadline.remaining(30.0) if deadline else 30.0
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise PipelineTimeout() from None
    need = cw * ch * 3
    if res.returncode != 0 or len(res.stdout) < need:
        return None
    return np.frombuffer(res.stdout[:need], np.uint8).reshape(ch, cw, 3)
