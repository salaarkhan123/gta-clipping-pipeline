"""Optional AI layer: titles, descriptions, hashtags and a virality estimate for each clip.

Uses the Anthropic Messages API when ANTHROPIC_API_KEY is set. Every failure is swallowed: a clip without
AI text is still a finished clip. The virality number is a model's opinion, not a forecast of views.
"""
import base64
import json
import logging
import re
import time
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
    "the signals given. Do not invent events, names or games that are not evident. If the frame or transcript shows "
    "a menu, loading screen, channel branding or intro card, ad, AFK or dead air rather than a real moment, score "
    "every part below 15."
)

TOOL = {
    "name": "clip_meta",
    "description": "Record the social copy and the virality rating for this clip.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Max 60 chars, no hashtags, no quotes."},
            "description": {"type": "string", "description": "Max 150 chars."},
            "hashtags": {"type": "array", "items": {"type": "string"}, "description": "3 to 5 tags without #."},
            "virality": {"type": "object", "properties": {k: {"type": "integer", "minimum": 0, "maximum": 100}
                                                          for k in PARTS}, "required": list(PARTS)},
            "reason": {"type": "string", "description": "One sentence on why it would or would not perform."},
        },
        "required": ["title", "hashtags", "virality", "reason"],
    },
}


def _clamp(v, lo=0, hi=100) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return 50


def parse_meta(text) -> dict | None:
    """Sanitise a model reply: a tool-call input dict, or text containing one JSON object."""
    if isinstance(text, dict):
        raw = text
    else:
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
    title = str(raw.get("title") or "").strip()
    if len(title) >= 2 and title[0] == title[-1] and title[0] in "\"'":   # wrapped in quotes: unwrap
        title = title[1:-1].strip()
    title = title[:80]
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
        context = context if isinstance(context, dict) else {}
        content = []
        if isinstance(thumb, (str, Path)) and Path(thumb).is_file():
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(Path(thumb).read_bytes()).decode()}})
        content.append({"type": "text", "text": (
            f"Clip length: {context.get('length', 0):.0f} s\n"
            f"Why it was picked (signal shares): {json.dumps(context.get('signals', {}))}\n"
            f"Transcript of the clip:\n{(transcript or '(no speech detected)')[:1500]}")})
        body = {"model": self.model, "max_tokens": 600, "system": SYSTEM, "tools": [TOOL],
                "tool_choice": {"type": "tool", "name": TOOL["name"]},
                "messages": [{"role": "user", "content": content}]}
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        for attempt in (1, 2):
            try:
                r = self.client.post(API_URL, headers=headers, json=body)
                if r.status_code in (429, 500, 502, 503, 529) and attempt == 1:
                    time.sleep(float(r.headers.get("retry-after") or 3))
                    continue
                r.raise_for_status()
                blocks = r.json().get("content", [])
                reply = next((b.get("input") for b in blocks if b.get("type") == "tool_use"), None)
                if reply is None:   # no tool call: fall back to any JSON in the text
                    reply = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                meta = parse_meta(reply)
                if meta is None:
                    log.warning("AI metadata unreadable: %s", str(reply)[:300])
                return meta
            except Exception as e:   # never fail a job over optional copy
                if attempt == 2:
                    log.warning("AI metadata failed: %s", str(e)[:200])
        return None


@lru_cache
def default_ai():
    s = get_settings()
    return ClaudeAI(s.anthropic_api_key, s.ai_model) if s.anthropic_api_key else None
