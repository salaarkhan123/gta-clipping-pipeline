"""The template catalogue: format, game filter, preview posters, and that a template never changes a price.
The game-type presets, the kind filter and the poster route are in test_template_presets.py."""
import importlib.util
import json
import re
import subprocess
import xml.dom.minidom
from pathlib import Path

import pytest

from app import templates as catalogue
from app.pipeline import PipelineOptions
from app.pipeline.captions import CAPTION_STYLES
from app.routes_media import ClipOptions
from app.templates import (DURATIONS, GAME_NAMES, GAMES, HOOK_POSITIONS, HOOK_STYLES, KINDS, LAYOUT_PANELS, LAYOUTS,
                           PREVIEW_VIDEOS, PROVISIONAL_LAYOUTS, PUBLIC_FIELDS, RESERVED_IDS, TEMPLATES, TUNING_FIELDS,
                           problems, with_tuning)
from tests.test_api import balance, upload

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "templates"
SCRIPT = ROOT / "scripts" / "make_template_previews.py"
GAME_TEMPLATES = {tid: t for tid, t in TEMPLATES.items() if t["kind"] == "game"}
PRESETS = {tid: t for tid, t in TEMPLATES.items() if t["kind"] == "preset"}

# The five templates that were live before the catalogue grew: their options and tuning are frozen.
LEGACY = {
    "gta-rp-reaction": ({"layout": "auto", "caption_style": "pop", "clip_length": 30, "tighten": True, "punch_zoom": True,
                         "flash_forward": True, "hook_overlay": True}, {"audio": 0.7, "chat_motion": 1.0}, 0.25, "GTA roleplay:"),
    "gta-online-chaos": ({"layout": "auto", "caption_style": "bold", "clip_length": 20, "tighten": True, "punch_zoom": True,
                          "flash_forward": True, "hook_overlay": True}, {"audio": 1.0, "chat_motion": 0.8}, 0.1, "GTA Online chaos:"),
    "car-chase": ({"layout": "auto", "caption_style": "clean", "clip_length": 40, "tighten": False, "punch_zoom": True,
                   "flash_forward": True, "hook_overlay": True}, {"audio": 0.9, "chat_motion": 0.8}, 0.1, "Car chases:"),
    "heist-moments": ({"layout": "auto", "caption_style": "boxed", "clip_length": 45, "tighten": True, "punch_zoom": True,
                       "flash_forward": False, "hook_overlay": True}, {"audio": 0.8, "chat_motion": 0.8}, 0.15, "Heists, robberies,"),
    "funny-fails": ({"layout": "auto", "caption_style": "neon", "clip_length": 15, "tighten": True, "punch_zoom": True,
                     "flash_forward": False, "hook_overlay": True}, {"audio": 1.0, "chat_motion": 0.9}, 0.2, "Fails, glitches,"),
}


