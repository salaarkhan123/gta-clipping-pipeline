"""1.3: rank within the run and a tier from the AI score; no tier for clips the AI did not rate."""
import pytest

from app.db import new_session
from app.models import Clip, new_id
from app.routes_media import tier_of
from tests.test_api import upload
from tests.test_projects import make_clips

AI = {"title": "t", "virality": {"score": 0, "hook": 0, "flow": 0, "value": 0, "trend": 0}, "reason": "r", "source": "ai"}


def rated(score):
    return {**AI, "virality": {**AI["virality"], "score": score}}


@pytest.mark.parametrize("score, tier", [(100, "top"), (75, "top"), (74, "strong"), (55, "strong"), (54, "solid"),
                                         (35, "solid"), (34, "long_shot"), (0, "long_shot")])
def test_tier_thresholds_are_fixed(score, tier):
    assert tier_of(rated(score)) == tier


def test_no_tier_without_an_ai_rating():
    assert tier_of(None) is None and tier_of({}) is None and tier_of({"title": "x"}) is None
    assert tier_of({"virality": {"score": 97}, "source": "signals"}) is None      # loudness alone is not a quality rating


def test_rank_is_by_score_within_each_run_and_updates_when_a_clip_is_removed(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job_a = make_clips(client, headers, up["upload_id"], transcriber, n=1)
    job_b = make_clips(client, headers, up["upload_id"], transcriber, n=1)
    with new_session() as db:
        first = db.query(Clip).filter(Clip.job_id == job_a).one()
        first.score, first.meta = 0.5, rated(60)
        extra = {}
        for name, score, meta in (("best", 0.9, rated(88)), ("worst", 0.1, None)):
            extra[name] = new_id("clip")
            db.add(Clip(id=extra[name], job_id=job_a, idx=9, start_sec=1, end_sec=2, score=score, signals={}, features={},
                        video_key=first.video_key, meta=meta))
        first_id = first.id
        db.commit()
    by_id = {c["id"]: c for c in client.get(f"/v1/projects/{up['upload_id']}", headers=headers).json()["clips"]}
    assert [(by_id[i]["rank"], by_id[i]["rank_of"], by_id[i]["tier"]) for i in (extra["best"], first_id, extra["worst"])] == \
        [(1, 3, "top"), (2, 3, "strong"), (3, 3, None)]
    other = next(c for c in by_id.values() if c["job_id"] == job_b)
    assert (other["rank"], other["rank_of"]) == (1, 1)                           # ranked inside its own run
    job = {c["id"]: c for c in client.get(f"/v1/jobs/{job_a}", headers=headers).json()["clips"]}
    lib = {c["id"]: c for c in client.get("/v1/clips", headers=headers).json()["clips"]}
    for view in (job, lib):                                                      # the same answer everywhere
        assert (view[first_id]["rank"], view[first_id]["rank_of"], view[first_id]["tier"]) == (2, 3, "strong")
    with new_session() as db:                                                    # the best clip expires
        from app.models import utcnow
        db.get(Clip, extra["best"]).deleted_at = utcnow()
        db.commit()
    clip = next(c for c in client.get(f"/v1/jobs/{job_a}", headers=headers).json()["clips"] if c["id"] == first_id)
    assert (clip["rank"], clip["rank_of"]) == (1, 2)
