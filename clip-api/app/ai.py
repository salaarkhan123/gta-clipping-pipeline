"""Optional AI layer: titles, descriptions, hashtags and a virality estimate for each clip.

Uses the Anthropic Messages API when ANTHROPIC_API_KEY is set. Every failure is swallowed: a clip without
AI text is still a finished clip. The virality number is a model's opinion, not a forecast of views.
"""
import base64
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

import httpx

from .config import get_settings

log = logging.getLogger("clipapi.ai")
API_URL = "https://api.anthropic.com/v1/messages"
PARTS = ("hook", "flow", "value", "trend")

SYSTEM = (
    "You write social copy for short gaming clips (TikTok, Shorts, Reels) and rate how well a clip is likely to "
    "perform. Reply with ONE JSON object and nothing else:\n"
    '{"title": "<max 60 chars, no hashtags, no quotes>", "description": "<max 150 chars>", '
    '"hashtags": ["<3 to 5 tags without #>"], '
    '"virality": {"hook": 0-100, "flow": 0-100, "value": 0-100, "trend": 0-100}, '
    '"reason": "<one sentence on why it would or would not perform>"}\n'
    "hook = how strongly the first 3 seconds grab attention; flow = pacing and whether it stands alone without "
    "context; value = how funny, impressive or surprising the moment is; trend = fit with what gaming audiences "
    "share. Be strict: an average clip scores around 50. Base everything only on the transcript, the frame and "
    "the signals given. Do not invent events, names or games that are not evident."
)


def _clamp(v, lo=0, hi=100) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return 50


def parse_meta(text: str) -> dict | None:
    """Extract and sanitise the JSON object from a model reply."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    v = raw.get("virality") if isinstance(raw.get("virality"), dict) else {}
    parts = {k: _clamp(v.get(k)) for k in PARTS}
    tags = raw.get("hashtags") if isinstance(raw.get("hashtags"), list) else []
    tags = [re.sub(r"[^A-Za-z0-9_]", "", str(t))[:30] for t in tags]
    title = str(raw.get("title") or "").strip().strip('"')[:80]
    if not title:
        return None
    return {"title": title, "description": str(raw.get("description") or "").strip()[:200],
            "hashtags": [t for t in tags if t][:5],
            "virality": {"score": round(sum(parts.values()) / len(parts)), **parts},
            "reason": str(raw.get("reason") or "").strip()[:240], "source": "ai"}


def signal_meta(score: float) -> dict:
    """Fallback when no AI key is set: an overall score from detection strength only."""
    return {"virality": {"score": _clamp(50 + 49 * min(1.0, max(0.0, score)))}, "source": "signals"}


class ClaudeAI:
    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None):
        self.api_key, self.model = api_key, model
        self.client = client or httpx.Client(timeout=45)

    def clip_meta(self, transcript: str, context: dict, thumb: Path | None = None) -> dict | None:
        content = []
        if thumb and Path(thumb).is_file():
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(Path(thumb).read_bytes()).decode()}})
        content.append({"type": "text", "text": (
            f"Clip length: {context.get('length', 0):.0f} s\n"
            f"Why it was picked (signal shares): {json.dumps(context.get('signals', {}))}\n"
            f"Transcript of the clip:\n{(transcript or '(no speech detected)')[:1500]}")})
        try:
            r = self.client.post(API_URL, headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                                                   "content-type": "application/json"},
                                 json={"model": self.model, "max_tokens": 500, "system": SYSTEM,
                                       "messages": [{"role": "user", "content": content}]})
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
            return parse_meta(text)
        except Exception as e:   # never fail a job over optional copy
            log.warning("AI metadata failed: %s", str(e)[:200])
            return None


@lru_cache
def default_ai():
    s = get_settings()
    return ClaudeAI(s.anthropic_api_key, s.ai_model) if s.anthropic_api_key else None
