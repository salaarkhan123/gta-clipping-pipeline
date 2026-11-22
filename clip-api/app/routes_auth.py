"""Accounts, login, email verification, password reset and API keys."""
import secrets
import time
import uuid
from datetime import timedelta

import pyotp
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import ledger, legal, token_epoch
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, client_ip, current_principal, rate_limit, session_principal
from .emailer import send_email
from .models import Account, ApiKey, new_id, utcnow
from .security import hash_password, make_token, new_api_key, password_version, read_token, verify_password

router = APIRouter()

DISPOSABLE = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "yopmail.com",
              "trashmail.com", "sharklasers.com", "getnada.com", "temp-mail.org", "throwawaymail.com"}


def _password_ok(password: str) -> bool:
    """SEC-008: length already enforced by Field; also require a letter and a digit."""
    return any(c.isalpha() for c in password) and any(c.isdigit() for c in password)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class SignupRequest(Credentials):
    # true: you accept the current Terms, Privacy Policy and Acceptable Use Policy (GET /v1/legal/policies).
    # The versions and the time are recorded (GET /v1/me/consents).
    accept_policies: bool | None = None


class ForgotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    password: str = Field(min_length=8, max_length=200)


class MfaCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=8)


def _pw_version(a: Account) -> str:
    """Changes whenever the password changes: reset links are single-use; session JWTs bind to it (SEC-002)."""
    return password_version(a.password_hash)


class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="default", min_length=1, max_length=80)


def account_json(db: Session, a: Account) -> dict:
    missing = legal.missing(db, a.id)
    return {"id": a.id, "email": a.email, "email_verified": a.email_verified, "plan": a.plan or "free",
            # true: a current policy version is not accepted yet (POST /v1/me/consents)
            "consent_required": bool(missing), "consents_missing": missing,
            "credits": ledger.balance(db, a.id), "created_at": a.created_at.isoformat() + "Z",
            # true: a ClutchClips admin (scripts/admin.py make-admin). The website shows the admin screens only then;
            # the admin routes check it themselves.
            "is_admin": bool(a.is_admin),
            # What Stripe last reported: null without a subscription; "past_due" means the last payment failed.
            "subscription_status": a.subscription_status,
            "subscription_cancel_at": a.subscription_cancel_at.isoformat() + "Z" if a.subscription_cancel_at else None}


def session_token(a: Account, *, amfa: int | None = None) -> str:
    """Session JWT bound to the current password version so a reset voids every outstanding session."""
    claims: dict = {"v": _pw_version(a)}
    if amfa is not None:
        claims["amfa"] = amfa  # unix time of last admin MFA step-up (SEC-004)
    return make_token(a.id, "session", timedelta(hours=get_settings().jwt_ttl_hours), **claims)


def mark_verified(db: Session, a: Account) -> None:
    """Verify the email and give the one-time free grant (idempotent)."""
    a.email_verified = True
    free = get_settings().free_signup_credits
    if free > 0:
        ledger.grant(db, a.id, free, "grant", f"signup:{a.id}", "Free signup credits")


def read_link_token(token: str, purpose: str) -> dict | None:
    """A verify or reset token, or None when it is invalid, expired, or from before the last epoch bump."""
    data = read_token(token, purpose)
    if data is None or data.get("e", 0) != token_epoch.current():
        return None
    return data


def send_verification(a: Account) -> bool:
    s = get_settings()
    token = make_token(a.id, "verify", timedelta(hours=48), e=token_epoch.current())
    link = f"{s.public_api_url}/v1/auth/verify?token={token}"
    return send_email(a.email, "Confirm your email",
                      f"Confirm your email to activate your account and get your free credits:\n\n{link}\n\n"
                      "If you didn't sign up, ignore this message.", idempotency_key=f"verify:{uuid.uuid4().hex}")


@router.post("/v1/auth/signup", status_code=201, summary="Sign up")
def signup(body: SignupRequest, request: Request, db: Session = Depends(get_db)):
    """Create an account. Returns a session token. Free signup credits land after email verification (when required)."""
    s = get_settings()
    ip = client_ip(request)
    rate_limit(f"signup:{ip}", s.signup_limit_per_ip_per_hour, 3600)
    if s.require_terms_acceptance and body.accept_policies is not True:
        raise ApiError(422, "terms_required", "Send accept_policies: true to accept the Terms of Service, Privacy "
                                              "Policy and Acceptable Use Policy (GET /v1/legal/policies).")
    if not _password_ok(body.password):
        raise ApiError(422, "weak_password", "Password must include at least one letter and one digit.")
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
    if body.accept_policies is True:
        legal.record(db, account.id, legal.current_versions(), "signup")
    if s.auto_verify_email:
        mark_verified(db, account)
    db.commit()
    if not s.auto_verify_email:
        send_verification(account)
    return {"token": session_token(account), "account": account_json(db, account)}


@router.post("/v1/auth/login", summary="Log in")
def login(body: Credentials, request: Request, db: Session = Depends(get_db)):
    """Exchange email and password for a session token used as `Authorization: Bearer`."""
    rate_limit(f"login:{client_ip(request)}", get_settings().login_limit_per_ip_per_minute, 60)
    account = db.execute(select(Account).where(Account.email == body.email.strip().lower())).scalar_one_or_none()
    if not account or not verify_password(account.password_hash, body.password):
        raise ApiError(401, "invalid_credentials", "Wrong email or password.")
    if account.status != "active":
        raise ApiError(403, "account_suspended", "This account is suspended.")
    return {"token": session_token(account), "account": account_json(db, account)}


