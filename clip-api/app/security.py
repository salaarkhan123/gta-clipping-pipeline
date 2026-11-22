import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from .config import get_settings
from .pinned_http import is_public_https_url  # noqa: F401  — re-export for callers

_ph = PasswordHasher()
API_KEY_PREFIX = "gck_"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def make_token(subject: str, purpose: str, ttl: timedelta, **claims) -> str:
    payload = {"sub": subject, "p": purpose, "exp": datetime.now(timezone.utc) + ttl, **claims}
    return jwt.encode(payload, get_settings().secret_key, algorithm="HS256")


def read_token(token: str, purpose: str) -> dict | None:
    """The claims of a token signed with SECRET_KEY, or with SECRET_KEY_PREVIOUS during a rotation."""
    s = get_settings()
    for key in filter(None, (s.secret_key, s.secret_key_previous)):
        try:
            data = jwt.decode(token, key, algorithms=["HS256"])
        except jwt.InvalidSignatureError:
            continue
        except jwt.PyJWTError:
            return None                    # expired, malformed or otherwise invalid whichever key signed it
        return data if data.get("p") == purpose else None
    return None


def new_api_key() -> tuple[str, str, str]:
    """Returns (full_key, display_prefix, sha256_hash). Only the hash is stored."""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:12], hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def password_version(password_hash: str) -> str:
    """Short fingerprint of the current password hash; embedded in session JWTs so a reset voids them."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]
