"""End-to-end API tests: signup, upload, job, credits, refunds, idempotency, billing webhook."""
import hashlib
import hmac
import json
import time

from app import worker
from app.db import new_session
from app.models import Job, utcnow
from app.pipeline import PipelineError


def upload(client, headers, video):
    r = client.post("/v1/uploads?filename=sample.mp4", content=video.read_bytes(), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def balance(client, headers) -> int:
    return client.get("/v1/credits", headers=headers).json()["balance"]


def test_signup_gives_free_credits_once(client, user):
    headers, account = user
    assert account["email_verified"] is True and account["credits"] == 30
    assert balance(client, headers) == 30
    r = client.post("/v1/auth/signup", json={"email": account["email"], "password": "correct-horse-9"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_login_and_bad_password(client, user):
    _, account = user
    ok = client.post("/v1/auth/login", json={"email": account["email"], "password": "correct-horse-9"})
    assert ok.status_code == 200 and ok.json()["token"]
    bad = client.post("/v1/auth/login", json={"email": account["email"], "password": "wrong-password"})
    assert bad.status_code == 401


def test_requires_auth(client):
    assert client.get("/v1/credits").status_code == 401
    assert client.get("/v1/credits", headers={"Authorization": "Bearer gck_nope"}).status_code == 401


def test_api_key_works_and_is_restricted(client, user):
    headers, _ = user
    key = client.post("/v1/keys", json={"name": "ci"}, headers=headers).json()
    assert key["key"].startswith("gck_")
    kh = {"Authorization": f"Bearer {key['key']}"}
    assert client.get("/v1/credits", headers=kh).status_code == 200
    assert client.post("/v1/keys", json={"name": "x"}, headers=kh).status_code == 403   # keys can't mint keys
    assert client.delete(f"/v1/keys/{key['id']}", headers=headers).status_code == 200
    assert client.get("/v1/credits", headers=kh).status_code == 401                     # revoked


def test_full_job_success_charges_credits(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    assert up["credits_required"] == 1
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                    headers=headers)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert balance(client, headers) == 29                    # reserved at submit
    assert worker.run_once(transcriber) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "SUCCEEDED" and job["credits_charged"] == 1 and len(job["clips"]) == 1
    clip = job["clips"][0]
    assert 12 <= clip["start_sec"] <= 24                     # found the loud burst at 20-24 s
    assert "audio" in clip["signals"]
    video_bytes = client.get(clip["video_url"].replace("http://localhost:8000", "")).content
    assert len(video_bytes) > 10_000
    assert balance(client, headers) == 29
    fb = client.post(f"/v1/clips/{clip['id']}/feedback", json={"kept": True}, headers=headers)
    assert fb.json()["kept"] is True


def test_failed_job_refunds(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()["job_id"]
    assert balance(client, headers) == 29

    def boom(*a, **k):
        raise PipelineError("media_error", "broken file")
    assert worker.run_once(None, pipeline=boom) == "FAILED"
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "FAILED" and job["credits_charged"] == 0 and job["error"]["code"] == "media_error"
    assert balance(client, headers) == 30


def test_crash_refunds_and_hides_internals(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()["job_id"]

    def crash(*a, **k):
        raise RuntimeError("secret internal detail")
    assert worker.run_once(None, pipeline=crash) == "FAILED"
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert "secret" not in json.dumps(job) and balance(client, headers) == 30


def test_cancel_queued_refunds_once(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()["job_id"]
    assert client.post(f"/v1/jobs/{job_id}/cancel", headers=headers).json()["status"] == "CANCELED"
    assert client.post(f"/v1/jobs/{job_id}/cancel", headers=headers).json()["status"] == "CANCELED"
    assert balance(client, headers) == 30                    # refunded exactly once
    assert worker.run_once(None) is None                     # nothing left to run


def test_stale_running_job_is_refunded_and_cannot_succeed_later(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                         headers=headers).json()["job_id"]
    assert worker.claim_job() == job_id
    with new_session() as db:                                # pretend the worker died 1 hour ago
        job = db.get(Job, job_id)
        job.heartbeat_at = utcnow().replace(year=utcnow().year - 1)
        db.commit()
    assert worker.sweep_stale_jobs() == 1
    assert balance(client, headers) == 30
    # The "dead" worker comes back and finishes: it must not flip the job to SUCCEEDED or charge.
    assert worker.process_job(job_id, transcriber) == "FAILED"
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "FAILED" and job["clips"] == [] and balance(client, headers) == 30


def test_idempotency_key_never_double_charges(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    h = {**headers, "Idempotency-Key": "same-key-123"}
    a = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=h).json()
    b = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=h).json()
    assert a["job_id"] == b["job_id"] and balance(client, headers) == 29
    client.post(f"/v1/jobs/{a['job_id']}/cancel", headers=headers)


def test_insufficient_credits_402_and_no_job(client, user, video):
    headers, account = user
    from app import ledger
    with new_session() as db:
        ledger.grant(db, account["id"], -30, "adjust", f"test-drain:{account['id']}")
        db.commit()
    up = upload(client, headers, video)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers)
    assert r.status_code == 402 and r.json()["error"]["code"] == "insufficient_credits"
    assert client.get("/v1/jobs", headers=headers).json()["jobs"] == [] and balance(client, headers) == 0


def test_concurrency_limit(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    ids = [client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()["job_id"] for _ in range(2)]
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers)
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_jobs"
    for j in ids:
        client.post(f"/v1/jobs/{j}/cancel", headers=headers)
    assert balance(client, headers) == 30


def test_upload_validation(client, user):
    headers, _ = user
    assert client.post("/v1/uploads?filename=x.exe", content=b"abc", headers=headers).status_code == 415
    r = client.post("/v1/uploads?filename=x.mp4", content=b"not a video at all", headers=headers)
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_media"
    assert client.post("/v1/uploads?filename=x.mp4", content=b"", headers=headers).status_code == 422


def test_cannot_use_someone_elses_upload_or_job(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    other = client.post("/v1/auth/signup", json={"email": f"o{time.time_ns()}@example.org", "password": "correct-horse-9"}).json()
    oh = {"Authorization": f"Bearer {other['token']}"}
    assert client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=oh).status_code == 404
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()["job_id"]
    assert client.get(f"/v1/jobs/{job_id}", headers=oh).status_code == 404
    client.post(f"/v1/jobs/{job_id}/cancel", headers=headers)


def test_webhook_url_must_be_public_https(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    for bad in ("http://example.com/hook", "https://127.0.0.1/hook", "https://localhost/hook", "https://10.0.0.5/x"):
        r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "webhook_url": bad}, headers=headers)
        assert r.status_code == 422, bad


def stripe_event(account_id: str, session_id: str, pack_id: str = "pack_300", paid: bool = True):
    payload = json.dumps({"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {
        "id": session_id, "payment_status": "paid" if paid else "unpaid",
        "metadata": {"account_id": account_id, "pack_id": pack_id, "credits": "999999"}}}})
    ts = int(time.time())
    sig = hmac.new(b"whsec_test", f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return payload, {"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}


def test_stripe_webhook_grants_once_from_server_side_pack(client, user):
    headers, account = user
    payload, sig = stripe_event(account["id"], f"cs_test_{account['id']}")
    assert client.post("/webhooks/stripe", content=payload, headers=sig).status_code == 200
    assert client.post("/webhooks/stripe", content=payload, headers=sig).status_code == 200   # redelivery
    assert balance(client, headers) == 330          # +300 once; the forged "credits" metadata is ignored


def test_stripe_webhook_rejects_bad_signature_and_unpaid(client, user):
    headers, account = user
    payload, sig = stripe_event(account["id"], f"cs_bad_{account['id']}")
    forged = {**sig, "stripe-signature": sig["stripe-signature"][:-4] + "0000"}
    assert client.post("/webhooks/stripe", content=payload, headers=forged).status_code == 400
    payload, sig = stripe_event(account["id"], f"cs_unpaid_{account['id']}", paid=False)
    assert client.post("/webhooks/stripe", content=payload, headers=sig).status_code == 200
    assert balance(client, headers) == 30


def test_parallel_submits_cannot_overspend(client, user, video):
    """Postgres only: 8 simultaneous submits with 1 credit left must produce exactly one job."""
    import pytest
    from concurrent.futures import ThreadPoolExecutor
    from app import ledger
    from app.config import get_settings
    if get_settings().database_url.startswith("sqlite"):
        pytest.skip("row locking needs Postgres")
    headers, account = user
    with new_session() as db:
        ledger.grant(db, account["id"], -29, "adjust", f"test-drain:{account['id']}")
        db.commit()
    up = upload(client, headers, video)

    def submit(_):
        return client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).status_code
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(submit, range(8)))
    assert codes.count(202) == 1 and set(codes) <= {202, 402}, codes
    assert balance(client, headers) == 0
    for j in client.get("/v1/jobs", headers=headers).json()["jobs"]:
        client.post(f"/v1/jobs/{j['job_id']}/cancel", headers=headers)
    assert balance(client, headers) == 1


def test_password_reset_is_single_use(client, user):
    from datetime import timedelta
    from app.models import Account
    from app.routes_auth import _pw_version
    from app.security import make_token
    _, account = user
    assert client.post("/v1/auth/forgot", json={"email": "nobody@example.org"}).json() == {"sent": True}
    with new_session() as db:
        a = db.get(Account, account["id"])
        token = make_token(a.id, "reset", timedelta(hours=1), v=_pw_version(a))
    assert client.post("/v1/auth/reset", json={"token": token, "password": "brand-new-pass-1"}).status_code == 200
    assert client.post("/v1/auth/reset", json={"token": token, "password": "another-pass-22"}).status_code == 400
    assert client.post("/v1/auth/login", json={"email": account["email"], "password": "brand-new-pass-1"}).status_code == 200
    assert client.post("/v1/auth/login", json={"email": account["email"], "password": "correct-horse-9"}).status_code == 401
