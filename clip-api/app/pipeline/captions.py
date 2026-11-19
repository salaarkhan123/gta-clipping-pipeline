"""Burned-in captions (ASS). The word-highlight styles are ported from test-tools/auto_clip.py; `impact` is the
default: one or two big words at a time in our own heavy font, the keyword in the accent colour."""
import re
from dataclasses import dataclass
from pathlib import Path

from .fonts import WEIGHTS, Face, text_width

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
# More styles, drawn by build_styled. `mode`: bounce, the word being said grows in; karaoke, the line fills with
# `hl` as it is said; reveal, the words appear one at a time; still, one line that does not change (`border` is
# BorderStyle, Outline, Shadow; `box` a box of `box_colour` behind it); tag, lower case with a filled box of `hl`
# behind the keyword only.
STYLED = {
    "bounce":   {"hl": "&H00FFFF&", "upper": True,  "size": 1.0,  "words": 3, "chars": 18, "mode": "bounce"},
    "karaoke":  {"hl": "&H3CFFB8&", "upper": True,  "size": 1.0,  "words": 4, "chars": 22, "mode": "karaoke"},
    "reveal":   {"hl": "&H00FFFF&", "upper": True,  "size": 1.0,  "words": 4, "chars": 22, "mode": "reveal"},
    "outline":  {"hl": None,        "upper": True,  "size": 1.0,  "words": 3, "chars": 18, "mode": "still",
                 "border": "1,9,0"},
    "subtitle": {"hl": None,        "upper": False, "size": 0.7,  "words": 8, "chars": 42, "mode": "still",
                 "border": "3,8,0", "box": True, "box_colour": "&H60000000"},
    "tag":      {"hl": "&H3CFFB8&", "upper": False, "size": 0.95, "words": 3, "chars": 18, "mode": "tag"},
}
STYLE_NAMES = (*CAPTION_STYLES, *STYLED)
BOUNCE = (80, 120, 118)     # bounce: the word being said grows from this % of its size, over this many ms, to this %
TAG_PAD = 6                 # tag: pixels of box around the keyword (more covers the next word's first letter)

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
ACTIVE_POP = (0.92, 1.08, 90)    # the word being said grows from this share of the line's size to this one, in ms
UPCOMING = "&H8C&"               # a word not said yet: its letters this transparent (ASS alpha), outline kept
IMPACT_LEAD = 0.7                # a word joins a caption only when it is said this soon after the caption's first
CAPTION_HOLD = 0.3              # a caption stays this long after its last word, unless the next one starts first
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


def impact_size(play_h: int, face: Face | None = None, scale: float = 1.0) -> ImpactSize:
    """`face`: the font (None: the bundled Anton); `scale`: the caption_look size, 1.0 = the style's own."""
    cap = IMPACT_CAP * play_h * scale
    em = cap / (face.cap if face else ANTON_CAP)
    outline = max(2, round(IMPACT_OUTLINE * em))
    line = (face.ascent + face.descent) if face else (ANTON_ASCENT + ANTON_DESCENT)
    return ImpactSize(size=round(em * line), em=em, cap=cap, outline=outline,
                      shadow=max(2, round(0.045 * em)), blur=max(2, round(0.05 * em)), half=cap / 2 + outline)


def impact_text(word: str, upper: bool = True) -> str:
    """A word as the impact style shows it: upper case (or as typed), no control characters, no punctuation at its
    ends."""
    return _clean(word, upper).strip().strip(_TRIM).strip()


def impact_width(texts: list[str], em: float, face: Face | None = None) -> float:
    """How wide these words are on one line at full size, outline included, in pixels."""
    line = WORD_GAP.join(texts)
    if face is None:
        letters = sum(ANTON_WIDTHS.get(ch, ANTON_OTHER) for ch in line)
    else:
        letters = text_width(face, line)
    return (letters + IMPACT_SPACING * max(0, len(line) - 1)) * em + 2 * max(2, round(IMPACT_OUTLINE * em))


def _bare_key(text: str) -> str:
    return re.sub(r"[^a-z0-9']", "", text.lower().replace("’", "'")).strip("'")


