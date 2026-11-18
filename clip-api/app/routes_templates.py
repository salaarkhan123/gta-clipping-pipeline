"""Templates: the public catalogue (game templates and game-type presets), their poster images, and an
account's own saved looks. Owned by the templates agent (docs/CONTRACTS.md).

Nothing here touches credits. A template, a preset or a saved look is only ever a set of options the client
sends with its job, so the job is priced on what the request says, exactly as without one.
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .deps import ApiError, Principal, current_principal
from .ledger import lock_account
from .models import CustomTemplate, new_id, utcnow
from .render_options import LayoutOptions, refused_layout
from .routes_media import ClipOptions, iso
from .templates import GAMES, KINDS, TEMPLATES, games, listing, poster_file

router = APIRouter()

# A technical cap on saved looks per account, so one account cannot fill the table. It is the same for every
# account: there are no per-plan limits and no plan gating on saved looks (owner's decision, 2026-11-16).
MAX_CUSTOM_TEMPLATES = 20
# The editing switches that are part of a look, next to every field of LayoutOptions.
EDIT_FIELDS = ("tighten", "punch_zoom", "flash_forward", "hook_overlay")
# Never saved in a look: these set what a job costs or a quality the plan caps, or name another template.
PRICED_FIELDS = frozenset({"max_clips", "clip_length", "duration", "limit", "range", "resolution", "render", "template"})
POSTER_HEADERS = {
    "Cache-Control": "public, max-age=3600",
    # A poster is only ever an image: never sniffed into another type, and an SVG opened on its own can run
    # no script and load nothing.
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
}


def look_fields() -> frozenset[str]:
    """The options a saved look may set, read from the request models: how a clip is framed and captioned
    (every field of LayoutOptions, so one added there later is accepted here without a change) and the editing
    switches, minus everything in PRICED_FIELDS."""
    return (frozenset(LayoutOptions.model_fields) | (frozenset(EDIT_FIELDS) & frozenset(ClipOptions.model_fields))) - PRICED_FIELDS


def check_look(options: dict[str, Any]) -> dict[str, Any]:
    """`options` as a saved look stores them: the same keys, with the values the clip options model read.
    ApiError 422 naming the key when one is priced, unknown or has a value `POST /v1/clips` would refuse."""
    if not options:
        raise ApiError(422, "bad_options", "options must set at least one option.")
    allowed = look_fields()
    for key in options:
        if key in PRICED_FIELDS:
            raise ApiError(422, "forbidden_option", f"'{key}' cannot be saved in a template: it sets what a job costs "
                                                    "or its quality. Send it with the job instead.")
        if key not in allowed:
            raise ApiError(422, "unknown_option", f"'{key}' is not an option a template can save. "
                                                  f"Use: {', '.join(sorted(allowed))}.")
    try:
        read = ClipOptions(**options)
    except ValidationError as e:
        refused = refused_layout(e.errors())
        if refused:
            raise ApiError(400, *refused) from None
        first = e.errors()[0]
        where = ".".join(str(x) for x in first.get("loc", ()))
        raise ApiError(422, "bad_options", f"{where}: {first['msg']}".strip(": ")) from None
    return {key: getattr(read, key) for key in options}


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class CustomTemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    options: dict[str, Any]


class CustomTemplatePatch(BaseModel):
    """Send only what changes."""
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    options: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _something(self):
        if self.name is None and self.options is None:
            raise ValueError("send name, options or both")
        return self


def custom_json(t: CustomTemplate) -> dict:
    return {"id": t.id, "name": t.name, "options": t.options, "created_at": iso(t.created_at), "updated_at": iso(t.updated_at)}


def own_custom(db: Session, p: Principal, template_id: str) -> CustomTemplate:
    """The caller's own saved look. Someone else's, a deleted one and a missing one are all the same 404."""
    t = db.get(CustomTemplate, template_id)
    if not t or t.account_id != p.account.id or t.deleted_at:
        raise ApiError(404, "not_found", "No such saved template.")
    return t


# The fixed paths (/custom, /games) are declared before the paths with an id in them.

@router.get("/v1/templates")
def list_templates(game: str | None = Query(default=None, max_length=40), kind: str | None = Query(default=None, max_length=40)):
    """The template catalogue. `?kind=game` are the per-game templates, grouped by game; `?kind=preset` are the
    game-type presets (a layout, panel sizes and a caption style; `game` is null). Without `kind`: both.
    `?game=` narrows to one game (ids from `GET /v1/templates/games`); presets belong to no game, so they are
    never in a game's list. Send a template's `options` together with `"template": id`: the id tunes what is
    detected and how the AI judges it, the options set the look. Public, no key needed."""
    if game is not None and game not in GAMES:
        raise ApiError(422, "unknown_game", f"Unknown game. Use one of: {', '.join(GAMES)}.")
    if kind is not None and kind not in KINDS:
        raise ApiError(422, "unknown_kind", f"Unknown kind. Use one of: {', '.join(KINDS)}.")
    return {"templates": listing(game, kind)}


@router.get("/v1/templates/games")
def list_games():
    """The games that have templates, with display names and template counts: the gallery's filter tabs.
    Presets belong to no game and are not counted; `total` is the number of game templates."""
    listed = games()
    return {"games": listed, "total": sum(g["templates"] for g in listed)}


@router.get("/v1/templates/custom")
def list_custom(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Your saved looks, newest first. To use one, send its `options` with your job: the server never applies
    a saved look for you."""
    rows = db.execute(select(CustomTemplate).where(CustomTemplate.account_id == p.account.id, CustomTemplate.deleted_at.is_(None))
                      .order_by(CustomTemplate.created_at.desc(), CustomTemplate.id.desc())).scalars()
    return {"templates": [custom_json(t) for t in rows], "limit": MAX_CUSTOM_TEMPLATES}


