"""An account's own caption fonts: upload (TrueType or OpenType, checked), list, delete. Owned by the captions agent.

A font is used by naming it in `caption_look.font` as "custom:<id>". Files live in storage under the account's
uploads prefix (`uploads/<account>/fonts/`), so deleting the account deletes them; an index file there lists them.
Nothing here touches credits: a font costs nothing to store or use.

Licence: the person uploading confirms they may use the font in videos they publish (`licence_confirmed=true`);
ClutchClips does not check font licences. Every response says so.
"""
import json
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .ledger import lock_account
from .models import utcnow
from .pipeline.fonts import MAX_FONT_BYTES, BadFont, read_face
from .storage import get_storage

router = APIRouter()

MAX_FONTS = 10                       # fonts one account may keep
FONT_EXT = (".ttf", ".otf")
LICENCE = ("You confirmed you hold a licence to use this font in videos you publish. ClutchClips does not check "
           "font licences; you are responsible for the fonts you upload.")


def font_prefix(account_id: str) -> str:
    return f"uploads/{account_id}/fonts/"


def font_key(account_id: str, font_id: str, ext: str = ".ttf") -> str:
    return f"{font_prefix(account_id)}{font_id}{ext}"


def _index(storage, account_id: str) -> list[dict]:
    key = font_prefix(account_id) + "index.json"
    if not storage.exists(key):
        return []
    with tempfile.TemporaryDirectory() as tmp:
        storage.fetch(key, Path(tmp) / "i.json")
        return json.loads((Path(tmp) / "i.json").read_text())


def _save_index(storage, account_id: str, fonts: list[dict]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "i.json").write_text(json.dumps(fonts))
        storage.put(font_prefix(account_id) + "index.json", Path(tmp) / "i.json")


def _public(f: dict) -> dict:
    return {"id": f["id"], "family": f["family"], "filename": f["filename"], "bytes": f["bytes"],
            "created_at": f["created_at"], "font": f"custom:{f['id']}"}


def account_font(storage, account_id: str, font_id: str) -> dict | None:
    """The account's font with this id (its index row, with "key"), or None."""
    return next((f for f in _index(storage, account_id) if f["id"] == font_id), None)


@router.get("/v1/fonts")
def list_fonts(p: Principal = Depends(current_principal)):
    return {"fonts": [_public(f) for f in _index(get_storage(), p.account.id)], "max": MAX_FONTS,
            "max_bytes": MAX_FONT_BYTES, "licence": LICENCE}


@router.post("/v1/fonts", status_code=201)
async def upload_font(request: Request, filename: str = Query(..., max_length=120),
                      licence_confirmed: bool = Query(False), p: Principal = Depends(current_principal),
                      db: Session = Depends(get_db)):
    """Send the font file as the raw request body. `licence_confirmed=true` is required."""
    if not licence_confirmed:
        raise ApiError(422, "licence_not_confirmed", "Confirm you hold a licence to use this font in your videos "
                       "(licence_confirmed=true).")
    ext = Path(filename).suffix.lower()
    if ext not in FONT_EXT:
        raise ApiError(415, "unsupported_type", "Upload a .ttf or .otf font file.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_FONT_BYTES:
        raise ApiError(413, "file_too_large", f"A font file may be at most {MAX_FONT_BYTES // 1024 ** 2} MB.")
    s = get_settings()
    tmp = s.work_dir / f"font_{uuid.uuid4().hex}{ext}"
    size = 0
    try:
        with open(tmp, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_FONT_BYTES:
                    raise ApiError(413, "file_too_large",
                                   f"A font file may be at most {MAX_FONT_BYTES // 1024 ** 2} MB.")
                fh.write(chunk)
        try:
            face = read_face(tmp)
        except BadFont as e:
            raise ApiError(422, "bad_font", str(e)) from None
        storage = get_storage()
        lock_account(db, p.account.id)                 # one index writer per account
        fonts = _index(storage, p.account.id)
        if len(fonts) >= MAX_FONTS:
            raise ApiError(409, "too_many_fonts", f"An account keeps at most {MAX_FONTS} fonts. Delete one first.")
        font_id = uuid.uuid4().hex[:16]
        key = font_key(p.account.id, font_id, ext)
        storage.put(key, tmp)
        row = {"id": font_id, "family": face.family, "filename": Path(filename).name, "bytes": size, "key": key,
               "created_at": utcnow().isoformat()}
        _save_index(storage, p.account.id, [*fonts, row])
        db.commit()
        return {**_public(row), "licence": LICENCE}
    finally:
        read_face.cache_clear()
        tmp.unlink(missing_ok=True)


@router.delete("/v1/fonts/{font_id}")
def delete_font(font_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    storage = get_storage()
    lock_account(db, p.account.id)
    fonts = _index(storage, p.account.id)
    row = next((f for f in fonts if f["id"] == font_id), None)
    if row is None:
        raise ApiError(404, "not_found", "No such font.")
    storage.delete(row["key"])
    _save_index(storage, p.account.id, [f for f in fonts if f["id"] != font_id])
    db.commit()
    return {"deleted": font_id}
