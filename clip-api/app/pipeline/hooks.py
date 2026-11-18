"""(U4) One hook per clip, and no two alike within a job.

The judge writes each clip's hook (the on-screen line over its first seconds, also used by the thumbnails) from
that clip alone, so a long job can repeat itself: "He did NOT see that coming" on five clips. `distinct` walks the
job's clips best first and rewrites any hook that is generic or close to one already used:

1. `writer` (the AI, app/ai.py ClaudeAI.rewrite_hook) writes a new one from the clip's own transcript, told which
   hooks are taken;
2. otherwise one of the clip's other titles, cut to a hook;
3. otherwise the clip's own strongest spoken line, cut to a hook;
4. otherwise the clip has no hook: a repeated line is worse than none.

No file, network or database code.
"""
import re
from typing import Callable

MAX_WORDS, MAX_CHARS = 6, 48
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


def best_line(lines: list[str]) -> str | None:
    """The clip's most striking line: the one with the most exclamations, then the shortest of 3 words or more."""
    good = [x for x in (" ".join(str(t).split()) for t in lines) if len(x.split()) >= 3]
    if not good:
        return None
    return min(good, key=lambda x: (-sum(x.lower().count(e) for e in EXCLAIM), len(x)))


def distinct(clips: list[dict], writer: Writer | None = None) -> dict:
    """Give every clip a hook no earlier clip has. `clips`, best first: {"hook", "titles", "lines" (the clip's own
    transcript lines), "context" (sent to the writer)}; each gets "hook" (new, or None) and, when it changed,
    "rewritten": {"from", "by"}. Returns counts: hooks, duplicates (generic or repeated before), rewritten,
    dropped, left (duplicates after: always 0)."""
    used: list[str] = []
    stats = {"hooks": 0, "duplicates": 0, "rewritten": 0, "dropped": 0}
    for clip in clips:
        hook = clean(clip.get("hook"))
        if hook is None:
            clip["hook"] = None
            continue
        stats["hooks"] += 1
        if not taken_by(hook, used):
            clip["hook"] = hook
            used.append(hook)
            continue
        stats["duplicates"] += 1
        tries: list[tuple[str, Callable[[], str | None]]] = []
        if writer is not None:
            tries.append(("ai", lambda: writer(" ".join(clip.get("lines") or []), list(used), clip.get("context") or {})))
        tries += [("title", lambda t=t: t) for t in (clip.get("titles") or [])]
        tries.append(("transcript", lambda: best_line(clip.get("lines") or [])))
        new = None
        for by, make in tries:
            try:
                candidate = clean(make())
            except Exception:                    # a failed rewrite is only a missed rewrite
                candidate = None
            if candidate is not None and not taken_by(candidate, used):
                new = candidate
                break
        clip["rewritten"] = {"from": hook, "by": by if new is not None else "dropped"}
        clip["hook"] = new
        if new is None:
            stats["dropped"] += 1
        else:
            stats["rewritten"] += 1
            used.append(new)
    stats["left"] = sum(1 for i, a in enumerate(used) for b in used[:i] if same(a, b))
    return stats
