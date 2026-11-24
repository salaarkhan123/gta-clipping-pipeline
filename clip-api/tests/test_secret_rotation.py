"""SECRET_KEY rotation (docs/ops/credential-rotation.md): SECRET_KEY signs session tokens, email verification and
password reset links, and local-disk download links. SECRET_KEY_PREVIOUS keeps the old ones readable during an
overlap; new tokens are always signed with SECRET_KEY. API keys and passwords do not depend on it."""
from datetime import timedelta

import pytest

from app.config import Settings, get_settings
from app.security import hash_api_key, make_token, read_token

OLD = "old-secret-key-old-secret-key-0000000"
NEW = "new-secret-key-new-secret-key-1111111"


@pytest.fixture
def rotated(monkeypatch):
    """Tokens are made with OLD, then the server moves to NEW. Returns a function that sets SECRET_KEY_PREVIOUS."""
    monkeypatch.setattr(get_settings(), "secret_key", OLD)
    tokens = {p: make_token("acct_x", p, timedelta(hours=1)) for p in ("session", "verify", "reset", "file")}
    monkeypatch.setattr(get_settings(), "secret_key", NEW)
    return tokens, lambda value: monkeypatch.setattr(get_settings(), "secret_key_previous", value)


def test_rotating_without_an_overlap_invalidates_every_old_token(rotated):
    tokens, previous = rotated
    previous("")
    assert all(read_token(t, p) is None for p, t in tokens.items())


def test_the_previous_key_keeps_old_tokens_valid_and_new_ones_use_the_new_key(rotated):
    tokens, previous = rotated
    previous(OLD)
    assert all(read_token(t, p)["sub"] == "acct_x" for p, t in tokens.items())
    assert read_token(tokens["verify"], "session") is None                # the purpose is still checked
    fresh = make_token("acct_y", "session", timedelta(hours=1))
    previous("")
    assert read_token(fresh, "session")["sub"] == "acct_y"                # signed with NEW, not OLD


def test_an_expired_token_stays_expired_under_either_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "secret_key", OLD)
    expired = make_token("acct_x", "session", timedelta(seconds=-5))
    monkeypatch.setattr(get_settings(), "secret_key", NEW)
    monkeypatch.setattr(get_settings(), "secret_key_previous", OLD)
    assert read_token(expired, "session") is None


def test_a_token_signed_with_an_unknown_key_is_refused(monkeypatch):
    monkeypatch.setattr(get_settings(), "secret_key", "some-other-key-some-other-key-22222")
    forged = make_token("acct_x", "session", timedelta(hours=1))
    monkeypatch.setattr(get_settings(), "secret_key", NEW)
    monkeypatch.setattr(get_settings(), "secret_key_previous", OLD)
    assert read_token(forged, "session") is None


def test_a_website_session_survives_the_rotation_only_with_the_overlap(client, user, monkeypatch):
    headers, account = user                                       # signed with the suite's SECRET_KEY
    old = get_settings().secret_key
    monkeypatch.setattr(get_settings(), "secret_key", NEW)
    assert client.get("/v1/me", headers=headers).status_code == 401
    monkeypatch.setattr(get_settings(), "secret_key_previous", old)
    assert client.get("/v1/me", headers=headers).json()["id"] == account["id"]


def test_api_keys_do_not_depend_on_the_secret_key(client, user, monkeypatch):
    headers, _ = user
    raw = client.post("/v1/keys", json={"name": "rotation"}, headers=headers).json()["key"]
    digest = hash_api_key(raw)
    monkeypatch.setattr(get_settings(), "secret_key", NEW)
    assert hash_api_key(raw) == digest
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {raw}"}).status_code == 200


def test_production_refuses_a_short_previous_key():
    prod = dict(env="prod", secret_key=NEW, database_url="postgresql://x/y", auto_verify_email=False,
                email_provider="smtp", smtp_host="smtp.example.invalid", admin_mfa_required=True,
                storage_backend="s3", s3_bucket="clips", s3_access_key_id="id", s3_secret_access_key="secret",
                s3_endpoint_url="https://example.r2.cloudflarestorage.com",
                stripe_secret_key="", stripe_webhook_secret="")
    with pytest.raises(RuntimeError, match="SECRET_KEY_PREVIOUS"):
        Settings(**prod, secret_key_previous="short").check_production()
    Settings(**prod, secret_key_previous=OLD).check_production()
