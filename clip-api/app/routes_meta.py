"""What the clip options accept: one public list, read from the request models themselves.

The website builds its job form from this, so a control appears only once the API accepts the option behind it.
Owned by the orchestrator (docs/CONTRACTS.md).
"""
from fastapi import APIRouter

from .routes_media import ClipOptions

router = APIRouter()
BOUNDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems")


def describe(prop: dict, defs: dict) -> dict:
    """One option, flattened: its type, allowed values, default and limits. `nullable` when null is accepted."""
    out: dict = {}
    choices = prop.get("anyOf") or [prop]
    if any(c.get("type") == "null" for c in choices):
        out["nullable"] = True
    for c in choices:
        if c.get("type") == "null":
            continue
        if "$ref" in c:
            c = defs.get(c["$ref"].rsplit("/", 1)[-1], {})
        if "type" in c:
            out["type"] = c["type"]
        if "enum" in c:
            out["values"] = c["enum"]
        elif "const" in c:
            out["values"] = [c["const"]]
        for k in BOUNDS:
            if k in c:
                out[k] = c[k]
    if "default" in prop:
        out["default"] = prop["default"]
    return out


def clip_options() -> dict:
    schema = ClipOptions.model_json_schema()
    defs = schema.get("$defs", {})
    return {name: describe(prop, defs) for name, prop in schema.get("properties", {}).items()}


@router.get("/v1/options")
def list_options():
    """Every option `POST /v1/clips` accepts, with its allowed values, default and limits. Public, no key needed.
    Send only options listed here: an unknown option is rejected with 422."""
    return {"clips": clip_options()}
