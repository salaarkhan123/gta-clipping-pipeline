import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Account, ApiKey, utcnow
from .security import API_KEY_PREFIX, hash_api_key, password_version, read_token


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# In-memory sliding-window limiter. Fine for one API process; move to Redis if the API is scaled out.
_buckets: dict[str, deque] = defaultdict(deque)


def rate_limit(key: str, limit: int, window_sec: float) -> None:
    now = time.monotonic()
    if len(_buckets) > 50_000:
        _buckets.clear()
    dq = _buckets[key]
    while dq and now - dq[0] > window_sec:
        dq.popleft()
    if len(dq) >= limit:
        raise ApiError(429, "rate_limited", "Too many requests. Slow down and try again shortly.")
    dq.append(now)


def client_ip(request: Request) -> str:
    """Peer address after uvicorn proxy-header handling (see FORWARDED_ALLOW_IPS / SEC-003)."""
    return request.client.host if request.client else "unknown"


@dataclass
class Principal:
    account: Account
    via: str  # "session" (website login) or "api_key"
    claims: dict = field(default_factory=dict)  # session JWT claims (password version, admin MFA, …)


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "Send 'Authorization: Bearer <api key or session token>'.")
    token = auth[7:].strip()
    claims: dict = {}
    if token.startswith(API_KEY_PREFIX):
        key = db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(token),
                                              ApiKey.revoked_at.is_(None))).scalar_one_or_none()
        if not key:
            raise ApiError(401, "unauthorized", "Invalid or revoked API key.")
        account = db.get(Account, key.account_id)
        key.last_used_at = utcnow()
        db.commit()
        via = "api_key"
    else:
        data = read_token(token, "session")
        account = db.get(Account, data["sub"]) if data else None
        # SEC-002: session must carry the current password version; reset/change voids older tokens.
        if account and data.get("v") != password_version(account.password_hash):
            account = None
        claims = dict(data) if data and account else {}
        via = "session"
    if not account:
        raise ApiError(401, "unauthorized", "Invalid or expired session.")
    if account.status != "active":
        raise ApiError(403, "account_suspended", "This account is suspended.")
    rate_limit(f"acct:{account.id}", get_settings().rate_limit_per_minute, 60)
    return Principal(account, via, claims)


def session_principal(p: Principal = Depends(current_principal)) -> Principal:
    if p.via != "session":
        raise ApiError(403, "session_required", "This endpoint needs a website login, not an API key.")
    return p


def admin_principal(p: Principal = Depends(session_principal)) -> Principal:
    """Admin routes: website login of an is_admin account; optional TOTP step-up when ADMIN_MFA_REQUIRED (SEC-004)."""
    if not p.account.is_admin:
        raise ApiError(403, "admin_required", "This endpoint is for ClutchClips admins.")
    s = get_settings()
    if not s.admin_mfa_required:
        return p
    if not p.account.mfa_secret:
        raise ApiError(403, "mfa_setup_required",
                       "Enroll admin MFA first (POST /v1/auth/mfa/enroll or scripts/admin.py enroll-mfa).")
    amfa = p.claims.get("amfa")
    if not isinstance(amfa, (int, float)) or (time.time() - float(amfa)) > s.admin_mfa_ttl_sec:
        raise ApiError(403, "mfa_required",
                       "Verify admin MFA (POST /v1/auth/mfa/verify) before using admin routes.")
    return p