@router.post("/v1/templates/custom", status_code=201)
def create_custom(body: CustomTemplateIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Save a look: a name and the clip options that make it (layout, shape, captions, editing switches).
    Options that set a price or a quality (`max_clips`, `clip_length`, `resolution` and the like) are refused.
    Free, and at most 20 per account."""
    options = check_look(body.options)
    lock_account(db, p.account.id)      # serialise this account's saves so two at once cannot pass the cap
    saved = db.execute(select(func.count()).select_from(CustomTemplate).where(
        CustomTemplate.account_id == p.account.id, CustomTemplate.deleted_at.is_(None))).scalar_one()
    if saved >= MAX_CUSTOM_TEMPLATES:
        raise ApiError(409, "too_many_templates", f"You can save up to {MAX_CUSTOM_TEMPLATES} templates. Delete one first.")
    now = utcnow()
    t = CustomTemplate(id=new_id("ctpl"), account_id=p.account.id, name=body.name, options=options,
                       created_at=now, updated_at=now)
    db.add(t)
    db.commit()
    return custom_json(t)


@router.patch("/v1/templates/custom/{template_id}")
def update_custom(template_id: str, body: CustomTemplatePatch, p: Principal = Depends(current_principal),
                  db: Session = Depends(get_db)):
    """Rename a saved look, replace its options, or both. `options` replaces the whole set."""
    t = own_custom(db, p, template_id)
    if body.options is not None:
        t.options = check_look(body.options)
    if body.name is not None:
        t.name = body.name
    t.updated_at = utcnow()
    db.commit()
    return custom_json(t)


@router.delete("/v1/templates/custom/{template_id}")
def delete_custom(template_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Delete a saved look. Jobs that were started with its options are not affected."""
    own_custom(db, p, template_id).deleted_at = utcnow()
    db.commit()
    return {"deleted": True}


@router.get("/v1/templates/{template_id}/poster")
def template_poster(template_id: str):
    """A catalogue template's poster image (`preview.poster` in the list is this path). Public, no key needed."""
    if template_id not in TEMPLATES:
        raise ApiError(404, "unknown_template", "No such template.")
    found = poster_file(template_id)
    if found is None:
        raise ApiError(404, "no_poster", "This template has no poster.")
    path, media_type = found
    return FileResponse(path, media_type=media_type, headers=POSTER_HEADERS)
