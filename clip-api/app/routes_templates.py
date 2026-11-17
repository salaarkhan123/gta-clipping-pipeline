"""Game templates: the public list. Owned by the templates agent (docs/CONTRACTS.md)."""
from fastapi import APIRouter, Query

from .deps import ApiError
from .templates import GAMES, TEMPLATES, for_game, games

router = APIRouter()


@router.get("/v1/templates")
def list_templates(game: str | None = Query(default=None, max_length=40)):
    """Game templates for the Clip Maker, grouped by game. `?game=` narrows the list to one game (ids from
    `GET /v1/templates/games`). Send a template's `options` together with `"template": id`: the id tunes what
    is detected and how the AI judges it, the options set the look and length. Public, no key needed."""
    if game is not None and game not in GAMES:
        raise ApiError(422, "unknown_game", f"Unknown game. Use one of: {', '.join(GAMES)}.")
    return {"templates": for_game(game)}


@router.get("/v1/templates/games")
def list_games():
    """The games that have templates, with display names and template counts: the gallery's filter tabs."""
    return {"games": games(), "total": len(TEMPLATES)}
