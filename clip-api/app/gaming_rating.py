"""Gaming highlight quality components — additive depth on top of editorial judge scores.

The nine components are an AI opinion of how strong a gaming highlight is (0–100 each).
They are **not** a virality probability, view forecast, or statistical chance of going viral.

Editorial judge v2 scores (hook / payoff / clarity / emotion / pacing in ranking.SCORES) stay
the ranking / SCORE_WEIGHTS surface. Gaming components are stored beside them for UI depth
and labelled eval / ablation. See docs in the Project store and clip-api/eval/gaming-rating.md.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

# Product-facing highlight-quality dimensions (AS-1). Keys are stable API / sheet ids.
GAMING_COMPONENTS: tuple[str, ...] = (
    "hook",
    "intensity",
    "kills_clutches",
    "funny",
    "reactions",
    "audio",
    "chat",
    "unexpected",
    "game_context",
)

GAMING_SCORING_VERSION = "judge-v3-gaming"

# Short labels for UI / eval sheets (not marketing copy).
GAMING_LABELS: dict[str, str] = {
    "hook": "Hook",
    "intensity": "Intensity",
    "kills_clutches": "Kills / clutches",
    "funny": "Funny",
    "reactions": "Reactions",
    "audio": "Audio",
    "chat": "Chat",
    "unexpected": "Unexpected",
    "game_context": "Game context",
}

# One-line judge rubric fragments (also mirrored in ai.py SYSTEM for the model).
GAMING_RUBRIC: dict[str, str] = {
    "hook": "first ~3 s stop-scroll strength for a cold viewer",
    "intensity": "stakes, urgency and peak energy of the beat",
    "kills_clutches": "skilled plays, eliminations, narrow wins or escapes (0 if none)",
    "funny": "comedy, witty lines or silly situations (0 if not a comedy beat)",
    "reactions": "streamer or on-screen reaction strength and timing to the payoff",
    "audio": "how much the sound bed (voice, game mix, bursts) sells the moment",
    "chat": "live chat / audience energy contribution when visible or audible (0 if none)",
    "unexpected": "novelty, reversal or surprise relative to this game",
    "game_context": "how clearly a newcomer can read the game situation without the VOD",
}

HONESTY = (
    "AI quality / highlight rating — the model's opinion of the cut. "
    "Not a forecast of views, shares, or chance of going viral."
)


def clamp_score(value, lo: int = 0, hi: int = 100) -> int:
    try:
        return max(lo, min(hi, int(round(float(value)))))
    except (TypeError, ValueError):
        return 50


def clean_components(raw) -> dict[str, int] | None:
    """Full gaming component dict or None when any required key is missing / unusable."""
    if not isinstance(raw, Mapping):
        return None
    try:
        return {k: clamp_score(raw[k]) for k in GAMING_COMPONENTS}
    except (KeyError, TypeError, ValueError):
        return None


def composite(
    components: Mapping[str, float | int] | None,
    *,
    drop: Iterable[str] | None = None,
    zero: Iterable[str] | None = None,
) -> int | None:
    """Equal-weight mean of components (0–100). Ablation: `drop` omits keys; `zero` forces keys to 0.

    Dropping leaves the mean over the remaining keys. Zeroing keeps the denominator (useful when
    comparing “without this signal” while holding the scale fixed). Returns None when nothing remains.
    """
    cleaned = clean_components(components) if components is not None else None
    if cleaned is None and isinstance(components, Mapping):
        # Partial dicts allowed for ablation math only when every present value clamps.
        try:
            cleaned = {k: clamp_score(components[k]) for k in GAMING_COMPONENTS if k in components}
        except (TypeError, ValueError):
            return None
    if not cleaned:
        return None
    skip = {str(x) for x in (drop or ())}
    zed = {str(x) for x in (zero or ())}
    vals = []
    for k, v in cleaned.items():
        if k in skip:
            continue
        vals.append(0 if k in zed else int(v))
    if not vals:
        return None
    return int(round(sum(vals) / len(vals)))


def ablation_table(components: Mapping[str, float | int]) -> dict[str, int | None]:
    """Full composite plus leave-one-out (drop) and zero-out composites for each component.

    Keys:
      - `full`: equal-weight mean of all nine
      - `drop:<name>`: mean with that component omitted
      - `zero:<name>`: mean with that component forced to 0 (denominator unchanged)
    """
    base = clean_components(components)
    if base is None:
        return {"full": None}
    out: dict[str, int | None] = {"full": composite(base)}
    for k in GAMING_COMPONENTS:
        out[f"drop:{k}"] = composite(base, drop=(k,))
        out[f"zero:{k}"] = composite(base, zero=(k,))
    return out


def components_from_signals(signals: Mapping | None) -> dict[str, int] | None:
    """Optional weak priors from nomination signals only — never a substitute for the judge.

    Used by eval / offline scaffolding when a clip has signal strengths but no AI gaming
    scores yet. Returns None when there is nothing usable. Does not invent events.
    """
    if not isinstance(signals, Mapping) or not signals:
        return None
    def unit(key: str) -> float:
        try:
            return max(0.0, min(1.0, float(signals.get(key) or 0.0)))
        except (TypeError, ValueError):
            return 0.0
    audio_u = max(unit("audio"), unit("loudness"), unit("bursts"), unit("flux"))
    chat_u = max(unit("chat"), unit("chat_motion"))
    if audio_u <= 0 and chat_u <= 0:
        return None
    # Only fill audio/chat-ish dimensions; leave the rest unset so clean_components stays None
    # unless the caller merges with a full judge reply.
    return {
        "audio": clamp_score(50 + 49 * audio_u) if audio_u else 0,
        "chat": clamp_score(50 + 49 * chat_u) if chat_u else 0,
    }


def rubric_lines() -> list[str]:
    """Judge-facing bullet lines for each gaming component."""
    return [f"{k} = {GAMING_RUBRIC[k]}" for k in GAMING_COMPONENTS]


def known_keys() -> Sequence[str]:
    return GAMING_COMPONENTS
