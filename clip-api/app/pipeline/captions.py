"""Burned-in captions (ASS). The word-highlight styles are ported from test-tools/auto_clip.py; `impact` is the
default: one or two big words at a time in our own heavy font, the keyword in the accent colour."""
import re
from dataclasses import dataclass
from pathlib import Path

# hl = highlight colour of the word being spoken (ASS &HBBGGRR&), scale = size of that word in percent,
# words / chars = the most words and characters on one caption line. `impact` is drawn by its own code below
# (build_impact): its keyword colour is the accent, and its lines are measured, not counted in characters.
CAPTION_STYLES = {
    "impact": {"hl": "&H3CFFB8&", "scale": 100, "upper": True, "box": False, "size": 1.0,  "words": 2, "chars": 12},
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


HOOK_SECONDS = 2.5    # how long the on-screen hook stays up at the start of a clip
HOOK_TEXT, HOOK_BOX = "&H00050D0A", "&H003CFFB8"     # near-black on the brand lime (ASS colours are BGR)


STYLE_FORMAT = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
                "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
                "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
EVENT_FORMAT = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

# ---------- impact ----------
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"     # the fonts we ship; render.py hands them to the renderer
IMPACT_FONT = "Anton"            # app/fonts/Anton-Regular.ttf: SIL Open Font License 1.1 (app/fonts/Anton-OFL.txt)
IMPACT_FILE = "Anton-Regular.ttf"
# Anton's own measurements, in em, read from the font file (tests/test_impact_captions.py checks them against
# it). An ASS font size is the height of the font's line (ascent + descent), not the em.
ANTON_ASCENT, ANTON_DESCENT, ANTON_CAP = 2876 / 2048, 674 / 2048, 1760 / 2048
ANTON_WIDTHS = {
    " ": 0.234, "!": 0.229, '"': 0.429, "#": 0.546, "$": 0.462, "%": 1.057, "&": 0.52, "'": 0.214, "(": 0.291,
    ")": 0.291, "*": 0.452, "+": 0.355, ",": 0.236, "-": 0.311, ".": 0.229, "/": 0.405, "0": 0.494, "1": 0.331,
    "2": 0.494, "3": 0.494, "4": 0.494, "5": 0.494, "6": 0.494, "7": 0.494, "8": 0.494, "9": 0.494, ":": 0.242,
    ";": 0.245, "<": 0.321, "=": 0.311, ">": 0.321, "?": 0.492, "@": 0.864, "A": 0.485, "B": 0.479, "C": 0.474,
    "D": 0.493, "E": 0.412, "F": 0.399, "G": 0.485, "H": 0.499, "I": 0.227, "J": 0.466, "K": 0.472, "L": 0.397,
    "M": 0.746, "N": 0.498, "O": 0.486, "P": 0.472, "Q": 0.494, "R": 0.477, "S": 0.461, "T": 0.396, "U": 0.474,
    "V": 0.469, "W": 0.712, "X": 0.484, "Y": 0.446, "Z": 0.41, "[": 0.318, "\\": 0.405, "]": 0.318, "^": 0.474,
    "_": 0.365, "`": 0.317, "{": 0.34, "|": 0.216, "}": 0.34, "~": 0.493}
ANTON_OTHER = 0.5                # a character not in the table (an accented capital is as wide as its letter)

IMPACT_CAP = 0.06                # the capitals' height, as a share of the frame height
IMPACT_OUTLINE = 0.08            # the dark outline, as a share of the font's em
IMPACT_SPACING = 0.03            # extra room between letters (em): the outlines of a heavy face would touch without it
IMPACT_FILL = 0.92               # the widest a caption gets, as a share of the width it is centred in
IMPACT_SHORT = 12                # three words share a caption only when they have this many characters between them
IMPACT_POP = (0.88, 90)          # each caption grows from this share of its size, over this many milliseconds
WORD_GAP = "  "                  # two spaces: the outline eats most of one
ACCENT = "#B8FF3C"               # the brand lime, the colour of the hook box
LOWER_THIRD = 0.70               # where the caption sits when the caller names no row
# Words that are never the keyword. Kept short on purpose: the keyword is the longest word left over.
STOP_WORDS = frozenset("""
a an the and or but so if then than that this these those there here
i me my mine myself we us our ours you your yours yourself he him his she her hers it its they them their theirs
i'm i've i'd i'll you're you've you'd you'll he's she's it's we're we've we'd we'll they're they've they'd they'll
that's there's here's what's who's let's im ive youre thats theres whats lets
is am are was were be been being do does did doing done have has had having
will would can could shall should may might must
don't doesn't didn't can't couldn't won't wouldn't shouldn't isn't aren't wasn't weren't haven't hasn't hadn't ain't
dont doesnt didnt cant couldnt wont wouldnt shouldnt isnt arent wasnt werent havent hasnt hadnt aint
not no nor yes yeah yep nope ok okay oh ah uh um hmm hey hi well
to of in on at by for with from into onto out up down off over under about as
just like really very too also only even still again now
get got gonna gotta wanna go going
what who whom which when where why how
all any some each both more most much many
""".split())
_TRIM = ".,;:…\"“”‘’()[]-–—"     # punctuation dropped from the ends of a word; ! and ? stay


@dataclass(frozen=True)
class ImpactSize:
    """The impact style's measurements for one frame height, in the frame's own pixels."""
    size: int                    # the ASS font size (the height of the font's line)
    em: float
    cap: float                   # the height of a capital letter
    outline: int
    shadow: int                  # how far the soft shadow drops
    blur: int
    half: float                  # from the middle of the capitals to the outer edge of the outline


def impact_size(play_h: int) -> ImpactSize:
    cap = IMPACT_CAP * play_h
    em = cap / ANTON_CAP
    outline = max(2, round(IMPACT_OUTLINE * em))
    return ImpactSize(size=round(em * (ANTON_ASCENT + ANTON_DESCENT)), em=em, cap=cap, outline=outline,
                      shadow=max(2, round(0.045 * em)), blur=max(2, round(0.05 * em)), half=cap / 2 + outline)


def impact_text(word: str) -> str:
    """A word as the impact style shows it: upper case, no control characters, no punctuation at its ends."""
    return _clean(word, True).strip().strip(_TRIM).strip()


def impact_width(texts: list[str], em: float) -> float:
    """How wide these words are on one line at full size, outline included, in pixels."""
    line = WORD_GAP.join(texts)
    letters = sum(ANTON_WIDTHS.get(ch, ANTON_OTHER) for ch in line) + IMPACT_SPACING * max(0, len(line) - 1)
    return letters * em + 2 * max(2, round(IMPACT_OUTLINE * em))


def keyword(texts: list[str]) -> int | None:
    """Which word of a caption is the keyword: the longest one that is not a stop word (the first of equals)."""
    best, length = None, 0
    for i, text in enumerate(texts):
        bare = re.sub(r"[^a-z0-9']", "", text.lower().replace("’", "'")).strip("'")
        if bare and bare not in STOP_WORDS and len(bare) > length:
            best, length = i, len(bare)
    return best


def group_impact(words, fits=lambda texts: True) -> list[list]:
    """(start, end, text) words as impact captions: one or two words, a third only when the three are short
    (IMPACT_SHORT characters between them). A caption also ends at a pause, after punctuation, and before a
    word that would not fit on the line (`fits(texts)`)."""
    chunks, cur = [], []
    for w in words:
        if cur:
            prev = cur[-1]
            hard = w[0] - prev[1] >= PAUSE or prev[2].strip()[-1:] in PUNCT
            texts = [impact_text(t) for _, _, t in cur] + [impact_text(w[2])]
            room = len(cur) < 2 or (len(cur) == 2 and sum(len(t) for t in texts) <= IMPACT_SHORT)
            if hard or not room or not fits(texts):
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def ass_colour(colour: str) -> str:
    """#RRGGBB as an ASS colour (&HBBGGRR&)."""
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour or ""):
        raise ValueError("caption_accent must be a colour like #B8FF3C")
    return f"&H{colour[5:7]}{colour[3:5]}{colour[1:3]}&".upper()


