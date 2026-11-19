"""The website's API contract (web-src/lib/api-contract.json) against this API's OpenAPI document.

A backend change that removes or renames a route, a request field or a query parameter the website uses fails here.
Routes marked `optional` are looked up by the site at runtime (lib/routes.ts) and may be absent, but when present
they must still take every field listed. The edit's option names must match the model the API validates them with.
"""
import json
import re
from pathlib import Path

import pytest

from app.main import app
from app.render_options import LayoutOptions

CONTRACT = json.loads((Path(__file__).resolve().parents[1] / "web-src" / "lib" / "api-contract.json").read_text())
SPEC = app.openapi()
SCHEMAS = SPEC.get("components", {}).get("schemas", {})


def _shape(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


OPS = {(m.upper(), _shape(p)): op for p, item in SPEC["paths"].items() for m, op in item.items()}


def _props(schema: dict, depth: int = 0) -> set[str]:
    if not schema or depth > 8:
        return set()
    if "$ref" in schema:
        return _props(SCHEMAS[schema["$ref"].rsplit("/", 1)[-1]], depth + 1)
    out = set(schema.get("properties", {}))
    for key in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(key, []):
            out |= _props(sub, depth + 1)
    return out


def _route_id(r: dict) -> str:
    return f"{r['method']} {r['path']}"


@pytest.mark.parametrize("route", CONTRACT["routes"], ids=_route_id)
def test_route_exists_with_its_fields(route):
    op = OPS.get((route["method"], _shape(route["path"])))
    if op is None:
        if route.get("optional"):
            pytest.skip("optional route not served by this API")
        pytest.fail(f"the website calls {_route_id(route)}, which this API does not serve")
    if route.get("body"):
        schema = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
        missing = sorted(set(route["body"]) - _props(schema))
        assert not missing, f"{_route_id(route)} no longer takes {missing}"
    if route.get("query"):
        params = {p["name"] for p in op.get("parameters", []) if p.get("in") == "query"}
        missing = sorted(set(route["query"]) - params)
        assert not missing, f"{_route_id(route)} no longer takes query {missing}"


READS = [r for r in CONTRACT["routes"] if r["method"] == "GET" and r.get("response") and "{" not in r["path"]]


@pytest.mark.parametrize("route", READS, ids=_route_id)
def test_response_has_the_fields_the_site_reads(route, client, user):
    # The OpenAPI document has no response models yet, so these are checked by calling the route as a new account.
    headers, _ = user
    r = client.get(route["path"], headers=headers)
    assert r.status_code == 200, f"{_route_id(route)}: {r.status_code} {r.text[:200]}"
    missing = sorted(set(route["response"]) - set(r.json()))
    assert not missing, f"{_route_id(route)} no longer returns {missing}"


def test_clip_object_has_the_fields_the_site_reads():
    # A clip as the API serializes it everywhere (app/routes_media.py clip_json), here one the AI judged.
    from app import ai
    from app.models import Clip
    from app.routes_media import clip_json

    v2 = hasattr(ai, "SCORING_VERSION")
    meta = {"source": "ai", "virality": {"score": 81}, "title": "A clip", "hook": "No way"}
    if v2:
        meta.update(scores={k: 80 for k in ai.SCORES}, scoring_version=ai.SCORING_VERSION)

    class Files:
        @staticmethod
        def url(key):
            return f"/files/{key}" if key else None

    clip = Clip(id="clip_contract", job_id="job_contract", idx=1, start_sec=1.0, end_sec=20.0, score=0.5, signals={}, meta=meta)
    out = clip_json(clip, Files())
    wanted = set(CONTRACT["clip_fields"]) - (set() if v2 else {"scores", "scoring_version"})
    missing = sorted(wanted - set(out))
    assert not missing, f"a clip no longer carries {missing}"
    if v2:
        assert set(out["scores"]) == set(ai.SCORES) and out["scoring_version"] == ai.SCORING_VERSION


def test_edit_options_match_the_edit_model():
    # lib/edit.ts sends only these in `edit.options`; the API rejects any other name with 422.
    assert sorted(CONTRACT["edit_options"]) == sorted(LayoutOptions.model_fields)
