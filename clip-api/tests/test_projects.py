"""1.1: projects (an upload with its jobs and clips) and the clip library."""
import uuid

from app import worker
from tests.test_api import upload


def new_user(client):
    r = client.post("/v1/auth/signup", json={"email": f"u{uuid.uuid4().hex[:10]}@example.org", "password": "correct-horse-9"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def make_clips(client, headers, upload_id, transcriber, n=2):
    r = client.post("/v1/clips", json={"upload_id": upload_id, "options": {"max_clips": n, "clip_length": 10}}, headers=headers)
    assert r.status_code == 202, r.text
    assert worker.run_once(transcriber) == "SUCCEEDED"
    return r.json()["job_id"]


def test_projects_list_counts_jobs_and_clips_per_upload(client, user, video, transcriber):
    headers, _ = user
    assert client.get("/v1/projects", headers=headers).json() == {"projects": []}
    first = upload(client, headers, video)
    second = client.post("/v1/uploads?filename=other.mp4", content=video.read_bytes() + b"\0", headers=headers).json()
    make_clips(client, headers, first["upload_id"], transcriber, n=2)
    queued = client.post("/v1/clips", json={"upload_id": second["upload_id"]}, headers=headers).json()["job_id"]
    projects = {p["upload_id"]: p for p in client.get("/v1/projects", headers=headers).json()["projects"]}
    a, b = projects[first["upload_id"]], projects[second["upload_id"]]
    assert (a["jobs"], a["active"], a["clips"]) == (1, False, len(client.get(f"/v1/projects/{a['upload_id']}", headers=headers).json()["clips"]))
    assert a["clips"] >= 1 and a["thumb_url"] and a["filename"] == "sample.mp4" and a["analyzed"] is True
    assert (b["jobs"], b["active"], b["clips"], b["thumb_url"]) == (1, True, 0, None)
    assert [p["upload_id"] for p in client.get("/v1/projects", headers=headers).json()["projects"]][0] == second["upload_id"]   # newest first
    client.post(f"/v1/jobs/{queued}/cancel", headers=headers)


def test_project_detail_has_source_jobs_and_all_clips_across_jobs(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job_a = make_clips(client, headers, up["upload_id"], transcriber, n=1)
    job_b = make_clips(client, headers, up["upload_id"], transcriber, n=1)
    project = client.get(f"/v1/projects/{up['upload_id']}", headers=headers).json()
    assert project["upload_id"] == up["upload_id"] and project["duration_sec"] == up["duration_sec"]
    assert len(client.get(project["source_url"].replace("http://localhost:8000", "")).content) == up["size_bytes"]
    assert [j["job_id"] for j in project["jobs"]] == [job_b, job_a]                   # newest first
    assert {c["job_id"] for c in project["clips"]} == {job_a, job_b} and all(c["tool"] == "clips" for c in project["clips"])
    scores = [c["score"] for c in project["clips"]]
    assert scores == sorted(scores, reverse=True) and all(c["video_url"] and c["created_at"] for c in project["clips"])


def test_projects_and_library_never_show_another_account(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    make_clips(client, headers, up["upload_id"], transcriber, n=1)
    stranger = new_user(client)
    assert client.get("/v1/projects", headers=stranger).json() == {"projects": []}
    assert client.get(f"/v1/projects/{up['upload_id']}", headers=stranger).status_code == 404
    assert client.get("/v1/clips", headers=stranger).json() == {"total": 0, "clips": []}
    assert client.get("/v1/projects").status_code == 401 and client.get("/v1/clips").status_code == 401


def test_library_lists_every_clip_with_its_project_and_pages(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    make_clips(client, headers, up["upload_id"], transcriber, n=1)
    make_clips(client, headers, up["upload_id"], transcriber, n=1)
    lib = client.get("/v1/clips", headers=headers).json()
    assert lib["total"] == len(lib["clips"]) == 2
    assert all(c["upload_id"] == up["upload_id"] and c["filename"] == "sample.mp4" and c["video_url"] for c in lib["clips"])
    page = client.get("/v1/clips?limit=1&offset=1", headers=headers).json()
    assert page["total"] == 2 and [c["id"] for c in page["clips"]] == [lib["clips"][1]["id"]]
