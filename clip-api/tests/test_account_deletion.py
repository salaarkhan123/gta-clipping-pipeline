"""Delete my account and download my data (#149).

One account is given everything an account can have: uploads (one imported by link), a transcript, a search index,
clip and export jobs with clips and files, a premium thumbnail, saved templates, API keys, policy acceptances, a
payment, ledger rows, webhook deliveries and a report about its content. Deleting it must leave no stored object
and no row holding its personal data, keep the ledger as it was, and lock every way back in.
"""
import json
import secrets
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app import account_data, deps, ledger, routes_account
from app.config import get_settings
from app.db import Base, new_session
from app.models import (Account, ApiKey, CaseEvent, CaseTarget, Clip, ClipFeedback, ClipThumbnail, CreditLedger,
                        CustomTemplate, Export, ImportLog, Job, LikenessConsent, Payment, TrustCase, Upload,
                        WebhookDelivery, new_id, utcnow)
from app.storage import LocalStorage, get_storage
from tests.test_check_storage import keys as bucket_keys
from tests.test_check_storage import s3  # noqa: F401  (fixture: a private bucket on a local S3 server)

PASSWORD = "correct-horse-9"


@pytest.fixture(autouse=True)
def fresh_limits():
    deps._buckets.clear()
    yield
    deps._buckets.clear()


@pytest.fixture
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(routes_account, "send_email", lambda to, subject, body, **kw: sent.append((to, subject, body)))
    return sent


def signup(client, email: str | None = None) -> tuple[dict, dict]:
    email = email or f"del{uuid.uuid4().hex[:10]}@example.org"
    r = client.post("/v1/auth/signup", json={"email": email, "password": PASSWORD, "accept_policies": True})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]


def put(key: str, data: bytes = b"x") -> None:
    tmp = get_settings().storage_dir.parent / f"put-{uuid.uuid4().hex}"
    tmp.write_bytes(data)
    get_storage().put(key, tmp)
    tmp.unlink()


def stored_keys() -> set[str]:
    root = get_settings().storage_dir
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} if root.exists() else set()


