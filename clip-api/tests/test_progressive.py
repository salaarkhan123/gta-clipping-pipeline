"""S1: clips are rendered best first and are stored and visible one by one while the job still runs."""
import subprocess
import time

import pytest

from app import worker
from app.config import get_settings
from app.db import new_session
from app.models import Clip, Job, utcnow
from app.pipeline import PipelineOptions, Timer, run_pipeline
from tests.test_api import balance
from tests.test_stage_timings import jt


@pytest.fixture(scope="module")
def rising(tmp_path_factory):
    """60 s with three loud moments of different strength, the earliest one the weakest."""
    out = tmp_path_factory.mktemp("v") / "rising.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
                    "-af", "volume='if(between(t,10,13),0.5,if(between(t,30,33),0.7,if(between(t,48,51),1.0,0.02)))':eval=frame",
                    "-t", "60", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    return out


OPTS = {"max_clips": 3, "clip_length": 10, "tighten": False, "punch_zoom": False}


def test_clips_are_handed_over_best_first_and_returned_in_video_order(rising, tmp_path):
    seen, timer = [], Timer()

    def on_clip(r):
        assert r.video_path.exists() and r.thumb_path.exists()            # complete when handed over
        seen.append((r.index, r.start))
    clips = run_pipeline(rising, PipelineOptions(**OPTS), tmp_path / "o", timer=timer, on_clip=on_clip)
    assert [r.index for r in clips] == [1, 2, 3] and [r.start for r in clips] == sorted(r.start for r in clips)
    by_score = [r.index for r in sorted(clips, key=lambda r: -r.score)]
    assert [i for i, _ in seen] == by_score                                # handed over strongest first
    assert by_score != [1, 2, 3]                                           # which is not the order of the video here
    assert 0 < timer.as_dict()["counts"]["first_clip_sec"] < sum(timer.as_dict()["stages"].values())
    assert len(run_pipeline(rising, PipelineOptions(**OPTS), tmp_path / "p")) == 3      # the callback is optional


def submit(client, headers, rising):
    up = client.post("/v1/uploads?filename=rising.mp4", content=rising.read_bytes(), headers=headers).json()
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": OPTS}, headers=headers).json()["job_id"]
    return up["upload_id"], job_id


def stored(job_id):
    return sorted(p.name for p in (get_settings().storage_dir / "clips" / job_id).glob("*")) if (get_settings().storage_dir / "clips" / job_id).exists() else []


def after_first_clip(do):
    """A pipeline that runs `do()` right after the first clip has been stored."""
    def pipeline(*a, on_clip=None, **k):
        count = [0]

        def hook(r):
            on_clip(r)
            count[0] += 1
            if count[0] == 1:
                do()
        return run_pipeline(*a, on_clip=hook, **k)
    return pipeline


def test_the_first_clip_is_visible_and_playable_while_the_job_is_still_running(client, user, rising):
    headers, _ = user
    upload_id, job_id = submit(client, headers, rising)
    snap = {}

    def look():
        snap["job"] = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
        snap["project"] = client.get(f"/v1/projects/{upload_id}", headers=headers).json()
        snap["video"] = client.get(snap["job"]["clips"][0]["video_url"].replace("http://localhost:8000", "")).status_code
    assert worker.run_once(None, pipeline=after_first_clip(look)) == "SUCCEEDED"
    assert snap["job"]["status"] == "RUNNING" and len(snap["job"]["clips"]) == 1 and snap["video"] == 200
    assert len(snap["project"]["clips"]) == 1
    done = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert done["status"] == "SUCCEEDED" and sorted(c["index"] for c in done["clips"]) == [1, 2, 3]
    assert len({c["id"] for c in done["clips"]}) == 3 and done["credits_charged"] == 1      # none stored twice
    best = max(done["clips"], key=lambda c: c["score"])
    assert snap["job"]["clips"][0]["id"] == best["id"] and best["index"] != 1               # the best one came first
    r = done["result"]
    assert 0 < r["first_clip_sec"] < r["elapsed_sec"] and r["counts"]["clips"] == 3


