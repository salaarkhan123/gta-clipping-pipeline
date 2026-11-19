import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Account, ApiKey, utcnow
from .security import API_KEY_PREFIX, hash_api_key, read_token


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
    return request.client.host if request.client else "unknown"


@dataclass
class Principal:
    account: Account
    via: str  # "session" (website login) or "api_key"


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "Send 'Authorization: Bearer <api key or session token>'.")
    token = auth[7:].strip()
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
        via = "session"
    if not account:
        raise ApiError(401, "unauthorized", "Invalid or expired session.")
    if account.status != "active":
        raise ApiError(403, "account_suspended", "This account is suspended.")
    rate_limit(f"acct:{account.id}", get_settings().rate_limit_per_minute, 60)
    return Principal(account, via)


def session_principal(p: Principal = Depends(current_principal)) -> Principal:
    if p.via != "session":
        raise ApiError(403, "session_required", "This endpoint needs a website login, not an API key.")
    return p


def admin_principal(p: Principal = Depends(session_principal)) -> Principal:
    """Admin routes: a website login of an account with is_admin set. API keys never reach them."""
    if not p.account.is_admin:
        raise ApiError(403, "admin_required", "This endpoint is for ClutchClips admins.")
    return p
