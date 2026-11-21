import hashlib
import ipaddress
import secrets
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from .config import get_settings

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


def is_public_https_url(url: str) -> bool:
    """Webhook targets must be https and must not resolve to private or local addresses (SSRF guard)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False
        return bool(infos)
    except (OSError, ValueError):
        return False
