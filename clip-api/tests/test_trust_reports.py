"""Copyright and likeness reports: the public form's rules, what it stores and sends, that it changes no
content, and that every admin route is closed to everyone but an admin's website login."""
import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import deps, routes_trust
from app.db import new_session
from app.main import app
from app.models import Account, CaseEvent, CaseTarget, Clip, Job, TrustCase, Upload, new_id, utcnow
from app.security import make_token


@pytest.fixture(autouse=True)
def fresh_limits():
    deps._buckets.clear()          # one IP ("testclient") sends every report in this module
    yield
    deps._buckets.clear()


@pytest.fixture
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(routes_trust, "send_email", lambda to, subject, body, **kw: sent.append((to, subject, body)))
    return sent


def signup(client):
    r = client.post("/v1/auth/signup", json={"email": f"t{uuid.uuid4().hex[:10]}@example.org",
                                              "password": "correct-horse-9"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]


@pytest.fixture
def content(client):
    """User A's upload, job and clip, as rows (no files: a report only reads rows)."""
    _, acct = signup(client)
    now = utcnow()
    with new_session() as db:
        up = Upload(id=new_id("upl"), account_id=acct["id"], filename="a.mp4", storage_key=f"uploads/{acct['id']}/x.mp4",
                    size_bytes=1, duration_sec=60, width=1, height=1, has_audio=True, expires_at=now + timedelta(days=7))
        db.add(up)
        db.flush()
        job = Job(id=new_id("job"), account_id=acct["id"], upload_id=up.id, status="SUCCEEDED", options={},
                  duration_sec=60, credits_reserved=1, expires_at=now + timedelta(days=7))
        db.add(job)
        db.flush()
        clip = Clip(id=new_id("clip"), job_id=job.id, idx=0, start_sec=0, end_sec=10, score=1, signals={}, features={},
                    video_key=f"clips/{job.id}/x.mp4")
        db.add(clip)
        db.commit()
        return {"account": acct["id"], "upload": up.id, "job": job.id, "clip": clip.id}


def body(**over):
    base = {"kind": "copyright", "name": "Rights Holder", "email": f"claim{uuid.uuid4().hex[:8]}@studio-example.com",
            "organization": "Studio Ltd", "address": "1 Main St, Edmonton AB", "phone": "+1 555 0100",
            "relationship": "owner", "work": "My original stream recording of 12 Nov 2026",
            "reported_urls": ["https://clutchclips.io/dashboard/project/?id=upl_" + "0" * 24],
            "details": "Uploaded without permission", "good_faith": True, "accurate": True,
            "signature": "Rights Holder"}
    return {**base, **over}


def case_of(reference):
    with new_session() as db:
        return db.execute(select(TrustCase).where(TrustCase.reference == reference)).scalar_one_or_none()


def test_a_valid_report_opens_a_case_and_emails_the_claimant_and_admins(client, mail, monkeypatch, content):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "trust_admin_email", "admin@clutchclips-example.com")
    b = body(reported_urls=[f"https://api.clutchclips.io/v1/clips/{content['clip']}",
                            f"https://clutchclips.io/dashboard/project/?id={content['upload']}"])
    r = client.post("/v1/trust/reports", json=b)
    assert r.status_code == 201, r.text
    ref = r.json()["reference"]
    assert re.fullmatch(r"CC-[A-Z2-9]{4}-[A-Z2-9]{4}", ref) and r.json()["status"] == "received"
    case = case_of(ref)
    assert case.claimant_email == b["email"] and case.kind == "copyright" and case.ip_hash and "testclient" not in case.ip_hash
    with new_session() as db:
        targets = {(t.kind, t.target_id, t.account_id) for t in
                   db.execute(select(CaseTarget).where(CaseTarget.case_id == case.id)).scalars()}
        events = db.execute(select(CaseEvent).where(CaseEvent.case_id == case.id)).scalars().all()
    assert targets == {("clip", content["clip"], content["account"]), ("upload", content["upload"], content["account"])}
    assert [(e.actor_kind, e.action) for e in events] == [("claimant", "received")]
    assert [m[0] for m in mail] == [b["email"], "admin@clutchclips-example.com"]
    assert ref in mail[0][1] and ref in mail[1][2]
    admin_mail = mail[1][2]
    for private in (b["email"], b["address"], b["phone"]):
        assert private not in admin_mail                 # the admin reads those in the dashboard, not by email


