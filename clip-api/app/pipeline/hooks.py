"""(U4) One hook per clip, and no two alike within a job.

The judge writes each clip's hook (the on-screen line over its first seconds, also used by the thumbnails) from
that clip alone, so a long job can repeat itself: "He did NOT see that coming" on five clips. `distinct` walks the
job's clips best first and rewrites any hook that is generic or close to one already used:

1. `writer` (the AI, app/ai.py ClaudeAI.rewrite_hook) writes a new one from the clip's own transcript, told which
   hooks are taken (every repeat in one parallel round);
2. otherwise one of the clip's other titles, cut to a hook;
3. otherwise the clip's own strongest spoken line, cut to a hook;
4. otherwise the clip has no hook: a repeated line is worse than none.

No file, network or database code.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

MAX_WORDS, MAX_CHARS = 6, 48
WRITERS = 8              # rewrites in flight at once
SAME = 0.6               # two hooks are the same when they share this much of their words (Jaccard)
STOP = frozenset("a an the to of and or in on at is it this that he she they we you i me my his her their".split())
# Lines that fit any clip, so they say nothing about this one.
GENERIC = frozenset({"wait for it", "watch till the end", "watch until the end", "you wont believe this",
                     "you wont believe what happened", "this is insane", "this is crazy", "no way", "omg",
                     "what just happened", "watch this", "did that just happen", "insane moment", "crazy moment",
                     "epic moment", "best moment", "funny moment"})
EXCLAIM = ("no way", "oh my god", "what", "bro", "dude", "let's go", "lets go", "run", "help", "wait")

# writer(transcript_text, taken_hooks, context) -> a new hook or None
Writer = Callable[[str, list[str], dict], str | None]


def clean(text) -> str | None:
    """`text` as a hook: one line, at most MAX_WORDS words and MAX_CHARS characters, no markup. None if empty."""
    words = re.sub(r"[{}\\\n\r#\"]", " ", str(text or "")).strip().strip(".").split()
    out = " ".join(words[:MAX_WORDS])[:MAX_CHARS].strip()
    return out or None


def _key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower().replace("'", "")))


def _words(text: str) -> set[str]:
    return {w for w in _key(text).split() if w not in STOP}


def generic(text: str) -> bool:
    return _key(text) in GENERIC


def same(a: str, b: str) -> bool:
    """Whether two hooks read as the same line."""
    if _key(a) == _key(b):
        return True
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= SAME


def taken_by(hook: str, used: list[str]) -> bool:
    return generic(hook) or any(same(hook, u) for u in used)


DANGLING = frozenset("and but so or to of the a an with for because like if then".split())


def best_line(lines: list[str]) -> str | None:
    """The clip's most striking whole sentence of 3 to MAX_WORDS words: the most exclamations, then the shortest.
    Transcript lines are split into sentences first, so a hook never starts or stops halfway through one."""
    good = []
    for s in (s for t in lines for s in re.split(r"(?<=[.?!])\s+", " ".join(str(t).split()))):
        words = s.strip(" .,…").split()
        while words and words[-1].lower().strip(",.!?") in DANGLING:
            words.pop()
        if 3 <= len(words) <= MAX_WORDS and len(" ".join(words)) <= MAX_CHARS:
            good.append(" ".join(words))
    if not good:
        return None
    return min(good, key=lambda x: (-sum(x.lower().count(e) for e in EXCLAIM), len(x)))


def usable(hook: str | None) -> bool:
    """A stand-in hook says something: at least 2 words and 6 characters."""
    return hook is not None and len(hook.split()) >= 2 and len(hook) >= 6


def distinct(clips: list[dict], writer: Writer | None = None) -> dict:
    """Give every clip a hook no earlier clip has. `clips`, best first: {"hook", "titles", "lines" (the clip's own
    transcript lines), "context" (sent to the writer)}; each gets "hook" (new, or None) and, when it changed,
    "rewritten": {"from", "by"}. Returns counts: hooks, duplicates (generic or repeated before), rewritten,
    dropped, left (duplicates after: always 0)."""
    stats = {"hooks": 0, "duplicates": 0, "rewritten": 0, "dropped": 0}
    # 1. Best first, a hook no better clip already has is kept; the rest are repeats.
    used: list[str] = []
    repeats: list[tuple[dict, str]] = []
    for clip in clips:
        hook = clean(clip.get("hook"))
        clip["hook"] = hook
        if hook is None:
            continue
        stats["hooks"] += 1
        if taken_by(hook, used):
            repeats.append((clip, hook))
        else:
            used.append(hook)
    stats["duplicates"] = len(repeats)
    # 2. The writer rewrites every repeat in one parallel round (not one call after another, so the first clip is
    #    not held back), each told every hook that is kept.
    written: list[str | None] = [None] * len(repeats)
    if writer is not None and repeats:
        kept = list(used)

        def write(item):
            clip, _hook = item
            try:
                return writer(" ".join(clip.get("lines") or []), kept, clip.get("context") or {})
            except Exception:                    # a failed rewrite is only a missed rewrite
                return None
        with ThreadPoolExecutor(min(WRITERS, len(repeats))) as pool:
            written = list(pool.map(write, repeats))
    # 3. Best first again: the rewrite, else a title, else the clip's own line, whichever is not taken by now.
    for (clip, hook), ai_hook in zip(repeats, written):
        tries = ([("ai", ai_hook)] if writer is not None else []) + \
            [("title", t) for t in (clip.get("titles") or [])] + [("transcript", best_line(clip.get("lines") or []))]
        new, by = None, "dropped"
        for source, text in tries:
            candidate = clean(text)
            if usable(candidate) and not taken_by(candidate, used):
                new, by = candidate, source
                break
        clip["rewritten"] = {"from": hook, "by": by}
        clip["hook"] = new
        if new is None:
            stats["dropped"] += 1
        else:
            stats["rewritten"] += 1
            used.append(new)
    stats["left"] = sum(1 for i, a in enumerate(used) for b in used[:i] if same(a, b))
    return stats
