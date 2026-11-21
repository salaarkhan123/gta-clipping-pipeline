"""Encrypt OAuth tokens at rest. Key from PUBLISH_TOKEN_KEY; PUBLISH_TOKEN_KEY_OLD for rotation reads."""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from ..config import get_settings
from ..deps import ApiError


def _fernets() -> MultiFernet:
    s = get_settings()
    keys = [k for k in (s.publish_token_key, s.publish_token_key_old) if k]
    if not keys:
        raise ApiError(503, "publishing_misconfigured", "Publishing token encryption is not configured.")
    try:
        return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])
    except (ValueError, TypeError) as e:
        raise ApiError(503, "publishing_misconfigured", "Publishing token encryption key is invalid.") from e


def encrypt(plain: str | None) -> str | None:
    if plain is None:
        return None
    return _fernets().encrypt(plain.encode()).decode()


def decrypt(blob: str | None) -> str | None:
    if blob is None:
        return None
    try:
        return _fernets().decrypt(blob.encode()).decode()
    except InvalidToken as e:
        raise ApiError(503, "publishing_misconfigured", "Stored token could not be decrypted.") from e
