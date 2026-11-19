"""Caption fonts: the open-licence families we ship, an account's own uploaded fonts, and the measurements the
caption code needs from a font file (read from the file itself, never assumed).

A font file is read here only to measure it and to check that it is one: TrueType or OpenType, with the tables a
renderer needs, inside a size limit. No file, network or database code beyond reading the given path.
"""
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
MAX_FONT_BYTES = 5 * 1024 * 1024        # an uploaded font file may be at most this big
SFNT_TAGS = (b"\x00\x01\x00\x00", b"OTTO", b"true")     # TrueType, OpenType (CFF), old Apple TrueType
NEEDED = ("head", "hhea", "hmtx", "cmap", "name", "OS/2")
WEIGHTS = {"regular": 400, "bold": 700, "black": 900}

# The families we ship (all SIL Open Font License 1.1, Luckiest Guy Apache 2.0; licence files beside them).
# Each weight and slant maps to the file that has it; a family without a bold or italic file is drawn with the
# nearest one it has (the renderer then slants or emboldens it).
FAMILIES = {
    "anton": {"name": "Anton", "files": {("regular", False): "Anton-Regular.ttf"}},
    "bebas": {"name": "Bebas Neue", "files": {("regular", False): "BebasNeue-Regular.ttf"}},
    "bangers": {"name": "Bangers", "files": {("regular", False): "Bangers-Regular.ttf"}},
    "luckiest": {"name": "Luckiest Guy", "files": {("regular", False): "LuckiestGuy-Regular.ttf"}},
    "poppins": {"name": "Poppins", "files": {
        ("regular", False): "Poppins-Regular.ttf", ("bold", False): "Poppins-Bold.ttf",
        ("black", False): "Poppins-Black.ttf", ("regular", True): "Poppins-Italic.ttf",
        ("bold", True): "Poppins-BoldItalic.ttf", ("black", True): "Poppins-BlackItalic.ttf"}},
}
DEFAULT_FAMILY = "anton"


class BadFont(ValueError):
    """Not a font file this renderer can use; the message says why, for the person who uploaded it."""


@dataclass(frozen=True)
class Face:
    """One font file as the caption code uses it. Measurements are shares of the em."""
    family: str            # the name a renderer finds it by
    file: Path
    ascent: float          # OS/2 winAscent: an ASS font size is the height ascent + descent, not the em
    descent: float
    cap: float             # the capitals' height
    weight: int            # 400 regular, 700 bold, 900 black
    italic: bool


def _tables(data: bytes) -> dict[str, bytes]:
    if len(data) < 12 or data[:4] not in SFNT_TAGS:
        raise BadFont("This is not a TrueType or OpenType font file (.ttf or .otf).")
    count = struct.unpack(">H", data[4:6])[0]
    if not 1 <= count <= 100 or 12 + 16 * count > len(data):
        raise BadFont("The font file is damaged.")
    tables = {}
    for i in range(count):
        tag, _sum, off, length = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        if off + length > len(data):
            raise BadFont("The font file is damaged.")
        tables[tag.decode("latin-1")] = data[off:off + length]
    missing = [t for t in NEEDED if t not in tables]
    if missing:
        raise BadFont(f"The font file has no {missing[0]} table, so it cannot be drawn.")
    return tables


def _family(name: bytes) -> str | None:
    count, strings = struct.unpack(">HH", name[2:6])
    found = {}
    for i in range(count):
        pid, _eid, _lid, nid, length, off = struct.unpack(">HHHHHH", name[6 + 12 * i:18 + 12 * i])
        raw = name[strings + off:strings + off + length]
        if nid in (1, 16) and pid in (0, 3):
            found.setdefault(nid, raw.decode("utf-16-be", "replace"))
        elif nid in (1, 16) and pid == 1:
            found.setdefault(nid, raw.decode("latin-1"))
    return found.get(16) or found.get(1)


@lru_cache(maxsize=64)
def read_face(path: Path) -> Face:
    """The measurements of a font file. Raises BadFont when it is not a usable TrueType/OpenType font."""
    path = Path(path)
    if path.stat().st_size > MAX_FONT_BYTES:
        raise BadFont(f"A font file may be at most {MAX_FONT_BYTES // (1024 * 1024)} MB.")
    tables = _tables(path.read_bytes())
    head, os2 = tables["head"], tables["OS/2"]
    if len(head) < 54 or len(os2) < 78:
        raise BadFont("The font file is damaged.")
    upm = struct.unpack(">H", head[18:20])[0]
    if not 16 <= upm <= 16384:
        raise BadFont("The font file is damaged.")
    weight = struct.unpack(">H", os2[4:6])[0]
    fs_selection = struct.unpack(">H", os2[62:64])[0]
    win_ascent, win_descent = struct.unpack(">HH", os2[74:78])
    cap = struct.unpack(">h", os2[88:90])[0] if len(os2) >= 90 else 0
    family = _family(tables["name"])
    if not family or not win_ascent:
        raise BadFont("The font file has no name or no measurements, so it cannot be drawn.")
    return Face(family=family.strip(), file=path, ascent=win_ascent / upm, descent=win_descent / upm,
                cap=(cap or 0.7 * upm) / upm, weight=weight or 400, italic=bool(fs_selection & 1))


@lru_cache(maxsize=64)
def _pil(path: Path):
    from PIL import ImageFont
    return ImageFont.truetype(str(path), 1000)


def text_width(face: Face, text: str) -> float:
    """How wide `text` is at an em of 1 (multiply by the em in pixels), by the font's own advances."""
    try:
        return _pil(face.file).getlength(text) / 1000
    except Exception:                          # a font PIL cannot shape: half an em a letter
        return 0.5 * len(text)


def bundled(family: str = DEFAULT_FAMILY, weight: str = "regular", italic: bool = False) -> Face:
    """A family we ship, in the file nearest the weight and slant asked for."""
    files = FAMILIES[family]["files"]
    order = [(weight, italic), (weight, False), ("regular", italic), ("regular", False)]
    order += [k for k in files if k[1] == italic] + list(files)
    name = next(files[k] for k in order if k in files)
    return read_face(FONT_DIR / name)
