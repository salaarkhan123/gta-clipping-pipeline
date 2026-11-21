"""Publishing: flag off, token crypto, status machine, idempotent submit, at-most-once final call."""
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.db import new_session
from app.models import Clip, Job, ScheduledPost, SocialAccount, Upload, new_id, utcnow
from app.publish import state, tokens
from app.publish import service
from app.publish.adapters.youtube import YouTubeAdapter


FERNET = Fernet.generate_key().decode()


@pytest.fixture
def publishing(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "publishing", True)
    monkeypatch.setattr(s, "publish_token_key", FERNET)
    monkeypatch.setattr(s, "youtube_client_id", "yt-client")
    monkeypatch.setattr(s, "youtube_client_secret", "yt-secret")
    return s


def test_flag_off_routes_404(client, user):
    headers, _ = user
    assert get_settings().publishing is False
    for path, method in (
        ("/v1/publish/platforms", "get"),
        ("/v1/social-accounts", "get"),
        ("/v1/posts", "get"),
    ):
        r = getattr(client, method)(path, headers=headers)
        assert r.status_code == 404, path
        assert r.json()["error"]["code"] == "publishing_disabled"


def test_token_round_trip_and_rotation(publishing, monkeypatch):
    plain = "access-token-xyz"
    blob = tokens.encrypt(plain)
    assert blob and blob != plain
    assert tokens.decrypt(blob) == plain
    old = publishing.publish_token_key
    new = Fernet.generate_key().decode()
    monkeypatch.setattr(publishing, "publish_token_key", new)
    monkeypatch.setattr(publishing, "publish_token_key_old", old)
    assert tokens.decrypt(blob) == plain
    assert tokens.decrypt(tokens.encrypt("fresh")) == "fresh"


def test_status_machine_transitions():
    assert state.can_transition("SCHEDULED", "QUEUED")
    assert state.can_transition("QUEUED", "UPLOADING")
    assert state.can_transition("UPLOADING", "PUBLISHED")
    assert state.can_cancel("SCHEDULED") and state.can_edit("SCHEDULED")
    assert not state.can_edit("PUBLISHED")
    assert state.can_retry("FAILED", "platform_unavailable")
    assert not state.can_retry("FAILED", "outcome_unknown")
    with pytest.raises(ValueError):
        state.advance("PUBLISHED", "QUEUED")


def _seed_clip(account_id: str, *, export: bool = True) -> str:
    with new_session() as db:
        up = Upload(
            id=new_id("up"), account_id=account_id, filename="a.mp4",
            storage_key=f"uploads/{account_id}/a.mp4", size_bytes=1000,
            duration_sec=30, width=1080, height=1920, has_audio=True,
            analyzed=True, expires_at=utcnow() + timedelta(days=7),
        )
        job = Job(
            id=new_id("job"), account_id=account_id, upload_id=up.id,
            status="SUCCEEDED", options={"aspect": "9:16"}, duration_sec=30,
            credits_reserved=1, credits_charged=1,
            expires_at=utcnow() + timedelta(days=7),
        )
        clip = Clip(
            id=new_id("clp"), job_id=job.id, idx=1, start_sec=0, end_sec=28,
            score=80, signals={}, features={},
            video_key=f"clips/{job.id}/1.mp4",
            export_key=(f"exports/{job.id}/1.mp4" if export else None),
            meta={"title": "Clutch play", "description": "Wow", "hashtags": ["gta"]},
        )
        db.add_all([up, job, clip])
        db.commit()
        return clip.id


def _seed_social(account_id: str, platform: str = "youtube") -> str:
    with new_session() as db:
        row = SocialAccount(
            id=new_id("soc"), account_id=account_id, platform=platform,
            external_id="chan_1", display_name="Test Channel",
            access_token_enc=tokens.encrypt("access"),
            refresh_token_enc=tokens.encrypt("refresh"),
            access_expires_at=utcnow() + timedelta(hours=1),
            scopes=["youtube.upload"], status="active",
        )
        db.add(row)
        db.commit()
        return row.id


