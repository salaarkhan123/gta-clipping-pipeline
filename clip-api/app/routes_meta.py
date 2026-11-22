"""What the clip options accept: one public list, read from the request models themselves.

The website builds its job form from this, so a control appears only once the API accepts the option behind it.
Owned by the orchestrator (docs/CONTRACTS.md).
"""
from functools import lru_cache

from fastapi import APIRouter
from pydantic import ValidationError

from .live.routes_live import listing as live_clipping_listing
from .render_options import provisional_on
from .routes_media import ClipOptions
from .templates import hook_style_catalogue
from .thumbnail_jobs import listing as premium_thumbnail_listing

router = APIRouter()
BOUNDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems", "pattern")


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


def accepted(name: str, value, **others) -> bool:
    try:
        ClipOptions(**{name: value, **others})
        return True
    except ValidationError:
        return False


def clip_options() -> dict:
    """Only values a request can actually send: a value the model names but refuses (a layout that is not built
    yet, or a provisional one while PROVISIONAL_LAYOUTS is off) is left out. Layouts depend on the aspect, so
    `layout.by_aspect` lists them per aspect."""
    return _clip_options(provisional_on())


@lru_cache
def _clip_options(_provisional: bool) -> dict:
    schema = ClipOptions.model_json_schema()
    defs = schema.get("$defs", {})
    out = {name: describe(prop, defs) for name, prop in schema.get("properties", {}).items()}
    for name, o in out.items():
        if "values" in o and name != "layout":
            o["values"] = [v for v in o["values"] if accepted(name, v)]
    layouts, aspects = out["layout"]["values"], out["aspect"]["values"]
    by_aspect = {a: [x for x in layouts if accepted("layout", x, aspect=a)] for a in aspects}
    out["layout"]["values"] = [x for x in layouts if any(x in by_aspect[a] for a in aspects)]
    out["layout"]["by_aspect"] = by_aspect
    # Hook styles: values stay the 13 ids (forms keep working); catalogue adds label + description per style.
    out["hook_style"]["catalogue"] = hook_style_catalogue()
    return out


@router.get("/v1/options", summary="List clip options")
def list_options():
    """Every option `POST /v1/clips` accepts, with allowed values, defaults and limits. Public, no key needed.
    `clips.hook_style.catalogue` is the hook-styles resource (id, label, description); default stays `serious`.
    Send only options listed here: an unknown option is rejected with 422."""
    premium = premium_thumbnail_listing()      # (#140) listed only while PREMIUM_THUMBNAILS is on
    live = live_clipping_listing()             # AS-3 scaffold; listed only while LIVE_CLIPPING is on
    out = {"clips": clip_options(), **({"premium_thumbnail": premium} if premium else {})}
    if live:
        out["live_clipping"] = live
    return out