# Words a gaming viewer's eye should land on. Every game shares GAME_TERMS; a game adds its own.
NUMBER_WORDS = frozenset("""one two three four five six seven eight nine ten eleven twelve fifteen twenty thirty forty
fifty hundred thousand million first last double triple quad quadra penta""".split())
GAME_TERMS = frozenset("""clutch ace aced headshot headshots snipe sniped sniper noscope kill kills killed knocked
downed eliminated wipe wiped wipeout victory win won lost dead died revive loot crash crashed drift drifted nitro
overtake chase heist cops police wanted busted wasted escape escaped explode exploded explosion boom gg ez nerf
cheater hacker hacks rank ranked boss raid spawn respawn camping camper rage noob bot bots""".split())
GAME_EXTRA = {
    "valorant": frozenset("spike defuse defused plant planted ult operator vandal phantom sheriff flash flashed "
                          "smoke entry retake eco".split()),
    "fortnite": frozenset("storm zone build builds box boxed pump shotgun royale crown edit".split()),
    "gta5": frozenset("stars heist bank robbery getaway lamar franklin trevor michael lester pursuit".split()),
    "cs2": frozenset("bomb defuse planted awp deagle eco retake entry".split()),
    "apex": frozenset("ring squad wipe kraber third".split()),
}


def _is_number(bare: str) -> bool:
    return bool(re.search(r"\d", bare)) or bare in NUMBER_WORDS


def keyword(texts: list[str], names: list[bool] | None = None, game: str | None = None) -> int | None:
    """Which word of a caption is the keyword (at most one): the first number, else the first name (`names[i]`:
    the transcript has it capitalised inside a sentence), else the first game term (GAME_TERMS, plus the game's
    own), else the first word said with an exclamation mark, else the longest word that is not a stop word (the
    first of equals). A stop word or a masked swear (f***) never is."""
    terms = GAME_TERMS | GAME_EXTRA.get(game or "", frozenset())
    bares = [_bare_key(t) for t in texts]
    usable = [i for i, b in enumerate(bares) if b and b not in STOP_WORDS and "*" not in texts[i]]
    for rule in (lambda i: _is_number(bares[i]), lambda i: bool(names and names[i]),
                 lambda i: bares[i] in terms, lambda i: texts[i].rstrip().endswith("!")):
        hit = next((i for i in usable if rule(i)), None)
        if hit is not None:
            return hit
    return max(usable, key=lambda i: (len(bares[i]), -i), default=None)


def proper_names(words) -> list[bool]:
    """For each (start, end, text) word: is it a name? Capitalised in the transcript, not the first word of a
    sentence, not "I" or a stop word."""
    out, prev = [], None
    for _s, _e, text in words:
        core = text.strip().strip(_TRIM + "!?")
        initial = prev is None or prev.rstrip()[-1:] in ".!?"
        out.append(bool(core[:1].isupper() and not initial and _bare_key(core) not in STOP_WORDS))
        prev = text
    return out