def test_platforms_list_and_idempotent_submit(client, user, publishing, tmp_path, monkeypatch):
    headers, acct = user
    r = client.get("/v1/publish/platforms", headers=headers)
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["platforms"]}
    assert "youtube" in ids and "x" not in ids
    yt = next(p for p in r.json()["platforms"] if p["id"] == "youtube")
    assert yt["configured"] is True
    assert yt["operational"] is False
    assert yt["readiness"] == "awaiting_approval"

    clip_id = _seed_clip(acct["id"])
    # Put a fake export file where LocalStorage expects it.
    from app.storage import get_storage
    storage = get_storage()
    with new_session() as db:
        clip = db.get(Clip, clip_id)
        key = clip.export_key
    path = storage.path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 64)

    soc_id = _seed_social(acct["id"])
    body = {
        "targets": [{
            "social_account_id": soc_id,
            "title": "Clutch play",
            "caption": "Wow",
            "hashtags": ["gta"],
            "privacy": "private",
            "options": {},
        }],
        "rights_confirmed": True,
    }
    r1 = client.post(f"/v1/clips/{clip_id}/publish", headers={**headers, "Idempotency-Key": "idem-1"}, json=body)
    assert r1.status_code == 202, r1.text
    post_id = r1.json()["posts"][0]["id"]
    assert r1.json()["posts"][0]["status"] == "QUEUED"

    r2 = client.post(f"/v1/clips/{clip_id}/publish", headers={**headers, "Idempotency-Key": "idem-1"}, json=body)
    assert r2.status_code == 202
    assert r2.json()["posts"][0]["id"] == post_id

    # Cancel while queued.
    c = client.post(f"/v1/posts/{post_id}/cancel", headers=headers, json={})
    assert c.status_code == 200 and c.json()["status"] == "CANCELED"


def test_schedule_cancel_and_missed_window(client, user, publishing):
    headers, acct = user
    clip_id = _seed_clip(acct["id"])
    from app.storage import get_storage
    with new_session() as db:
        key = db.get(Clip, clip_id).export_key
    p = get_storage().path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00" * 32)
    soc_id = _seed_social(acct["id"])
    when = (utcnow() + timedelta(hours=2)).isoformat() + "Z"
    r = client.post(
        f"/v1/clips/{clip_id}/publish",
        headers={**headers, "Idempotency-Key": "sched-1"},
        json={
            "targets": [{"social_account_id": soc_id, "title": "T", "caption": "C",
                         "hashtags": [], "privacy": "private", "options": {}}],
            "publish_at": when,
            "rights_confirmed": True,
        },
    )
    assert r.status_code == 202, r.text
    post = r.json()["posts"][0]
    assert post["status"] == "SCHEDULED"
    assert post["can_cancel"] and post["can_edit"]

    # Force missed schedule.
    with new_session() as db:
        row = db.get(ScheduledPost, post["id"])
        row.publish_at = utcnow() - timedelta(hours=2)
        db.commit()
    with new_session() as db:
        claimed = service.claim_due_post(db)
        assert claimed is None  # failed as missed, not claimed
    with new_session() as db:
        row = db.get(ScheduledPost, post["id"])
        assert row.status == "FAILED" and row.error_code == "missed_schedule"


def test_youtube_adapter_at_most_once_final_call(publishing, tmp_path):
    """Lost answer on the final PUT must not invent success; outcome_unknown, no blind repeat."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "uploadType=resumable" in str(request.url) and request.method == "POST":
            return httpx.Response(200, headers={"Location": "https://upload.example/session"})
        if request.method == "PUT":
            return httpx.Response(408, text="timeout")
        return httpx.Response(500, text="nope")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    adapter = YouTubeAdapter(client=client)
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"\x00" * 128)
    result = adapter.publish(
        access_token="t", media_path=str(media), media_url=None,
        title="Hi", caption="c", privacy="private", options={},
        step=None, external_ref=None,
    )
    assert result.ok is False
    assert result.error_code == "outcome_unknown"
    assert result.retryable is False


def test_connect_requires_session(client, user, publishing):
    headers, _ = user
    # API key path: create a key then try connect.
    k = client.post("/v1/keys", headers=headers, json={"name": "pub"})
    assert k.status_code == 201
    key = k.json()["key"]
    r = client.post("/v1/social-accounts/youtube/connect", headers={"Authorization": f"Bearer {key}"}, json={})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "session_required"


def test_export_required(client, user, publishing):
    headers, acct = user
    clip_id = _seed_clip(acct["id"], export=False)
    soc_id = _seed_social(acct["id"])
    r = client.post(
        f"/v1/clips/{clip_id}/publish",
        headers={**headers, "Idempotency-Key": "no-export"},
        json={
            "targets": [{"social_account_id": soc_id, "title": "T", "caption": "C",
                         "hashtags": [], "privacy": "private", "options": {}}],
            "rights_confirmed": True,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "export_required"


def test_calendar_list(client, user, publishing):
    headers, acct = user
    clip_id = _seed_clip(acct["id"])
    from app.storage import get_storage
    with new_session() as db:
        key = db.get(Clip, clip_id).export_key
    path = get_storage().path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 16)
    soc_id = _seed_social(acct["id"])
    client.post(
        f"/v1/clips/{clip_id}/publish",
        headers={**headers, "Idempotency-Key": "cal-1"},
        json={
            "targets": [{"social_account_id": soc_id, "title": "T", "caption": "C",
                         "hashtags": [], "privacy": "unlisted", "options": {}}],
            "rights_confirmed": True,
        },
    )
    listed = client.get("/v1/posts", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["posts"]) >= 1