def load_script():
    spec = importlib.util.spec_from_file_location("make_template_previews", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the format -------------------------------------------------------------------------------------------------

def test_every_template_follows_the_format():
    assert [p for tid, t in TEMPLATES.items() for p in problems(tid, t)] == []
    for tid, t in TEMPLATES.items():
        assert set(t) == set(PUBLIC_FIELDS) | set(TUNING_FIELDS), tid          # nothing extra, nothing missing
        assert t["kind"] in KINDS and t["layout"] in LAYOUTS, tid
        assert t["caption_style"] in CAPTION_STYLES, tid                       # a style the renderer has today
        assert t["preview"] == {"video": None, "poster": f"/v1/templates/{tid}/poster"}, tid
    assert len(GAME_TEMPLATES) == 31 and len(GAME_TEMPLATES) + len(PRESETS) == len(TEMPLATES)
    for tid, t in GAME_TEMPLATES.items():
        assert t["game"] in GAMES and t["duration"] in DURATIONS, tid
        assert t["hook"]["style"] in HOOK_STYLES and t["hook"]["position"] in HOOK_POSITIONS, tid
        assert t["options"]["layout"] == t["layout"], tid                      # the layout's own name, not an older one


def test_panels_say_where_the_camera_is_and_never_sit_in_the_options():
    for tid, t in TEMPLATES.items():
        camera, ratio = t["panels"]["camera"], t["panels"]["split_ratio"]
        assert set(t["panels"]) == {"camera", "split_ratio"}, tid
        assert camera in ("top", "bottom", None) and (ratio is None) is (camera is None), tid
        assert ratio is None or 0.25 <= ratio <= 0.75, tid
        assert not {"camera", "split_ratio", "panels"} & set(t["options"]), tid   # not clip options yet
    for tid, t in GAME_TEMPLATES.items():                                      # a game template: its layout's own boxes
        assert (t["panels"]["camera"], t["panels"]["split_ratio"]) == LAYOUT_PANELS.get(t["layout"], (None, None)), tid
    assert {t["layout"] for t in TEMPLATES.values() if t["panels"]["camera"]} == set(LAYOUT_PANELS)
    assert TEMPLATES["lol-voice-comms"]["panels"] == {"camera": "top", "split_ratio": 0.33}
    assert TEMPLATES["lol-teamfight"]["panels"] == {"camera": "bottom", "split_ratio": 0.7}
    assert TEMPLATES["cs2-clutch"]["panels"] == TEMPLATES["car-chase"]["panels"] == {"camera": None, "split_ratio": None}


def test_panels_match_the_boxes_the_renderer_draws():
    layouts = pytest.importorskip("app.pipeline.layouts")
    splits = getattr(layouts, "_SPLITS", None)                                 # name: (camera first?, camera's share stacked, ...)
    if splits is None:
        pytest.skip("the renderer no longer keeps its stacked layouts in _SPLITS")
    assert set(splits) == set(LAYOUT_PANELS)
    for name, (camera_first, share, *_rest) in splits.items():
        camera, ratio = LAYOUT_PANELS[name]
        assert camera == ("top" if camera_first else "bottom"), name
        assert ratio == round(share if camera_first else 1 - share, 2), name   # the top panel's share of the height


def test_the_format_check_catches_a_bad_template():
    good = TEMPLATES["valorant-clutch"]
    for change, word in [({"layout": "trio"}, "layout"), ({"duration": "10-20"}, "duration"), ({"game": "gta"}, "game"),
                         ({"caption_style": "comic"}, "caption_style"), ({"judge_focus": "x" * 401}, "judge_focus"),
                         ({"hook": {**good["hook"], "style": "angry"}}, "hook style"),
                         ({"hook": {**good["hook"], "position": "middle"}}, "hook position"),
                         ({"options": {**good["options"], "clip_length": 12}}, "clip_length"),
                         ({"options": {**good["options"], "judge_focus": "x"}}, "tuning"),
                         ({"weights": {"audio": 1.0}}, "weights"), ({"provisional": True}, "provisional"),
                         ({"kind": "bundle"}, "kind"), ({"panels": {"camera": "bottom", "split_ratio": 0.33}}, "panels.camera"),
                         ({"panels": {"camera": "top", "split_ratio": 0.9}}, "split_ratio"),
                         ({"panels": {"camera": "top", "split_ratio": 0.4}}, "split_ratio disagrees"),
                         ({"panels": {"camera": "top"}}, "panels needs"),
                         ({"options": {**good["options"], "split_ratio": 0.33}}, "panel sizes inside options"),
                         ({"options": {**good["options"], "layout": "auto"}}, "options.layout"),
                         ({"preview": {"video": None, "poster": "templates/valorant-clutch/poster.svg"}}, "preview")]:
        found = problems("valorant-clutch", {**good, **change})
        assert found and any(word in p for p in found), (change, found)


def test_ids_and_names_are_unique_and_ids_are_url_safe():
    assert len(TEMPLATES) == len(catalogue._CATALOGUE) + len(catalogue._PRESETS)   # no id used twice
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", tid) and len(tid) <= 40 for tid in TEMPLATES)
    assert len({t["name"] for t in TEMPLATES.values()}) == len(TEMPLATES)
    assert not set(TEMPLATES) & set(GAMES)                                     # an id is never just a game name
    assert RESERVED_IDS == ("custom", "games") and not set(TEMPLATES) & set(RESERVED_IDS)   # nor a fixed path
    for bad in ("custom", "games", "Valorant-Clutch", "valorant_clutch", "../valorant-clutch", "valorant-clutch/x", ""):
        assert any("url-safe" in p for p in problems(bad, {**TEMPLATES["valorant-clutch"], "id": bad})), bad


def test_every_game_has_at_least_two_different_templates():
    assert GAMES == ("lol", "gta5", "wow", "ow2", "minecraft", "apex", "valorant", "fortnite", "dota2", "rust", "cs2", "other")
    assert set(GAME_NAMES) == set(GAMES)
    for game in GAMES:
        mine = [t for t in GAME_TEMPLATES.values() if t["game"] == game]
        assert len(mine) >= 2, game
        looks = {(t["layout"], t["caption_style"], t["duration"], t["hook"]["style"]) for t in mine}
        assert len(looks) == len(mine), game                                   # no two of a game look alike
        assert len({t["judge_focus"] for t in mine}) == len(mine), game
    # across the catalogue: no two option sets alike, and every layout we may name is used
    assert len({json.dumps(t["options"], sort_keys=True) for t in GAME_TEMPLATES.values()}) == len(GAME_TEMPLATES)
    assert {t["layout"] for t in GAME_TEMPLATES.values()} == set(LAYOUTS)
    assert not {"trio", "grid4", "ots"} & set(LAYOUTS)
    # game templates grouped by game in GAMES order, then the presets
    assert list(TEMPLATES) == [tid for g in GAMES for tid, t in TEMPLATES.items() if t["game"] == g] + list(PRESETS)


def test_the_judge_focus_names_its_game_and_fits_what_the_judge_reads():
    for tid, t in TEMPLATES.items():
        assert len(t["judge_focus"]) <= 400, tid                               # app/ai.py cuts the focus at 400 characters
    for tid, t in GAME_TEMPLATES.items():
        if t["game"] not in ("gta5", "other") or tid == "gta5-street-race":
            first = GAME_NAMES.get(t["game"], "").split()[0] if t["game"] != "gta5" else "GTA"
            assert first in t["judge_focus"], tid


def test_every_options_set_is_accepted_by_todays_clip_maker():
    for tid, t in TEMPLATES.items():
        sent = ClipOptions(template=tid, **t["options"])                       # extra or invalid fields would raise
        assert sent.caption_style == t["caption_style"] and sent.aspect == t["aspect"], tid
        PipelineOptions(**with_tuning({"template": tid, **t["options"]}))      # and the pipeline takes the tuned set


def test_the_five_old_ids_still_resolve_with_the_same_options_and_tuning():
    for tid, (options, weights, bonus, focus) in LEGACY.items():
        t = TEMPLATES[tid]
        assert t["game"] == "gta5" and t["options"] == options, tid
        assert t["weights"] == weights and t["transcript_bonus"] == bonus and t["judge_focus"].startswith(focus), tid
        ClipOptions(template=tid)                                              # still a valid template id on its own
        tuned = with_tuning({"template": tid, "clip_length": 30})
        assert tuned["weights"] == weights and tuned["clip_length"] == 30


def test_template_layouts_are_ones_the_renderer_has():
    layouts = pytest.importorskip("app.pipeline.layouts")                      # the render agent's module, when merged
    assert set(LAYOUTS) <= set(layouts.LAYOUTS)
    allowed = getattr(layouts, "ALLOWED", None)
    if allowed:
        for tid, t in TEMPLATES.items():
            assert t["layout"] in allowed[t["aspect"]], tid


def test_gameplay_a_and_b_templates_are_marked_provisional():
    assert set(PROVISIONAL_LAYOUTS) == {"gameplay_a", "gameplay_b"}
    for tid, t in GAME_TEMPLATES.items():
        assert t["provisional"] is (t["layout"] in PROVISIONAL_LAYOUTS), tid
    for tid, t in TEMPLATES.items():
        assert (t["provisional_reason"] is not None) is t["provisional"], tid
    assert sum(t["provisional"] for t in GAME_TEMPLATES.values()) >= 2


# --- the API ----------------------------------------------------------------------------------------------------

def test_the_list_shows_the_public_fields_and_never_the_tuning(client):
    listed = client.get("/v1/templates").json()["templates"]                   # no key needed
    assert [t["id"] for t in listed] == list(TEMPLATES)
    raw = json.dumps(listed)
    for t in listed:
        assert set(t) == set(PUBLIC_FIELDS), t["id"]
        assert not set(t) & set(TUNING_FIELDS) and not set(t["options"]) & set(TUNING_FIELDS), t["id"]
        assert set(t["preview"]) == {"video", "poster"} and set(t["panels"]) == {"camera", "split_ratio"}, t["id"]
        assert t["hook"] is None if t["kind"] == "preset" else set(t["hook"]) == {"enabled", "style", "position", "duration_ms"}
        assert TEMPLATES[t["id"]]["judge_focus"] not in raw                    # not even inside another field
    assert "judge_focus" not in raw and "transcript_bonus" not in raw and "weights" not in raw
    street = next(t for t in listed if t["id"] == "gta5-street-race")
    assert street["provisional"] is True and "provisional" in street["provisional_reason"]
    assert next(t for t in listed if t["id"] == "car-chase")["provisional"] is False


def test_the_game_filter_and_the_games_list(client):
    for game in GAMES:
        got = client.get("/v1/templates", params={"game": game}).json()["templates"]
        assert got and all(t["game"] == game for t in got), game
        assert [t["id"] for t in got] == [tid for tid, t in TEMPLATES.items() if t["game"] == game]
    bad = client.get("/v1/templates", params={"game": "tetris"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unknown_game"
    assert all(g in bad.json()["error"]["message"] for g in GAMES)             # the message lists the valid ones
    assert client.get("/v1/templates", params={"game": ""}).status_code == 422
    games = client.get("/v1/templates/games").json()
    assert [g["id"] for g in games["games"]] == list(GAMES)
    assert all(g["name"] == GAME_NAMES[g["id"]] and g["templates"] >= 2 for g in games["games"])
    assert sum(g["templates"] for g in games["games"]) == games["total"] == len(GAME_TEMPLATES)   # presets: no game
    assert next(g for g in games["games"] if g["id"] == "gta5") == {"id": "gta5", "name": "GTA 5", "templates": 6}


def test_no_template_id_changes_what_a_job_costs_or_renders(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    start = balance(client, headers)

    def reserve(options):
        r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": options}, headers=headers)
        assert r.status_code == 202, r.text
        client.post(f"/v1/jobs/{r.json()['job_id']}/cancel", headers=headers)
        return r.json()
    plain = reserve({"max_clips": 2})
    for tid in TEMPLATES:                                                      # every game template and every preset
        tuned = reserve({"max_clips": 2, "template": tid})
        assert tuned["credits_reserved"] == plain["credits_reserved"], tid
        assert {k: v for k, v in tuned["options"].items() if k not in ("template", *TUNING_FIELDS)} == \
               {k: v for k, v in plain["options"].items() if k not in ("template", *TUNING_FIELDS)}, tid
    assert balance(client, headers) == start                                   # every cancelled job was refunded in full


# --- preview assets ---------------------------------------------------------------------------------------------

def test_every_template_has_its_poster_and_it_is_what_the_script_draws():
    script = load_script()
    for tid, t in TEMPLATES.items():
        path = ASSETS / tid / "poster.svg"
        assert path.is_file(), tid                                             # the drawing, kept as the fallback
        assert catalogue.poster_file(tid) == (ASSETS / tid / "poster.webp", "image/webp"), tid   # the footage frame is served
        text = path.read_text(encoding="utf-8")
        assert text == script.poster_svg(t), f"{tid}: run scripts/make_template_previews.py --posters"
        xml.dom.minidom.parseString(text)                                      # well-formed
        assert t["name"] in text and "#b8ff3c" in text and "#3cf0ff" in text, tid
        assert "<image" not in text and "href" not in text and "data:" not in text, tid   # drawn, nothing embedded or linked
        assert ("PROVISIONAL" in text) is t["provisional"], tid
        assert ("PROVISIONAL PRESET" in text) is (t["kind"] == "preset"), tid
    assert {p.name for p in ASSETS.iterdir() if p.is_dir()} == set(TEMPLATES)  # no folder for a template that is gone


def test_no_footage_is_committed_unless_it_is_listed():
    committed = {p.parent.name for p in ASSETS.glob("*/preview.mp4")}
    assert committed == set(PREVIEW_VIDEOS)                                    # today: none of either
    media = [p for p in ASSETS.rglob("*") if p.is_file() and p.suffix.lower() not in (".svg", ".md")
             and p.name not in ("preview.mp4", "poster.webp")]
    assert media == []                                                         # no screenshots or other artwork
    # The only other images: one poster frame per template, rendered by the script from the owner's own footage.
    assert {p.parent.name for p in ASSETS.glob("*/poster.webp")} == set(TEMPLATES)


def test_the_script_writes_posters_and_refuses_footage_without_the_rights_flag(tmp_path, video, capsys):
    script = load_script()
    assert script.main(["--posters", "--out", str(tmp_path / "p")]) == 0
    assert len(list((tmp_path / "p").glob("*/poster.svg"))) == len(TEMPLATES)
    assert script.main([str(video), "--out", str(tmp_path / "v")]) == 2        # no --i-have-rights
    assert "permission" in capsys.readouterr().err and not (tmp_path / "v").exists()
    assert script.main([str(tmp_path / "missing.mp4"), "--i-have-rights"]) == 2
    assert script.main([str(video), "--i-have-rights", "--only", "nope"]) == 2


def test_the_script_renders_a_preview_clip_per_template(tmp_path, video):
    script = load_script()
    code = script.main([str(video), "--i-have-rights", "--start", "19", "--seconds", "3", "--out", str(tmp_path),
                        "--only", "cs2-frag-highlight,dota2-teamfight"])
    assert code == 0
    sizes = {}
    for tid in ("cs2-frag-highlight", "dota2-teamfight"):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                              "-of", "json", str(tmp_path / tid / "preview.mp4")], capture_output=True, text=True, check=True)
        data = json.loads(out.stdout)
        sizes[tid] = (data["streams"][0]["width"], data["streams"][0]["height"])
        assert 2.5 <= float(data["format"]["duration"]) <= 3.6, tid
    assert sizes == {"cs2-frag-highlight": (540, 960), "dota2-teamfight": (960, 540)}   # each in its template's shape
    assert sorted(p.parent.name for p in tmp_path.glob("*/preview.mp4")) == ["cs2-frag-highlight", "dota2-teamfight"]


def test_the_script_writes_a_poster_frame_per_template_in_its_shape(tmp_path, video):
    from PIL import Image
    script = load_script()
    assert script.main([str(video), "--poster-frames", "--out", str(tmp_path)]) == 2      # no --i-have-rights
    code = script.main([str(video), "--i-have-rights", "--poster-frames", "--start", "19", "--out", str(tmp_path),
                        "--only", "cs2-frag-highlight,dota2-teamfight"])
    assert code == 0
    sizes = {tid: Image.open(tmp_path / tid / "poster.webp").size for tid in ("cs2-frag-highlight", "dota2-teamfight")}
    assert sizes == {"cs2-frag-highlight": (360, 640), "dota2-teamfight": (640, 360)}     # each in its template's shape
    assert all((tmp_path / tid / "poster.webp").stat().st_size < 150_000 for tid in sizes)
