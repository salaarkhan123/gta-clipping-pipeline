"""SEC-002: password reset voids outstanding session JWTs via password-version claim."""
import uuid
from datetime import timedelta

from app import token_epoch
from app.db import new_session
from app.models import Account
from app.routes_auth import _pw_version
from app.security import make_token, password_version, read_token


def signup(client):
    email = f"r{uuid.uuid4().hex[:10]}@example.org"
    password = "correct-horse-9"
    r = client.post("/v1/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["token"], r.json()["account"], email, password


def test_session_carries_password_version(client):
    token, acct, _email, _pw = signup(client)
    with new_session() as db:
        account = db.get(Account, acct["id"])
        data = read_token(token, "session")
        assert data is not None and data["v"] == password_version(account.password_hash)


def test_password_reset_invalidates_prior_session(client):
    old_token, acct, email, _password = signup(client)
    headers = {"Authorization": f"Bearer {old_token}"}
    assert client.get("/v1/me", headers=headers).status_code == 200

    # Mint a reset token directly (skip /forgot so a JWT is not emailed into the suite log scan).
    with new_session() as db:
        account = db.get(Account, acct["id"])
        reset = make_token(account.id, "reset", timedelta(hours=1),
                           v=_pw_version(account), e=token_epoch.current())

    r = client.post("/v1/auth/reset", json={"token": reset, "password": "new-correct-horse-9"})
    assert r.status_code == 200, r.text
    assert client.get("/v1/me", headers=headers).status_code == 401

    login = client.post("/v1/auth/login", json={"email": email, "password": "new-correct-horse-9"})
    assert login.status_code == 200
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {login.json()['token']}"}).status_code == 200


def test_legacy_session_without_version_is_rejected(client):
    _token, acct, _email, _pw = signup(client)
    legacy = make_token(acct["id"], "session", timedelta(hours=1))  # no v claim
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401
