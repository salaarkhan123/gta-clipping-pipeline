"""0.3: uploading the same bytes again returns the first upload instead of storing and charging again."""
import uuid
from datetime import timedelta

from app import worker
from app.config import get_settings
from app.db import new_session
from app.models import Upload, utcnow
from tests.test_api import balance


def send(client, headers, data, name="sample.mp4"):
    return client.post(f"/v1/uploads?filename={name}", content=data, headers=headers)


def new_user(client):
    r = client.post("/v1/auth/signup", json={"email": f"u{uuid.uuid4().hex[:10]}@example.org", "password": "correct-horse-9"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def stored_files(account_id):
    return sorted(p.name for p in (get_settings().storage_dir / "uploads" / account_id).glob("*"))


def test_same_bytes_return_the_first_upload_and_store_nothing_new(client, user, video, transcriber):
    headers, account = user
    data = video.read_bytes()
    first = send(client, headers, data)
    assert first.status_code == 201 and first.json()["reused"] is False
    again = send(client, headers, data, name="renamed copy.mp4")           # the name does not matter, the bytes do
    assert again.status_code == 200 and again.json()["reused"] is True
    assert again.json()["upload_id"] == first.json()["upload_id"]
    assert len(stored_files(account["id"])) == 1                           # one file on disk, one row
    assert len(client.get("/v1/uploads", headers=headers).json()["uploads"]) == 1


def test_a_reused_upload_is_priced_as_already_analysed(client, user, video, transcriber):
    headers, _ = user
    data = video.read_bytes()
    up = send(client, headers, data).json()
    opts = {"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}}
    client.post("/v1/clips", json=opts, headers=headers)
    assert worker.run_once(transcriber) == "SUCCEEDED" and balance(client, headers) == 29   # full price, once
    again = send(client, headers, data).json()
    assert again["reused"] is True and again["analyzed"] is True           # so jobs on it only pay for what is rendered
    with new_session() as db:                                               # same row the pricing rule reads
        assert db.get(Upload, again["upload_id"]).analyzed is True


def test_another_account_or_other_bytes_get_a_normal_upload(client, user, video):
    headers, _ = user
    data = video.read_bytes()
    first = send(client, headers, data).json()
    other = send(client, new_user(client), data)                           # never shared across accounts
    assert other.status_code == 201 and other.json()["upload_id"] != first["upload_id"]
    changed = send(client, headers, data + b"\x00" * 16)                    # different bytes
    assert changed.status_code == 201 and changed.json()["upload_id"] != first["upload_id"]


def test_after_the_first_copy_expires_or_is_deleted_it_is_a_normal_upload(client, user, video):
    headers, _ = user
    data = video.read_bytes()
    first = send(client, headers, data).json()
    with new_session() as db:                                               # past the 7-day retention
        db.get(Upload, first["upload_id"]).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    second = send(client, headers, data)
    assert second.status_code == 201 and second.json()["upload_id"] != first["upload_id"]
    with new_session() as db:
        db.get(Upload, second.json()["upload_id"]).deleted_at = utcnow()
        db.commit()
    third = send(client, headers, data)
    assert third.status_code == 201 and third.json()["upload_id"] not in (first["upload_id"], second.json()["upload_id"])
