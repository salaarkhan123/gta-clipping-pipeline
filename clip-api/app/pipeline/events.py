"""Gameplay events read off the screen: the banners games put up when something happens ("WON", "ACE", "VICTORY
ROYALE", "WASTED", "MISSION PASSED"), and the screens that say nothing is happening (a shop, a settings menu, a
lobby). They ride on the shared frame pass (frames.py): each key frame is scored for banner-like text in the two
places games put it (the top band and the middle band), and only the strongest few are read with OCR.

OCR is the local `tesseract` program (free, no network). Without it there are no game events and nothing else
changes. Words found are matched against the tables below, per game and shared; an unknown word is ignored, so a
misread never invents an event.
"""
import difflib
import io
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field

import numpy as np

from .ff import Deadline

log = logging.getLogger("clipapi.events")

# Where banners sit, as (y0, y1, x0, x1) fractions of the frame.
BANDS = {"top": (0.02, 0.32, 0.25, 0.75), "mid": (0.35, 0.65, 0.20, 0.80)}
MAX_READS = 80                  # key frames read per video, strongest banners first
MIN_SCORE = 4.0                 # a key frame's banner score must stand this far above the video's own (robust z)
OCR_TIMEOUT = 10.0              # seconds for one read

# Phrase -> (kind, games). Kinds: "event" (something worth clipping just happened), "round" (a phase marker: not a
# highlight, but where a round starts or ends), "menu" (nothing is being played). Games are templates.GAMES keys
# (GTA 6 and GTA Online fold into gta5; Forza is "other"); "*" is any game. When the game is not known, only
# phrases of 6 letters or more count: a short word ("won", "ace", "1st") in OCR noise is too easy to read wrongly.
PHRASES: dict[str, tuple[str, tuple[str, ...]]] = {
    # Valorant
    "won": ("event", ("valorant",)), "flawless": ("event", ("valorant",)), "ace": ("event", ("valorant",)),
    "clutch": ("event", ("valorant",)), "thrifty": ("event", ("valorant",)), "team ace": ("event", ("valorant",)),
    "victory": ("event", ("*",)), "defeat": ("event", ("*",)), "lost": ("event", ("valorant",)),
    "buy phase": ("round", ("valorant",)), "last round before swap": ("round", ("valorant",)),
    "match point": ("round", ("valorant",)), "switching sides": ("round", ("valorant",)),
    "overtime": ("round", ("valorant",)),
    # Fortnite
    "victory royale": ("event", ("fortnite",)), "eliminated": ("event", ("fortnite", "*")),
    "eliminated by": ("event", ("fortnite",)), "knocked": ("event", ("fortnite",)), "squad wiped": ("event", ("fortnite",)),
    "item shop": ("menu", ("fortnite",)), "use code": ("menu", ("fortnite",)), "locker": ("menu", ("fortnite",)),
    "battle pass": ("menu", ("fortnite",)), "quests": ("menu", ("fortnite",)),
    # GTA
    "wasted": ("event", ("gta5",)), "busted": ("event", ("gta5",)),
    "mission passed": ("event", ("gta5",)), "mission failed": ("event", ("gta5",)),
    "heist passed": ("event", ("gta5",)), "winner": ("event", ("*",)),
    "loading": ("menu", ("*",)), "settings": ("menu", ("*",)), "paused": ("menu", ("*",)),
    # Forza
    "1st": ("event", ("other",)), "finish": ("event", ("other",)), "wrecked": ("event", ("other",)),
}
MATCH = 0.86                    # difflib ratio a read word group must reach against a phrase


@dataclass
class Banner:
    t: float                     # source second of the key frame
    kind: str                    # event | round | menu
    phrase: str                  # the table phrase it matched
    text: str                    # what OCR read, cleaned
    band: str                    # top | mid


