"""SEC-004: admin routes require TOTP step-up when ADMIN_MFA_REQUIRED is on."""
import time
import uuid

import pyotp
import pytest

from app.config import get_settings
from app.db import new_session
from app.models import Account


@pytest.fixture
def admin_user(client):
    email = f"a{uuid.uuid4().hex[:10]}@example.org"
    r = client.post("/v1/auth/signup", json={"email": email, "password": "correct-horse-9"})
    assert r.status_code == 201, r.text
    token, acct = r.json()["token"], r.json()["account"]
    with new_session() as db:
        db.get(Account, acct["id"]).is_admin = True
        db.commit()
    return {"Authorization": f"Bearer {token}"}, acct, email


def test_admin_works_without_mfa_when_not_required(client, admin_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_mfa_required", False)
    h, _acct, _email = admin_user
    assert client.get("/v1/admin/trust/cases", headers=h).status_code == 200


def test_admin_denied_until_enroll_and_verify(client, admin_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_mfa_required", True)
    h, _acct, _email = admin_user
    denied = client.get("/v1/admin/trust/cases", headers=h)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "mfa_setup_required"

    enrolled = client.post("/v1/auth/mfa/enroll", headers=h)
    assert enrolled.status_code == 200, enrolled.text
    secret = enrolled.json()["secret"]
    assert secret and enrolled.json()["otpauth_url"].startswith("otpauth://")

    still = client.get("/v1/admin/trust/cases", headers=h)
    assert still.status_code == 403 and still.json()["error"]["code"] == "mfa_required"

    bad = client.post("/v1/auth/mfa/verify", json={"code": "000000"}, headers=h)
    assert bad.status_code == 401

    code = pyotp.TOTP(secret).now()
    ok = client.post("/v1/auth/mfa/verify", json={"code": code}, headers=h)
    assert ok.status_code == 200, ok.text
    stepped = {"Authorization": f"Bearer {ok.json()['token']}"}
    assert client.get("/v1/admin/trust/cases", headers=stepped).status_code == 200
    me = client.get("/v1/me", headers=stepped).json()
    assert me["mfa_enrolled"] is True and me["mfa_ok"] is True


def test_mfa_claim_expires(client, admin_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_mfa_required", True)
    monkeypatch.setattr(get_settings(), "admin_mfa_ttl_sec", 1)
    h, _acct, _email = admin_user
    secret = client.post("/v1/auth/mfa/enroll", headers=h).json()["secret"]
    token = client.post("/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()}, headers=h).json()["token"]
    stepped = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/admin/trust/cases", headers=stepped).status_code == 200
    time.sleep(1.1)
    expired = client.get("/v1/admin/trust/cases", headers=stepped)
    assert expired.status_code == 403 and expired.json()["error"]["code"] == "mfa_required"