def test_admin_notice_goes_to_admin_accounts_when_no_address_is_set(client, mail, content):
    _, admin = signup(client)
    with new_session() as db:
        db.get(Account, admin["id"]).is_admin = True
        db.commit()
    assert client.post("/v1/trust/reports", json=body()).status_code == 201
    assert admin["email"] in [m[0] for m in mail]


def test_a_likeness_report(client, mail):
    r = client.post("/v1/trust/reports", json=body(kind="likeness", relationship="self", address=None,
                                                   work="My face in an AI thumbnail I never agreed to"))
    assert r.status_code == 201 and r.json()["kind"] == "likeness"


@pytest.mark.parametrize("over, says", [
    ({"good_faith": False}, "good_faith and accurate"),
    ({"accurate": False}, "good_faith and accurate"),
    ({"signature": ""}, "signature"),
    ({"address": None}, "address is required"),
    ({"relationship": "self"}, "owner or agent"),
    ({"kind": "likeness", "relationship": "owner"}, "self or representative"),
    ({"reported_urls": []}, "reported_urls"),
    ({"reported_urls": ["https://x.test/a"] * 21}, "reported_urls"),
    ({"email": "not-an-email"}, "email"),
    ({"surprise": 1}, "surprise"),
])
def test_incomplete_reports_are_refused_with_the_reason(client, mail, over, says):
    before = _cases()
    r = client.post("/v1/trust/reports", json=body(**over))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert says in r.json()["error"]["message"]
    assert _cases() == before and mail == []


def _cases() -> int:
    with new_session() as db:
        return db.execute(select(func.count(TrustCase.id))).scalar_one()


def test_a_body_over_32_kb_is_refused(client, mail):
    r = client.post("/v1/trust/reports", json=body(details="x" * 40_000))
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


def test_the_sixth_report_in_an_hour_from_one_address_is_refused(client, mail):
    for _ in range(5):
        assert client.post("/v1/trust/reports", json=body()).status_code == 201
    r = client.post("/v1/trust/reports", json=body())
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


def test_the_fourth_report_in_a_day_for_one_claimant_email_is_refused(client, mail):
    same = body()
    for _ in range(3):
        assert client.post("/v1/trust/reports", json=same).status_code == 201
    deps._buckets.pop("trust:h:testclient", None)            # not the IP limit: the per-email one
    assert client.post("/v1/trust/reports", json=same).status_code == 429


def test_a_filled_spam_trap_looks_accepted_but_stores_and_sends_nothing(client, mail):
    before = _cases()
    r = client.post("/v1/trust/reports", json=body(website="http://spam.test"))
    assert r.status_code == 201 and r.json()["reference"].startswith("CC-")
    assert _cases() == before and mail == [] and case_of(r.json()["reference"]) is None


def test_a_report_changes_no_content(client, mail, content):
    def snapshot():
        with new_session() as db:
            up, job, clip = db.get(Upload, content["upload"]), db.get(Job, content["job"]), db.get(Clip, content["clip"])
            return (up.deleted_at, up.expires_at, job.status, job.cancel_requested, clip.deleted_at, clip.video_key)
    before = snapshot()
    urls = [f"x {content['upload']} {content['job']} {content['clip']}"]
    assert client.post("/v1/trust/reports", json=body(reported_urls=urls)).status_code == 201
    assert snapshot() == before


def test_signed_links_are_traced_to_their_content_even_after_expiry(client, mail, content):
    expired = make_token("file", "file", timedelta(seconds=-60), k=f"clips/{content['job']}/{content['clip']}.mp4")
    forged = expired[:-4] + ("AAAA" if not expired.endswith("AAAA") else "BBBB")
    s3 = (f"https://bucket.tor1.digitaloceanspaces.com/uploads/{content['account']}/{content['upload']}.mp4"
          "?X-Amz-Signature=abc")
    r = client.post("/v1/trust/reports", json=body(reported_urls=[
        f"https://api.clutchclips.io/v1/files/{expired}", f"https://api.clutchclips.io/v1/files/{forged}x", s3]))
    case = case_of(r.json()["reference"])
    with new_session() as db:
        found = {(t.kind, t.target_id) for t in db.execute(select(CaseTarget).where(CaseTarget.case_id == case.id)).scalars()}
    assert found == {("clip", content["clip"]), ("job", content["job"]), ("upload", content["upload"])}