def group_impact(words, fits=lambda texts: True) -> list[list]:
    """(start, end, text) words as impact captions: one or two words, a third only when the three are short
    (IMPACT_SHORT characters between them). A caption also ends at a pause, after punctuation, before a word
    that would not fit on the line (`fits(texts)`), and before a word said more than IMPACT_LEAD after the
    caption's first (a slow speaker's next word would sit on screen too long before it is said)."""
    chunks, cur = [], []
    for w in words:
        if cur:
            prev = cur[-1]
            hard = (w[0] - prev[1] >= PAUSE or prev[2].strip()[-1:] in PUNCT
                    or w[0] - cur[0][0] > IMPACT_LEAD)
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
                 span: tuple[float, float], center: int | None, accent: str | None,
                 hook_at: tuple[float, float] | None = None, game: str | None = None,
                 look: dict | None = None, face: Face | None = None) -> int:
    """The impact style: see build_ass. `look` (render_options.CaptionLook as a dict) and `face` (its font, read
    by the caller) change the font, weight, slant, underline, colours, size and case. Each caption is one event pair per word in it (a soft shadow, and the
    words over it), from the moment that word is said: the word being said grows in (ACTIVE_POP), the words not
    said yet are see-through (UPCOMING), the keyword is in the accent colour. A Cap event is named w<i>, the
    index in `words` of the word it marks as being said (scripts/caption_checks.py times them)."""
    play_w, play_h = play
    look = look or {}
    m = impact_size(play_h, face, (look.get("size") or 100) / 100)
    upper = look.get("case", "upper") != "as_typed"
    family = face.family if face else IMPACT_FONT
    fill = ass_colour(look["colour"])[2:8] if look.get("colour") else "FFFFFF"
    edge = ass_colour(look["outline_colour"])[2:8] if look.get("outline_colour") else "000000"
    flags = f"{WEIGHTS[look['weight']] if look.get('weight') else 0},{-1 if look.get('italic') else 0}," \
            f"{-1 if look.get('underline') else 0},0"
    room = (span[1] - span[0]) * play_w * IMPACT_FILL
    x = round((span[0] + span[1]) / 2 * play_w)
    y = round(LOWER_THIRD * play_h) if center is None else center
    k = 1.0 if vertical else play_h / 1080             # the hook is sized for the 1080 canvas; a source frame may not be one
    spacing = round(IMPACT_SPACING * m.em, 1)
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {play_w}\nPlayResY: {play_h}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n" + STYLE_FORMAT +
        f"Style: Cap,{family},{m.size},&H00{fill},&H00{fill},&H00{edge},&H00000000,{flags},"
        f"100,100,{spacing},0,1,{m.outline},0,5,0,0,0,1\n"
        # The same letters with nothing visible but their shadow, blurred: a soft shadow under a crisp outline.
        f"Style: CapShadow,{family},{m.size},&HFF000000,&HFF000000,&HFF000000,&H50000000,{flags},"
        f"100,100,{spacing},0,1,{m.outline},{m.shadow},5,0,0,0,1\n"
        + _hook_style(font, round((78 if vertical and play_h >= play_w else 64) * k), int(span[0] * play_w),
                      int((1 - span[1]) * play_w), hook_top, k)
        + "\n[Events]\n" + EVENT_FORMAT)
    names = proper_names(words)
    shown = [(i, w) for i, w in enumerate(words) if impact_text(w[2], upper)]
    grow = ACTIVE_POP[1]
    # Room for the word being said at its grown size, wherever it is in the line.
    chunks = group_impact([w for _, w in shown], lambda texts: impact_width(texts, m.em, face) * grow <= room)
    index = iter(i for i, _ in shown)
    accent_on, white = "\\c" + ass_colour(accent or ACCENT), f"\\c&H{fill}&"
    lines = []
    if hook:
        a, b = hook_at or (0, HOOK_SECONDS)
        lines.append(f"Dialogue: 2,{ass_time(a)},{ass_time(b)},Hook,,0,0,0,,{{\\fad(120,220)}}{_clean(hook, True)}")
    for ci, chunk in enumerate(chunks):
        ids = [next(index) for _ in chunk]
        end = chunk[-1][1] + CAPTION_HOLD
        if ci + 1 < len(chunks):
            end = min(end, chunks[ci + 1][0][0])
        texts = [impact_text(t, upper) for _, _, t in chunk]
        # A word too long for the line at full size is drawn smaller, never wrapped and never off the frame.
        pct = min(100, int(100 * (room - 2 * m.outline) / max(1.0, impact_width(texts, m.em, face) * grow - 2 * m.outline)))
        # \an5 hangs the line by the middle of the font's whole line; the capitals sit a little under that.
        asc, desc, capr = (face.ascent, face.descent, face.cap) if face else (ANTON_ASCENT, ANTON_DESCENT, ANTON_CAP)
        row = y - (asc - desc - capr) / 2 * m.em * pct / 100
        place = f"\\pos({x},{row:.0f})\\q2\\fscx{pct}\\fscy{pct}"
        key = keyword([w[2] for w in chunk], [names[i] for i in ids], game)
        small, big, ms = round(pct * ACTIVE_POP[0]), round(pct * grow), ACTIVE_POP[2]
        pop = f"\\fscx{small}\\fscy{small}\\t(0,{ms},\\fscx{big}\\fscy{big})"
        back = f"\\fscx{pct}\\fscy{pct}"
        for j, i in enumerate(ids):
            a = chunk[0][0] if j == 0 else chunk[j][0]
            b = chunk[j + 1][0] if j + 1 < len(chunk) else end
            drawn, shadow = [], []
            for n, t in enumerate(texts):
                colour = accent_on if n == key else white
                alpha = "\\1a" + (UPCOMING if n > j else "&H00&")
                size = pop if n == j else back
                drawn.append(f"{{{colour}{alpha}{size}}}{t}")
                shadow.append(f"{{{size}}}{t}")
            when = f"{ass_time(a)},{ass_time(max(b, a + 0.05))}"
            lines.append(f"Dialogue: 0,{when},CapShadow,,0,0,0,,{{{place}\\blur{m.blur}}}{WORD_GAP.join(shadow)}")
            lines.append(f"Dialogue: 1,{when},Cap,w{i},0,0,0,,{{{place}}}{WORD_GAP.join(drawn)}")
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return len(chunks)