def make_rich(client) -> dict:
    """An account with one of everything. Returns its headers, ids, the stored keys and the strings that must
    not survive deletion."""
    h, acct = signup(client)
    aid = acct["id"]
    key = client.post("/v1/keys", json={"name": "my-bot"}, headers=h).json()
    tpl = client.post("/v1/templates/custom", json={"name": f"Look {uuid.uuid4().hex[:6]}",
                                                   "options": {"captions": False}}, headers=h)
    assert tpl.status_code == 201, tpl.text
    now, tag = utcnow(), uuid.uuid4().hex[:10]
    s = {"ip": f"2001:db8::{tag[:4]}:{tag[4:8]}", "filename": f"my-private-stream-{tag}.mp4",
         "source_url": f"https://www.twitch.tv/videos/9{secrets.randbelow(10**9)}",
         "prompt": f"find the bit where I talk about my sister {tag}", "job_name": f"Sunday stream {tag}",
         "webhook": f"https://hooks.example.org/{tag}", "title": f"My clip title {tag}",
         "idem": f"idem-{tag}", "edit_text": f"edited words {tag}", "export_text": f"overlay {tag}"}
    with new_session() as db:
        a = db.get(Account, aid)
        a.signup_ip = s["ip"]
        k = db.get(ApiKey, key["id"])
        s.update(email=a.email, password_hash=a.password_hash, webhook_secret=a.webhook_secret,
                 key_hash=k.key_hash, key_prefix=k.prefix)
        up = Upload(id=new_id("upl"), account_id=aid, filename=s["filename"], storage_key=f"uploads/{aid}/x.mp4",
                    size_bytes=10, duration_sec=60, width=1, height=1, has_audio=True, content_hash="c" * 64,
                    expires_at=now + timedelta(days=7))
        imported = Upload(id=new_id("upl"), account_id=aid, filename="twitch.mp4", source_url=s["source_url"],
                          source_platform="twitch", storage_key=f"uploads/{aid}/y.mp4", size_bytes=10,
                          duration_sec=60, width=1, height=1, has_audio=True, expires_at=now + timedelta(days=7))
        db.add_all([up, imported])
        db.flush()
        up.storage_key, imported.storage_key = f"uploads/{aid}/{up.id}.mp4", f"uploads/{aid}/{imported.id}.mp4"
        imp = Job(id=new_id("imp"), account_id=aid, upload_id=imported.id, status="SUCCEEDED",
                  options={"tool": "import", "url": s["source_url"], "platform": "twitch"}, duration_sec=60,
                  credits_reserved=0, expires_at=now + timedelta(days=7))
        job = Job(id=new_id("job"), account_id=aid, upload_id=up.id, status="SUCCEEDED", name=s["job_name"],
                  options={"tool": "clips", "prompt": s["prompt"]}, duration_sec=60, credits_reserved=2,
                  webhook_url=s["webhook"], idempotency_key=s["idem"], result={"note": s["prompt"]},
                  expires_at=now + timedelta(days=7))
        export_job = Job(id=new_id("job"), account_id=aid, upload_id=up.id, status="SUCCEEDED",
                         options={"tool": "export", "source_job": job.id}, duration_sec=10, credits_reserved=1,
                         expires_at=now + timedelta(days=7))
        queued = Job(id=new_id("job"), account_id=aid, upload_id=up.id, status="QUEUED",
                     options={"tool": "clips", "prompt": s["prompt"]}, duration_sec=60, credits_reserved=5,
                     expires_at=now + timedelta(days=7), created_at=now + timedelta(days=3650))  # never claimed first
        db.add_all([imp, job, export_job, queued])
        db.flush()
        ledger.reserve(db, aid, job.id, 2)
        ledger.settle(db, job, success=True)
        ledger.reserve(db, aid, queued.id, 5)
        clip = Clip(id=new_id("clip"), job_id=job.id, idx=0, start_sec=0, end_sec=10, score=1,
                    signals={"loud": 1}, features={"thumbnail": {"frame_key": f"clips/{job.id}/c.frame.jpg"}},
                    video_key=f"clips/{job.id}/c.mp4", thumb_key=f"clips/{job.id}/c.jpg",
                    captions_key=f"clips/{job.id}/c.json", preview_key=f"clips/{job.id}/c.preview.mp4",
                    export_key=f"exports/{export_job.id}/e.mp4", meta={"title": s["title"]}, kept=True,
                    reaction="like", edit={"text": s["edit_text"]})
        db.add(clip)
        db.flush()
        thumb = ClipThumbnail(id=new_id("thb"), clip_id=clip.id, account_id=aid, kind="premium", style="cinematic",
                              instruction=s["prompt"][:200], clean_key=f"thumbs/{clip.id}/t.clean.jpg",
                              image_key=f"thumbs/{clip.id}/t.jpg", show_text=True)
        export = Export(id=new_id("exp"), clip_id=clip.id, account_id=aid, resolution="1080",
                        options={"text": s["export_text"]}, status="SUCCEEDED",
                        storage_key=f"exports/{export_job.id}/e.mp4")
        clip.thumb_id = thumb.id
        db.add_all([thumb, export,
                    LikenessConsent(account_id=aid, clip_id=clip.id, consent=True, wording="I am the streamer."),
                    ClipFeedback(clip_id=clip.id, account_id=aid, kind="kept", value="true"),
                    ImportLog(account_id=aid, source_url=s["source_url"], platform="twitch", consent=True),
                    WebhookDelivery(job_id=job.id, url=s["webhook"], status_code=200, attempt=1),
                    Payment(account_id=aid, kind="pack", stripe_ref=f"cs_{tag}", amount_cents=500, credits=100,
                            status="paid")])
        ledger.grant(db, aid, 100, "topup", f"stripe:cs_{tag}", "Credit pack")
        db.commit()
        ids = {"account": aid, "upload": up.id, "imported": imported.id, "job": job.id, "imp": imp.id,
               "export_job": export_job.id, "queued": queued.id, "clip": clip.id, "thumb": thumb.id,
               "export": export.id, "template": tpl.json()["id"], "key": key["id"]}
    keys = [up.storage_key, imported.storage_key, f"transcripts/{up.id}.json", f"transcripts/{up.id}.parts.json",
            f"index/{up.id}.npz", clip.video_key, clip.thumb_key, clip.captions_key, clip.preview_key,
            f"clips/{job.id}/c.frame.jpg", f"exports/{export_job.id}/e.mp4", thumb.clean_key, thumb.image_key,
            f"clips/{job.id}/a-file-nobody-listed.bin",          # unknown names: only the prefix finds them
            f"transcripts/{up.id}.someday-format.txt"]
    for k in keys:
        put(k)
    return {"h": h, "key_h": {"Authorization": f"Bearer {key['key']}"}, "ids": ids, "keys": keys, "secrets": s}


