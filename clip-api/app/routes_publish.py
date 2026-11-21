"""Publishing API. Session-only for connect/disconnect. Behind PUBLISHING (404 when off)."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, current_principal, session_principal
from .publish import service

router = APIRouter()


class TargetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    social_account_id: str
    title: str | None = Field(default=None, max_length=300)
    caption: str | None = Field(default="", max_length=5000)
    hashtags: list[str] = Field(default_factory=list, max_length=40)
    privacy: str | None = Field(default=None, max_length=40)
    options: dict[str, Any] = Field(default_factory=dict)


class CheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[TargetIn] = Field(min_length=1, max_length=10)


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[TargetIn] = Field(min_length=1, max_length=10)
    publish_at: datetime | None = None
    rights_confirmed: bool = False


class PatchPostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=300)
    caption: str | None = Field(default=None, max_length=5000)
    hashtags: list[str] | None = Field(default=None, max_length=40)
    privacy: str | None = Field(default=None, max_length=40)
    options: dict[str, Any] | None = None
    publish_at: datetime | None = None


@router.get("/v1/publish/platforms", tags=["publishing"], summary="Configured publish destinations")
def publish_platforms(_p: Principal = Depends(current_principal)):
    return service.platforms_payload()


@router.get("/v1/social-accounts", tags=["publishing"], summary="Connected social accounts")
def social_accounts(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return {"accounts": service.list_accounts(db, p.account.id)}


@router.post("/v1/social-accounts/{platform}/connect", tags=["publishing"],
             summary="Start OAuth connect (website session)")
def connect_start(platform: str, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    return service.start_connect(db, p.account.id, platform)


@router.get("/v1/social-accounts/{platform}/callback", tags=["publishing"],
            summary="OAuth redirect target", include_in_schema=False)
def connect_callback(platform: str, code: str = "", state: str = "", error: str = "",
                     db: Session = Depends(get_db)):
    web = get_settings().public_web_url.rstrip("/")
    if error or not code or not state:
        return RedirectResponse(f"{web}/dashboard/social-accounts/?error=oauth_denied")
    try:
        row = service.finish_connect(db, platform, code, state)
    except ApiError:
        return RedirectResponse(f"{web}/dashboard/social-accounts/?error=oauth_failed")
    return RedirectResponse(f"{web}/dashboard/social-accounts/?connected={row.id}")


@router.delete("/v1/social-accounts/{social_id}", tags=["publishing"],
               summary="Disconnect and revoke", status_code=204)
def disconnect(social_id: str, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    service.disconnect(db, p.account.id, social_id)
    return Response(status_code=204)


@router.post("/v1/clips/{clip_id}/publish/check", tags=["publishing"],
             summary="Validate publish targets without sending")
def publish_check(clip_id: str, body: CheckIn, p: Principal = Depends(current_principal),
                  db: Session = Depends(get_db)):
    return service.check_publish(db, p.account.id, clip_id, [t.model_dump() for t in body.targets])


@router.post("/v1/clips/{clip_id}/publish", tags=["publishing"], status_code=202,
             summary="Publish now or schedule")
def publish(clip_id: str, body: PublishIn, p: Principal = Depends(current_principal),
            db: Session = Depends(get_db),
            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    posts = service.submit_publish(
        db, p.account.id, clip_id, [t.model_dump() for t in body.targets],
        body.publish_at, idempotency_key or "", body.rights_confirmed,
    )
    return {"posts": [service.post_json(x) for x in posts]}


@router.get("/v1/posts", tags=["publishing"], summary="List posts (calendar feed)")
def list_posts(
    p: Principal = Depends(current_principal), db: Session = Depends(get_db),
    clip_id: str | None = None, status: str | None = None,
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
):
    rows = service.list_posts(db, p.account.id, clip_id=clip_id, status=status,
                              from_at=_naive(from_at), to_at=_naive(to_at))
    return {"posts": [service.post_json(r) for r in rows]}


@router.get("/v1/posts/{post_id}", tags=["publishing"])
def get_post(post_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return service.post_json(service.get_post(db, p.account.id, post_id))


@router.patch("/v1/posts/{post_id}", tags=["publishing"])
def patch_post(post_id: str, body: PatchPostIn, p: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)
    if "publish_at" in fields:
        fields["publish_at"] = _naive(fields["publish_at"])
    return service.post_json(service.patch_post(db, p.account.id, post_id, fields))


@router.post("/v1/posts/{post_id}/cancel", tags=["publishing"])
def cancel_post(post_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return service.post_json(service.cancel_post(db, p.account.id, post_id))


@router.post("/v1/posts/{post_id}/retry", tags=["publishing"])
def retry_post(post_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return service.post_json(service.retry_post(db, p.account.id, post_id))


@router.post("/webhooks/meta/data-deletion", tags=["publishing"], include_in_schema=False)
def meta_data_deletion():
    """Meta data-deletion callback stub. Wired when Meta apps are registered."""
    service.require_publishing()
    return {"url": f"{get_settings().public_web_url}/privacy", "confirmation_code": "pending"}


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        from datetime import timezone
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