def _hook_style(font: str, size: int, left: int, right: int, hook_top: int, k: float = 1.0) -> str:
    return (f"Style: Hook,{font},{int(size * 0.9)},{HOOK_TEXT},{HOOK_TEXT},{HOOK_BOX},{HOOK_BOX},1,0,0,0,"
            f"100,100,0,0,3,{round(14 * k)},0,8,{round(90 * k) + left},{round(90 * k) + right},{hook_top},1\n")


def build_impact(words, path: Path, vertical: bool, font: str, play: tuple[int, int], hook: str | None, hook_top: int,
                 span: tuple[float, float], center: int | None, accent: str | None) -> int:
    """The impact style: see build_ass. One event pair per caption: a soft shadow, and the words over it."""
    play_w, play_h = play
    m = impact_size(play_h)
    room = (span[1] - span[0]) * play_w * IMPACT_FILL
    x = round((span[0] + span[1]) / 2 * play_w)
    y = round(LOWER_THIRD * play_h) if center is None else center
    k = 1.0 if vertical else play_h / 1080             # the hook is sized for the 1080 canvas; a source frame may not be one
    spacing = round(IMPACT_SPACING * m.em, 1)
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {play_w}\nPlayResY: {play_h}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n" + STYLE_FORMAT +
        f"Style: Cap,{IMPACT_FONT},{m.size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,"
        f"100,100,{spacing},0,1,{m.outline},0,5,0,0,0,1\n"
        # The same letters with nothing visible but their shadow, blurred: a soft shadow under a crisp outline.
        f"Style: CapShadow,{IMPACT_FONT},{m.size},&HFF000000,&HFF000000,&HFF000000,&H50000000,0,0,0,0,"
        f"100,100,{spacing},0,1,{m.outline},{m.shadow},5,0,0,0,1\n"
        + _hook_style(font, round((78 if vertical and play_h >= play_w else 64) * k), int(span[0] * play_w),
                      int((1 - span[1]) * play_w), hook_top, k)
        + "\n[Events]\n" + EVENT_FORMAT)
    shown = [w for w in words if impact_text(w[2])]
    chunks = group_impact(shown, lambda texts: impact_width(texts, m.em) <= room)
    on, off = "{\\c" + ass_colour(accent or ACCENT) + "}", "{\\c&HFFFFFF&}"
    lines = []
    if hook:
        lines.append(f"Dialogue: 2,{ass_time(0)},{ass_time(HOOK_SECONDS)},Hook,,0,0,0,,{{\\fad(120,220)}}{_clean(hook, True)}")
    for ci, chunk in enumerate(chunks):
        start, end = chunk[0][0], chunk[-1][1]
        if ci + 1 < len(chunks):
            end = min(end + 0.3, chunks[ci + 1][0][0])
        texts = [impact_text(t) for _, _, t in chunk]
        # A word too long for the line at full size is drawn smaller, never wrapped and never off the frame.
        pct = min(100, int(100 * (room - 2 * m.outline) / max(1.0, impact_width(texts, m.em) - 2 * m.outline)))
        # \an5 hangs the line by the middle of the font's whole line; the capitals sit a little under that.
        row = y - (ANTON_ASCENT - ANTON_DESCENT - ANTON_CAP) / 2 * m.em * pct / 100
        small, ms = round(pct * IMPACT_POP[0]), IMPACT_POP[1]
        place = (f"\\pos({x},{row:.0f})\\q2\\fscx{small}\\fscy{small}\\t(0,{ms},\\fscx{pct}\\fscy{pct})")
        key = keyword(texts)
        text = WORD_GAP.join(on + t + off if i == key else t for i, t in enumerate(texts))
        when = f"{ass_time(start)},{ass_time(max(end, start + 0.05))}"
        lines.append(f"Dialogue: 0,{when},CapShadow,,0,0,0,,{{{place}\\blur{m.blur}}}{WORD_GAP.join(texts)}")
        lines.append(f"Dialogue: 1,{when},Cap,,0,0,0,,{{{place}}}{text}")
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return len(chunks)