def test_unknown_ids_are_not_targets(client, mail):
    r = client.post("/v1/trust/reports", json=body(reported_urls=["upl_" + "f" * 24, "clip_" + "e" * 24]))
    case = case_of(r.json()["reference"])
    with new_session() as db:
        assert db.execute(select(CaseTarget).where(CaseTarget.case_id == case.id)).first() is None


def test_case_events_cannot_be_changed_or_deleted(client, mail):
    case = case_of(client.post("/v1/trust/reports", json=body()).json()["reference"])
    with new_session() as db:
        ev = db.execute(select(CaseEvent).where(CaseEvent.case_id == case.id)).scalars().first()
        ev.note = "rewritten"
        with pytest.raises(RuntimeError, match="append-only"):
            db.flush()
        db.rollback()
        db.delete(db.execute(select(CaseEvent).where(CaseEvent.case_id == case.id)).scalars().first())
        with pytest.raises(RuntimeError, match="append-only"):
            db.flush()


# ---- admin routes: every one closed to anonymous callers, normal users, API keys, other admins' keys ----

def admin_routes() -> list[tuple[str, str]]:
    """Read from the OpenAPI document, so a new admin route shows up here without anyone listing it."""
    return sorted((m.upper(), path) for path, ops in app.openapi()["paths"].items() if path.startswith("/v1/admin/")
                  for m in ops)


@pytest.fixture
def people(client):
    admin_h, admin = signup(client)
    with new_session() as db:
        db.get(Account, admin["id"]).is_admin = True
        db.commit()
    key = client.post("/v1/keys", json={"name": "k"}, headers=admin_h).json()["key"]
    user_h, _ = signup(client)
    return {"admin": admin_h, "admin_key": {"Authorization": f"Bearer {key}"}, "user": user_h}


# Each admin route, with the body an admin's call sends. A new admin route must be added here.
ADMIN_BODIES = {
    ("GET", "/v1/admin/trust/cases"): None,
    ("GET", "/v1/admin/trust/cases/{reference}"): None,
    ("POST", "/v1/admin/trust/cases/{reference}/decisions"): {"action": "note", "note": "access test"},
    ("GET", "/v1/admin/accounts/{account_id}/export"): None,                       # (#149) emailed requests
    ("POST", "/v1/admin/accounts/{account_id}/delete"): {"note": "access test"},
}


def test_every_admin_route_has_an_access_case():
    assert admin_routes() == sorted(ADMIN_BODIES)


def _call(client, method, path, headers, ref, account_id):
    return client.request(method, path.replace("{reference}", ref).replace("{account_id}", account_id),
                          headers=headers or {}, json=ADMIN_BODIES[(method, path)])


@pytest.mark.parametrize("method, path", admin_routes())
def test_admin_routes_refuse_everyone_but_an_admin_login(client, mail, people, method, path):
    ref = client.post("/v1/trust/reports", json=body()).json()["reference"]
    _, throwaway = signup(client)           # the admin's own call may delete it
    assert _call(client, method, path, None, ref, throwaway["id"]).status_code == 401
    r = _call(client, method, path, people["user"], ref, throwaway["id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "admin_required"
    r = _call(client, method, path, people["admin_key"], ref, throwaway["id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "session_required"
    assert _call(client, method, path, people["admin"], ref, throwaway["id"]).status_code == 200


def test_the_case_list_leaves_out_contact_details_and_the_case_page_has_them(client, mail, people, content):
    b = body(reported_urls=[content["clip"]])
    ref = client.post("/v1/trust/reports", json=b).json()["reference"]
    listed = client.get("/v1/admin/trust/cases", headers=people["admin"]).json()
    row = next(c for c in listed["cases"] if c["reference"] == ref)
    assert b["email"] not in str(row) and b["address"] not in str(row) and row["targets"] == 1
    full = client.get(f"/v1/admin/trust/cases/{ref.lower()}", headers=people["admin"]).json()
    assert full["claimant"]["email"] == b["email"] and full["claimant"]["address"] == b["address"]
    assert full["targets"][0]["id"] == content["clip"] and full["events"][0]["action"] == "received"
    assert client.get("/v1/admin/trust/cases/CC-NONE-NONE", headers=people["admin"]).status_code == 404
    only = client.get("/v1/admin/trust/cases", params={"kind": "likeness"}, headers=people["admin"]).json()
    assert all(c["kind"] == "likeness" for c in only["cases"])
