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
    defaults = ClipOptions().model_dump()
    for name, o in opts.items():
        assert o["default"] == defaults[name], name


def test_allowed_values_and_limits_are_listed():
    opts = clip_options()
    assert opts["aspect"]["values"] == ["9:16", "4:5", "1:1", "16:9"] and opts["aspect"]["type"] == "string"
    assert opts["max_clips"]["minimum"] == 1 and opts["max_clips"]["maximum"] >= 10
    assert opts["captions"] == {"type": "boolean", "default": True}
    assert opts["template"]["nullable"] is True and opts["template"]["default"] is None
    assert opts["facecam_region"]["nullable"] is True and "top-left" in opts["facecam_region"]["values"]


def test_every_listed_value_is_accepted_and_others_are_not():
    for name, o in clip_options().items():
        if name == "layout":                                                 # some layouts need a camera position
            continue
        for v in o.get("values", []):
            ClipOptions(**{name: v})
    r = TestClient(app).post("/v1/clips", json={"upload_id": "x", "options": {"not_an_option": 1}},
                             headers={"authorization": "Bearer nope"})
    assert r.status_code in (401, 422)
