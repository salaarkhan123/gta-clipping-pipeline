"""Admin decisions on copyright and likeness cases: disable hides and keeps files, restore brings content back,
delete removes the files only after a verified removal, every decision is one event, strikes and the
repeat-infringer rule, counter-notices from the content's owner only, and what the reported user can see."""
import uuid

import pytest
from sqlalchemy import select

from app import deps, routes_trust, worker
from app.config import get_settings
from app.db import new_session
from app.models import Account, CaseEvent, Clip, TrustCase
from app.storage import get_storage
from tests.test_api import upload

COUNTER = {"name": "Stream Er", "address": "2 Side St, Calgary AB", "phone": "+1 555 0101",
           "explanation": "This is my own stream recording.", "mistake": True, "consent": True,
           "signature": "Stream Er"}


@pytest.fixture(autouse=True)
def fresh_limits():
    deps._buckets.clear()
    yield
    deps._buckets.clear()


@pytest.fixture
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(routes_trust, "send_email", lambda to, subject, body, **kw: sent.append((to, subject, body)))
    return sent


def signup(client):
    r = client.post("/v1/auth/signup", json={"email": f"d{uuid.uuid4().hex[:10]}@example.org",
                                              "password": "correct-horse-9"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]


@pytest.fixture
def admin(client):
    h, acct = signup(client)
    with new_session() as db:
        db.get(Account, acct["id"]).is_admin = True
        db.commit()
    return h, acct


@pytest.fixture
def owned(client, video, transcriber):
    """A user with an upload and one finished clip, with real files."""
    h, acct = signup(client)
    up = upload(client, h, video)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                    headers=h)
    assert r.status_code == 202, r.text
    assert worker.run_once(transcriber) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=h).json()
    return {"h": h, "account": acct, "upload": up["upload_id"], "job": job["job_id"], "clip": job["clips"][0]["id"]}


def report(client, *ids, kind="copyright"):
    b = {"kind": kind, "name": "Rights Holder", "email": f"c{uuid.uuid4().hex[:8]}@studio-example.com",
         "organization": "Studio Ltd", "address": "1 Main St", "phone": "+1 555 0100",
         "relationship": "owner" if kind == "copyright" else "self", "work": "My original recording",
         "reported_urls": list(ids), "good_faith": True, "accurate": True, "signature": "Rights Holder"}
    r = client.post("/v1/trust/reports", json=b)
    assert r.status_code == 201, r.text
    return r.json()["reference"], b


def decide(client, admin_h, ref, action, **extra):
    return client.post(f"/v1/admin/trust/cases/{ref}/decisions", json={"action": action, **extra}, headers=admin_h)


def clip_keys(clip_id):
    with new_session() as db:
        c = db.get(Clip, clip_id)
        return [k for k in (c.video_key, c.thumb_key, c.captions_key, c.preview_key, c.export_key) if k]


def visible(client, o):
    clips = client.get("/v1/clips", headers=o["h"]).json()["clips"]
    project = client.get(f"/v1/projects/{o['upload']}", headers=o["h"])
    return any(c["id"] == o["clip"] for c in clips), project.status_code


def events(ref):
    with new_session() as db:
        case = db.execute(select(TrustCase).where(TrustCase.reference == ref)).scalar_one()
        return [(e.actor_kind, e.action) for e in
                db.execute(select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.id)).scalars()]


def test_disable_hides_everything_and_restore_brings_it_back_with_its_files(client, mail, admin, owned):
    ref, _ = report(client, owned["upload"])
    keys = clip_keys(owned["clip"])
    assert visible(client, owned) == (True, 200)
    r = decide(client, admin[0], ref, "disable", note="checking the claim")
    assert r.status_code == 200, r.text and r.json()["status"] == "disabled"
    assert visible(client, owned) == (False, 404)
    assert client.get(f"/v1/jobs/{owned['job']}", headers=owned["h"]).json()["clips"] == []
    assert all(get_storage().exists(k) for k in keys)                      # files kept
    assert owned["account"]["email"] in [m[0] for m in mail]               # the owner is told
    assert client.post("/v1/clips", json={"upload_id": owned["upload"]}, headers=owned["h"]).status_code == 404
    r = decide(client, admin[0], ref, "restore")
    assert r.json()["status"] == "restored"
    assert visible(client, owned) == (True, 200)
    assert events(ref) == [("claimant", "received"), ("admin", "disable"), ("admin", "restore")]


