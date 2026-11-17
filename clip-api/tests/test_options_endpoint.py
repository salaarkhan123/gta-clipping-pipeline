"""GET /v1/options: the public list of what the clip options accept, read from the request model."""
from fastapi.testclient import TestClient

from app.main import app
from app.routes_media import ClipOptions
from app.routes_meta import clip_options


def test_options_are_public_and_match_the_request_model():
    r = TestClient(app).get("/v1/options")                                   # no key
    assert r.status_code == 200
    opts = r.json()["clips"]
    assert set(opts) == set(ClipOptions.model_fields)                        # every option, nothing else
    for name, o in opts.items():
        assert o["default"] == ClipOptions.model_fields[name].default, name


def test_allowed_values_and_limits_are_listed():
    opts = clip_options()
    assert opts["aspect"]["values"] == ["9:16", "4:5", "1:1", "16:9"] and opts["aspect"]["type"] == "string"
    assert opts["max_clips"]["minimum"] == 1 and opts["max_clips"]["maximum"] >= 10
    assert opts["captions"] == {"type": "boolean", "default": True}
    assert opts["template"]["nullable"] is True and opts["template"]["default"] is None
    assert opts["facecam_region"]["nullable"] is True and "top-left" in opts["facecam_region"]["values"]


def test_every_listed_value_is_accepted_and_others_are_not():
    opts = clip_options()
    for name, o in opts.items():
        if name == "layout":
            continue
        for v in o.get("values", []):
            ClipOptions(**{name: v})
    for aspect, layouts in opts["layout"]["by_aspect"].items():              # layouts depend on the aspect
        assert "auto" in layouts
        for layout in layouts:
            ClipOptions(aspect=aspect, layout=layout)
    listed = set(opts["layout"]["values"])
    assert listed == {x for layouts in opts["layout"]["by_aspect"].values() for x in layouts}
    named = set(ClipOptions.model_json_schema()["properties"]["layout"]["enum"])
    assert listed < named                                                    # some layouts are named but not built yet
    for refused in named - listed:
        for aspect in opts["aspect"]["values"]:
            try:
                ClipOptions(aspect=aspect, layout=refused)
            except ValueError:
                continue
            raise AssertionError(f"{refused} is accepted in {aspect} but not listed")
    r = TestClient(app).post("/v1/clips", json={"upload_id": "x", "options": {"not_an_option": 1}},
                             headers={"authorization": "Bearer nope"})
    assert r.status_code in (401, 422)