def build_ass(words, path: Path, vertical: bool, caption_top: int, font: str, style: str = "pop",
              play: tuple[int, int] = (1080, 1920), hook: str | None = None, hook_top: int = 0,
              span: tuple[float, float] = (0.0, 1.0), *, center: int | None = None, accent: str | None = None,
              hook_at: tuple[float, float] | None = None, game: str | None = None, look: dict | None = None,
              face: Face | None = None) -> int:
    """A few words at a time. Returns the number of captions.
    `hook` is one line of text shown in a box for the first HOOK_SECONDS, `hook_top` pixels from the top.
    `span` is the part of the frame's width (fractions, left and right) the text is centred in: the gameplay
    panel when a camera panel sits beside it.

    The word-highlight styles (pop, bold, neon, boxed, clean) show up to five words with the one being said
    highlighted, `caption_top` pixels from the top, in `font`.

    `impact` shows one or two words (a third when all three are short) in upper case in the bundled heavy font,
    with a dark outline and a soft shadow, the keyword in `accent` (#RRGGBB; the brand lime when None). `center`
    is the row of the middle of the capitals, in `play` pixels (the lower third when None); `caption_top` is not
    used. `play` is the frame the numbers are for, reframed or not. A word too wide for the line is drawn smaller.

    The STYLED styles (bounce, karaoke, reveal, outline, subtitle, tag) sit where the word-highlight ones do.
    `hook_at` is when the hook is on screen, (from, to) seconds on the clip's timeline; None: the first HOOK_SECONDS."""
    if style == "impact":
        return build_impact(words, path, vertical, font, play, hook, hook_top, span, center, accent, hook_at, game,
                            look, face)
    if style in STYLED:
        return build_styled(words, path, vertical, caption_top, font, STYLED[style], play, hook, hook_top, span,
                            hook_at)
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
        a, b = hook_at or (0, HOOK_SECONDS)
        lines.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Hook,,0,0,0,,{{\\fad(120,220)}}{_clean(hook, True)}")
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


