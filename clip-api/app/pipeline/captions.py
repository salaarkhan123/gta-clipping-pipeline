"""Burned-in word-highlight captions (ASS). Ported from test-tools/auto_clip.py, with selectable styles."""
from pathlib import Path

# hl = highlight colour of the word being spoken (ASS &HBBGGRR&), scale = size of that word in percent,
# words / chars = the most words and characters on one caption line.
CAPTION_STYLES = {
    "pop":   {"hl": "&H00FFFF&", "scale": 114, "upper": True,  "box": False, "size": 1.0,  "words": 3, "chars": 18},
    "bold":  {"hl": "&H00FFFF&", "scale": 100, "upper": True,  "box": False, "size": 1.0,  "words": 3, "chars": 18},
    "neon":  {"hl": "&H66FF7A&", "scale": 110, "upper": True,  "box": False, "size": 1.0,  "words": 3, "chars": 18},
    "boxed": {"hl": "&H00FFFF&", "scale": 100, "upper": True,  "box": True,  "size": 0.9,  "words": 3, "chars": 18},
    "clean": {"hl": None,        "scale": 100, "upper": False, "box": False, "size": 0.75, "words": 5, "chars": 30},
}

PAUSE = 0.35          # a gap this long between two words always starts a new line
GLUE = 0.2            # a short word followed this quickly belongs with the next word
SHORT = 3             # "short word": this many letters or fewer (had, get, the, to, a)
PUNCT = ".,!?;:…"


def _bare(text: str) -> str:
    return text.strip().strip(PUNCT + "\"'")


def group_words(words, max_words: int = 3, max_chars: int = 18) -> list[list]:
    """Split (start, end, text) words into caption lines.

    A line ends at a pause (>= PAUSE s), after punctuation, or when it reaches max_words / max_chars. When a
    full line would end on a short word that runs straight into the next one (< GLUE s), that word moves down
    to start the next line instead, as long as the line keeps at least two words.
    """
    chunks, cur = [], []
    for w in words:
        if cur:
            prev = cur[-1]
            hard = w[0] - prev[1] >= PAUSE or prev[2].strip()[-1:] in PUNCT
            length = len(" ".join(t.strip() for _, _, t in cur)) + 1 + len(w[2].strip())
            full = len(cur) >= max_words or length > max_chars
            if hard or full:
                carry = []
                if (not hard and len(cur) >= 3 and len(_bare(prev[2])) <= SHORT and w[0] - prev[1] < GLUE
                        and cur[-2][2].strip()[-1:] not in PUNCT):
                    carry = [cur.pop()]
                chunks.append(cur)
                cur = carry
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def ass_time(t: float) -> str:
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _clean(word: str, upper: bool) -> str:
    # Braces and backslashes are ASS control characters.
    word = word.replace("{", "").replace("}", "").replace("\\", "").replace("\n", " ")
    return word.upper() if upper else word


def build_ass(words, path: Path, vertical: bool, caption_top: int, font: str, style: str = "pop",
              play: tuple[int, int] = (1080, 1920)) -> int:
    """A few words at a time, the word being said highlighted. Returns the number of chunks."""
    st = CAPTION_STYLES.get(style, CAPTION_STYLES["pop"])
    if vertical:
        play_w, play_h = play
        size = int((78 if play_h >= play_w else 64) * st["size"])
        margin_v = max(80, play_h - caption_top - size - 20)
    else:
        play_w, play_h, size, margin_v = 1920, 1080, int(64 * st["size"]), 70
    border = "3,10,0" if st["box"] else "1,6,2"   # BorderStyle, Outline, Shadow
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {play_w}\nPlayResY: {play_h}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,"
        f"100,100,1,0,{border},2,60,60,{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    chunks = group_words(words, st["words"], st["chars"])
    on = ""
    if st["hl"]:
        on = "{\\c" + st["hl"] + (f"\\fscx{st['scale']}\\fscy{st['scale']}" if st["scale"] != 100 else "") + "}"
    off = "{\\c&HFFFFFF&\\fscx100\\fscy100}" if st["hl"] else ""
    lines = []
    for ci, chunk in enumerate(chunks):
        chunk_end = chunk[-1][1]
        if ci + 1 < len(chunks):
            chunk_end = min(chunk_end + 0.3, chunks[ci + 1][0][0])
        if not st["hl"]:   # no per-word highlight: one event per chunk
            text = " ".join(_clean(t, st["upper"]) for _, _, t in chunk)
            lines.append(f"Dialogue: 0,{ass_time(chunk[0][0])},{ass_time(max(chunk_end, chunk[0][0] + 0.05))},Cap,,0,0,0,,{text}")
            continue
        for wi, (s, _e, _) in enumerate(chunk):
            end = chunk[wi + 1][0] if wi + 1 < len(chunk) else chunk_end
            text = " ".join((on + _clean(t, st["upper"]) + off) if j == wi else _clean(t, st["upper"])
                            for j, (_, _, t) in enumerate(chunk))
            lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(max(end, s + 0.05))},Cap,,0,0,0,,{text}")
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return len(chunks)
