"""WORKER_CONCURRENCY: two jobs at once in one worker, each claimed once, refunds intact."""
import threading
import time

import pytest
from pydantic import ValidationError

from app import worker
from app.config import Settings
from app.pipeline import run_pipeline
from tests.test_api import balance, upload


def submit(client, headers, video, n):
    up = upload(client, headers, video)
    return [client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                        headers=headers).json()["job_id"] for _ in range(n)]


def serve_until_done(client, headers, job_ids, pipeline, transcriber, concurrency=2):
    stop = threading.Event()
    t = threading.Thread(target=worker.serve, args=(concurrency, stop, transcriber, pipeline))
    t.start()
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            jobs = [client.get(f"/v1/jobs/{j}", headers=headers).json() for j in job_ids]
            if all(j["status"] in ("SUCCEEDED", "FAILED") for j in jobs):
                return jobs
            time.sleep(0.2)
        raise AssertionError(f"jobs did not finish: {[j['status'] for j in jobs]}")
    finally:
        stop.set()
        t.join(timeout=60)


def test_two_jobs_run_at_once_and_each_is_claimed_once(client, user, video, transcriber):
    headers, _ = user
    job_ids = submit(client, headers, video, 2)
    together, calls = threading.Barrier(2), []

    def both_running(*a, **k):
        together.wait(timeout=30)          # only passes when two jobs are inside the pipeline at the same time
        calls.append(threading.current_thread().name)
        return run_pipeline(*a, **k)
    jobs = serve_until_done(client, headers, job_ids, both_running, transcriber)
    assert [j["status"] for j in jobs] == ["SUCCEEDED", "SUCCEEDED"]
    assert sorted(calls) == ["slot-0", "slot-1"]                      # two pipeline runs, one per slot, no third
    assert [j["credits_charged"] for j in jobs] == [1, 1] and balance(client, headers) == 28


def test_a_crash_in_one_slot_refunds_it_and_the_other_still_succeeds(client, user, video, transcriber):
    headers, _ = user
    job_ids = submit(client, headers, video, 2)
    together, first = threading.Barrier(2), threading.Lock()

    def one_crashes(*a, **k):
        together.wait(timeout=30)
        if first.acquire(blocking=False):
            raise RuntimeError("secret internal detail")
        return run_pipeline(*a, **k)
    jobs = serve_until_done(client, headers, job_ids, one_crashes, transcriber)
    assert sorted(j["status"] for j in jobs) == ["FAILED", "SUCCEEDED"]
    assert sorted(j["credits_charged"] for j in jobs) == [0, 1] and balance(client, headers) == 29


def test_many_claimers_never_share_a_job(client, user, video):
    headers, _ = user
    job_ids = submit(client, headers, video, 2)                       # an account may have 2 active jobs
    start, got = threading.Barrier(8), []

    def claim():
        start.wait(timeout=10)
        got.append(worker.claim_job())
    threads = [threading.Thread(target=claim) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    claimed = [j for j in got if j]
    assert sorted(claimed) == sorted(job_ids)                         # both, neither twice
    for j in job_ids:                                                 # leave the queue clean: cancel refunds
        client.post(f"/v1/jobs/{j}/cancel", headers=headers)


def test_concurrency_is_one_by_default_and_capped_at_two():
    assert Settings.model_fields["worker_concurrency"].default == 1
    for bad in (0, 3):
        with pytest.raises(ValidationError):
            Settings(worker_concurrency=bad)
