"""Shared setup for the Creators League tests: accounts, an admin, clips stored directly, and a competition."""
import uuid
from datetime import timedelta

from app.db import new_session
from app.league_rules import VERSION
from app.models import Account, Clip, Job, Upload, new_id, utcnow


def signup(client):
    r = client.post("/v1/auth/signup", json={"email": f"lg{uuid.uuid4().hex[:10]}@example.org",
                                              "password": "correct-horse-9"})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]


def make_admin(client):
    h, acct = signup(client)
    with new_session() as db:
        db.get(Account, acct["id"]).is_admin = True
        db.commit()
    return h, acct


def make_clip(account_id: str, options: dict | None = None, deleted: bool = False) -> str:
    """A finished clip of the account's, written straight to the database (no render needed for these tests)."""
    now = utcnow()
    with new_session() as db:
        up = Upload(id=new_id("upl"), account_id=account_id, filename="vod.mp4", storage_key="k/vod.mp4",
                    size_bytes=1, duration_sec=60.0, width=1920, height=1080, has_audio=True,
                    expires_at=now + timedelta(days=3))
        job = Job(id=new_id("job"), account_id=account_id, upload_id=up.id, status="SUCCEEDED",
                  options=options or {"template": None, "caption_style": "impact"}, duration_sec=60.0,
                  credits_reserved=1, credits_charged=1, expires_at=now + timedelta(days=3))
        clip = Clip(id=new_id("clip"), job_id=job.id, idx=0, start_sec=5.0, end_sec=27.5, score=0.5, signals={},
                    features={}, video_key="k/clip.mp4", thumb_key="k/clip.jpg", meta={"title": "A clutch"},
                    deleted_at=now if deleted else None)
        for row in (up, job, clip):        # the models carry no relationships, so the flush order is ours to set
            db.add(row)
            db.flush()
        db.commit()
        return clip.id


def unique_slug() -> str:
    return f"cup-{uuid.uuid4().hex[:10]}"


def competition(client, admin_h, starts_in_h: float = -1, ends_in_h: float = 24, opened: bool = True, prizes=None):
    now = utcnow()
    body = {"name": "November Cup", "slug": unique_slug(),
            "starts_at": (now + timedelta(hours=starts_in_h)).isoformat() + "Z",
            "ends_at": (now + timedelta(hours=ends_in_h)).isoformat() + "Z", "prizes": prizes or []}
    r = client.post("/v1/admin/league/competitions", json=body, headers=admin_h)
    assert r.status_code == 201, r.text
    if opened:
        r = client.post(f"/v1/admin/league/competitions/{body['slug']}/status", json={"action": "open"}, headers=admin_h)
        assert r.status_code == 200, r.text
    return body["slug"]


def creator(client, username: str | None = None, public: bool = True):
    """A signed-up creator with a profile and one clip."""
    h, acct = signup(client)
    name = username or f"u{uuid.uuid4().hex[:10]}"
    r = client.put("/v1/league/me/profile", json={"username": name, "avatar": "sky", "games": ["GTA 5"],
                                                  "is_public": public}, headers=h)
    assert r.status_code == 200, r.text
    return {"h": h, "account": acct, "username": name, "clip": make_clip(acct["id"])}


def short_url() -> str:
    return f"https://www.youtube.com/shorts/{uuid.uuid4().hex[:11]}"


def entry_body(clip_id: str, **over) -> dict:
    return {"clip_id": clip_id, "platform": "youtube", "url": short_url(), "attribution_confirmed": True,
            "rules_version": VERSION, **over}


def enter(client, slug: str, who: dict, **over):
    return client.post(f"/v1/league/{slug}/entries", json=entry_body(who["clip"], **over), headers=who["h"])


def approved_entry(client, admin_h, slug: str, who: dict, views: int | None = None, **over) -> str:
    r = enter(client, slug, who, **over)
    assert r.status_code == 201, r.text
    entry_id = r.json()["id"]
    assert client.post(f"/v1/admin/league/entries/{entry_id}/review", json={"action": "approve"},
                       headers=admin_h).status_code == 200
    if views is not None:
        r = client.post(f"/v1/admin/league/entries/{entry_id}/observations", json={"views": views}, headers=admin_h)
        assert r.status_code == 201, r.text
    return entry_id
