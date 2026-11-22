"""AS-1 gaming highlight-quality components: composite, ablation, parse, honesty."""
import json
from pathlib import Path

import httpx

from app.ai import (
    GAMING_SCORING_VERSION,
    LEGACY_VERSION,
    SCORING_VERSION,
    ClaudeAI,
    parse_meta,
    rating_of,
    signal_meta,
)
from app.gaming_rating import (
    GAMING_COMPONENTS,
    HONESTY,
    ablation_table,
    clean_components,
    composite,
    components_from_signals,
)
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gaming_rating_eval as gre  # noqa: E402


NINE = {
    "hook": 80,
    "intensity": 70,
    "kills_clutches": 60,
    "funny": 40,
    "reactions": 75,
    "audio": 65,
    "chat": 20,
    "unexpected": 55,
    "game_context": 70,
}
FIVE = {"hook": 82, "payoff": 91, "clarity": 64, "emotion": 77, "pacing": 56}
BASE = {
    "titles": ["a", "b", "c"],
    "hook": "He never saw it",
    "hashtags": ["gta"],
    "reason": "Strong clutch with a clear open.",
    "kind": "clutch",
    "virality": FIVE,
    "gaming": NINE,
}


def test_composite_and_ablation_hooks():
    assert clean_components(NINE) == NINE
    assert composite(NINE) == round(sum(NINE.values()) / 9)
    table = ablation_table(NINE)
    assert table["full"] == composite(NINE)
    assert table["drop:chat"] == composite(NINE, drop=("chat",))
    assert table["zero:chat"] == composite(NINE, zero=("chat",))
    assert table["drop:chat"] != table["full"]
    assert table["zero:chat"] < table["full"]
    assert clean_components({"hook": 1}) is None
    assert "virality" not in HONESTY.lower() or "not" in HONESTY.lower()
    assert "forecast of views" in HONESTY.lower() or "not a forecast" in HONESTY.lower()


def test_parse_meta_stores_gaming_beside_editorial_and_overall_is_gaming_mean():
    meta = parse_meta(BASE)
    assert meta["scores"] == FIVE
    assert meta["gaming_scores"] == NINE
    assert meta["scoring_version"] == GAMING_SCORING_VERSION == "judge-v3-gaming"
    assert meta["virality"]["score"] == composite(NINE)
    rated = rating_of(meta)
    assert rated["scores"] == NINE
    assert rated["editorial_scores"] == FIVE
    assert rated["gaming_scores"] == NINE
    assert rated["rating"] == composite(NINE)


def test_v2_only_reply_still_works_without_gaming():
    meta = parse_meta({"titles": ["a", "b", "c"], "hashtags": [], "virality": FIVE})
    assert meta["scores"] == FIVE and meta["scoring_version"] == SCORING_VERSION
    assert "gaming_scores" not in meta
    assert rating_of(meta)["scores"] == FIVE and rating_of(meta)["gaming_scores"] is None


def test_unrated_without_api_key_path_and_signals_have_no_rating():
    assert rating_of(signal_meta(0.9)) is None
    assert rating_of(None) is None
    assert rating_of({"title": "t", "source": "signals", "virality": {"score": 80}}) is None
    old = parse_meta({"titles": ["a"], "hashtags": [], "virality": {"hook": 90, "flow": 80, "value": 70, "trend": 60}})
    assert rating_of(old)["scoring_version"] == LEGACY_VERSION


def test_tool_schema_requires_gaming_and_prompt_rejects_virality_percent_claim():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "clip_meta", "input": BASE}]})

    ai = ClaudeAI("k", "claude-haiku-5-5", httpx.Client(transport=httpx.MockTransport(handler)))
    meta = ai.clip_meta("clutch play", {"length": 30.0, "signals": {"audio": 1.0}}, None)
    assert rating_of(meta)["gaming_scores"] == NINE
    body = seen[0]
    props = body["tools"][0]["input_schema"]["properties"]
    assert body["tools"][0]["input_schema"]["required"] == [
        "titles", "hook", "hashtags", "virality", "gaming", "reason", "kind",
    ]
    assert list(props["gaming"]["required"]) == list(GAMING_COMPONENTS)
    system = body["system"].lower()
    assert "chance of going viral" in system or "not a forecast of views" in system
    assert "virality percentage" in system or "not a virality" in system


def test_label_sheet_stats_are_empty_and_honest():
    sheet = Path(__file__).resolve().parents[1] / "eval" / "gi-gta-label-sheet.csv"
    stats = gre.sheet_stats(sheet)
    assert stats["rows"] >= 1
    assert stats["human_rated_complete"] == 0
    assert stats["metrics_ready"] is False
    assert stats["ndcg_claimed"] is False
    assert stats["virality_percent_claimed"] is False
    assert stats["treats_clutch_score_as_gt"] is False


def test_components_from_signals_are_partial_priors_only():
    assert components_from_signals(None) is None
    partial = components_from_signals({"audio": 0.8, "chat_motion": 0.2})
    assert partial["audio"] > 50 and partial["chat"] > 50
    assert clean_components(partial) is None  # not a full nine
