"""Direct uploads: the browser sends the video in parts straight to the bucket (S3 multipart), resumable.

1. POST /v1/uploads/multipart            {filename, size_bytes}  -> upload_token, part_size, part_count
2. POST /v1/uploads/multipart/parts      {upload_token}          -> signed PUT URLs for parts not yet stored
   PUT each part's bytes to its URL. After a dropped connection call parts again: it lists what is stored and
   signs only the rest.
3. POST /v1/uploads/multipart/complete   {upload_token}          -> the upload, as POST /v1/uploads returns it
4. POST /v1/uploads/multipart/abort      {upload_token}          -> 204, the parts are discarded

Only with STORAGE_BACKEND=s3 (409 direct_upload_unavailable otherwise: use POST /v1/uploads). Same limits as
POST /v1/uploads. The upload is recorded only after every part is stored at the agreed sizes, the bucket holds
exactly size_bytes, and the file reads as a video within the length limits; anything else deletes the object.
The token is signed, names the account, and lasts 24 hours; unfinished uploads are aborted by the bucket after
7 days (R2's default, a lifecycle rule on Spaces: DEPLOY.md).
"""
import hashlib
import math
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal
from .models import Upload, new_id
from .routes_media import ALLOWED_EXT, probe_upload, record_upload, same_upload, upload_json
from .security import make_token, read_token
from .storage import S3Storage, get_storage

router = APIRouter()

MiB = 1024 ** 2
MIN_PART = 16 * MiB              # R2 and S3: 5 MiB at least, every part but the last the same size
MAX_PARTS = 10_000
PARTS_PER_CALL = 16              # signed per call: few, so a slow connection sends them before the links expire
TOKEN_TTL = timedelta(hours=24)


class StartUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)


class UploadToken(BaseModel):
    upload_token: str = Field(min_length=1, max_length=4096)


def part_size_for(size: int) -> int:
    """Whole MiB, at least 16 MiB, few enough parts for the 10,000 limit."""
    return max(MIN_PART, math.ceil(size / MAX_PARTS / MiB) * MiB)


def bucket() -> S3Storage:
    store = get_storage()
    if not isinstance(store, S3Storage):
        raise ApiError(409, "direct_upload_unavailable",
                       "Direct uploads need bucket storage. Send the file to POST /v1/uploads instead.")
    return store


def pending(p: Principal, token: str) -> dict:
    data = read_token(token, "direct_upload")
    if not data or data.get("sub") != p.account.id:
        raise ApiError(404, "not_found", "This upload has expired or does not exist. Start the upload again.")
    return data


def stored_parts(store: S3Storage, t: dict) -> dict[int, tuple[int, str]]:
    try:
        return store.parts(t["k"], t["m"])
    except LookupError:
        raise ApiError(404, "upload_gone", "This upload was finished or cancelled. Start the upload again.") from None


def sizes(t: dict) -> list[int]:
    count = math.ceil(t["s"] / t["ps"])
    return [t["ps"]] * (count - 1) + [t["s"] - t["ps"] * (count - 1)]


@router.post("/v1/uploads/multipart", status_code=201)
def start_upload(body: StartUpload, p: Principal = Depends(current_principal)):
    s, store = get_settings(), bucket()
    ext = Path(body.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ApiError(415, "unsupported_type", f"Upload a video file ({', '.join(sorted(ALLOWED_EXT))}).")
    if body.size_bytes > s.max_upload_bytes:
        raise ApiError(413, "file_too_large", f"Maximum upload size is {s.max_upload_bytes // MiB} MB.")
    upload_id = new_id("upl")
    key = f"uploads/{p.account.id}/{upload_id}{ext}"
    part_size = part_size_for(body.size_bytes)
    claims = dict(u=upload_id, k=key, m=store.start_multipart(key), s=body.size_bytes, ps=part_size, f=body.filename)
    return {"upload_id": upload_id, "upload_token": make_token(p.account.id, "direct_upload", TOKEN_TTL, **claims),
            "part_size": part_size, "part_count": len(sizes(claims))}


@router.post("/v1/uploads/multipart/parts")
def part_urls(body: UploadToken, p: Principal = Depends(current_principal)):
    """Signed URLs for the next 16 parts that are not stored yet; call again for the ones after."""
    t, store = pending(p, body.upload_token), bucket()
    want = sizes(t)
    stored = {n for n, (size, _) in stored_parts(store, t).items() if size == want[n - 1]}
    todo = [n for n in range(1, len(want) + 1) if n not in stored][:PARTS_PER_CALL]
    ttl = get_settings().signed_url_ttl_sec
    return {"part_size": t["ps"], "part_count": len(want), "done": sorted(stored),
            "parts": [{"part_number": n, "size": want[n - 1], "url": store.part_url(t["k"], t["m"], n, want[n - 1], ttl)}
                      for n in todo]}


@router.post("/v1/uploads/multipart/complete", status_code=201)
async def complete_upload(body: UploadToken, response: Response, p: Principal = Depends(current_principal),
                          db: Session = Depends(get_db)):
    t, store = pending(p, body.upload_token), bucket()
    done = db.get(Upload, t["u"])
    if done is not None and done.account_id == p.account.id:          # a retried complete
        response.status_code = 200
        return {**upload_json(done), "reused": False}
    want = sizes(t)
    stored = await run_in_threadpool(stored_parts, store, t)
    missing = [n for n in range(1, len(want) + 1) if n not in stored]
    if missing:
        raise ApiError(409, "upload_incomplete", f"{len(missing)} of {len(want)} parts are not uploaded yet "
                                                 f"(first: {missing[0]}). Ask for their URLs and send them.")
    wrong = [n for n, (size, _) in stored.items() if n > len(want) or size != want[n - 1]]
    if wrong:
        await run_in_threadpool(store.abort_multipart, t["k"], t["m"])
        raise ApiError(422, "upload_size_mismatch", "The parts do not add up to the file size given at the start. "
                                                    "Start the upload again.")
    try:
        await run_in_threadpool(store.complete_multipart, t["k"], t["m"], {n: etag for n, (_, etag) in stored.items()})
    except LookupError:                                  # another complete call got there first
        raise ApiError(409, "upload_finishing", "This upload is being finished. Ask again in a moment.") from None
    tmp = get_settings().work_dir / f"up_{uuid.uuid4().hex}{Path(t['k']).suffix}"
    keep = False
    try:
        if await run_in_threadpool(store.size, t["k"]) != t["s"]:
            raise ApiError(422, "upload_size_mismatch", "The stored file is not the size given at the start.")
        await run_in_threadpool(store.fetch, t["k"], tmp)             # free from R2 to the droplet
        content_hash = await run_in_threadpool(sha256, tmp)
        same = same_upload(db, p.account.id, content_hash, t["s"])
        if same is not None:
            response.status_code = 200
            return {**upload_json(same), "reused": True}
        info = await probe_upload(tmp)
        upload = record_upload(db, p, t["u"], t["k"], t["f"], t["s"], content_hash, info)
        keep = True
        return {**upload_json(upload), "reused": False}
    finally:
        tmp.unlink(missing_ok=True)
        if not keep:
            await run_in_threadpool(store.delete, t["k"])


@router.post("/v1/uploads/multipart/abort", status_code=204)
def abort_upload(body: UploadToken, p: Principal = Depends(current_principal)):
    t, store = pending(p, body.upload_token), bucket()
    store.abort_multipart(t["k"], t["m"])
    return Response(status_code=204)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 * MiB), b""):
            digest.update(chunk)
    return digest.hexdigest()
