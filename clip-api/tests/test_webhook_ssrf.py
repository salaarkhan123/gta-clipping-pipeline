"""SEC-001: customer webhooks pin DNS like ingest — a rebinding answer must not change the connect address."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import pinned_http, worker
from app.db import new_session
from app.models import Account, Job, Upload, WebhookDelivery, new_id, utcnow
from app.pinned_http import is_public_https_url
from tests.ingest_support import PUBLIC_IP, web  # noqa: F401


@pytest.fixture
def pin_web(web, monkeypatch):
    """Route pinned_http seams through the same local HTTPS + fake DNS fixture as ingest."""
    monkeypatch.setattr(pinned_http, "_resolve", web.resolve)
    monkeypatch.setattr(pinned_http, "_connect", web.connect)
    monkeypatch.setattr(pinned_http, "_tls", web.tls)
    web.posts = []

    def do_post(self):
        path = self.path.split("?")[0]
        web.hits.append((self.headers.get("Host", ""), self.path, dict(self.headers.items())))
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else b""
        web.posts.append((path, body, dict(self.headers.items())))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"ok")

    web.server.RequestHandlerClass.do_POST = do_post
    return web


def test_is_public_https_url_refuses_private(pin_web):
    assert is_public_https_url("https://cdn.test/hook") is True
    assert is_public_https_url("https://internal.test/hook") is False
    assert is_public_https_url("http://cdn.test/hook") is False


def test_pinned_post_connects_to_checked_address_even_if_dns_changes(pin_web):
    """DNS rebinding: public at check time, private afterwards — connect still uses the checked public IP."""
    pin_web.dns_script["cdn.test"] = [[PUBLIC_IP], ["10.0.0.5"], ["10.0.0.5"]]
    code = pinned_http.pinned_https_request(
        "POST", "https://cdn.test/hook", body=b'{"ok":1}', headers={"content-type": "application/json"}, timeout=5,
    )
    assert code == 200
    assert pin_web.resolved == ["cdn.test"]
    assert pin_web.connected == [PUBLIC_IP]
    assert pin_web.posts[-1][0] == "/hook"


def test_send_webhook_uses_pin_not_rebinding(client, user, pin_web, monkeypatch):
    _headers, acct = user
    # After the single pinned resolve, further answers would be private — pin must not look again.
    pin_web.dns_script["cdn.test"] = [[PUBLIC_IP], ["10.0.0.5"], ["10.0.0.5"]]
    with new_session() as db:
        account = db.get(Account, acct["id"])
        up = Upload(
            id=new_id("up"), account_id=account.id, filename="x.mp4", storage_key="uploads/x.mp4",
            size_bytes=1, duration_sec=10.0, width=640, height=360, has_audio=True,
            expires_at=utcnow() + timedelta(days=1),
        )
        db.add(up)
        job = Job(
            id=new_id("job"), account_id=account.id, upload_id=up.id, status="SUCCEEDED",
            options={}, duration_sec=10.0, credits_reserved=0, credits_charged=0,
            stage="done", progress=100, webhook_url="https://cdn.test/hook",
            expires_at=utcnow() + timedelta(days=1),
        )
        db.add(job)
        db.commit()
        job_id = job.id

    monkeypatch.setattr(worker.time, "sleep", lambda *_: None)
    worker.send_webhook(job_id)
    assert pin_web.connected == [PUBLIC_IP]
    assert pin_web.posts and pin_web.posts[0][0] == "/hook"
    payload = json.loads(pin_web.posts[0][1])
    assert payload["job_id"] == job_id and payload["status"] == "SUCCEEDED"
    with new_session() as db:
        rows = list(db.execute(select(WebhookDelivery).where(WebhookDelivery.job_id == job_id)).scalars())
        assert rows and rows[0].status_code == 200
