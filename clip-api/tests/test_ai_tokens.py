"""The judge call can't be cut off by max_tokens, and a cut-off or refused reply is logged, not silently dropped."""
import json
import logging

import httpx

from app.ai import MAX_TOKENS, TOOL, ClaudeAI

GOOD = {"title": "Clean getaway", "description": "d", "hashtags": ["gta6"],
        "virality": {"hook": 70, "flow": 60, "value": 80, "trend": 50}, "reason": "y"}


def ai_with(reply, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply)
    return ClaudeAI("k", "claude-haiku-5-5", httpx.Client(transport=httpx.MockTransport(handler)))


def test_request_leaves_room_for_the_whole_tool_call():
    seen = []
    ai_with({"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "clip_meta", "input": GOOD}]},
            seen).clip_meta("x", {"length": 30})
    body = seen[0]
    # Forced tool call: Haiku 5.5 skips thinking, so the budget only has to hold the tool input.
    assert body["tool_choice"] == {"type": "tool", "name": TOOL["name"]} and "thinking" not in body
    # A worst case tool input (60 + 150 chars, 5 tags, 4 scores, a 200-char reason) is well under 1024 tokens.
    worst = json.dumps({"title": "x" * 60, "description": "y" * 150, "hashtags": ["t" * 30] * 5,
                        "virality": {k: 100 for k in ("hook", "flow", "value", "trend")}, "reason": "z" * 200})
    assert body["max_tokens"] == MAX_TOKENS >= 1024 and len(worst) < MAX_TOKENS


def test_cut_off_reply_is_logged_and_kept_only_with_a_title(caplog):
    caplog.set_level(logging.WARNING, logger="clipapi")
    partial = {"stop_reason": "max_tokens", "content": [{"type": "tool_use", "name": "clip_meta",
                                                         "input": {"virality": {"hook": 50}}}]}
    assert ai_with(partial).clip_meta("x", {}) is None
    assert "hit max_tokens" in caplog.text
    caplog.clear()
    titled = {"stop_reason": "max_tokens", "content": [{"type": "tool_use", "name": "clip_meta",
                                                        "input": {**GOOD, "reason": ""}}]}
    assert ai_with(titled).clip_meta("x", {})["title"] == "Clean getaway"
    assert "hit max_tokens" in caplog.text


def test_refusal_is_logged_and_returns_nothing(caplog):
    caplog.set_level(logging.WARNING, logger="clipapi")
    refused = {"stop_reason": "refusal", "stop_details": {"type": "refusal", "category": "general_harms"},
               "content": []}
    assert ai_with(refused).clip_meta("x", {}) is None
    assert "refused" in caplog.text and "general_harms" in caplog.text
