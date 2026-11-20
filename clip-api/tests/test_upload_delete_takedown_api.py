"""Public upload soft-delete and account-scoped import takedown (Wave A3).

DELETE /v1/uploads/{id} marks Upload.deleted_at and hides the row from lists.
POST /v1/imports/takedown reuses app.ingest.takedown for this account only, with consent.
"""
import uuid

from sqlalchemy import select

from app import worker
from app.db import new_session
from app.models import CreditLedger, Upload
from tests.ingest_support import web  # noqa: F401
from tests.test_api import balance, upload as hand_upload


def new_user(client):
    r = client.post("/v1/auth/signup", json={"email": f"u{uuid.uuid4().hex[:10]}@example.org",
                                            "password": "correct-horse-9"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]


def imported(client, headers, url) -> str:
    imp = client.post("/v1/imports", json={"url": url, "consent": True}, headers=headers).json()
    worker.run_once()
    done = client.get(f"/v1/imports/{imp['import_id']}", headers=headers).json()
    assert done["status"] == "SUCCEEDED", done
    return done["upload_id"]


def ledger_for(job_id) -> list[tuple]:
    with new_session() as db:
        return [(r.kind, r.delta, r.idempotency_key) for r in db.execute(
            select(CreditLedger).where(CreditLedger.job_id == job_id).order_by(CreditLedger.id)).scalars()]


def test_delete_upload_soft_marks_and_hides_from_lists(client, user, video):
    headers, _ = user
    up = hand_upload(client, headers, video)
    uid = up["upload_id"]
    assert any(p["upload_id"] == uid for p in client.get("/v1/projects", headers=headers).json()["projects"])
    assert any(u["upload_id"] == uid for u in client.get("/v1/uploads", headers=headers).json()["uploads"])

    got = client.delete(f"/v1/uploads/{uid}", headers=headers)
    assert got.status_code == 200 and got.json() == {"deleted": True, "upload_id": uid}

    assert client.get("/v1/uploads", headers=headers).json()["uploads"] == []
    assert client.get("/v1/projects", headers=headers).json()["projects"] == []
    assert client.get(f"/v1/projects/{uid}", headers=headers).status_code == 404
    assert client.delete(f"/v1/uploads/{uid}", headers=headers).status_code == 404
    with new_session() as db:
        assert db.get(Upload, uid).deleted_at is not None


def test_delete_upload_is_account_scoped(client, video):
    a, _ = new_user(client)
    b, _ = new_user(client)
    uid = hand_upload(client, a, video)["upload_id"]
    assert client.delete(f"/v1/uploads/{uid}", headers=b).status_code == 404
    assert any(u["upload_id"] == uid for u in client.get("/v1/uploads", headers=a).json()["uploads"])


def test_self_takedown_by_url_refunds_queued_job_once(client, user, web, transcriber):
    headers, account = user
    url = f"https://cdn.test/video.mp4?v={uuid.uuid4().hex}"
    upload_id = imported(client, headers, url)
    job_id = client.post("/v1/clips", json={"upload_id": upload_id, "options": {"max_clips": 1, "clip_length": 10}},
                         headers=headers).json()["job_id"]
    held = balance(client, headers)
    assert held < 30

    bad = client.post("/v1/imports/takedown", json={"url": url}, headers=headers)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "consent_required"

    report = client.post("/v1/imports/takedown", json={"url": url, "consent": True}, headers=headers)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["uploads_removed"] == 1 and body["import_log_rows"] >= 1
    assert any(j["job_id"] == job_id for j in body["jobs_cancelled"])
    assert balance(client, headers) == 30
    assert ledger_for(job_id) == [("reserve", -(30 - held), f"reserve:{job_id}"),
                                  ("release", 30 - held, f"settle:{job_id}")]

    again = client.post("/v1/imports/takedown", json={"url": url, "consent": True}, headers=headers).json()
    assert again["uploads_removed"] == 0 and again["jobs_cancelled"] == []
    assert ledger_for(job_id) == [("reserve", -(30 - held), f"reserve:{job_id}"),
                                  ("release", 30 - held, f"settle:{job_id}")]
    assert client.get("/v1/uploads", headers=headers).json()["uploads"] == []
    assert client.get("/v1/projects", headers=headers).json()["projects"] == []
    assert account["id"] in body["target"]


def test_self_takedown_by_url_leaves_other_accounts_alone(client, web):
    url = f"https://cdn.test/video.mp4?v={uuid.uuid4().hex}"
    a, _ = new_user(client)
    b, _ = new_user(client)
    a_up, b_up = imported(client, a, url), imported(client, b, url)

    report = client.post("/v1/imports/takedown", json={"url": url, "consent": True}, headers=a).json()
    assert report["uploads_removed"] == 1
    assert [r["upload_id"] for r in report["removed"]] == [a_up]
    assert client.get("/v1/uploads", headers=a).json()["uploads"] == []
    assert [u["upload_id"] for u in client.get("/v1/uploads", headers=b).json()["uploads"]] == [b_up]


def test_self_takedown_all_imports_keeps_hand_uploads(client, user, web, video):
    headers, _ = user
    by_hand = hand_upload(client, headers, video)["upload_id"]
    link = f"https://cdn.test/video.mp4?v={uuid.uuid4().hex}"
    imported_id = imported(client, headers, link)

    both = client.post("/v1/imports/takedown",
                       json={"url": link, "all_imports": True, "consent": True}, headers=headers)
    assert both.status_code == 422 and both.json()["error"]["code"] == "takedown_target"

    report = client.post("/v1/imports/takedown", json={"all_imports": True, "consent": True},
                         headers=headers).json()
    assert report["uploads_removed"] == 1
    assert [u["upload_id"] for u in client.get("/v1/uploads", headers=headers).json()["uploads"]] == [by_hand]
    assert imported_id not in {u["upload_id"] for u in client.get("/v1/uploads", headers=headers).json()["uploads"]}


def test_delete_upload_does_not_touch_ledger(client, user, video):
    headers, _ = user
    up = hand_upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()["job_id"]
    before = ledger_for(job_id)
    assert client.delete(f"/v1/uploads/{up['upload_id']}", headers=headers).json()["deleted"] is True
    assert ledger_for(job_id) == before
    assert client.post(f"/v1/jobs/{job_id}/cancel", headers=headers).json()["status"] == "CANCELED"
    assert balance(client, headers) == 30
    assert ledger_for(job_id) == [before[0], ("release", -before[0][1], f"settle:{job_id}")]
