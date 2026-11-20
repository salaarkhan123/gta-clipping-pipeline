"""The words a clip ships with (app/pipeline/copy_check.py): no tool names, no filler, no claims the clip does not
make, clean hashtags; anything removed is replaced only with the clip's own words."""
from app.pipeline import _template_game
from app.pipeline.copy_check import check_copy, hashtags, problems

SAID = ("Bro he was one shot. I hit him with the Sheriff and he just dropped. "
        "Thirty kills this game, no way. Let's go!")
LINES = ["Bro he was one shot.", "I hit him with the Sheriff and he just dropped.", "Thirty kills this game, no way.",
         "Let's go!"]


def meta(**kw):
    base = {"title": "Sheriff one-tap to close the round", "titles": ["Sheriff one-tap to close the round",
            "30 kills and still hungry", "He dropped in one shot"], "hook": "One Sheriff shot, he drops",
            "description": "A one-shot Sheriff kill that ends the round. Thirty kills in one game.",
            "hashtags": ["valorant", "sheriff", "clutch"]}
    return {**base, **kw}


def test_good_copy_ships_as_it_is():
    out, found = check_copy(meta(), SAID, "valorant", LINES)
    assert found == [] and out == meta()


def test_no_other_product_or_tool_is_ever_named():
    m = meta(titles=["Made with OpusClip: Sheriff ace", "Sheriff one-tap to close the round"],
             hook="ChatGPT picked this Sheriff shot", description="Clipped by Wayin. A one-shot Sheriff kill.",
             hashtags=["opusclip", "AI", "valorant", "aimbot", "WayinVideo"])
    out, found = check_copy(m, SAID, "valorant", LINES)
    text = " ".join([out["title"], *out["titles"], out["hook"] or "", out["description"], *out["hashtags"]]).lower()
    assert not any(name in text for name in ("opus", "wayin", "chatgpt", " ai "))
    assert out["titles"] == ["Sheriff one-tap to close the round"] and out["description"] == "A one-shot Sheriff kill."
    assert out["hashtags"] == ["valorant", "aimbot"]                       # "aim..." is not "ai"
    assert out["hook"] in LINES or out["hook"] in {"Bro he was one shot", "Thirty kills this game, no way"}
    assert {"title:banned:opusclip", "hook:banned:chatgpt", "description:banned:wayin"} <= set(found)


def test_filler_and_unsupported_claims_go_numbers_must_be_said():
    out, found = check_copy(meta(hook="You won't believe this", titles=["World record 50 kill game",
                                                                         "30 kills and still hungry"]), SAID, None, LINES)
    assert out["titles"] == ["30 kills and still hungry"]                  # thirty was said; 50 and a record were not
    assert "title:claim:world record" in found and "title:number:50" in found and "hook:filler:you won't believe" in found
    assert out["hook"] and "believe" not in out["hook"]
    assert problems("1v5 in GTA 5 and CS2", "one versus five") == []      # a game's name is not a number claimed
    assert problems("Top 3 plays", "the plays") == ["number:3"]


def test_the_last_title_is_kept_with_the_bad_words_cut_out():
    out, _ = check_copy(meta(titles=["OpusClip: Sheriff one-tap"], title="OpusClip: Sheriff one-tap"), SAID, None, LINES)
    assert out["titles"] == ["Sheriff one-tap"] == [out["title"]]


def test_hashtags_are_clean_spam_free_and_lead_with_the_game():
    assert hashtags(["#FYP", "Viral", "#Clutch", "clutch", "sheriff", "2024", "gaming", "ace", "one"], "valorant") == \
        ["valorant", "clutch", "sheriff", "gaming", "ace"]
    assert hashtags(["gta", "heist"], None) == ["gta", "heist"]


def test_the_game_comes_from_the_template_and_other_is_none():
    assert _template_game(None) is None and _template_game("no-such-template") is None
    from app.templates import TEMPLATES
    game_tpl = next(t for t in TEMPLATES.values() if t.get("game") == "valorant")
    assert _template_game(game_tpl["id"]) == "valorant"