def build_ass(words, path: Path, vertical: bool, caption_top: int, font: str, style: str = "pop",
              play: tuple[int, int] = (1080, 1920), hook: str | None = None, hook_top: int = 0,
              span: tuple[float, float] = (0.0, 1.0), *, center: int | None = None, accent: str | None = None) -> int:
    """A few words at a time. Returns the number of captions.
    `hook` is one line of text shown in a box for the first HOOK_SECONDS, `hook_top` pixels from the top.
    `span` is the part of the frame's width (fractions, left and right) the text is centred in: the gameplay
    panel when a camera panel sits beside it.

    The word-highlight styles (pop, bold, neon, boxed, clean) show up to five words with the one being said
    highlighted, `caption_top` pixels from the top, in `font`.

    `impact` shows one or two words (a third when all three are short) in upper case in the bundled heavy font,
    with a dark outline and a soft shadow, the keyword in `accent` (#RRGGBB; the brand lime when None). `center`
    is the row of the middle of the capitals, in `play` pixels (the lower third when None); `caption_top` is not
    used. `play` is the frame the numbers are for, reframed or not. A word too wide for the line is drawn smaller."""
    if style == "impact":
        return build_impact(words, path, vertical, font, play, hook, hook_top, span, center, accent)
    st = CAPTION_STYLES.get(style, CAPTION_STYLES["pop"])
    if vertical:
        play_w, play_h = play
        size = int((78 if play_h >= play_w else 64) * st["size"])
        margin_v = max(80, play_h - caption_top - size - 20)
    else:
        play_w, play_h, size, margin_v = 1920, 1080, int(64 * st["size"]), 70
    left, right = int(span[0] * play_w), int((1 - span[1]) * play_w)
    border = "3,10,0" if st["box"] else "1,6,2"   # BorderStyle, Outline, Shadow
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {play_w}\nPlayResY: {play_h}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,"
        f"100,100,1,0,{border},2,{60 + left},{60 + right},{margin_v},1\n"
        f"Style: Hook,{font},{int(size * 0.9)},{HOOK_TEXT},{HOOK_TEXT},{HOOK_BOX},{HOOK_BOX},1,0,0,0,"
        f"100,100,0,0,3,14,0,8,{90 + left},{90 + right},{hook_top},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    chunks = group_words(words, st["words"], st["chars"])
    on = ""
    if st["hl"]:
        on = "{\\c" + st["hl"] + (f"\\fscx{st['scale']}\\fscy{st['scale']}" if st["scale"] != 100 else "") + "}"
    off = "{\\c&HFFFFFF&\\fscx100\\fscy100}" if st["hl"] else ""
    lines = []
    if hook:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(HOOK_SECONDS)},Hook,,0,0,0,,{{\\fad(120,220)}}{_clean(hook, True)}")
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