@pytest.fixture
def rich(client):
    return make_rich(client)


def ledger_rows(account_id: str) -> list[tuple]:
    with new_session() as db:
        return [(r.id, r.delta, r.kind, r.job_id, r.note, r.idempotency_key, r.created_at)
                for r in db.execute(select(CreditLedger).where(CreditLedger.account_id == account_id)
                                    .order_by(CreditLedger.id)).scalars()]


def delete_me(client, h, password=PASSWORD, confirm="DELETE"):
    return client.post("/v1/me/delete", json={"password": password, "confirm": confirm}, headers=h)


def every_value():
    """(table, column, row, text) for every value of every table."""
    with new_session() as db:
        for table in Base.metadata.sorted_tables:
            for row in db.execute(table.select()).mappings():
                for col, value in row.items():
                    if value is None:
                        continue
                    text = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
                    yield table.name, col, row, text


# ---- AC1: nothing of the account is left ----

def test_ac1_deletion_leaves_no_file_and_no_personal_value_in_any_table(client, rich, mail):
    ids, s = rich["ids"], rich["secrets"]
    assert set(rich["keys"]) <= stored_keys()
    r = delete_me(client, rich["h"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True and body["jobs_cancelled"] == 1 and body["credits_refunded"] == 5
    assert body["files_deleted"] == len(rich["keys"])
    left = sorted(k for k in stored_keys() if any(x in k for x in (ids["account"], ids["upload"], ids["imported"],
                                                                   ids["job"], ids["export_job"], ids["clip"])))
    assert left == []
    needles = {name: s[name] for name in ("email", "ip", "password_hash", "webhook_secret", "key_hash", "key_prefix",
                                          "filename", "source_url", "prompt", "job_name", "webhook", "title", "idem",
                                          "edit_text", "export_text")}
    found = []
    for table, col, row, text in every_value():
        for name, needle in needles.items():
            if needle not in text:
                continue
            if table == "case_events" and row["action"] == "account_deleted" and name == "email":
                continue                    # s. 41.26(1)(b): the identity kept inside the case record
            if table == "import_log" and col == "source_url" and name == "source_url":
                continue                    # the import record, kept until #150 decides its retention
            found.append((table, col, name))
    assert found == []
    with new_session() as db:
        a = db.get(Account, ids["account"])
        assert (a.status, a.email, a.password_hash, a.webhook_secret, a.signup_ip, a.is_admin) == (
            "deleted", f"deleted+{ids['account']}@deleted.invalid", "", "", None, False)
        assert a.deleted_at is not None and a.deleted_email_hash == account_data.email_hash(s["email"])
        assert db.get(ApiKey, ids["key"]) is None and db.get(CustomTemplate, ids["template"]) is None
        assert db.get(ClipThumbnail, ids["thumb"]) is None
        assert db.execute(select(WebhookDelivery).where(WebhookDelivery.job_id == ids["job"])).first() is None
        clip, up, job = db.get(Clip, ids["clip"]), db.get(Upload, ids["upload"]), db.get(Job, ids["imp"])
        assert clip.deleted_at and clip.meta is None and clip.features == {} and clip.video_key == ""
        assert up.deleted_at and up.filename == "deleted" and up.storage_key == "" and up.content_hash is None
        assert job.options == {"tool": "import"}
        # kept: proof of consent and the records #150 decides on
        assert db.execute(select(LikenessConsent).where(LikenessConsent.account_id == ids["account"])).first()
        assert db.execute(select(ClipFeedback).where(ClipFeedback.account_id == ids["account"])).first()
        assert db.execute(select(ImportLog).where(ImportLog.account_id == ids["account"])).first()
    assert [m[0] for m in mail] == [s["email"]]


def test_local_storage_lists_and_deletes_by_prefix(tmp_path):
    st = LocalStorage(tmp_path)
    for k in ("clips/job_a/1.mp4", "clips/job_a/sub/2.jpg", "clips/job_ab/3.mp4", "transcripts/upl_a.json",
              "transcripts/upl_a.parts.json", "transcripts/upl_b.json"):
        (tmp_path / k).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / k).write_text("x")
    assert st.keys("clips/job_a/") == ["clips/job_a/1.mp4", "clips/job_a/sub/2.jpg"]
    assert st.keys("transcripts/upl_a") == ["transcripts/upl_a.json", "transcripts/upl_a.parts.json"]
    assert st.keys("clips/none/") == []
    assert st.delete_prefix("clips/job_a/") == 2 and st.delete_prefix("transcripts/upl_a") == 2
    assert st.keys("clips/") == ["clips/job_ab/3.mp4"] and st.keys("transcripts/") == ["transcripts/upl_b.json"]
    assert st.delete_prefix("clips/job_a/") == 0
    for bad in ("", "clips/", "clips", "../x/", "/etc/"):
        with pytest.raises(ValueError):
            st.delete_prefix(bad)


def test_s3_storage_lists_and_deletes_by_prefix_across_pages(s3):  # noqa: F811
    st = get_storage()
    assert type(st).__name__ == "S3Storage"
    many = [f"clips/job_s3/{i:04d}.jpg" for i in range(1005)]          # more than one list page (1000)
    for k in [*many, "clips/job_s3x/keep.mp4", "transcripts/upl_s3.json", "transcripts/upl_s3.parts.json"]:
        st.client.put_object(Bucket=st.bucket, Key=k, Body=b"x")
    assert st.keys("clips/job_s3/") == sorted(many)
    assert st.keys("transcripts/upl_s3") == ["transcripts/upl_s3.json", "transcripts/upl_s3.parts.json"]
    assert st.delete_prefix("clips/job_s3/") == 1005 and st.delete_prefix("transcripts/upl_s3") == 2
    assert sorted(bucket_keys(s3)) == ["clips/job_s3x/keep.mp4"]
    with pytest.raises(ValueError):
        st.delete_prefix("clips/")


# ---- AC2: the ledger is untouched ----

def test_ac2_ledger_rows_are_unchanged_and_the_balance_still_runs(client, rich, mail):
    aid = rich["ids"]["account"]
    before = ledger_rows(aid)
    assert delete_me(client, rich["h"]).status_code == 200
    after = ledger_rows(aid)
    assert after[:len(before)] == before                       # every old row exactly as it was
    added = after[len(before):]
    assert [(r[1], r[2], r[3], r[5]) for r in added] == [(5, "release", rich["ids"]["queued"],
                                                          f"settle:{rich['ids']['queued']}")]
    with new_session() as db:
        assert ledger.balance(db, aid) == sum(r[1] for r in after)
        assert db.execute(select(Payment).where(Payment.account_id == aid)).scalar_one().amount_cents == 500


# ---- AC3: a live subscription refuses, and changes nothing ----

def snapshot(aid: str):
    with new_session() as db:
        a = db.get(Account, aid)
        return ((a.email, a.status, a.password_hash, a.stripe_customer_id),
                sorted((j.id, j.status) for j in db.execute(select(Job).where(Job.account_id == aid)).scalars()),
                len(db.execute(select(ApiKey).where(ApiKey.account_id == aid)).all()),
                ledger_rows(aid))


def test_ac3_an_active_subscription_gives_409_and_changes_nothing(client, rich, mail):
    aid = rich["ids"]["account"]
    with new_session() as db:
        a = db.get(Account, aid)
        a.stripe_customer_id, a.stripe_subscription_id, a.subscription_status = "cus_x", "sub_x", "active"
        db.commit()
    before, files = snapshot(aid), stored_keys()
    r = delete_me(client, rich["h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "subscription_active"
    assert snapshot(aid) == before and stored_keys() >= set(rich["keys"]) and mail == []
    with new_session() as db:                         # cancelled in the billing portal: now it goes
        db.get(Account, aid).subscription_status = "canceled"
        db.commit()
    assert delete_me(client, rich["h"]).status_code == 200
    with new_session() as db:
        a = db.get(Account, aid)
        assert (a.stripe_customer_id, a.stripe_subscription_id, a.subscription_status, a.plan) == (None, None, None, "free")
    assert files                                       # (the snapshot was taken)


# ---- AC4: no way back in ----

def test_ac4_login_session_and_api_key_are_401_after_deletion(client, rich, mail):
    email = rich["secrets"]["email"]
    assert client.get("/v1/me", headers=rich["key_h"]).status_code == 200
    assert delete_me(client, rich["h"]).status_code == 200
    r = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = client.post("/v1/auth/login", json={"email": f"deleted+{rich['ids']['account']}@deleted.invalid",
                                            "password": PASSWORD})
    assert r.status_code == 422 and "token" not in r.text     # .invalid is not an address anyone can log in with
    for h in (rich["h"], rich["key_h"]):
        r = client.get("/v1/me", headers=h)
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized", r.text
    assert client.get("/v1/me", headers=rich["h"]).json()["error"]["message"] == "Invalid or expired session."


def test_old_verify_and_reset_links_do_nothing_after_deletion(client, rich, mail):
    from app.routes_auth import _pw_version
    from app.security import make_token
    aid = rich["ids"]["account"]
    with new_session() as db:
        reset = make_token(aid, "reset", timedelta(hours=1), v=_pw_version(db.get(Account, aid)))
    verify = make_token(aid, "verify", timedelta(hours=1))
    assert delete_me(client, rich["h"]).status_code == 200
    before = ledger_rows(aid)
    assert client.get(f"/v1/auth/verify?token={verify}").status_code == 400
    with new_session() as db:
        reset = make_token(aid, "reset", timedelta(hours=1), v=_pw_version(db.get(Account, aid)))
    assert client.post("/v1/auth/reset", json={"token": reset, "password": "new-password-1"}).status_code == 400
    with new_session() as db:
        assert db.get(Account, aid).password_hash == "" and db.get(Account, aid).email_verified is False
    assert ledger_rows(aid) == before


# ---- AC5: the export ----

def test_ac5_export_has_everything_of_the_caller_and_nothing_of_anyone_else(client, rich, mail):
    other = make_rich(client)
    r = client.get("/v1/me/export", headers=rich["h"])
    assert r.status_code == 200, r.text
    data, text = r.json(), r.text
    ids, s = rich["ids"], rich["secrets"]
    assert data["profile"]["id"] == ids["account"] and data["profile"]["email"] == s["email"]
    assert data["profile"]["signup_ip"] == s["ip"]
    for secret in (s["password_hash"], s["webhook_secret"], s["key_hash"]):
        assert secret not in text
    assert {c["policy"] for c in data["policy_acceptances"]} >= {"terms", "privacy"}
    assert {u["id"] for u in data["uploads"]} == {ids["upload"], ids["imported"]}
    assert {j["id"] for j in data["jobs"]} == {ids["job"], ids["imp"], ids["export_job"], ids["queued"]}
    assert [c["id"] for c in data["clips"]] == [ids["clip"]] and data["clips"][0]["meta"]["title"] == s["title"]
    assert data["clips"][0]["kept"] is True and data["clips"][0]["reaction"] == "like"
    assert [t["id"] for t in data["templates"]] == [ids["template"]]
    assert [k["prefix"] for k in data["api_keys"]] == [s["key_prefix"]]
    assert {row["kind"] for row in data["credit_ledger"]} >= {"grant", "reserve", "commit", "topup"}
    assert data["payments"][0]["amount_cents"] == 500 and "stripe_ref" not in data["payments"][0]
    assert [i["source_url"] for i in data["import_log"]] == [s["source_url"]]
    assert [t["id"] for t in data["premium_thumbnails"]] == [ids["thumb"]]
    assert [c["clip_id"] for c in data["likeness_consents"]] == [ids["clip"]]
    their = [*other["ids"].values(), other["secrets"]["email"], other["secrets"]["source_url"]]
    assert [x for x in their if x in text] == []
    assert client.get("/v1/me/export", headers=rich["key_h"]).status_code == 403   # website login only
    _cleanup(other)


def _cleanup(world: dict) -> None:
    """Leave no QUEUED job for other tests' workers to pick up."""
    with new_session() as db:
        for job in db.execute(select(Job).where(Job.account_id == world["ids"]["account"],
                                                Job.status.in_(("QUEUED", "RUNNING")))).scalars():
            job.status = "FAILED"
            ledger.settle(db, job, success=False)
        db.commit()


def test_export_lists_cases_about_my_content_without_the_claimants_contact(client, rich, mail):
    ref = _report(client, rich["ids"]["clip"])
    data = client.get("/v1/me/export", headers=rich["h"]).json()
    assert [c["reference"] for c in data["cases"]] == [ref]
    assert "claim-contact@studio-example.com" not in json.dumps(data) and "1 Main St" not in json.dumps(data)
    _cleanup(rich)


# ---- refusals and repeats ----

def _report(client, target: str) -> str:
    r = client.post("/v1/trust/reports", json={
        "kind": "copyright", "name": "Rights Holder", "email": "claim-contact@studio-example.com",
        "address": "1 Main St, Edmonton AB", "relationship": "owner", "work": "My original stream recording",
        "reported_urls": [target], "good_faith": True, "accurate": True, "signature": "Rights Holder"})
    assert r.status_code == 201, r.text
    return r.json()["reference"]


def _set_case(ref: str, status: str, created_days_ago: int = 0) -> None:
    with new_session() as db:
        case = db.execute(select(TrustCase).where(TrustCase.reference == ref)).scalar_one()
        case.status, case.created_at = status, utcnow() - timedelta(days=created_days_ago)
        db.commit()


@pytest.mark.parametrize("status", ["received", "in_review", "info_requested", "disabled", "removed",
                                    "counter_noticed"])
def test_an_open_case_about_my_content_refuses(client, rich, mail, status):
    ref = _report(client, rich["ids"]["clip"])
    _set_case(ref, status)
    before = snapshot(rich["ids"]["account"])
    r = delete_me(client, rich["h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "case_open"
    assert "support@clutchclips.io" in r.json()["error"]["message"]
    assert snapshot(rich["ids"]["account"]) == before
    _cleanup(rich)


def test_a_closed_case_keeps_the_identity_inside_the_case_for_a_year(client, rich, mail):
    recent, old = _report(client, rich["ids"]["clip"]), _report(client, rich["ids"]["upload"])
    _set_case(recent, "closed", 30)
    _set_case(old, "closed", 400)
    assert delete_me(client, rich["h"]).status_code == 200
    with new_session() as db:
        def events(ref):
            case = db.execute(select(TrustCase).where(TrustCase.reference == ref)).scalar_one()
            return [(e.actor_kind, e.data) for e in db.execute(select(CaseEvent).where(
                CaseEvent.case_id == case.id, CaseEvent.action == "account_deleted")).scalars()]
        assert events(recent) == [("system", {"account_id": rich["ids"]["account"],
                                              "email": rich["secrets"]["email"]})]
        assert events(old) == []
        assert db.execute(select(CaseTarget).where(CaseTarget.account_id == rich["ids"]["account"])).first()


def test_a_running_job_refuses_and_changes_nothing(client, rich, mail):
    with new_session() as db:
        db.get(Job, rich["ids"]["job"]).status = "RUNNING"
        db.commit()
    before = snapshot(rich["ids"]["account"])
    r = delete_me(client, rich["h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_running"
    assert snapshot(rich["ids"]["account"]) == before
    with new_session() as db:
        db.get(Job, rich["ids"]["job"]).status = "SUCCEEDED"
        db.commit()
    _cleanup(rich)


def test_queued_jobs_are_cancelled_and_refunded_once(client, rich, mail):
    h = rich["h"]
    before = client.get("/v1/credits", headers=h).json()["balance"]
    assert delete_me(client, h).json()["credits_refunded"] == 5
    with new_session() as db:
        job = db.get(Job, rich["ids"]["queued"])
        assert (job.status, job.error_code, job.credits_charged) == ("CANCELED", "account_deleted", 0)
        assert ledger.balance(db, rich["ids"]["account"]) == before + 5


def test_deleting_twice_changes_nothing_more(client, rich, mail):
    aid = rich["ids"]["account"]
    ref = _report(client, rich["ids"]["clip"])
    _set_case(ref, "closed")
    assert delete_me(client, rich["h"]).status_code == 200
    put(f"clips/{rich['ids']['job']}/left-by-a-crash.mp4")         # an interrupted run's leftover
    first = (ledger_rows(aid), [v for v in every_value() if v[0] == "accounts" and v[2]["id"] == aid])
    with new_session() as db:
        report = account_data.delete(db, db.get(Account, aid), actor="admin:test")
        db.commit()
    assert report.already_deleted and report.files_deleted == 1 and report.credits_refunded == 0
    assert report.case_records == 0
    second = (ledger_rows(aid), [v for v in every_value() if v[0] == "accounts" and v[2]["id"] == aid])
    assert second == first
    with new_session() as db:
        case = db.execute(select(TrustCase).where(TrustCase.reference == ref)).scalar_one()
        assert len(db.execute(select(CaseEvent).where(CaseEvent.case_id == case.id,
                                                      CaseEvent.action == "account_deleted")).all()) == 1
        assert db.get(Account, aid).deleted_email_hash == account_data.email_hash(rich["secrets"]["email"])


def test_signing_up_again_makes_a_new_account_without_a_second_free_grant(client, rich, mail):
    email = rich["secrets"]["email"]
    assert delete_me(client, rich["h"]).status_code == 200
    h, acct = signup(client, email.upper())
    assert acct["id"] != rich["ids"]["account"] and acct["email"] == email and acct["credits"] == 0
    assert client.get("/v1/me/export", headers=h).json()["uploads"] == []
    _, fresh = signup(client)
    assert fresh["credits"] == get_settings().free_signup_credits         # everyone else still gets it


def test_wrong_password_and_missing_confirmation_are_refused(client, rich, mail):
    r = delete_me(client, rich["h"], password="not-my-password")
    assert r.status_code == 403 and r.json()["error"]["code"] == "wrong_password"
    assert delete_me(client, rich["h"], confirm="delete").status_code == 422
    assert client.post("/v1/me/delete", json={"password": PASSWORD, "confirm": "DELETE"},
                       headers=rich["key_h"]).status_code == 403            # website login only
    assert client.get("/v1/me", headers=rich["h"]).status_code == 200 and mail == []
    _cleanup(rich)


def test_delete_is_limited_to_five_tries_an_hour(client, rich, mail):
    for _ in range(5):
        assert delete_me(client, rich["h"], password="wrong-guess-123").status_code == 403
    r = delete_me(client, rich["h"])
    assert r.status_code == 429
    _cleanup(rich)


# ---- admin routes and the CLI (requests that arrive by email) ----

@pytest.fixture
def admin(client):
    h, acct = signup(client)
    with new_session() as db:
        db.get(Account, acct["id"]).is_admin = True
        db.commit()
    return h, acct


def test_admin_export_and_delete(client, rich, mail, admin, caplog):
    ah, acct = admin
    aid = rich["ids"]["account"]
    r = client.get(f"/v1/admin/accounts/{aid}/export", headers=ah)
    assert r.status_code == 200 and r.json()["profile"]["email"] == rich["secrets"]["email"]
    assert client.get("/v1/admin/accounts/acct_nobody/export", headers=ah).status_code == 404
    assert client.post(f"/v1/admin/accounts/{aid}/delete", json={}, headers=ah).status_code == 422
    with caplog.at_level("INFO", logger="clipapi.account"):
        r = client.post(f"/v1/admin/accounts/{aid}/delete", json={"note": "email request 2026-11-18"}, headers=ah)
    assert r.status_code == 200 and r.json()["deleted"] is True, r.text
    assert acct["id"] in caplog.text and aid in caplog.text
    assert [m[0] for m in mail] == [rich["secrets"]["email"]]
    assert client.get("/v1/me", headers=rich["h"]).status_code == 401
    again = client.post(f"/v1/admin/accounts/{aid}/delete", json={"note": "again"}, headers=ah)
    assert again.status_code == 200 and len(mail) == 1                    # no second email


def test_admin_delete_is_refused_like_the_user_one(client, rich, mail, admin):
    with new_session() as db:
        db.get(Job, rich["ids"]["job"]).status = "RUNNING"
        db.commit()
    r = client.post(f"/v1/admin/accounts/{rich['ids']['account']}/delete", json={"note": "x"}, headers=admin[0])
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_running"
    with new_session() as db:
        db.get(Job, rich["ids"]["job"]).status = "SUCCEEDED"
        db.commit()
    _cleanup(rich)


ADMIN_PY = Path(__file__).resolve().parent.parent / "scripts" / "admin.py"


def _admin_py(*args) -> subprocess.CompletedProcess:
    import os
    return subprocess.run([sys.executable, str(ADMIN_PY), *args], capture_output=True, text=True, timeout=120,
                          env={**os.environ})


def test_cli_dry_run_changes_nothing_then_deletes(client, rich, mail):
    aid, email = rich["ids"]["account"], rich["secrets"]["email"]
    before, files = snapshot(aid), stored_keys()
    out = _admin_py("delete-account", email, "--dry-run")
    assert out.returncode == 0, out.stderr
    assert "dry run" in out.stdout and f"{len(rich['keys'])} file(s)" in out.stdout
    assert snapshot(aid) == before and stored_keys() >= files
    exported = _admin_py("export-account", email)
    assert exported.returncode == 0 and json.loads(exported.stdout)["profile"]["id"] == aid
    out = _admin_py("delete-account", email)
    assert out.returncode == 0, out.stderr
    with new_session() as db:
        assert db.get(Account, aid).status == "deleted"
    assert not set(rich["keys"]) & stored_keys()
    assert _admin_py("delete-account", aid).returncode == 0                # by id, again: nothing more