@pytest.mark.parametrize("second", ["clip", "upload"])
def test_restoring_one_case_never_undoes_another_cases_removal(client, mail, admin, owned, second):
    """Two cases on the same content (Codex, #218): A disables, B disables too; restoring or rejecting A keeps
    the content hidden while B still holds it, and it comes back only when B lets go as well."""
    a, _ = report(client, owned["clip"])
    b, _ = report(client, owned[second])
    assert decide(client, admin[0], a, "disable").status_code == 200
    assert decide(client, admin[0], b, "disable").status_code == 200
    assert visible(client, owned)[0] is False
    assert decide(client, admin[0], a, "restore").json()["status"] == "restored"
    assert visible(client, owned)[0] is False                     # B still holds it
    assert decide(client, admin[0], b, "reject", message="Not your work").json()["status"] == "rejected"
    assert visible(client, owned)[0] is True                      # nobody holds it now


def test_reject_after_disable_puts_the_content_back(client, mail, admin, owned):
    ref, _ = report(client, owned["clip"])
    decide(client, admin[0], ref, "disable")
    assert visible(client, owned)[0] is False
    assert decide(client, admin[0], ref, "reject", message="Not your work").json()["status"] == "rejected"
    assert visible(client, owned)[0] is True


def test_delete_content_only_after_a_verified_removal_and_it_removes_every_file(client, mail, admin, owned):
    ref, _ = report(client, owned["upload"])
    keys = clip_keys(owned["clip"])
    r = decide(client, admin[0], ref, "delete_content")
    assert r.status_code == 409 and r.json()["error"]["code"] == "decision_not_allowed"
    decide(client, admin[0], ref, "disable")
    assert decide(client, admin[0], ref, "delete_content").status_code == 409     # disabled is not verified
    assert decide(client, admin[0], ref, "remove").json()["status"] == "removed"
    assert all(get_storage().exists(k) for k in keys)
    r = decide(client, admin[0], ref, "delete_content", note="verified infringement")
    assert r.status_code == 200
    with new_session() as db:
        from app.models import Upload
        up_key = db.get(Upload, owned["upload"]).storage_key
    assert not any(get_storage().exists(k) for k in [*keys, up_key])
    assert {t["state"] for t in r.json()["targets"]} == {"deleted"}
    assert decide(client, admin[0], ref, "restore").json()["status"] == "restored"   # nothing to bring back
    assert visible(client, owned) == (False, 404)


def test_each_decision_adds_exactly_one_admin_event_with_actor_and_time(client, mail, admin, owned):
    ref, _ = report(client, owned["clip"])
    for action, extra in (("review", {}), ("request_info", {"message": "Which stream?"}), ("note", {"note": "x"}),
                          ("disable", {}), ("forward_notice", {})):
        before = len(events(ref))
        assert decide(client, admin[0], ref, action, **extra).status_code == 200, action
        assert len(events(ref)) == before + 1
    full = client.get(f"/v1/admin/trust/cases/{ref}", headers=admin[0]).json()
    last = full["events"][-1]
    assert last["action"] == "forward_notice" and last["actor_id"] == admin[1]["id"] and last["created_at"]
    assert full["events"][2]["data"]["message"] == "Which stream?"


def test_request_info_needs_a_message_and_wrong_statuses_are_refused(client, mail, admin, owned):
    ref, _ = report(client, owned["clip"])
    assert decide(client, admin[0], ref, "request_info").json()["error"]["code"] == "message_required"
    assert decide(client, admin[0], ref, "close").status_code == 409
    assert decide(client, admin[0], ref, "bogus").status_code == 422


def strikes_of(account_id):
    from app.trust_decisions import strikes
    with new_session() as db:
        return strikes(db, account_id)


def status_of(account_id):
    with new_session() as db:
        return db.get(Account, account_id).status


def test_three_verified_removals_suspend_the_account(client, mail, admin, owned):
    acct = owned["account"]["id"]
    for i in range(3):
        ref, _ = report(client, owned["clip"])
        assert decide(client, admin[0], ref, "remove").status_code == 200
        assert strikes_of(acct) == i + 1
    assert status_of(acct) == "suspended"
    assert ("system", "account_suspended") in events(ref)
    assert client.get("/v1/me", headers=owned["h"]).status_code == 403


