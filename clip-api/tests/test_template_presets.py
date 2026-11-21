"""Game-type presets (docs/CONTRACTS.md "Game-type presets"), the kind filter, and the poster route."""
import xml.dom.minidom

import pytest

from app import templates as catalogue
from app.pipeline.layouts import ALLOWED
from app.routes_media import ClipOptions
from app.routes_templates import POSTER_HEADERS, PRICED_FIELDS, look_fields
from app.templates import (GAMES, KINDS, PRESET_CAPTION_STYLE, PRESET_OPTIONS, PRESET_PROVISIONAL, PUBLIC_FIELDS, TEMPLATES,
                           TUNING_FIELDS, problems)
from tests.test_api import balance, upload
from tests.test_template_gallery import ASSETS, load_script

PRESETS = {tid: t for tid, t in TEMPLATES.items() if t["kind"] == "preset"}
# The contract's table: id -> (layout, where the camera panel is, the top panel's share of the height).
CONTRACT = {
    "racing-gameplay": ("screen_first", "bottom", 0.60),        # gameplay 60% over camera 40%
    "racing-camera-top": ("split2", "top", 0.33),               # camera 33% over gameplay 67%
    "shooter-gameplay": ("full", None, None),                   # gameplay only
    "fighting-screen-first": ("screen_first", "bottom", 0.57),  # gameplay 57% over camera 43%
    "moba-screen-first": ("screen_first", "bottom", 0.63),      # gameplay 63% over camera 37%
    "moba-full": ("full", None, None),                          # gameplay only
    "moba-gameplay": ("screen_first", "bottom", 0.66),          # gameplay 66% over camera 34%
}
THEIR_NAMES = ("Racing Gameplay", "Racing 2 Gameplay", "Shooting Gameplay", "Fighting Screen First", "MOBA Screen First",
               "MOBA Full", "MOBA Gameplay")


# --- the presets ------------------------------------------------------------------------------------------------

def test_the_seven_presets_are_the_contracts_with_its_panel_sizes():
    assert list(PRESETS) == list(CONTRACT)                                     # the same seven, in the contract's order
    for tid, (layout, camera, ratio) in CONTRACT.items():
        t = PRESETS[tid]
        assert problems(tid, t) == [], tid
        assert (t["layout"], t["aspect"], t["panels"]) == (layout, "9:16", {"camera": camera, "split_ratio": ratio}), tid
        assert t["game"] is None and t["duration"] is None and t["hook"] is None, tid   # a look, nothing else
        assert set(t) == set(PUBLIC_FIELDS) | set(TUNING_FIELDS), tid
    assert {t["genre"] for t in PRESETS.values()} == {"racing", "shooter", "fighting", "moba"}
    assert len({t["name"] for t in PRESETS.values()}) == 7                     # our own names, none of theirs
    assert not {t["name"].lower() for t in PRESETS.values()} & {n.lower() for n in THEIR_NAMES}
    assert len({(t["genre"], t["layout"], t["panels"]["split_ratio"]) for t in PRESETS.values()}) == 7   # no two alike


def test_every_preset_is_provisional_and_says_why():
    for tid, t in PRESETS.items():
        assert t["provisional"] is True and t["provisional_reason"] == PRESET_PROVISIONAL, tid
    assert "not confirmed" in PRESET_PROVISIONAL and "adjust" in PRESET_PROVISIONAL
    settled = {**PRESETS["moba-full"], "provisional": False, "provisional_reason": None}
    assert any("provisional" in p for p in problems("moba-full", settled))     # the catalogue refuses a settled preset


def test_a_presets_options_are_a_look_the_api_accepts_and_never_a_price():
    assert PRESET_CAPTION_STYLE in catalogue.CAPTION_STYLES                    # the large-caption style
    for tid, t in PRESETS.items():
        assert t["options"] == {"layout": t["layout"], "aspect": "9:16", "captions": True, "caption_style": PRESET_CAPTION_STYLE}, tid
        sent = ClipOptions(template=tid, **t["options"])                       # today's API takes every one of them
        assert sent.layout == t["layout"] and sent.caption_style == t["caption_style"], tid
        assert t["layout"] in ALLOWED["9:16"], tid
        assert not {"camera", "split_ratio"} & set(t["options"]), tid          # panel sizes: `panels`, not options
    assert set(PRESET_OPTIONS) <= look_fields()                                # a preset can be saved as a custom template
    assert not set(PRESET_OPTIONS) & (PRICED_FIELDS | {"max_clips", "clip_length"})   # nothing a job is priced on
    priced = {**PRESETS["moba-full"], "options": {**PRESETS["moba-full"]["options"], "clip_length": 30}}
    assert any("options are exactly" in p for p in problems("moba-full", priced))


