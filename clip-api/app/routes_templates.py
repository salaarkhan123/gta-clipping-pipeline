"""Game templates: the public list. Owned by the templates agent (docs/CONTRACTS.md)."""
from fastapi import APIRouter

from .templates import TEMPLATES, public as public_template

router = APIRouter()


@router.get("/v1/templates")
def list_templates():
    """Game templates for the Clip Maker. Send a template's `options` together with `"template": id`: the id
    tunes what is detected and how the AI judges it, the options set the look and length. Public, no key needed."""
    return {"templates": [public_template(tid) for tid in TEMPLATES]}