def test_rejected_withdrawn_and_countered_cases_leave_no_strike(client, mail, admin, owned):
    acct = owned["account"]["id"]
    rejected, _ = report(client, owned["clip"])
    decide(client, admin[0], rejected, "reject")
    withdrawn, _ = report(client, owned["clip"])
    decide(client, admin[0], withdrawn, "remove")
    assert strikes_of(acct) == 1
    decide(client, admin[0], withdrawn, "withdraw", note="claimant withdrew by email")
    assert strikes_of(acct) == 0
    countered, _ = report(client, owned["clip"])
    decide(client, admin[0], countered, "remove")
    r = client.post(f"/v1/trust/my-cases/{countered}/counter-notice", json=COUNTER, headers=owned["h"])
    assert r.status_code == 200, r.text and r.json()["status"] == "counter_noticed"
    assert strikes_of(acct) == 1
    decide(client, admin[0], countered, "restore", note="no court action in 10 business days")
    assert strikes_of(acct) == 0 and status_of(acct) == "active"


def test_strikes_can_expire(client, mail, admin, owned, monkeypatch):
    ref, _ = report(client, owned["clip"])
    decide(client, admin[0], ref, "remove")
    assert strikes_of(owned["account"]["id"]) == 1
    from datetime import timedelta
    from app.models import utcnow
    with new_session() as db:
        case = db.execute(select(TrustCase).where(TrustCase.reference == ref)).scalar_one()
        strike = db.execute(select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.action == "strike")).scalar_one()
        when = strike.created_at
    monkeypatch.setattr(get_settings(), "repeat_infringer_strike_days", 30)
    monkeypatch.setattr("app.trust_decisions.utcnow", lambda: when + timedelta(days=31))
    assert strikes_of(owned["account"]["id"]) == 0


def test_terminate_suspends_at_once_for_a_serious_violation(client, mail, admin, owned):
    ref, _ = report(client, owned["clip"], kind="likeness")
    r = decide(client, admin[0], ref, "terminate", account_id=owned["account"]["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "note_required"
    _, other = signup(client)
    r = decide(client, admin[0], ref, "terminate", account_id=other["id"], note="x")
    assert r.json()["error"]["code"] == "not_a_reported_account" and status_of(other["id"]) == "active"
    r = decide(client, admin[0], ref, "terminate", account_id=owned["account"]["id"], note="sexual deepfake")
    assert r.status_code == 200 and status_of(owned["account"]["id"]) == "suspended"
    assert [a for _k, a in events(ref)][-2:] == ["terminate", "account_suspended"]


def test_counter_notice_only_from_the_owner_and_only_after_action(client, mail, admin, owned):
    ref, claim = report(client, owned["clip"])
    r = client.post(f"/v1/trust/my-cases/{ref}/counter-notice", json=COUNTER, headers=owned["h"])
    assert r.status_code == 409                                         # nothing was disabled yet
    decide(client, admin[0], ref, "disable")
    stranger, _ = signup(client)
    assert client.post(f"/v1/trust/my-cases/{ref}/counter-notice", json=COUNTER, headers=stranger).status_code == 404
    assert client.post(f"/v1/trust/my-cases/{ref}/counter-notice", json=COUNTER).status_code == 401
    bad = client.post(f"/v1/trust/my-cases/{ref}/counter-notice", json={**COUNTER, "consent": False}, headers=owned["h"])
    assert bad.status_code == 422
    mail.clear()
    r = client.post(f"/v1/trust/my-cases/{ref}/counter-notice", json=COUNTER, headers=owned["h"])
    assert r.status_code == 200 and r.json()["status"] == "counter_noticed"
    to_claimant = next(m for m in mail if m[0] == claim["email"])
    assert COUNTER["address"] in to_claimant[2] and COUNTER["phone"] in to_claimant[2]       # 512(g)(2)(B)


def test_the_reported_user_never_sees_the_claimants_contact_details(client, mail, admin, owned):
    ref, claim = report(client, owned["clip"])
    decide(client, admin[0], ref, "forward_notice")
    mine = client.get("/v1/trust/my-cases", headers=owned["h"]).json()["cases"]
    (case,) = [c for c in mine if c["reference"] == ref]
    assert case["reported_by"] == "Studio Ltd" and case["your_content"][0]["id"] == owned["clip"]
    to_owner = [m for m in mail if m[0] == owned["account"]["email"]]
    for private in (claim["email"], claim["address"], claim["phone"]):
        assert private not in str(case) and not any(private in m[2] for m in to_owner)
    stranger, _ = signup(client)
    assert all(c["reference"] != ref for c in client.get("/v1/trust/my-cases", headers=stranger).json()["cases"])