@router.get("/v1/auth/verify")
def verify(token: str, request: Request, db: Session = Depends(get_db)):
    data = read_link_token(token, "verify")
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
    return {"sent": send_verification(p.account)}     # false: delivery failed; try again later


@router.post("/v1/auth/forgot")
def forgot(body: ForgotRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"forgot:{client_ip(request)}", 5, 3600)
    account = db.execute(select(Account).where(Account.email == body.email.strip().lower())).scalar_one_or_none()
    if account:
        token = make_token(account.id, "reset", timedelta(hours=1), v=_pw_version(account), e=token_epoch.current())
        # A failed delivery is logged by the emailer (masked address, no link); the answer stays the same.
        send_email(account.email, "Reset your password",
                   f"Reset your password here (link valid for 1 hour):\n\n"
                   f"{get_settings().public_web_url}/reset-password?token={token}\n\n"
                   "If you didn't ask for this, ignore this message.", idempotency_key=f"reset:{uuid.uuid4().hex}")
    return {"sent": True}   # same answer whether or not the email exists, and whether or not it was delivered


@router.post("/v1/auth/reset")
def reset(body: ResetRequest, db: Session = Depends(get_db)):
    data = read_link_token(body.token, "reset")
    account = db.get(Account, data["sub"]) if data else None
    if not account or data.get("v") != _pw_version(account):
        raise ApiError(400, "invalid_token", "This reset link is invalid, expired or already used.")
    if not _password_ok(body.password):
        raise ApiError(422, "weak_password", "Password must include at least one letter and one digit.")
    account.password_hash = hash_password(body.password)
    db.commit()
    return {"reset": True}


@router.post("/v1/auth/mfa/enroll", summary="Enroll admin TOTP")
def mfa_enroll(p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Generate a TOTP secret for an admin account. Secret returned once; required when ADMIN_MFA_REQUIRED."""
    if not p.account.is_admin:
        raise ApiError(403, "admin_required", "MFA enrollment is for ClutchClips admins.")
    account = db.get(Account, p.account.id)
    if account.mfa_secret:
        raise ApiError(409, "mfa_already_enrolled", "MFA is already enrolled. Use scripts/admin.py reset-mfa to rotate.")
    secret = pyotp.random_base32()
    account.mfa_secret = secret
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=account.email, issuer_name="ClutchClips Admin")
    return {"enrolled": True, "secret": secret, "otpauth_url": uri}


@router.post("/v1/auth/mfa/verify", summary="Verify admin TOTP step-up")
def mfa_verify(body: MfaCode, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Exchange a valid TOTP code for a session token with an admin MFA claim (SEC-004)."""
    if not p.account.is_admin:
        raise ApiError(403, "admin_required", "MFA verify is for ClutchClips admins.")
    account = db.get(Account, p.account.id)
    if not account.mfa_secret:
        raise ApiError(400, "mfa_not_enrolled", "Enroll MFA first (POST /v1/auth/mfa/enroll).")
    rate_limit(f"mfa:{account.id}", 10, 60)
    if not pyotp.TOTP(account.mfa_secret).verify(body.code.strip(), valid_window=1):
        raise ApiError(401, "invalid_mfa", "Invalid or expired MFA code.")
    return {"token": session_token(account, amfa=int(time.time())), "account": account_json(db, account)}


@router.get("/v1/me", summary="Current account")
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Plan, credit balance, and verification state for the caller. Session auth also returns `webhook_secret`."""
    out = account_json(db, p.account)
    if p.via == "session":
        out["webhook_secret"] = p.account.webhook_secret
        out["mfa_enrolled"] = bool(p.account.mfa_secret) if p.account.is_admin else False
        out["mfa_ok"] = bool(
            p.account.is_admin and isinstance(p.claims.get("amfa"), (int, float))
            and (time.time() - float(p.claims["amfa"])) <= get_settings().admin_mfa_ttl_sec
        )
    return out


@router.post("/v1/keys", status_code=201, summary="Create API key")
def create_key(body: KeyCreate, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Mint a key (`gck_…`) for programmatic access. The full key is returned once and never stored again."""
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


@router.get("/v1/keys", summary="List API keys")
def list_keys(p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Active keys for the account (prefix and metadata only; the secret is never shown again)."""
    keys = db.execute(select(ApiKey).where(ApiKey.account_id == p.account.id,
                                           ApiKey.revoked_at.is_(None)).order_by(ApiKey.created_at)).scalars()
    return {"keys": [{"id": k.id, "name": k.name, "prefix": k.prefix,
                      "created_at": k.created_at.isoformat() + "Z",
                      "last_used_at": k.last_used_at.isoformat() + "Z" if k.last_used_at else None}
                     for k in keys]}


@router.delete("/v1/keys/{key_id}", summary="Revoke API key")
def revoke_key(key_id: str, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Revoke a key. Existing Bearer tokens with that key stop working immediately."""
    key = db.get(ApiKey, key_id)
    if not key or key.account_id != p.account.id or key.revoked_at:
        raise ApiError(404, "not_found", "No such API key.")
    key.revoked_at = utcnow()
    db.commit()
    return {"revoked": True}
