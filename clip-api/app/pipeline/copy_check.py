"""The words a clip ships with (on-screen hook, titles, description, hashtags), checked against what the clip says.

The judge writes them from the clip's transcript; this is the last check before they reach the clip and the
thumbnail. It only removes or replaces with the clip's own words, never writes anything new:

- No other product's or tool's name (OpusClip, Wayin, ChatGPT, "AI", ...) in any of them, and no hashtag for one.
- No filler that fits any clip ("you won't believe", "wait for it", "insane moment") in the hook or a title.
- No claim the clip does not make: a number, or a "world record" / "first ever" style claim, that is not in the
  transcript.
- Hashtags: lower case, no "#", no spam tags (fyp, viral), the game's own tag first when the game is known,
  at most 5.

A hook that fails becomes the clip's strongest whole sentence (hooks.best_line), else None (hooks.distinct then
leaves it out). A title that fails is dropped while another is left; the last one is kept with the offending
words cut out. No file, network or database code.
"""
import re

from . import hooks

# Names of other clipping products, AI vendors and creator tools. Lower case, matched as whole words.
BANNED = ("opusclip", "opus clip", "opus pro", "opus.pro", "wayin", "wayinvideo", "wayin video", "chatgpt",
          "chat gpt", "gpt", "openai", "claude", "anthropic", "gemini", "capcut", "vizard", "submagic", "klap",
          "eklipse", "medal.tv", "outplayed", "streamladder", "clutchclips", "clutch clips", "ai", "a.i.",
          "ai-generated", "ai generated")
FILLER = ("you won't believe", "you wont believe", "wait for it", "watch till the end", "watch until the end",
          "watch to the end", "insane moment", "crazy moment", "epic moment", "best moment ever", "must watch",
          "gone wrong", "not clickbait", "what happens next", "you need to see this", "this is insane",
          "this is crazy", "omg")
CLAIMS = ("world record", "first ever", "world's first", "worlds first", "never been done", "nobody has ever",
          "100% real", "not fake", "#1", "number one", "best player")
SPAM_TAGS = frozenset("fyp foryou foryoupage fy viral trending explore explorepage xyzbca reels shorts tiktok "
                      "clips clip video funny".split())
GAME_TAGS = {"lol": "leagueoflegends", "gta5": "gta5", "wow": "worldofwarcraft", "ow2": "overwatch2",
             "minecraft": "minecraft", "apex": "apexlegends", "valorant": "valorant", "fortnite": "fortnite",
             "dota2": "dota2", "rust": "rust", "cs2": "cs2"}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
                "fifty": 50, "hundred": 100, "thousand": 1000, "million": 1000000}
MAX_TAGS = 5
# A number that is part of a game's name is not a claim ("GTA 5", "CS2", "Dota 2", "Overwatch 2", "FIFA 23").
GAME_NUMBER = re.compile(r"\b(gta|cs|ow|dota|overwatch|fifa|fc|nba ?2k|madden|cod|mw|bo|battlefield|bf|forza horizon"
                         r"|forza motorsport)\s?v?\d+\b", re.I)


def _has(text: str, phrase: str) -> bool:
    return re.search(r"(?<![\w.])" + re.escape(phrase) + r"(?![\w])", text.lower().replace("’", "'")) is not None


def _numbers(text: str) -> set[int]:
    """Every number in `text`, digits or words, ("1v5" is 1 and 5; "2k" is 2)."""
    low = GAME_NUMBER.sub(" ", text.lower().replace(",", ""))
    out = {int(n) for n in re.findall(r"\d+", low)}
    out |= {v for w, v in NUMBER_WORDS.items() if re.search(rf"\b{w}\b", low)}
    return out


def problems(text: str, transcript: str) -> list[str]:
    """Why `text` may not ship with a clip whose transcript is `transcript` (empty: it may)."""
    found = [f"banned:{b}" for b in BANNED if _has(text, b)]
    found += [f"filler:{f}" for f in FILLER if _has(text, f)]
    found += [f"claim:{c}" for c in CLAIMS if _has(text, c) and not _has(transcript, c)]
    found += [f"number:{n}" for n in sorted(_numbers(text) - _numbers(transcript))]
    return found


def _strip(text: str) -> str:
    """`text` without banned names, filler and unsupported claim phrases (numbers are left to the caller)."""
    for phrase in (*BANNED, *FILLER, *CLAIMS):
        text = re.sub(r"(?<![\w.])" + re.escape(phrase) + r"(?![\w])", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" -:|,.")


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def _banned_tag(tag: str) -> bool:
    """A tag naming a banned product: exactly, or starting with a long enough name (#opusclipedit, not #aimbot)."""
    names = {re.sub(r"[^a-z0-9]", "", b) for b in BANNED}
    return tag in names or any(len(n) >= 5 and tag.startswith(n) for n in names)


def hashtags(tags, game: str | None) -> list[str]:
    out = []
    lead = GAME_TAGS.get(game or "")
    for tag in ([lead] if lead else []) + [str(t) for t in tags or []]:
        tag = re.sub(r"[^a-z0-9]", "", tag.lower())
        if tag and tag not in out and tag not in SPAM_TAGS and not tag.isdigit() and not _banned_tag(tag):
            out.append(tag)
    return out[:MAX_TAGS]


def check_copy(meta: dict, transcript: str, game: str | None = None,
               lines: list[str] | None = None) -> tuple[dict, list[str]]:
    """`meta` (the judge's title, titles, hook, description, hashtags) made safe to ship with a clip whose
    transcript is `transcript`; `lines` are its transcript lines (for a replacement hook; default: `transcript`).
    Returns (a new dict, what was found, as "<field>:<problem>")."""
    meta, found = dict(meta), []
    titles = [t for t in (meta.get("titles") or [meta.get("title")]) if isinstance(t, str) and t.strip()]
    ok = []
    for t in titles:
        bad = problems(t, transcript)
        found += [f"title:{p}" for p in bad]
        if not bad:
            ok.append(t)
    if not ok and titles:                       # keep one title: the first, with the offending words cut out
        cut = _strip(titles[0])
        cut = " ".join(w for w in cut.split() if not (_numbers(w) - _numbers(transcript)))
        line = hooks.best_line(lines if lines is not None else [transcript])
        ok = [cut] if len(cut.split()) >= 2 else [line] if line else []
    if titles:
        meta["titles"] = ok
        meta["title"] = ok[0] if ok else None
    hook = meta.get("hook")
    if isinstance(hook, str) and hook.strip():
        bad = problems(hook, transcript) + (["generic"] if hooks.generic(hook) else [])
        if bad:
            found += [f"hook:{p}" for p in bad]
            line = hooks.best_line(lines if lines is not None else [transcript])
            meta["hook"] = line if hooks.usable(line) and not problems(line, transcript) else None
    desc = meta.get("description")
    if isinstance(desc, str) and desc:
        kept = []
        for s in _sentences(desc):
            bad = problems(s, transcript)
            found += [f"description:{p}" for p in bad]
            if not bad:
                kept.append(s)
        meta["description"] = " ".join(kept)
    if "hashtags" in meta or game:
        before = [str(t) for t in meta.get("hashtags") or []]
        meta["hashtags"] = hashtags(before, game)
        dropped = [t for t in before if re.sub(r"[^a-z0-9]", "", t.lower()) not in meta["hashtags"]]
        found += [f"hashtags:dropped:{t}" for t in dropped]
    return meta, found
