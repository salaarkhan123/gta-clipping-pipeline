"""Pick distinct clips: after ranking, skip a candidate that is close in time to, or about the same thing as,
one already picked.

Two cheap tests, no model calls:
- time: the two windows are less than `min_gap` seconds apart (overlap counts as 0 s apart). min_gap_for()
  gives MIN_GAP on long videos and less on short ones, so a 1-minute upload can still yield 3 clips;
- topic: the judge's title, description and hashtags share at least TOPIC_OVERLAP of the smaller token set,
  or the two transcripts share at least SPEECH_JACCARD of their words.

In a pool of at least COMMON_POOL candidates, topic tokens shared by more than half of them (#gta6,
"gameplay", the streamer's catchphrase) say nothing about a clip and are ignored. Transcripts count as the
same speech only when both have at least MIN_SPEECH_TOKENS content words: a few words are too thin to judge.
When too few distinct candidates exist, fewer clips come back: a repeat of the same moment is worse than
one clip less.

For a long list (dozens of clips from a multi-hour video) the caller passes `horizon`: the topic and speech
tests then only compare clips less than that many seconds apart. Every clip is otherwise compared with every
clip already picked, and with 50 picks two unrelated moments hours apart that happen to share words (two car
chases, two arguments with the same person) would cost a clip each time. The time test always applies.
"""
import re

MIN_GAP = 60.0
HORIZON = 900.0           # with a long list, "same topic" and "same speech" only count within 15 minutes
TOPIC_OVERLAP = 0.5
SPEECH_JACCARD = 0.5
MIN_SPEECH_TOKENS = 6
COMMON_POOL = 4
STOPWORDS = frozenset(
    "the and for you this that with are was but not have has had his her they them then than what when where "
    "who why how all any can could would should will just get got its it's into out off over from your our "
    "one two too very really like yeah okay gta clip clips moment".split())


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(t) >= 3 and t not in STOPWORDS}


def topic_text(meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return ""
    tags = meta.get("hashtags") if isinstance(meta.get("hashtags"), list) else []
    return " ".join([str(meta.get("title") or ""), str(meta.get("description") or ""), *map(str, tags)])


def min_gap_for(duration: float, count: int) -> float:
    """MIN_GAP, or less when the video is too short to spread `count` clips that far apart."""
    return min(MIN_GAP, duration / (2 * max(1, count)))


def gap(a, b) -> float:
    """Seconds between two (start, end) windows; 0 when they overlap."""
    return max(0.0, max(a[0], b[0]) - min(a[1], b[1]))


def _strip_common(sets: list[set[str]]) -> list[set[str]]:
    if len(sets) < COMMON_POOL:
        return sets
    counts: dict[str, int] = {}
    for s in sets:
        for t in s:
            counts[t] = counts.get(t, 0) + 1
    common = {t for t, k in counts.items() if k > len(sets) / 2}
    return [s - common for s in sets]


def overlap(a: set, b: set) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def pick_distinct(ranked: list, n: int, window, meta, speech, min_gap: float = MIN_GAP,
                  horizon: float | None = None) -> tuple[list, list[tuple[int, str]]]:
    """Greedy over `ranked` (best first). `window(c)` -> (start, end), `meta(c)` -> judge dict or None,
    `speech(c)` -> transcript text. Returns (picked, skipped) where skipped is [(index in ranked, reason)].
    `horizon`: compare topic and speech only between clips less than this many seconds apart (None = always)."""
    topics = _strip_common([tokens(topic_text(meta(c))) for c in ranked])
    words = [w if len(w) >= MIN_SPEECH_TOKENS else set() for w in (tokens(speech(c)) for c in ranked)]
    picked: list[int] = []
    skipped: list[tuple[int, str]] = []
    for i, c in enumerate(ranked):
        if len(picked) == n:
            break
        reason = None
        for j in picked:
            apart = gap(window(c), window(ranked[j]))
            if apart < min_gap:
                reason = f"within {min_gap:.0f} s of a picked clip"
            elif horizon is not None and apart >= horizon:
                continue
            elif overlap(topics[i], topics[j]) >= TOPIC_OVERLAP:
                reason = "same topic as a picked clip"
            elif jaccard(words[i], words[j]) >= SPEECH_JACCARD:
                reason = "same speech as a picked clip"
            if reason:
                break
        if reason:
            skipped.append((i, reason))
        else:
            picked.append(i)
    return [ranked[i] for i in picked], skipped
