"""Legal policy versions and consent records: what an account accepted, when, and what it still has to accept."""
import uuid

import pytest
from sqlalchemy import select

from app import legal
from app.config import get_settings
from app.db import new_session
from app.legal import POLICIES, REQUIRED, Policy
from app.models import PolicyAcceptance


def signup(client, **extra):
    r = client.post("/v1/auth/signup", json={"email": f"c{uuid.uuid4().hex[:10]}@example.org",
                                              "password": "correct-horse-9", **extra})
    return r


def auth(r):
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_policies_are_public_with_version_date_and_page(client):
    r = client.get("/v1/legal/policies")
    assert r.status_code == 200
    body = r.json()
    ids = [p["id"] for p in body["policies"]]
    assert ids == ["terms", "privacy", "acceptable-use", "copyright", "refunds", "cookies"]
    for p in body["policies"]:
        assert p["version"] and p["effective"] and p["path"].startswith("/")
    assert body["required"] == ["terms", "privacy", "acceptable-use"]


def test_signup_with_accept_policies_records_every_required_version(client):
    r = signup(client, accept_policies=True)
    assert r.status_code == 201, r.text
    assert r.json()["account"]["consent_required"] is False
    c = client.get("/v1/me/consents", headers=auth(r)).json()
    assert c["consent_required"] is False and c["missing"] == []
    got = {(a["policy"], a["version"], a["source"]) for a in c["acceptances"]}
    assert got == {(pid, POLICIES[pid].version, "signup") for pid in REQUIRED}
    assert all(a["accepted_at"].endswith("Z") for a in c["acceptances"])


def test_signup_without_it_still_works_but_reports_consent_required(client):
    r = signup(client)            # API clients from before consent records: not refused while the switch is off
    assert r.status_code == 201
    assert r.json()["account"]["consent_required"] is True
    me = client.get("/v1/me", headers=auth(r)).json()
    assert me["consent_required"] is True and me["consents_missing"] == list(REQUIRED)


def test_accept_policies_false_records_nothing(client):
    r = signup(client, accept_policies=False)
    assert r.status_code == 201
    assert client.get("/v1/me/consents", headers=auth(r)).json()["acceptances"] == []


def test_the_switch_makes_acceptance_mandatory_at_signup(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "require_terms_acceptance", True)
    r = signup(client)
    assert r.status_code == 422 and r.json()["error"]["code"] == "terms_required"
    assert signup(client, accept_policies=True).status_code == 201


def test_accepting_later_clears_consent_required(client):
    h = auth(signup(client))
    r = client.post("/v1/me/consents", json={"policies": legal.current_versions()}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["consent_required"] is False
    assert {a["source"] for a in r.json()["acceptances"]} == {"reaccept"}
    assert client.get("/v1/me", headers=h).json()["consent_required"] is False


def test_accepting_twice_adds_no_rows(client):
    r = signup(client, accept_policies=True)
    again = client.post("/v1/me/consents", json={"policies": legal.current_versions()}, headers=auth(r))
    assert again.status_code == 200
    assert len(again.json()["acceptances"]) == len(REQUIRED)


def test_a_stale_or_unknown_version_is_refused(client):
    h = auth(signup(client))
    stale = {**legal.current_versions(), "terms": "0.1"}
    r = client.post("/v1/me/consents", json={"policies": stale}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "policy_version_stale"
    r = client.post("/v1/me/consents", json={"policies": {"nonsense": "1"}}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_policy"
    assert client.get("/v1/me/consents", headers=h).json()["acceptances"] == []


def test_a_new_version_asks_again_and_keeps_the_old_record(client, monkeypatch):
    r = signup(client, accept_policies=True)
    h = auth(r)
    old = POLICIES["terms"]
    monkeypatch.setitem(POLICIES, "terms", Policy(old.id, old.title, "2.0", "2027-01-01", old.path, True))
    me = client.get("/v1/me", headers=h).json()
    assert me["consent_required"] is True and me["consents_missing"] == ["terms"]
    client.post("/v1/me/consents", json={"policies": {"terms": "2.0"}}, headers=h)
    rows = client.get("/v1/me/consents", headers=h).json()["acceptances"]
    assert [a["version"] for a in rows if a["policy"] == "terms"] == [old.version, "2.0"]


def test_consents_need_a_login_and_show_only_your_own(client):
    assert client.get("/v1/me/consents").status_code == 401
    assert client.post("/v1/me/consents", json={"policies": {}}).status_code == 401
    a, b = signup(client, accept_policies=True), signup(client)
    assert client.get("/v1/me/consents", headers=auth(b)).json()["acceptances"] == []
    assert len(client.get("/v1/me/consents", headers=auth(a)).json()["acceptances"]) == len(REQUIRED)


def test_acceptance_rows_cannot_be_changed_or_deleted(client):
    acct = signup(client, accept_policies=True).json()["account"]["id"]
    with new_session() as db:
        row = db.execute(select(PolicyAcceptance).where(PolicyAcceptance.account_id == acct)).scalars().first()
        row.version = "forged"
        with pytest.raises(RuntimeError, match="append-only"):
            db.flush()
        db.rollback()
        row = db.execute(select(PolicyAcceptance).where(PolicyAcceptance.account_id == acct)).scalars().first()
        db.delete(row)
        with pytest.raises(RuntimeError, match="append-only"):
            db.flush()
        db.rollback()


def test_migrations_have_one_head():
    """Two branches that both build on the same revision would leave two heads and break `migrate()`."""
    from alembic.script import ScriptDirectory

    from app.migrate import config
    assert len(ScriptDirectory.from_config(config()).get_heads()) == 1
