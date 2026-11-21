"""S1 / Wave B2: chosen moments are published (times, scores, copy) before encodes finish."""
import subprocess

import pytest

from app import worker
from app.pipeline import run_pipeline
from tests.test_api import balance
from tests.test_progressive import OPTS, after_first_clip, stored, submit


@pytest.fixture(scope="module")
def rising(tmp_path_factory):
    """60 s with three loud moments of different strength, the earliest one the weakest."""
    out = tmp_path_factory.mktemp("v") / "rising.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
                    "-af", "volume='if(between(t,10,13),0.5,if(between(t,30,33),0.7,if(between(t,48,51),1.0,0.02)))':eval=frame",
                    "-t", "60", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(out)], check=True)
    return out


def after_moments(do):
    """Run `do()` right after on_moments has stored rows, before any encode / on_clip."""
    def pipeline(*a, on_moments=None, on_clip=None, **k):
        def hook(moments):
            if on_moments is not None:
                on_moments(moments)
            do()
        return run_pipeline(*a, on_moments=hook, on_clip=on_clip, **k)
    return pipeline


def test_moments_are_listed_before_any_encode(client, user, rising):
    headers, _ = user
    upload_id, job_id = submit(client, headers, rising)
    snap = {}

    def look():
        snap["job"] = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
        snap["project"] = client.get(f"/v1/projects/{upload_id}", headers=headers).json()
        snap["files"] = stored(job_id)

    assert worker.run_once(None, pipeline=after_moments(look)) == "SUCCEEDED"
    assert snap["job"]["status"] == "RUNNING"
    clips = snap["job"]["clips"]
    assert len(clips) == 3
    assert all(c["rendered"] == "none" and c["video_url"] is None for c in clips)
    assert all(c["start_sec"] < c["end_sec"] and c["score"] is not None for c in clips)
    assert [c["index"] for c in clips] == [1, 2, 3]
    assert [c["start_sec"] for c in clips] == sorted(c["start_sec"] for c in clips)
    assert snap["files"] == []                                          # no media written yet
    assert len(snap["project"]["clips"]) == 3

    done = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert done["status"] == "SUCCEEDED" and done["credits_charged"] == 1
    assert {c["id"] for c in clips} == {c["id"] for c in done["clips"]}  # same rows, later filled in
    assert all(c["video_url"] for c in done["clips"])
    assert len({c["id"] for c in done["clips"]}) == 3


def test_render_none_publishes_moments_before_thumbnails(client, user, rising):
    headers, _ = user
    up = client.post("/v1/uploads?filename=rising.mp4", content=rising.read_bytes(), headers=headers).json()
    body = {"upload_id": up["upload_id"], "options": {**OPTS, "render": "none"}}
    job_id = client.post("/v1/clips", json=body, headers=headers).json()["job_id"]
    snap = {}

    def look():
        snap["job"] = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
        snap["files"] = stored(job_id)

    assert worker.run_once(None, pipeline=after_moments(look)) == "SUCCEEDED"
    assert snap["job"]["status"] == "RUNNING"
    clips = snap["job"]["clips"]
    assert len(clips) == 3 and all(c["rendered"] == "none" and c["video_url"] is None for c in clips)
    assert snap["files"] == []

    done = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert done["status"] == "SUCCEEDED" and {c["id"] for c in clips} == {c["id"] for c in done["clips"]}
    assert all(c["rendered"] == "none" and c["video_url"] is None and c["thumb_url"] for c in done["clips"])
    assert done["credits_charged"] == 1 and balance(client, headers) == 29


def test_crash_after_moments_hides_rows_and_refunds(client, user, rising):
    headers, _ = user
    _, job_id = submit(client, headers, rising)

    def crash():
        raise RuntimeError("disk fell off")

    assert worker.run_once(None, pipeline=after_moments(crash)) == "FAILED"
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "FAILED" and job["clips"] == [] and job["credits_charged"] == 0
    assert stored(job_id) == [] and balance(client, headers) == 30


def test_first_encode_still_updates_the_early_moment_row(client, user, rising):
    """on_clip fills the same clip id that on_moments created (no duplicate rows)."""
    headers, _ = user
    _, job_id = submit(client, headers, rising)
    snap = {}

    def look():
        snap["after_first"] = client.get(f"/v1/jobs/{job_id}", headers=headers).json()

    assert worker.run_once(None, pipeline=after_first_clip(look)) == "SUCCEEDED"
    mid = snap["after_first"]["clips"]
    assert len(mid) == 3
    playable = [c for c in mid if c.get("video_url")]
    assert len(playable) == 1
    done = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert {c["id"] for c in mid} == {c["id"] for c in done["clips"]}
    assert playable[0]["id"] in {c["id"] for c in done["clips"] if c.get("video_url")}
