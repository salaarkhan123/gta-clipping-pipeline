"""What a run on an already-analysed upload costs (owner's decision, 2026-11-16): the worst case is reserved, the
job is charged for the seconds it rendered, and the rest is returned in the same settle. A first run is unchanged."""
import pytest
from sqlalchemy import select

from app import ledger, worker
from app.db import new_session
from app.models import CreditLedger, Job, Upload
from app.pipeline import PipelineError
from app.routes_media import ClipOptions, rerun_seconds
from tests.test_api import balance, upload


def analysed(client, headers, video, seconds=1800.0, analysed=True):
    """An upload the account already paid to analyse, recorded as `seconds` long."""
    up = upload(client, headers, video)
    with new_session() as db:
        u = db.get(Upload, up["upload_id"])
        u.analyzed, u.duration_sec = analysed, seconds
        db.commit()
    return up["upload_id"]


def renders(seconds: float):
    """A stand-in pipeline that reports having rendered `seconds` of clips."""
    def pipeline(src, opts, out, progress, transcriber, deadline, timer=None, **kw):
        if seconds:
            timer.count("rendered_sec", seconds)
        return []
    return pipeline


def run(client, headers, upload_id, options, pipeline):
    r = client.post("/v1/clips", json={"upload_id": upload_id, "options": options}, headers=headers)
    assert r.status_code == 202, r.text
    status = worker.run_once(None, pipeline=pipeline)
    return status, client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()


def rows(job_id):
    with new_session() as db:
        return [(r.kind, r.delta, r.idempotency_key) for r in db.execute(
            select(CreditLedger).where(CreditLedger.job_id == job_id).order_by(CreditLedger.id)).scalars()]


@pytest.mark.parametrize("options,video_sec,expected", [
    ({}, 7200, 90),                                                    # none of the new options: max_clips * clip_length
    ({"max_clips": 10, "clip_length": 60}, 120, 600),                  # ... exactly as before, not capped by the video
    ({"duration": "0-90"}, 7200, 4500),                                # every moment: 50 clips of up to 90 s
    ({"duration": "0-90"}, 1800, 1800),                                # never more than the video holds
    ({"duration": "180-300", "limit": 50}, 7200, 7200),
    ({"duration": "30-60", "limit": 3}, 7200, 180),
    ({"limit": 9, "clip_length": 20}, 7200, 180),                      # a limit without a bucket: clip_length each
    ({"duration": "0-30", "range": {"start": 600, "end": 900}}, 7200, 300),      # never more than the range holds
    ({"range": {"start": 0, "end": 60}}, 7200, 60),                    # a range alone: 3 clips of 30 s, capped at the range
])
def test_the_most_a_rerun_can_render(options, video_sec, expected):
    assert rerun_seconds(ClipOptions(**options), video_sec) == expected


def test_a_rerun_reserves_the_worst_case_and_is_charged_for_what_it_rendered(client, user, video):
    headers, _ = user
    up = analysed(client, headers, video)
    status, job = run(client, headers, up, {"duration": "0-90"}, renders(95.0))          # 30 minutes: 30 credits held
    assert status == "SUCCEEDED" and job["options"]["charge_basis"] == "rendered"
    assert (job["credits_reserved"], job["credits_charged"]) == (30, 2)                    # 95 s rendered: 2 credits
    assert rows(job["job_id"]) == [("reserve", -30, f"reserve:{job['job_id']}"), ("commit", 28, f"settle:{job['job_id']}")]
    assert balance(client, headers) == 28
    with new_session() as db:                                                               # settled once: a second settle
        again = db.get(Job, job["job_id"])                                                      # of either kind does nothing
        assert ledger.settle(db, again, success=True, charged=0) is False
        assert ledger.settle(db, again, success=False) is False
        db.commit()
    assert balance(client, headers) == 28 and len(rows(job["job_id"])) == 2


@pytest.mark.parametrize("rendered,charged", [(0, 0), (1.0, 1), (60.0, 1), (60.5, 2), (1800.0, 30), (99999.0, 30)])
def test_the_charge_follows_the_seconds_rendered_and_never_exceeds_the_reservation(client, user, video, rendered, charged):
    headers, _ = user
    up = analysed(client, headers, video)
    _, job = run(client, headers, up, {"duration": "0-90"}, renders(rendered))
    assert (job["credits_reserved"], job["credits_charged"]) == (30, charged)
    assert balance(client, headers) == 30 - charged
    assert sum(r[1] for r in rows(job["job_id"])) == -charged and len(rows(job["job_id"])) == 2


def test_a_rerun_without_the_new_options_reserves_as_before_and_is_charged_for_what_it_rendered(client, user, video):
    headers, _ = user
    up = analysed(client, headers, video)
    _, job = run(client, headers, up, {"max_clips": 3, "clip_length": 30}, renders(50.0))
    assert (job["credits_reserved"], job["credits_charged"]) == (2, 1) and balance(client, headers) == 29


def test_a_first_run_is_charged_for_the_whole_video_whatever_it_renders(client, user, video):
    headers, _ = user
    up = analysed(client, headers, video, analysed=False)
    _, job = run(client, headers, up, {"duration": "0-30", "limit": 1}, renders(12.0))
    assert "charge_basis" not in job["options"]
    assert (job["credits_reserved"], job["credits_charged"]) == (30, 30) and balance(client, headers) == 0
    assert rows(job["job_id"]) == [("reserve", -30, f"reserve:{job['job_id']}"), ("commit", 0, f"settle:{job['job_id']}")]


def test_a_rerun_that_fails_is_refunded_in_full(client, user, video):
    headers, _ = user
    up = analysed(client, headers, video)

    def broken(*a, **kw):
        raise PipelineError("media_error", "This file could not be read.")
    status, job = run(client, headers, up, {"duration": "0-90"}, broken)
    assert status == "FAILED" and (job["credits_reserved"], job["credits_charged"]) == (30, 0)
    assert rows(job["job_id"]) == [("reserve", -30, f"reserve:{job['job_id']}"), ("release", 30, f"settle:{job['job_id']}")]
    assert balance(client, headers) == 30


def test_a_rerun_the_balance_cannot_cover_in_the_worst_case_is_refused(client, user, video):
    headers, _ = user
    up = analysed(client, headers, video, seconds=7200.0)                                   # worst case 75 credits; 30 held
    r = client.post("/v1/clips", json={"upload_id": up, "options": {"duration": "0-90"}}, headers=headers)
    assert r.status_code == 402 and r.json()["error"]["code"] == "insufficient_credits"
    assert balance(client, headers) == 30
    ok = client.post("/v1/clips", json={"upload_id": up, "options": {"duration": "0-90", "limit": 20}}, headers=headers)
    assert ok.status_code == 202 and ok.json()["credits_reserved"] == 30                    # a limit brings it in reach
    client.post(f"/v1/jobs/{ok.json()['job_id']}/cancel", headers=headers)                  # leave nothing queued
    assert balance(client, headers) == 30


def test_a_real_rerun_on_a_short_video(client, user, video, transcriber):
    headers, _ = user
    up = analysed(client, headers, video, seconds=40.0)
    r = client.post("/v1/clips", json={"upload_id": up, "options": {"duration": "0-30", "vertical": False, "punch_zoom": False}},
                    headers=headers)
    assert r.json()["credits_reserved"] == 1 and worker.run_once(transcriber) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert job["clips"] and 0 < job["result"]["counts"]["rendered_sec"] <= 60 and job["credits_charged"] == 1