def test_the_format_check_catches_a_bad_preset():
    good = PRESETS["racing-gameplay"]
    for change, word in [({"game": "gta5"}, "no game"), ({"duration": "0-30"}, "no duration"),
                         ({"hook": {"enabled": True, "style": "excited", "position": "beginning", "duration_ms": 2000}}, "no hook"),
                         ({"panels": {"camera": "top", "split_ratio": 0.6}}, "panels.camera"),
                         ({"panels": {"camera": "bottom", "split_ratio": 0.8}}, "split_ratio"),
                         ({"panels": {"camera": "bottom", "split_ratio": None}}, "split_ratio"),
                         ({"caption_style": "comic-sans", "options": {**good["options"], "caption_style": "comic-sans"}}, "caption_style"),
                         ({"options": {**good["options"], "captions": False}}, "captions on"),
                         ({"options": {**good["options"], "max_clips": 5}}, "options are exactly")]:
        found = problems("racing-gameplay", {**good, **change})
        assert found and any(word in p for p in found), (change, found)


def test_sending_a_presets_options_never_changes_what_a_job_costs(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    start = balance(client, headers)

    def reserve(options):
        r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": options}, headers=headers)
        assert r.status_code == 202, r.text
        client.post(f"/v1/jobs/{r.json()['job_id']}/cancel", headers=headers)
        return r.json()
    plain = reserve({"max_clips": 2})
    for tid, t in PRESETS.items():                                             # the id and its whole look, as a client sends them
        job = reserve({"max_clips": 2, "template": tid, **t["options"]})
        assert job["credits_reserved"] == plain["credits_reserved"], tid
        assert (job["options"]["max_clips"], job["options"]["clip_length"]) == \
               (plain["options"]["max_clips"], plain["options"]["clip_length"]), tid
        assert job["options"]["layout"] == t["layout"] and job["options"]["template"] == tid, tid
        assert job["options"]["judge_focus"] == t["judge_focus"], tid          # the game type's tuning, from the id
    assert balance(client, headers) == start


# --- the list ---------------------------------------------------------------------------------------------------

def test_the_kind_filter(client):
    everything = client.get("/v1/templates").json()["templates"]
    assert [t["id"] for t in everything] == list(TEMPLATES)                    # without kind: both
    presets = client.get("/v1/templates", params={"kind": "preset"}).json()["templates"]
    assert [t["id"] for t in presets] == list(PRESETS)
    assert all(t["kind"] == "preset" and t["game"] is None and set(t) == set(PUBLIC_FIELDS) for t in presets)
    assert presets[0]["panels"] == {"camera": "bottom", "split_ratio": 0.6}
    assert presets[0]["preview"] == {"video": None, "poster": "/v1/templates/racing-gameplay/poster"}
    assert presets[0]["provisional"] is True and "judge_focus" not in presets[0]
    games = client.get("/v1/templates", params={"kind": "game"}).json()["templates"]
    assert [t["id"] for t in games] == [tid for tid in TEMPLATES if tid not in PRESETS] and len(games) == 31
    assert all(t["kind"] == "game" and t["game"] in GAMES for t in games)
    bad = client.get("/v1/templates", params={"kind": "custom"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unknown_kind"
    assert all(k in bad.json()["error"]["message"] for k in KINDS)
    assert client.get("/v1/templates", params={"kind": ""}).json()["error"]["code"] == "unknown_kind"


def test_kind_and_game_combine_and_a_preset_belongs_to_no_game(client):
    for game in GAMES:
        with_kind = client.get("/v1/templates", params={"game": game, "kind": "game"}).json()["templates"]
        assert with_kind == client.get("/v1/templates", params={"game": game}).json()["templates"] and with_kind
        assert client.get("/v1/templates", params={"game": game, "kind": "preset"}).json() == {"templates": []}
    both_bad = client.get("/v1/templates", params={"game": "tetris", "kind": "preset"})
    assert both_bad.status_code == 422 and both_bad.json()["error"]["code"] == "unknown_game"
    listed = client.get("/v1/templates/games").json()
    assert listed["total"] == 31 and "preset" not in str(listed)               # the tabs count game templates only


# --- posters ----------------------------------------------------------------------------------------------------

def attr_before(svg: str, closing: str, name: str) -> float:
    """The `name` attribute of the element whose text ends with `closing` (">WORD</text>")."""
    return float(svg[:svg.index(closing)].rsplit(f' {name}="', 1)[1].split('"')[0])


def test_each_preset_has_its_own_poster_drawn_by_the_script():
    script = load_script()
    seen = set()
    for tid, t in PRESETS.items():
        text = (ASSETS / tid / "poster.svg").read_text(encoding="utf-8")
        assert text == script.poster_svg(t), f"{tid}: run scripts/make_template_previews.py --posters"
        xml.dom.minidom.parseString(text)
        word = script.CAPTION_WORDS[tid]
        assert text.count(f">{word}</text>") == 2 and word.isalpha() and word.isupper(), tid   # one word: outline, then fill
        camera, ratio = t["panels"]["camera"], t["panels"]["split_ratio"]
        if camera:                                                             # the panels in order, with their sizes
            top, bottom = f"{round(ratio * 100)}%", f"{100 - round(ratio * 100)}%"
            first, second = ("CAMERA", "GAMEPLAY") if camera == "top" else ("GAMEPLAY", "CAMERA")
            assert attr_before(text, f">{first} · {top}</text>", "y") < attr_before(text, f">{second} · {bottom}</text>", "y"), tid
        else:
            assert "CAMERA" not in text and "gameplay only" in text, tid
        assert f'{t["genre"].upper()} PRESET' in text and "NOT GAME FOOTAGE" in text and "CAPTIONS ·" not in text, tid
        seen.add(text)
    assert len(seen) == len(PRESETS)                                           # no two presets share a picture
    assert len(set(script.CAPTION_WORDS.values())) == len(script.CAPTION_WORDS)


def test_a_poster_puts_the_caption_word_on_the_line_between_the_panels_or_in_the_lower_third():
    script = load_script()
    top, height = script.FRAME_TOP, script.SIZES["9:16"][1]
    for tid, t in PRESETS.items():
        baseline = attr_before(script.poster_svg(t), f">{script.CAPTION_WORDS[tid]}</text>", "y")
        where = t["panels"]["split_ratio"] if t["panels"]["camera"] else 0.70
        assert baseline - script.WORD_SIZE * 0.35 == pytest.approx(top + where * height, abs=0.11), tid


def test_the_poster_route_serves_each_poster_as_an_image_only(client):
    for tid, t in TEMPLATES.items():
        r = client.get(t["preview"]["poster"])                                 # the path the list gives; no key
        assert r.status_code == 200, tid
        path, media_type = catalogue.poster_file(tid)
        assert r.headers["content-type"] == media_type, tid
        assert r.headers["x-content-type-options"] == "nosniff", tid
        assert r.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'", tid
        assert r.headers["cache-control"] == "public, max-age=3600", tid
        assert r.content == path.read_bytes(), tid
    assert POSTER_HEADERS["Content-Security-Policy"] == "default-src 'none'; style-src 'unsafe-inline'"


def test_the_poster_route_cannot_be_walked_out_of_the_catalogue(client, tmp_path, monkeypatch):
    missing = client.get("/v1/templates/tetris-line-clear/poster")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "unknown_template"
    secret = tmp_path / "secret.svg"
    secret.write_text("<svg/>")
    for attempt in ("..", "%2e%2e", "..%2Fapp%2Fmain.py", "lol-teamfight%2F..%2F..%2FREADME.md", "..%2Ftemplates%2Flol-teamfight",
                    "lol-teamfight%00", "LOL-TEAMFIGHT", "lol-teamfight ", "%2Fetc%2Fpasswd", str(secret).replace("/", "%2F")):
        r = client.get(f"/v1/templates/{attempt}/poster")
        assert r.status_code == 404, attempt
    for attempt in ("../templates/lol-teamfight", "lol-teamfight/../lol-teamfight", "lol-teamfight/", str(secret), "", "."):
        assert catalogue.poster_file(attempt) is None, attempt                 # only an exact catalogue id resolves
    path, media_type = catalogue.poster_file("lol-teamfight")
    assert path.parent == ASSETS / "lol-teamfight" and path.name in catalogue.POSTER_TYPES and media_type == catalogue.POSTER_TYPES[path.name]
    monkeypatch.setattr(catalogue, "ASSETS", tmp_path)                         # a template whose folder has no poster
    gone = client.get("/v1/templates/lol-teamfight/poster")
    assert gone.status_code == 404 and gone.json()["error"]["code"] == "no_poster"


def test_a_poster_in_another_format_is_served_with_its_own_type(client, tmp_path, monkeypatch):
    (tmp_path / "moba-full").mkdir()
    (tmp_path / "moba-full" / "poster.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "moba-full" / "notes.html").write_text("<script>1</script>")   # never served: not a poster name
    monkeypatch.setattr(catalogue, "ASSETS", tmp_path)
    r = client.get("/v1/templates/moba-full/poster")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(b"\x89PNG")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_the_fixed_paths_are_never_read_as_a_template_id(client, user):
    headers, _ = user
    assert client.get("/v1/templates/games").json()["games"][0]["id"] == "lol"
    assert client.get("/v1/templates/custom").status_code == 401               # the saved-looks route, asking for a key
    assert client.get("/v1/templates/custom", headers=headers).json()["templates"] == []
    for word in ("custom", "games"):                                           # and neither word is ever an id with a poster
        r = client.get(f"/v1/templates/{word}/poster")
        assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_template"


def test_a_footage_poster_is_served_before_the_schematic_one():
    """Every template has a frame rendered from the owner's footage; it is the poster, small enough for a grid."""
    for tid in TEMPLATES:
        path, media_type = catalogue.poster_file(tid)
        assert path.name == "poster.webp" and media_type == "image/webp", tid
        assert path.stat().st_size < 150_000, tid
        assert (ASSETS / tid / "poster.svg").is_file(), tid                  # the drawing stays as the fallback
