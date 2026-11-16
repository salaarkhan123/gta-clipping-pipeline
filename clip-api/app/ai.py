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
MAX_TOKENS = 1024

SYSTEM = (
    "You package short gaming clips (TikTok, Shorts, Reels) for GTA clippers, and rate how well a clip is likely "
    "to perform. Answer with the clip_meta tool.\n\n"
    "TITLES. Give exactly 3 different titles in the style of the best GTA RP and GTA Online Shorts channels. Each "
    "one: under 60 characters, plain words, specific to what actually happens in THIS clip (who, what, how it "
    "ends), and built on curiosity: point at the payoff without giving it away. Make the three different angles: "
    "(1) the event with its twist, (2) the streamer's reaction or the best line said, close to their own words, "
    "(3) a question or a cliffhanger. Never use a template like \"Streamer does X in GTA\", never empty hype "
    "words (insane, crazy, epic, you won't believe) and never hashtags or quotation marks. A title must not "
    "promise anything the clip does not show: a title that misdescribes the clip is worse than a plain one.\n\n"
    "HOOK. One line of on-screen text, 6 words at most, shown over the first seconds of the clip. It tells a "
    "viewer why to keep watching and must be true to the clip. No hashtags, no emoji, no full stop.\n\n"
    "RATING. virality has four parts, each 0-100: hook = how strongly the first 3 seconds grab attention; flow = "
    "pacing and whether it stands alone without context; value = how funny, impressive or surprising the moment "
    "is; trend = fit with what gaming audiences share. Be strict: an average clip scores around 50. Base "
    "everything only on the transcript, the frame and the signals given. Do not invent events, names or games "
    "that are not evident; if the game is not clearly GTA, write for the game you see. If the frame or transcript "
    "shows a menu, loading screen, channel branding or intro card, ad, AFK or dead air rather than a real moment, "
    "score every part below 15.\n\n"
    "CUT. When the transcript lines carry time marks like [12.4], also choose the cut, in seconds on those marks: "
    "cut.start and cut.end are the best 15 to 45 second clip of this moment. Start right where the action or the "
    "reaction begins, not on the build-up before it, and end just after the payoff, not on a trailing silence. "
    "cut.peak is the second where the most striking 1 to 2 seconds begin (the loudest reaction or the punchline). "
    "Stay within the marks you were given."
)

TOOL = {
    "name": "clip_meta",
    "description": "Record the social copy and the virality rating for this clip.",
    "input_schema": {
        "type": "object",
        "properties": {
            "titles": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                       "description": "Exactly 3 titles, each under 60 chars, three different angles."},
            "hook": {"type": "string", "description": "On-screen text for the first seconds: 6 words at most."},
            "description": {"type": "string", "description": "Max 150 chars."},
            "hashtags": {"type": "array", "items": {"type": "string"}, "description": "3 to 5 tags without #."},
            "virality": {"type": "object", "properties": {k: {"type": "integer", "minimum": 0, "maximum": 100}
                                                          for k in PARTS}, "required": list(PARTS)},
            "reason": {"type": "string",
                       "description": "One sentence, max 200 chars, on why it would or would not perform."},
            "cut": {"type": "object", "description": "Only when the transcript has time marks: the clip to cut.",
                    "properties": {"start": {"type": "number"}, "end": {"type": "number"}, "peak": {"type": "number"}},
                    "required": ["start", "end", "peak"]},
        },
        "required": ["titles", "hook", "hashtags", "virality", "reason"],
    },
}


def _clamp(v, lo=0, hi=100) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return 50


def _title(value) -> str:
    title = str(value or "").strip()
    if len(title) >= 2 and title[0] == title[-1] and title[0] in "\"'":   # wrapped in quotes: unwrap
        title = title[1:-1].strip()
    return title[:80]


def _hook(value) -> str | None:
    """On-screen hook text: one line, at most 6 words and 48 characters, no markup. None if there is none."""
    words = re.sub(r"[{}\\\n\r#]", " ", str(value or "")).strip().strip(".").split()
    text = " ".join(words[:6])[:48].strip()
    return text or None


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
    given = raw.get("titles") if isinstance(raw.get("titles"), list) else []
    titles = []
    for candidate in [*given, raw.get("title")]:           # "title" alone is the older reply shape
        title = _title(candidate)
        if title and title.lower() not in {x.lower() for x in titles}:
            titles.append(title)
    titles = titles[:3]
    if not titles:
        return None
    title = titles[0]
    out = {"title": title, "titles": titles, "hook": _hook(raw.get("hook")), "description": str(raw.get("description") or "").strip()[:200],
           "hashtags": [t for t in tags if t][:5],
           "virality": {"score": round(sum(parts.values()) / len(parts)), **parts},
           "reason": str(raw.get("reason") or "").strip()[:240], "source": "ai"}
    cut = raw.get("cut")
    if isinstance(cut, dict):
        try:      # the pipeline checks the numbers against the clip; here they only have to be numbers
            out["trim"] = {k: float(cut[k]) for k in ("start", "end", "peak")}
        except (KeyError, TypeError, ValueError):
            pass
    return out


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
        lines = context.get("lines")
        if lines:      # timed lines: the judge also chooses where the clip starts, ends and peaks
            a, b = context.get("window", (0, context.get("length", 0)))
            said = "\n".join(f"[{s:.1f}] {text}" for s, text in lines)[:2500]
            body_text = (f"The moment was detected between {a:.1f} and {b:.1f} on these time marks.\n"
                         f"Transcript with time marks (seconds):\n{said}")
        else:
            body_text = f"Transcript of the clip:\n{(transcript or '(no speech detected)')[:1500]}"
        content.append({"type": "text", "text": (
            f"Clip length: {context.get('length', 0):.0f} s\n"
            f"Why it was picked (signal shares): {json.dumps(context.get('signals', {}))}\n" + body_text)})
        # The forced tool call means Haiku 5.5 skips thinking, so max_tokens only has to hold the tool input
        # (~150-300 tokens). 1024 leaves room for a long reason; only the tokens produced are billed.
        body = {"model": self.model, "max_tokens": MAX_TOKENS, "system": SYSTEM, "tools": [TOOL],
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
                data = r.json()
                stop = data.get("stop_reason")
                if stop == "refusal":
                    log.warning("AI metadata refused: %s", str(data.get("stop_details") or "")[:200])
                    return None
                if stop == "max_tokens":
                    log.warning("AI metadata hit max_tokens (%d); keeping it only if it still has a title", MAX_TOKENS)
                blocks = data.get("content", [])
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
