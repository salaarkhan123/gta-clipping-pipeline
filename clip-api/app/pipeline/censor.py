"""Optional profanity masking for captions: keep the first letter, star the swear, keep its ending.

    fucking -> f***ing, SHIT -> S***, motherfucker -> m***********, "bitch!" -> "b****!"

Whole words only (Scunthorpe, classic and shitake stay as they are), case-insensitive. A word is masked when it is
one of the roots below, or a root plus a common ending (-ing, -in', -ed, -er, -ers, -s, -es, -y, -ty, -head).
"""
import re

ROOTS = ("fuck", "fuk", "shit", "bitch", "cunt", "dick", "pussy", "asshole", "arsehole", "bastard",
         "motherfucker", "bullshit", "twat", "wanker", "prick", "slut", "whore")
ENDINGS = ("", "s", "es", "ing", "in", "in'", "ed", "er", "ers", "y", "ty", "head", "heads")
_WORD = re.compile(r"^(\W*)([A-Za-z']+?)(\W*)$")
_FORMS = {root + end: len(root) for root in ROOTS for end in ENDINGS}


def mask(word: str) -> str:
    """The word with any swear masked; anything else unchanged (punctuation around it is kept)."""
    m = _WORD.match(word)
    if not m:
        return word
    lead, core, trail = m.groups()
    root_len = _FORMS.get(core.lower())
    if root_len is None:
        return word
    return lead + core[0] + "*" * (root_len - 1) + core[root_len:] + trail


def mask_words(words) -> list:
    """Mask the text of (start, end, text) words; times unchanged."""
    return [(s, e, t.like(mask(t)) if hasattr(t, "like") else mask(t)) for s, e, t in words]
