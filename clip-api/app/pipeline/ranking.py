"""How a clip's five editorial sub-scores become its place in the ranking, per game.

The judge rates five editorial things (SCORES, each 0-100): hook, payoff, clarity, emotion, pacing. These stay the
SCORE_WEIGHTS / rank_score surface. Gaming highlight-quality components (app.gaming_rating.GAMING_COMPONENTS) are
stored separately for AI quality UI and eval — they do not replace these five unless SCORE_WEIGHTS is refit.

When SCORE_WEIGHTS is empty, rank order follows the clip's overall AI quality number from the judge (plain mean of
editorial scores, or the gaming composite when judge-v3-gaming filled both). Weights only reorder clips; editorial
sub-scores are stored one by one, so new weights need no new judging.

Weights are data, not opinion: the table is empty (every game ranks by the plain mean) until
`scripts/fit_score_weights.py` fits it on the owner's labels (tuning videos only) and the result is put in
SCORE_WEIGHTS. A game without its own weights uses its genre's, then "default", then equal weights.

Neither number is a probability or a forecast of views. No file, network or database code.
"""
import hashlib
import json

SCORES = ("hook", "payoff", "clarity", "emotion", "pacing")
EQUAL = "equal"                       # the version name of equal weights
DEFAULT = "default"                   # the table key used when a game and its genre have no weights of their own


def clean(weights) -> dict[str, float] | None:
    """`weights` as {sub-score: share}, summing to 1, or None when it is not a usable set: every sub-score must be
    there, none negative, and not all zero."""
    if not isinstance(weights, dict):
        return None
    try:
        vals = {k: float(weights[k]) for k in SCORES}
    except (KeyError, TypeError, ValueError):
        return None
    total = sum(vals.values())
    if any(v < 0 for v in vals.values()) or total <= 0:
        return None
    return {k: round(v / total, 4) for k, v in vals.items()}


def version_of(key: str, weights: dict[str, float]) -> str:
    """A name for one set of weights: its table key and a short hash, so a clip says which weights ranked it."""
    digest = hashlib.sha256(json.dumps([weights[k] for k in SCORES]).encode()).hexdigest()[:8]
    return f"{key}:{digest}"


def weights_for(game: str | None, genre: str | None = None, table: dict | None = None) -> tuple[dict[str, float] | None, str]:
    """(weights, version) for a clip of `game`: the game's own, else its genre's, else the table's default, else
    (None, "equal"). An unusable entry is skipped, never half-used."""
    for key in (game, genre, DEFAULT):
        weights = clean((table or {}).get(key)) if key else None
        if weights is not None:
            return weights, version_of(key, weights)
    return None, EQUAL


def rank_score(scores, weights: dict[str, float] | None) -> float | None:
    """The weighted mean of the five sub-scores (0-100), or None when `scores` is not a full set. Without weights:
    the plain mean."""
    if not isinstance(scores, dict):
        return None
    try:
        vals = {k: float(scores[k]) for k in SCORES}
    except (KeyError, TypeError, ValueError):
        return None
    if weights is None:
        return round(sum(vals.values()) / len(SCORES), 2)
    return round(sum(vals[k] * weights[k] for k in SCORES), 2)
