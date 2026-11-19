"""Direct, resumable uploads to the bucket (S3 multipart from the browser), against moto with R2 settings.
test_r2_live.py runs the same flow against a real bucket, where the signed part size is enforced."""
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app import config, routes_direct_upload, storage
from app.db import new_session
from app.models import Upload
from tests.r2_contract import MiB
from tests.test_api import upload
from tests.test_r2_storage import BUCKET, r2  # noqa: F401  (fixture)


@pytest.fixture
def padded(video, tmp_path, monkeypatch):
    """The sample video padded to 11 MiB with 5 MiB parts: three parts, the last one short."""
    monkeypatch.setattr(routes_direct_upload, "MIN_PART", 5 * MiB)
    path = tmp_path / "stream.mp4"
    path.write_bytes(video.read_bytes() + bytes(11 * MiB - video.stat().st_size))
    return path


def other_user(client):
    r = client.post("/v1/auth/signup", json={"email": f"u{uuid.uuid4().hex[:10]}@example.org",
                                             "password": "correct-horse-9"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def start(client, headers, path, name="stream.mp4", size=None):
    r = client.post("/v1/uploads/multipart", json={"filename": name, "size_bytes": size or path.stat().st_size},
                    headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def send(part: dict, data: bytes) -> None:
    n, size = part["part_number"], part["size"]
    r = httpx.put(part["url"], content=data[(n - 1) * 5 * MiB:(n - 1) * 5 * MiB + size])
    assert r.status_code == 200, r.text


def test_resumable_upload_is_recorded_only_after_a_verified_complete(client, user, padded, r2):  # noqa: F811
    headers, account = user
    data = padded.read_bytes()
    up = start(client, headers, padded)
    assert (up["part_size"], up["part_count"]) == (5 * MiB, 3)
    token = {"upload_token": up["upload_token"]}
    parts = client.post("/v1/uploads/multipart/parts", json=token, headers=headers).json()
    assert [(p["part_number"], p["size"]) for p in parts["parts"]] == [(1, 5 * MiB), (2, 5 * MiB), (3, MiB)]
    q = parse_qs(urlsplit(parts["parts"][0]["url"]).query)
    assert q["X-Amz-SignedHeaders"] == ["content-length;host"]          # the bucket refuses any other size
    assert not [k for k in q if "checksum" in k.lower()] and int(q["X-Amz-Expires"][0]) <= 604_800
    send(parts["parts"][0], data)
    send(parts["parts"][1], data)                                       # then the connection drops

    r = client.post("/v1/uploads/multipart/complete", json=token, headers=headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "upload_incomplete"
    with new_session() as db:
        assert db.get(Upload, up["upload_id"]) is None                  # nothing recorded yet
    again = client.post("/v1/uploads/multipart/parts", json=token, headers=headers).json()
    assert again["done"] == [1, 2] and [p["part_number"] for p in again["parts"]] == [3]   # resume: only part 3
    send(again["parts"][0], data)

    r = client.post("/v1/uploads/multipart/complete", json=token, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["upload_id"] == up["upload_id"] and body["duration_sec"] > 30 and body["reused"] is False
    key = f"uploads/{account['id']}/{up['upload_id']}.mp4"
    store = storage.get_storage()
    assert store.size(key) == len(data)
    assert store.client.head_object(Bucket=BUCKET, Key=key)["ContentType"] == "video/mp4"
    assert client.get("/v1/uploads", headers=headers).json()["uploads"][0]["upload_id"] == up["upload_id"]
    retry = client.post("/v1/uploads/multipart/complete", json=token, headers=headers)
    assert retry.status_code == 200 and retry.json()["upload_id"] == up["upload_id"]
    assert r2.violations == []


def test_the_same_file_again_hands_back_the_first_upload(client, user, video, r2):  # noqa: F811
    headers, _ = user
    first = upload(client, headers, video)                              # through the api
    up = start(client, headers, video, name="again.mp4")
    token = {"upload_token": up["upload_token"]}
    (part,) = client.post("/v1/uploads/multipart/parts", json=token, headers=headers).json()["parts"]
    assert httpx.put(part["url"], content=video.read_bytes()).status_code == 200
    r = client.post("/v1/uploads/multipart/complete", json=token, headers=headers)
    assert r.status_code == 200 and r.json()["reused"] is True and r.json()["upload_id"] == first["upload_id"]
    assert not storage.get_storage().exists(f"uploads/{user[1]['id']}/{up['upload_id']}.mp4")   # copy removed


def test_a_file_that_is_not_a_video_is_deleted_and_not_recorded(client, user, tmp_path, r2):  # noqa: F811
    headers, account = user
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video" * 1000)
    up = start(client, headers, junk)
    token = {"upload_token": up["upload_token"]}
    (part,) = client.post("/v1/uploads/multipart/parts", json=token, headers=headers).json()["parts"]
    httpx.put(part["url"], content=junk.read_bytes())
    r = client.post("/v1/uploads/multipart/complete", json=token, headers=headers)
    assert r.status_code == 415
    assert storage.get_storage().keys(f"uploads/{account['id']}/") == []
    with new_session() as db:
        assert db.get(Upload, up["upload_id"]) is None


def test_parts_of_the_wrong_size_are_refused_and_discarded(client, user, video, r2):  # noqa: F811
    headers, account = user
    up = start(client, headers, video, size=video.stat().st_size + 100)        # claims 100 bytes more
    token = {"upload_token": up["upload_token"]}
    store = storage.get_storage()
    key = f"uploads/{account['id']}/{up['upload_id']}.mp4"
    upload_id = routes_direct_upload.read_token(up["upload_token"], "direct_upload")["m"]
    store.client.upload_part(Bucket=BUCKET, Key=key, UploadId=upload_id, PartNumber=1, Body=video.read_bytes())
    r = client.post("/v1/uploads/multipart/complete", json=token, headers=headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "upload_size_mismatch"
    r = client.post("/v1/uploads/multipart/parts", json=token, headers=headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "upload_gone"     # the parts were aborted
    assert not store.exists(key)


def test_limits_ownership_and_abort(client, user, r2, monkeypatch):  # noqa: F811
    headers, _ = user
    r = client.post("/v1/uploads/multipart", json={"filename": "x.exe", "size_bytes": 10}, headers=headers)
    assert r.status_code == 415
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1000")
    config.get_settings.cache_clear()
    r = client.post("/v1/uploads/multipart", json={"filename": "x.mp4", "size_bytes": 1001}, headers=headers)
    assert r.status_code == 413
    up = client.post("/v1/uploads/multipart", json={"filename": "x.mp4", "size_bytes": 1000}, headers=headers).json()
    token = {"upload_token": up["upload_token"]}
    for path in ("parts", "complete", "abort"):                      # another account cannot use the token
        r = client.post(f"/v1/uploads/multipart/{path}", json=token, headers=other_user(client))
        assert r.status_code == 404, path
    assert client.post("/v1/uploads/multipart/abort", json=token, headers=headers).status_code == 204
    assert client.post("/v1/uploads/multipart/abort", json=token, headers=headers).status_code == 204   # again: fine
    r = client.post("/v1/uploads/multipart/parts", json=token, headers=headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "upload_gone"


def test_without_bucket_storage_the_site_uses_the_api_upload(client, user):
    r = client.post("/v1/uploads/multipart", json={"filename": "x.mp4", "size_bytes": 10}, headers=user[0])
    assert r.status_code == 409 and r.json()["error"]["code"] == "direct_upload_unavailable"


@pytest.mark.parametrize("size,part", [(1, 16 * MiB), (16 * MiB * 10_000 + 1, 17 * MiB), (8 * 1024 ** 3, 16 * MiB)])
def test_part_size_keeps_under_ten_thousand_equal_parts(size, part):
    assert routes_direct_upload.part_size_for(size) == part
    assert -(-size // part) <= 10_000