@dataclass
class BannerReader:
    """Collects the banner score of every key frame during the frame pass (`on_frame`), keeps a copy of the
    strongest bands, and reads them afterwards (`read`)."""
    max_reads: int = MAX_READS
    scores: list = field(default_factory=list)          # (t, score, band name)
    crops: dict = field(default_factory=dict)           # t -> (score, band name, ink mask)

    def on_frame(self, t: float, rgb: np.ndarray) -> None:
        best, best_band, best_img = 0.0, "top", None
        h, w = rgb.shape[:2]
        for name, (y0, y1, x0, x1) in BANDS.items():
            band = rgb[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
            ink = text_ink(band)
            score = float(np.abs(np.diff(ink.astype(np.int8), axis=1)).mean())       # light-dark changes: letters
            if score > best:
                best, best_band, best_img = score, name, ink
        self.scores.append((t, best, best_band))
        if best_img is not None:
            self.crops[t] = (best, best_band, best_img)
            if len(self.crops) > 4 * self.max_reads:      # keep memory bounded: drop the weakest kept bands
                keep = sorted(self.crops, key=lambda k: -self.crops[k][0])[: 2 * self.max_reads]
                self.crops = {k: self.crops[k] for k in keep}

    def chosen(self) -> list[float]:
        """The key frames worth reading: banner score MIN_SCORE robust z above the video's own, strongest first."""
        if len(self.scores) < 5:
            return []
        s = np.array([x[1] for x in self.scores])
        med = float(np.median(s))
        mad = max(float(np.median(np.abs(s - med))) * 1.4826, 1e-3)
        picked = [(t, (sc - med) / mad) for t, sc, _b in self.scores if (sc - med) / mad >= MIN_SCORE and t in self.crops]
        return [t for t, _z in sorted(picked, key=lambda x: -x[1])[: self.max_reads]]

    def read(self, deadline: Deadline | None = None, game: str | None = None) -> list[Banner]:
        """OCR the chosen bands and keep what matches a phrase (for `game`, or any game when it is not known)."""
        if shutil.which("tesseract") is None:
            return []
        out = []
        for t in sorted(self.chosen()):
            if deadline is not None:
                deadline.remaining()
            _score, band, img = self.crops[t]
            text = ocr(img)
            hit = match(text, game)
            if hit is not None:
                out.append(Banner(t=t, kind=hit[1], phrase=hit[0], text=text, band=band))
        return out


def text_ink(band: np.ndarray) -> np.ndarray:
    """Where banner letters are: bright, nearly colourless or strongly lit pixels (white, yellow and red banner
    text all pass), as a boolean mask."""
    mx, mn = band.max(axis=2).astype(np.int16), band.min(axis=2).astype(np.int16)
    return (mn > 200) | ((mx > 235) & (mx - mn > 120))


def ocr(ink: np.ndarray) -> str:
    """Read a binarised band: letters dark on white, scaled up 3 times for tesseract."""
    from PIL import Image
    img = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).resize((ink.shape[1] * 3, ink.shape[0] * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    try:
        res = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "6"], input=buf.getvalue(),
                             capture_output=True, timeout=OCR_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return " ".join(re.findall(r"[a-z0-9#]+", res.stdout.decode("utf-8", "replace").lower()))


def match(text: str, game: str | None = None) -> tuple[str, str] | None:
    """The table phrase `text` contains (as whole words, allowing small misreads), with its kind; None when none
    does. Longer phrases win over shorter ones."""
    words = text.split()
    if not words:
        return None
    for phrase in sorted(PHRASES, key=lambda p: -len(p)):
        kind, games = PHRASES[phrase]
        if game and "*" not in games and game not in games:
            continue
        if not game and len(phrase) < 6:
            continue
        n = len(phrase.split())
        for i in range(len(words) - n + 1):
            group = " ".join(words[i:i + n])
            if group == phrase or (len(phrase) >= 4 and difflib.SequenceMatcher(None, group, phrase).ratio() >= MATCH):
                return phrase, kind
    return None


def available() -> bool:
    return shutil.which("tesseract") is not None


EVENT_LEAD = 15.0               # seconds before a result banner that it is about (the round, the fight, the crash)
EVENT_TAIL = 2.0                # ... and after it


def game_of(template: str | None) -> str | None:
    """The game a built-in template is for (templates.GAMES), or None."""
    if not template:
        return None
    try:
        from ..templates import TEMPLATES          # data only; no web or database code is reached
    except ImportError:
        return None
    game = (TEMPLATES.get(template) or {}).get("game")
    return game if game and game != "other" else None


def event_seconds(banners: list[Banner], kind: str, base: int, n: int, lead: float, tail: float) -> np.ndarray:
    """1 for every second within [t - lead, t + tail] of a banner of `kind` (second i = source second base + i)."""
    out = np.zeros(n)
    for b in banners:
        if b.kind == kind:
            out[max(0, int(b.t - lead) - base):max(0, int(b.t + tail) - base + 1)] = 1.0
    return out
