"""Accounts, login, email verification, password reset and API keys."""
import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import ledger
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, client_ip, current_principal, rate_limit, session_principal
from .emailer import send_email
from .models import Account, ApiKey, new_id, utcnow
from .security import hash_password, make_token, new_api_key, read_token, verify_password

router = APIRouter()

DISPOSABLE = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "yopmail.com",
              "trashmail.com", "sharklasers.com", "getnada.com", "temp-mail.org", "throwawaymail.com"}


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class ForgotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    password: str = Field(min_length=8, max_length=200)


def _pw_version(a: Account) -> str:
    """Changes whenever the password changes, which makes reset links single-use."""
    return hashlib.sha256(a.password_hash.encode()).hexdigest()[:16]


class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="default", min_length=1, max_length=80)


def account_json(db: Session, a: Account) -> dict:
    return {"id": a.id, "email": a.email, "email_verified": a.email_verified, "plan": a.plan or "free",
            "credits": ledger.balance(db, a.id), "created_at": a.created_at.isoformat() + "Z",
            # What Stripe last reported: null without a subscription; "past_due" means the last payment failed.
            "subscription_status": a.subscription_status,
            "subscription_cancel_at": a.subscription_cancel_at.isoformat() + "Z" if a.subscription_cancel_at else None}


def session_token(a: Account) -> str:
    return make_token(a.id, "session", timedelta(hours=get_settings().jwt_ttl_hours))


def mark_verified(db: Session, a: Account) -> None:
    """Verify the email and give the one-time free grant (idempotent)."""
    a.email_verified = True
    free = get_settings().free_signup_credits
    if free > 0:
        ledger.grant(db, a.id, free, "grant", f"signup:{a.id}", "Free signup credits")


def send_verification(a: Account) -> None:
    s = get_settings()
    token = make_token(a.id, "verify", timedelta(hours=48))
    link = f"{s.public_api_url}/v1/auth/verify?token={token}"
    send_email(a.email, "Confirm your email",
               f"Confirm your email to activate your account and get your free credits:\n\n{link}\n\n"
               "If you didn't sign up, ignore this message.")


@router.post("/v1/auth/signup", status_code=201)
def signup(body: Credentials, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    ip = client_ip(request)
    rate_limit(f"signup:{ip}", s.signup_limit_per_ip_per_hour, 3600)
    email = body.email.strip().lower()
    if email.rsplit("@", 1)[-1] in DISPOSABLE:
        raise ApiError(422, "email_not_allowed", "Please sign up with a permanent email address.")
    account = Account(id=new_id("acct"), email=email, password_hash=hash_password(body.password),
                      webhook_secret=secrets.token_urlsafe(32), signup_ip=ip)
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists.") from None
    if s.auto_verify_email:
        mark_verified(db, account)
    db.commit()
    if not s.auto_verify_email:
        send_verification(account)
    return {"token": session_token(account), "account": account_json(db, account)}


@router.post("/v1/auth/login")
def login(body: Credentials, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"login:{client_ip(request)}", get_settings().login_limit_per_ip_per_minute, 60)
    account = db.execute(select(Account).where(Account.email == body.email.strip().lower())).scalar_one_or_none()
    if not account or not verify_password(account.password_hash, body.password):
        raise ApiError(401, "invalid_credentials", "Wrong email or password.")
    if account.status != "active":
        raise ApiError(403, "account_suspended", "This account is suspended.")
    return {"token": session_token(account), "account": account_json(db, account)}


@router.get("/v1/auth/verify")
def verify(token: str, request: Request, db: Session = Depends(get_db)):
    data = read_token(token, "verify")
    account = db.get(Account, data["sub"]) if data else None
    if not account:
        raise ApiError(400, "invalid_token", "This verification link is invalid or has expired.")
    mark_verified(db, account)
    db.commit()
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(f"{get_settings().public_web_url}/login?verified=1", status_code=303)
    return {"verified": True}


@router.post("/v1/auth/resend-verification")
def resend(p: Principal = Depends(session_principal)):
    if p.account.email_verified:
        return {"sent": False, "email_verified": True}
    rate_limit(f"resend:{p.account.id}", 3, 3600)
    send_verification(p.account)
    return {"sent": True}


@router.post("/v1/auth/forgot")
def forgot(body: ForgotRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"forgot:{client_ip(request)}", 5, 3600)
    account = db.execute(select(Account).where(Account.email == body.email.strip().lower())).scalar_one_or_none()
    if account:
        token = make_token(account.id, "reset", timedelta(hours=1), v=_pw_version(account))
        send_email(account.email, "Reset your password",
                   f"Reset your password here (link valid for 1 hour):\n\n"
                   f"{get_settings().public_web_url}/reset-password?token={token}\n\n"
                   "If you didn't ask for this, ignore this message.")
    return {"sent": True}   # same answer whether or not the email exists


@router.post("/v1/auth/reset")
def reset(body: ResetRequest, db: Session = Depends(get_db)):
    data = read_token(body.token, "reset")
    account = db.get(Account, data["sub"]) if data else None
    if not account or data.get("v") != _pw_version(account):
        raise ApiError(400, "invalid_token", "This reset link is invalid, expired or already used.")
    account.password_hash = hash_password(body.password)
    db.commit()
    return {"reset": True}


@router.get("/v1/me")
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    out = account_json(db, p.account)
    if p.via == "session":
        out["webhook_secret"] = p.account.webhook_secret
    return out


@router.post("/v1/keys", status_code=201)
def create_key(body: KeyCreate, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    active = db.execute(select(ApiKey).where(ApiKey.account_id == p.account.id,
                                             ApiKey.revoked_at.is_(None))).scalars().all()
    if len(active) >= 10:
        raise ApiError(422, "too_many_keys", "Revoke an existing key first (limit 10).")
    raw, prefix, digest = new_api_key()
    key = ApiKey(id=new_id("key"), account_id=p.account.id, name=body.name, prefix=prefix, key_hash=digest)
    db.add(key)
    db.commit()
    # The full key is returned once and never stored.
    return {"id": key.id, "name": key.name, "prefix": prefix, "key": raw}


@router.get("/v1/keys")
def list_keys(p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    keys = db.execute(select(ApiKey).where(ApiKey.account_id == p.account.id,
                                           ApiKey.revoked_at.is_(None)).order_by(ApiKey.created_at)).scalars()
    return {"keys": [{"id": k.id, "name": k.name, "prefix": k.prefix,
                      "created_at": k.created_at.isoformat() + "Z",
                      "last_used_at": k.last_used_at.isoformat() + "Z" if k.last_used_at else None}
                     for k in keys]}


@router.delete("/v1/keys/{key_id}")
def revoke_key(key_id: str, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    key = db.get(ApiKey, key_id)
    if not key or key.account_id != p.account.id or key.revoked_at:
        raise ApiError(404, "not_found", "No such API key.")
    key.revoked_at = utcnow()
    db.commit()
    return {"revoked": True}