def build_styled(words, path: Path, vertical: bool, caption_top: int, font: str, st: dict,
                 play: tuple[int, int] = (1080, 1920), hook: str | None = None, hook_top: int = 0,
                 span: tuple[float, float] = (0.0, 1.0), hook_at: tuple[float, float] | None = None) -> int:
    """The STYLED caption styles: placed and sized as the word-highlight styles are (see build_ass), drawn as
    `st["mode"]` says. Returns the number of captions."""
    if vertical:
        play_w, play_h = play
        size = int((78 if play_h >= play_w else 64) * st["size"])
        margin_v = max(80, play_h - caption_top - size - 20)
    else:
        play_w, play_h, size, margin_v = 1920, 1080, int(64 * st["size"]), 70
    left, right = int(span[0] * play_w), int((1 - span[1]) * play_w)
    mode, hl = st["mode"], st["hl"]
    # karaoke: the words go from white (secondary) to the highlight (primary) as they are said
    primary = _style_colour(hl) if mode == "karaoke" else "&H00FFFFFF"
    outline = st["box_colour"] if st.get("box") else "&H00000000"
    styles = (f"Style: Cap,{font},{size},{primary},&H00FFFFFF,{outline},&H80000000,1,0,0,0,"
              f"100,100,1,0,{st.get('border', '1,6,2')},2,{60 + left},{60 + right},{margin_v},1\n")
    if mode == "tag":       # the keyword again, in dark letters on a box of the highlight colour
        styles += (f"Style: Tag,{font},{size},&H00101010,&H00101010,{_style_colour(hl)},{_style_colour(hl)},1,0,0,0,"
                   f"100,100,1,0,3,{TAG_PAD},0,2,{60 + left},{60 + right},{margin_v},1\n")
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {play_w}\nPlayResY: {play_h}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n" + STYLE_FORMAT + styles +
        f"Style: Hook,{font},{int(size * 0.9)},{HOOK_TEXT},{HOOK_TEXT},{HOOK_BOX},{HOOK_BOX},1,0,0,0,"
        f"100,100,0,0,3,14,0,8,{90 + left},{90 + right},{hook_top},1\n\n"
        "[Events]\n" + EVENT_FORMAT)
    chunks = group_words(words, st["words"], st["chars"])
    lines = []
    if hook:
        a, b = hook_at or (0, HOOK_SECONDS)
        lines.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Hook,,0,0,0,,{{\\fad(120,220)}}{_clean(hook, True)}")
    for ci, chunk in enumerate(chunks):
        texts = [_clean(t, st["upper"]) for _, _, t in chunk]
        first, last = chunk[0][0], chunk[-1][1]
        if ci + 1 < len(chunks):
            last = min(last + 0.3, chunks[ci + 1][0][0])
        when = f"{ass_time(first)},{ass_time(max(last, first + 0.05))}"
        if mode in ("still", "tag"):
            lines.append(f"Dialogue: 0,{when},Cap,,0,0,0,,{' '.join(texts)}")
            key = keyword(texts) if mode == "tag" else None
            if key is not None:     # the same line on top with every word but the keyword invisible
                hide, show = "{\\alpha&HFF&}", "{\\alpha&H00&}"
                text = " ".join(show + t + hide if i == key else t for i, t in enumerate(texts))
                lines.append(f"Dialogue: 1,{when},Tag,,0,0,0,,{hide}{text}")
        elif mode == "karaoke":     # one event; \kf fills each word over the time it is said
            parts, at = [], first
            for (s, e, _), t in zip(chunk, texts):
                gap = max(0, round((s - at) * 100))
                parts.append((f"{{\\k{gap}}}" if gap else "") + f"{{\\kf{max(1, round((e - s) * 100))}}}{t}")
                at = e
            lines.append(f"Dialogue: 0,{when},Cap,,0,0,0,,{' '.join(parts)}")
        else:                       # bounce, reveal: one event per word
            small, ms, big = BOUNCE
            for wi, (s, _e, _) in enumerate(chunk):
                end = chunk[wi + 1][0] if wi + 1 < len(chunk) else last
                if mode == "bounce":
                    grow = f"{{\\c{hl}\\fscx{small}\\fscy{small}\\t(0,{ms},\\fscx{big}\\fscy{big})}}"
                    text = " ".join(grow + t + "{\\c&HFFFFFF&\\fscx100\\fscy100}" if j == wi else t
                                    for j, t in enumerate(texts))
                else:               # reveal: the words said so far, the newest in the highlight colour
                    text = " ".join("{\\c" + hl + "}" + t + "{\\c&HFFFFFF&}" if j == wi else t
                                    for j, t in enumerate(texts[:wi + 1]))
                lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(max(end, s + 0.05))},Cap,,0,0,0,,{text}")
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return len(chunks)


def _style_colour(colour: str) -> str:
    """An override colour (&HBBGGRR&) as a style colour (&HAABBGGRR, opaque)."""
    return "&H00" + colour[2:8]