def test_a_job_that_crashes_after_storing_a_clip_keeps_it_and_charges(client, user, rising):
    """Late crash after progressive handoff must not erase clips the customer already saw."""
    headers, _ = user
    upload_id, job_id = submit(client, headers, rising)
    seen = {}

    def crash():
        seen["files"] = stored(job_id)
        raise RuntimeError("disk fell off")
    assert worker.run_once(None, pipeline=after_first_clip(crash)) == "SUCCEEDED"
    assert len(seen["files"]) >= 2                                          # the clip really was stored first
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "SUCCEEDED" and len(job["clips"]) == 1 and job["credits_charged"] == 1
    assert job["result"].get("partial") is True and job["result"].get("ended_early_code") == "processing_failed"
    assert len(client.get(f"/v1/projects/{upload_id}", headers=headers).json()["clips"]) == 1
    assert client.get("/v1/clips", headers=headers).json()["total"] == 1
    assert stored(job_id) and balance(client, headers) == 29                 # charged, not refunded


def test_cancelling_mid_run_removes_the_clips_already_shown_and_refunds(client, user, rising):
    headers, _ = user
    _, job_id = submit(client, headers, rising)
    assert worker.run_once(None, pipeline=after_first_clip(
        lambda: client.post(f"/v1/jobs/{job_id}/cancel", headers=headers))) == "CANCELED"
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "CANCELED" and job["clips"] == [] and stored(job_id) == [] and balance(client, headers) == 30


def test_a_dead_workers_clips_are_kept_and_it_cannot_add_more_when_it_comes_back(client, user, rising):
    headers, _ = user
    _, job_id = submit(client, headers, rising)
    seen = {}

    def presumed_dead():
        with new_session() as db:                                           # no heartbeat for a year
            db.get(Job, job_id).heartbeat_at = utcnow().replace(year=utcnow().year - 1)
            db.commit()
        seen["swept"] = worker.sweep_stale_jobs()
        snap = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
        seen["status"] = snap["status"]
        seen["clips"] = len(snap["clips"])
        seen["files"] = len(stored(job_id))
    # Returning worker sees LOST (already finalised) and must not wipe the kept clips.
    assert worker.run_once(None, pipeline=after_first_clip(presumed_dead)) == "SUCCEEDED"
    assert seen["swept"] == 1 and seen["status"] == "SUCCEEDED" and seen["clips"] == 1 and seen["files"] >= 2
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "SUCCEEDED" and len(job["clips"]) == 1 and job["result"].get("partial") is True
    assert stored(job_id) and balance(client, headers) == 29                 # charged exactly once
    with new_session() as db:
        assert db.query(Clip).filter(Clip.job_id == job_id, Clip.deleted_at.is_(None)).count() == 1


def test_a_crash_at_finalise_99_keeps_all_handed_over_clips(client, user, rising):
    """Reproduce the production failure mode: clips visible, then a late error at uploading/99."""
    headers, _ = user
    _, job_id = submit(client, headers, rising)
    n = [0]

    def pipeline(*a, on_clip=None, **k):
        out = run_pipeline(*a, on_clip=on_clip, **k)
        n[0] = len(out)
        raise RuntimeError("finalise failed at 99")

    assert worker.run_once(None, pipeline=pipeline) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "SUCCEEDED" and len(job["clips"]) == n[0] == 3
    assert job["result"].get("partial") is True and job["credits_charged"] == 1
    assert balance(client, headers) == 29


def test_the_timing_script_reports_the_first_clip(tmp_path, capsys):
    import json
    p = tmp_path / "job.json"
    p.write_text(json.dumps({"job_id": "j", "status": "SUCCEEDED", "clips": [{}] * 3, "result": {
        "elapsed_sec": 100.0, "speed_x": 72.0, "queue_sec": 4.0, "total_sec": 104.0, "first_clip_sec": 41.0,
        "stages": {"render": 60.0}, "counts": {"source_sec": 7200.0, "clips": 3}}}))
    assert jt.compare(jt.load(p))["first_clip_sec"] == 45.0                  # queue included: what the customer waits
    assert jt.main([str(p)]) == 0 and "First clip watchable after 45 s" in capsys.readouterr().out
