"""Publishing use-cases: connect, check, submit, cancel, retry, list. Tokens stay server-side."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import ApiError
from ..models import Clip, Job, ScheduledPost, SocialAccount, new_id, utcnow
from ..security import make_token, read_token
from ..storage import get_storage
from . import PLATFORMS
from .adapters import get_adapter
from .platforms import configured, specs, validate_media, validate_text
from . import state
from . import tokens


BACKOFF_MINUTES = (1, 5, 15, 60, 60)
MAX_ATTEMPTS = 5
STALE_CLAIM_MIN = 15
MISSED_SCHEDULE_MIN = 60
CONNECT_TTL = timedelta(minutes=10)


def require_publishing() -> None:
    s = get_settings()
    if not s.publishing:
        raise ApiError(404, "publishing_disabled", "Publishing is not enabled on this server.")
    if s.publishing and not s.publish_token_key:
        raise ApiError(503, "publishing_misconfigured", "PUBLISH_TOKEN_KEY is required when PUBLISHING is on.")


def platforms_payload() -> dict:
    require_publishing()
    return {"platforms": specs(), "timezone_note": "Schedule times are stored in UTC; the website shows your local zone."}


def list_accounts(db: Session, account_id: str) -> list[dict]:
    require_publishing()
    rows = db.execute(
        select(SocialAccount).where(
            SocialAccount.account_id == account_id,
            SocialAccount.disconnected_at.is_(None),
        ).order_by(SocialAccount.platform, SocialAccount.created_at)
    ).scalars().all()
    return [_account_json(a) for a in rows]


def start_connect(db: Session, account_id: str, platform: str) -> dict:
    require_publishing()
    if platform not in PLATFORMS:
        raise ApiError(400, "platform_held", f"{platform} is not offered yet.")
    if not configured(platform):
        raise ApiError(400, "not_configured", f"{platform} is not configured on this server.")
    verifier = secrets.token_urlsafe(32)
    challenge = _pkce_challenge(verifier)
    nonce = secrets.token_urlsafe(16)
    state_tok = make_token(account_id, "social_connect", CONNECT_TTL,
                           platform=platform, nonce=nonce, verifier=verifier)
    redirect = f"{get_settings().public_api_url}/v1/social-accounts/{platform}/callback"
    adapter = get_adapter(platform)
    url = adapter.authorize_url(redirect, state_tok, challenge)
    return {"authorize_url": url, "platform": platform}


def finish_connect(db: Session, platform: str, code: str, state_tok: str) -> SocialAccount:
    require_publishing()
    data = read_token(state_tok, "social_connect")
    if not data or data.get("platform") != platform:
        raise ApiError(400, "bad_state", "Connect link expired or was invalid. Start again from the dashboard.")
    account_id = data["sub"]
    redirect = f"{get_settings().public_api_url}/v1/social-accounts/{platform}/callback"
    adapter = get_adapter(platform)
    try:
        tok = adapter.exchange_code(code, redirect, code_verifier=data.get("verifier"))
    except Exception as e:
        raise ApiError(400, "oauth_failed", f"Could not connect {platform}: {e}") from e
    now = utcnow()
    expires = now + timedelta(seconds=int(tok["expires_in"] or 3600)) if tok.get("expires_in") else None
    refresh_expires = None
    if tok.get("refresh_expires_in"):
        refresh_expires = now + timedelta(seconds=int(tok["refresh_expires_in"]))
    existing = db.execute(
        select(SocialAccount).where(
            SocialAccount.account_id == account_id,
            SocialAccount.platform == platform,
            SocialAccount.external_id == tok["external_id"],
        )
    ).scalar_one_or_none()
    row = existing or SocialAccount(
        id=new_id("soc"), account_id=account_id, platform=platform,
        external_id=tok["external_id"],
    )
    row.display_name = tok.get("display_name")
    row.avatar_url = tok.get("avatar_url")
    row.access_token_enc = tokens.encrypt(tok["access_token"])
    row.refresh_token_enc = tokens.encrypt(tok.get("refresh_token")) if tok.get("refresh_token") else None
    # Instagram stores long-lived token as refresh stand-in
    if platform == "instagram" and not row.refresh_token_enc:
        row.refresh_token_enc = tokens.encrypt(tok["access_token"])
    row.access_expires_at = expires
    row.refresh_expires_at = refresh_expires
    row.scopes = list(tok.get("scopes") or [])
    row.status = "active"
    row.disconnected_at = None
    row.updated_at = now
    if not existing:
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def disconnect(db: Session, account_id: str, social_id: str) -> None:
    require_publishing()
    row = db.get(SocialAccount, social_id)
    if not row or row.account_id != account_id or row.disconnected_at:
        raise ApiError(404, "not_found", "Connected account not found.")
    # Cancel unsent posts for this account.
    for post in db.execute(
        select(ScheduledPost).where(
            ScheduledPost.social_account_id == social_id,
            ScheduledPost.status.in_(("SCHEDULED", "QUEUED")),
        )
    ).scalars():
        post.status = "CANCELED"
        post.error_code = "account_disconnected"
        post.error_message = "Social account was disconnected."
        post.updated_at = utcnow()
    access = tokens.decrypt(row.access_token_enc) if row.access_token_enc else None
    if access and configured(row.platform):
        try:
            get_adapter(row.platform).revoke(access)
        except Exception:
            pass
    row.access_token_enc = None
    row.refresh_token_enc = None
    row.display_name = None
    row.avatar_url = None
    row.status = "revoked"
    row.disconnected_at = utcnow()
    row.updated_at = utcnow()
    db.commit()


def own_clip(db: Session, account_id: str, clip_id: str) -> Clip:
    clip = db.get(Clip, clip_id)
    if not clip or clip.deleted_at:
        raise ApiError(404, "not_found", "Clip not found.")
    job = db.get(Job, clip.job_id)
    if not job or job.account_id != account_id:
        raise ApiError(404, "not_found", "Clip not found.")
    return clip


def check_publish(db: Session, account_id: str, clip_id: str, targets: list[dict]) -> dict:
    require_publishing()
    clip = own_clip(db, account_id, clip_id)
    duration = float(clip.end_sec) - float(clip.start_sec)
    export_ready = bool(clip.export_key)
    size = None
    results = []
    for t in targets:
        soc = _own_social(db, account_id, t["social_account_id"])
        reasons = []
        if not export_ready:
            reasons.append("Export this clip at full quality before publishing.")
        reasons.extend(validate_media(soc.platform, duration, size))
        reasons.extend(validate_text(soc.platform, t.get("title"), t.get("caption") or "", t.get("hashtags") or []))
        if soc.platform == "tiktok" and not t.get("privacy"):
            reasons.append("TikTok requires an explicit privacy choice (no default).")
        if soc.status != "active":
            reasons.append("Reconnect this account before publishing.")
        already = db.execute(
            select(ScheduledPost).where(
                ScheduledPost.clip_id == clip_id,
                ScheduledPost.social_account_id == soc.id,
                ScheduledPost.status == "PUBLISHED",
            ).order_by(ScheduledPost.published_at.desc()).limit(1)
        ).scalar_one_or_none()
        results.append({
            "social_account_id": soc.id,
            "platform": soc.platform,
            "display_name": soc.display_name,
            "avatar_url": soc.avatar_url,
            "readiness": next((p["readiness"] for p in specs() if p["id"] == soc.platform), "not_configured"),
            "ok": not reasons,
            "reasons": reasons,
            "already_published_at": already.published_at.isoformat() + "Z" if already and already.published_at else None,
            "defaults": _defaults(clip, soc.platform),
            "cost": "Free",
        })
    return {
        "clip_id": clip_id,
        "duration_sec": duration,
        "export_ready": export_ready,
        "targets": results,
        "rights_line": "I have the rights to post this clip on the selected accounts.",
    }


def submit_publish(
    db: Session, account_id: str, clip_id: str, targets: list[dict],
    publish_at: datetime | None, request_key: str, rights_confirmed: bool,
) -> list[ScheduledPost]:
    require_publishing()
    if not rights_confirmed:
        raise ApiError(400, "rights_required", "Confirm you have the rights to post this clip.")
    if not request_key or len(request_key) > 200:
        raise ApiError(400, "idempotency_required", "Send an Idempotency-Key header.")
    clip = own_clip(db, account_id, clip_id)
    if not clip.export_key:
        raise ApiError(400, "export_required", "Export this clip at full quality before publishing.")
    now = utcnow()
    if publish_at is not None:
        if publish_at.tzinfo is not None:
            publish_at = publish_at.astimezone(timezone.utc).replace(tzinfo=None)
        min_at = now + timedelta(minutes=get_settings().publish_min_ahead_min)
        max_at = now + timedelta(days=get_settings().publish_max_ahead_days)
        if publish_at < min_at:
            raise ApiError(400, "schedule_too_soon",
                           f"Schedule at least {get_settings().publish_min_ahead_min} minutes ahead.")
        if publish_at > max_at:
            raise ApiError(400, "schedule_too_far",
                           f"Schedule at most {get_settings().publish_max_ahead_days} days ahead.")

    posts: list[ScheduledPost] = []
    for t in targets:
        soc = _own_social(db, account_id, t["social_account_id"])
        existing = db.execute(
            select(ScheduledPost).where(
                ScheduledPost.clip_id == clip_id,
                ScheduledPost.social_account_id == soc.id,
                ScheduledPost.request_key == request_key,
            )
        ).scalar_one_or_none()
        if existing:
            posts.append(existing)
            continue
        check = check_publish(db, account_id, clip_id, [t])
        target = check["targets"][0]
        if not target["ok"]:
            raise ApiError(400, "clip_unfit", "; ".join(target["reasons"]))
        status = "SCHEDULED" if publish_at else "QUEUED"
        row = ScheduledPost(
            id=new_id("pst"), account_id=account_id, clip_id=clip_id,
            social_account_id=soc.id, platform=soc.platform,
            request_key=request_key,
            title=t.get("title"), caption=t.get("caption") or "",
            hashtags=list(t.get("hashtags") or []),
            privacy=t.get("privacy"),
            options=dict(t.get("options") or {}),
            publish_at=publish_at, status=status,
            attempts=0, created_at=now, updated_at=now,
        )
        if soc.platform == "facebook":
            row.options = {**row.options, "page_id": soc.external_id}
        db.add(row)
        posts.append(row)
    db.commit()
    for p in posts:
        db.refresh(p)
    return posts


def get_post(db: Session, account_id: str, post_id: str) -> ScheduledPost:
    require_publishing()
    row = db.get(ScheduledPost, post_id)
    if not row or row.account_id != account_id:
        raise ApiError(404, "not_found", "Post not found.")
    return row


def list_posts(
    db: Session, account_id: str, *, clip_id: str | None = None, status: str | None = None,
    from_at: datetime | None = None, to_at: datetime | None = None,
) -> list[ScheduledPost]:
    require_publishing()
    q = select(ScheduledPost).where(ScheduledPost.account_id == account_id)
    if clip_id:
        q = q.where(ScheduledPost.clip_id == clip_id)
    if status:
        q = q.where(ScheduledPost.status == status)
    if from_at:
        q = q.where(or_(ScheduledPost.publish_at >= from_at, and_(ScheduledPost.publish_at.is_(None),
                                                                  ScheduledPost.created_at >= from_at)))
    if to_at:
        q = q.where(or_(ScheduledPost.publish_at <= to_at, and_(ScheduledPost.publish_at.is_(None),
                                                                ScheduledPost.created_at <= to_at)))
    return list(db.execute(q.order_by(ScheduledPost.created_at.desc()).limit(500)).scalars())


def patch_post(db: Session, account_id: str, post_id: str, fields: dict) -> ScheduledPost:
    row = get_post(db, account_id, post_id)
    if not state.can_edit(row.status):
        raise ApiError(409, "not_editable", "Only scheduled posts can be edited.")
    if "title" in fields:
        row.title = fields["title"]
    if "caption" in fields:
        row.caption = fields["caption"]
    if "hashtags" in fields:
        row.hashtags = list(fields["hashtags"] or [])
    if "privacy" in fields:
        row.privacy = fields["privacy"]
    if "options" in fields:
        row.options = dict(fields["options"] or {})
    if "publish_at" in fields:
        when = fields["publish_at"]
        if when is None:
            raise ApiError(400, "schedule_required", "Scheduled posts need a publish_at time.")
        if getattr(when, "tzinfo", None) is not None:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
        now = utcnow()
        if when < now + timedelta(minutes=get_settings().publish_min_ahead_min):
            raise ApiError(400, "schedule_too_soon", "Schedule further ahead.")
        row.publish_at = when
    reasons = validate_text(row.platform, row.title, row.caption or "", row.hashtags or [])
    if reasons:
        raise ApiError(400, "clip_unfit", "; ".join(reasons))
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def cancel_post(db: Session, account: str, post_id: str) -> ScheduledPost:
    row = get_post(db, account, post_id)
    if not state.can_cancel(row.status):
        raise ApiError(409, "not_cancelable", "This post can no longer be canceled.")
    row.status = state.advance(row.status, "CANCELED")
    row.error_code = "canceled"
    row.error_message = "Canceled by the customer."
    row.updated_at = utcnow()
    row.claimed_at = None
    db.commit()
    db.refresh(row)
    return row


def retry_post(db: Session, account_id: str, post_id: str) -> ScheduledPost:
    row = get_post(db, account_id, post_id)
    if not state.can_retry(row.status, row.error_code):
        raise ApiError(409, "not_retryable",
                       "This failure cannot be retried automatically. Check the account or clip first.")
    row.status = state.advance(row.status, "QUEUED")
    row.next_attempt_at = None
    row.error_code = None
    row.error_message = None
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def claim_due_post(db: Session) -> str | None:
    """Claim one due scheduled/queued post. Same conditional UPDATE pattern as claim_job."""
    if not get_settings().publishing:
        return None
    now = utcnow()
    # Release stale claims.
    db.execute(
        update(ScheduledPost).where(
            ScheduledPost.status.in_(("UPLOADING", "PROCESSING")),
            ScheduledPost.claimed_at.is_not(None),
            ScheduledPost.claimed_at < now - timedelta(minutes=STALE_CLAIM_MIN),
        ).values(status="QUEUED", claimed_at=None, updated_at=now)
    )
    db.commit()

    for _ in range(5):
        q = (
            select(ScheduledPost.id)
            .where(
                or_(
                    and_(ScheduledPost.status == "QUEUED",
                         or_(ScheduledPost.next_attempt_at.is_(None), ScheduledPost.next_attempt_at <= now)),
                    and_(ScheduledPost.status == "SCHEDULED",
                         ScheduledPost.publish_at.is_not(None),
                         ScheduledPost.publish_at <= now),
                )
            )
            .order_by(ScheduledPost.publish_at.nullsfirst(), ScheduledPost.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        post_id = db.execute(q).scalar_one_or_none()
        if not post_id:
            return None
        row = db.get(ScheduledPost, post_id)
        # Missed schedule window.
        if row.status == "SCHEDULED" and row.publish_at and row.publish_at < now - timedelta(minutes=MISSED_SCHEDULE_MIN):
            row.status = "FAILED"
            row.error_code = "missed_schedule"
            row.error_message = "Worker was down past the schedule window. Re-send when ready."
            row.updated_at = now
            db.commit()
            continue
        if not get_settings().publishing:
            if row.status == "SCHEDULED" and row.publish_at and row.publish_at < now - timedelta(minutes=MISSED_SCHEDULE_MIN):
                row.status = "FAILED"
                row.error_code = "missed_schedule"
                row.error_message = "Publishing was disabled past the schedule window."
                row.updated_at = now
                db.commit()
            return None
        won = db.execute(
            update(ScheduledPost).where(
                ScheduledPost.id == post_id,
                ScheduledPost.status.in_(("SCHEDULED", "QUEUED")),
            ).values(status="UPLOADING", claimed_at=now, updated_at=now,
                     attempts=ScheduledPost.attempts + 1)
        ).rowcount
        db.commit()
        if won:
            return post_id
    return None


def process_post(db: Session, post_id: str, client=None) -> None:
    """Run one publish attempt. Transfer retries; final call is at-most-once via adapter."""
    row = db.get(ScheduledPost, post_id)
    if not row or row.status not in ("UPLOADING", "PROCESSING"):
        return
    soc = db.get(SocialAccount, row.social_account_id)
    clip = db.get(Clip, row.clip_id)
    if not soc or soc.disconnected_at or not soc.access_token_enc:
        _fail(db, row, "reconnect_required", "Reconnect the social account.", retryable=False)
        return
    if not clip or clip.deleted_at or not clip.export_key:
        _fail(db, row, "export_required", "The clip export is missing.", retryable=False)
        return

    access = _fresh_token(db, soc)
    if access is None:
        _fail(db, row, "reconnect_required", "Token expired. Reconnect the account.", retryable=False)
        if soc:
            soc.status = "needs_reconnect"
            db.commit()
        return

    storage = get_storage()
    media_path = None
    media_url = None
    if hasattr(storage, "path"):
        try:
            local = storage.path(clip.export_key)
            if local.exists():
                media_path = str(local)
        except Exception:
            media_path = None
    # Platforms that pull by URL (TikTok/Instagram) or when local bytes are unavailable.
    if row.platform in ("tiktok", "instagram") or not media_path:
        try:
            media_url = storage.url(clip.export_key)
        except Exception:
            media_url = None
    if row.platform in ("youtube", "facebook", "x") and not media_path:
        work = get_settings().work_dir / f"publish_{row.id}.mp4"
        try:
            storage.fetch(clip.export_key, work)
            media_path = str(work)
        except Exception as e:
            _fail(db, row, "platform_unavailable", f"Could not read export: {e}", retryable=True)
            return

    adapter = get_adapter(row.platform, client=client)
    # If we already completed a final step, status-check instead of repeating.
    if row.step in ("inserted", "published") and row.external_ref:
        result = adapter.status(access_token=access, external_ref=row.external_ref)
    else:
        result = adapter.publish(
            access_token=access, media_path=media_path, media_url=media_url,
            title=row.title, caption=row.caption or "", privacy=row.privacy,
            options=row.options or {}, step=row.step, external_ref=row.external_ref,
        )

    if result.ok and result.data.get("awaiting_processing"):
        # Re-queue shortly so status polling resumes without repeating the final publish call.
        row.step = result.step or row.step
        row.external_ref = result.external_ref or row.external_ref
        row.status = "QUEUED"
        row.next_attempt_at = utcnow() + timedelta(seconds=30)
        row.updated_at = utcnow()
        row.claimed_at = None
        db.commit()
        return

    if result.ok:
        row.status = "PUBLISHED"
        row.step = result.step or "published"
        row.external_ref = result.external_ref or row.external_ref
        row.external_id = result.external_id
        row.external_url = result.external_url
        row.published_at = utcnow()
        row.error_code = None
        row.error_message = None
        row.claimed_at = None
        row.updated_at = utcnow()
        soc.last_used_at = utcnow()
        db.commit()
        return

    if result.error_code == "outcome_unknown":
        _fail(db, row, "outcome_unknown", result.error_message or "Outcome unknown.", retryable=False)
        row.step = result.step or row.step
        row.external_ref = result.external_ref or row.external_ref
        db.commit()
        return

    if result.retryable and row.attempts < MAX_ATTEMPTS:
        delay = BACKOFF_MINUTES[min(row.attempts - 1, len(BACKOFF_MINUTES) - 1)]
        row.status = "QUEUED"
        row.next_attempt_at = utcnow() + timedelta(minutes=delay)
        row.step = result.step or row.step
        row.external_ref = result.external_ref or row.external_ref
        row.error_code = result.error_code
        row.error_message = (result.error_message or "")[:400]
        row.claimed_at = None
        row.updated_at = utcnow()
        db.commit()
        return

    _fail(db, row, result.error_code or "platform_error", result.error_message or "Publish failed.",
          retryable=False)


def post_json(row: ScheduledPost) -> dict:
    return {
        "id": row.id,
        "clip_id": row.clip_id,
        "social_account_id": row.social_account_id,
        "platform": row.platform,
        "title": row.title,
        "caption": row.caption,
        "hashtags": row.hashtags or [],
        "privacy": row.privacy,
        "options": row.options or {},
        "publish_at": _iso(row.publish_at),
        "status": row.status,
        "attempts": row.attempts,
        "next_attempt_at": _iso(row.next_attempt_at),
        "external_id": row.external_id,
        "external_url": row.external_url,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "published_at": _iso(row.published_at),
        "can_cancel": state.can_cancel(row.status),
        "can_edit": state.can_edit(row.status),
        "can_retry": state.can_retry(row.status, row.error_code),
    }


def _account_json(a: SocialAccount) -> dict:
    return {
        "id": a.id,
        "platform": a.platform,
        "external_id": a.external_id,
        "display_name": a.display_name,
        "avatar_url": a.avatar_url,
        "status": a.status,
        "scopes": a.scopes or [],
        "created_at": _iso(a.created_at),
        "updated_at": _iso(a.updated_at),
        "last_used_at": _iso(a.last_used_at),
    }


def _own_social(db: Session, account_id: str, social_id: str) -> SocialAccount:
    row = db.get(SocialAccount, social_id)
    if not row or row.account_id != account_id or row.disconnected_at:
        raise ApiError(404, "not_found", "Connected account not found.")
    return row


def _defaults(clip: Clip, platform: str) -> dict:
    meta = clip.meta or {}
    title = meta.get("title") or (meta.get("titles") or [None])[0]
    desc = meta.get("description") or ""
    tags = list(meta.get("hashtags") or [])
    if platform == "youtube":
        return {"title": title, "caption": desc, "hashtags": tags, "privacy": "private"}
    if platform == "tiktok":
        return {"title": None, "caption": title or "", "hashtags": tags, "privacy": None,
                "options": {"disable_comment": True, "disable_duet": True, "disable_stitch": True}}
    if platform in ("instagram", "facebook"):
        cap = title or ""
        if tags:
            cap = f"{cap}\n{' '.join(t if str(t).startswith('#') else f'#{t}' for t in tags)}".strip()
        return {"title": title if platform == "facebook" else None, "caption": cap,
                "hashtags": tags, "privacy": "public"}
    return {"title": title, "caption": desc, "hashtags": tags, "privacy": "public"}


def _fresh_token(db: Session, soc: SocialAccount) -> str | None:
    access = tokens.decrypt(soc.access_token_enc)
    if not access:
        return None
    now = utcnow()
    if soc.access_expires_at and soc.access_expires_at > now + timedelta(minutes=10):
        return access
    refresh = tokens.decrypt(soc.refresh_token_enc) if soc.refresh_token_enc else None
    if not refresh:
        return access if not soc.access_expires_at or soc.access_expires_at > now else None
    # Row lock via SELECT FOR UPDATE in caller session — refresh under this session.
    try:
        adapter = get_adapter(soc.platform)
        tok = adapter.refresh(refresh)
    except Exception:
        return None
    soc.access_token_enc = tokens.encrypt(tok["access_token"])
    if tok.get("refresh_token"):
        soc.refresh_token_enc = tokens.encrypt(tok["refresh_token"])
    if tok.get("expires_in"):
        soc.access_expires_at = now + timedelta(seconds=int(tok["expires_in"]))
    soc.updated_at = now
    db.commit()
    return tok["access_token"]


def _fail(db: Session, row: ScheduledPost, code: str, message: str, *, retryable: bool) -> None:
    row.status = "FAILED"
    row.error_code = code
    row.error_message = (message or "")[:400]
    row.claimed_at = None
    row.updated_at = utcnow()
    db.commit()


def _pkce_challenge(verifier: str) -> str:
    import base64
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None
