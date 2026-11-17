"""display_score: the AI's raw score calibrated across the clips of one job (docs/CONTRACTS.md, "Score calibration"),
worked out when clips are read and returned next to the raw numbers, which stay as they are."""
import random

import pytest

from app.db import new_session
from app.models import Clip, new_id, utcnow
from app.scoring import ai_score, display_scores
from tests.test_api import upload
from tests.test_projects import make_clips, new_user
from tests.test_score_display import rated


# ---- the formula ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, shown", [
    ([], []),
    ([70], [95]),                                   # one clip shows the top: 90 + 9 * (70 - 40) / 50 = 95.4
    ([20], [90]), ([40], [90]), ([0], [90]),        # a best raw score of 40 or less: the top is 90
    ([90], [99]), ([97], [99]), ([100], [99]),      # 90 or more: the top is 99
    ([65], [95]),                                   # 94.5: a half rounds up
    ([50, 50, 50], [92, 92, 92]),                   # all equal: every clip shows the top (91.8)
    ([35, 20, 10], [90, 69, 55]),                   # best below 40: top 90, floor 55
    ([100, 90, 50], [99, 91, 59]),                  # best at 90 or above: top 99, floor 59
    ([88, 80, 71, 64, 52, 40], [99, 92, 84, 79, 69, 59]),      # a spread: top 98.64, floor 58.64
    ([40, 88, 52, 80, 64, 71], [59, 99, 69, 92, 79, 84]),      # the answer follows the clip, not its position
    ([88, None, 40, None], [99, None, 59, None]),   # a clip the AI did not rate has none, and does not move the scale
    ([None, None], [None, None]), ([None, 72], [None, 96]),
    ([80, 80, 60], [97, 97, 57]),                   # ties stay ties
    ([71.5, 60.25], [96, 56]),                      # raw scores need not be whole numbers
])
def test_the_formula(raw, shown):
    assert display_scores(raw) == shown


def test_any_set_of_scores_keeps_its_order_and_stays_in_range():
    rng = random.Random(7)
    for _ in range(2000):
        raw = [rng.choice([None, rng.randint(0, 100), rng.randint(0, 100), round(rng.uniform(0, 100), 1)])
               for _ in range(rng.randint(1, 50))]
        shown = display_scores(raw)
        assert len(shown) == len(raw)
        assert all((s is None) == (d is None) for s, d in zip(raw, shown))                     # None stays None
        pairs = [(s, d) for s, d in zip(raw, shown) if s is not None]
        if not pairs:
            continue
        assert all(type(d) is int and 55 <= d <= 99 for _s, d in pairs)                        # whole numbers, 55 to 99
        best = max(pairs)[1]
        assert 90 <= best <= 99 and best == max(d for _s, d in pairs)                          # the top clip: 90 to 99
        for (s1, d1) in pairs:
            for (s2, d2) in pairs:
                assert d1 == d2 if s1 == s2 else (d1 >= d2) == (s1 > s2) or d1 == d2           # never out of order
        by_raw = sorted(pairs, key=lambda p: p[0], reverse=True)
        assert [d for _s, d in by_raw] == sorted((d for _s, d in pairs), reverse=True)         # the raw order is a display order


def test_a_higher_best_raw_score_shows_a_higher_top():
    tops = [display_scores([hi, 0])[0] for hi in range(0, 101)]
    assert tops == sorted(tops) and tops[0] == tops[40] == 90 and tops[90] == tops[100] == 99 and tops[65] == 95


def test_only_an_ai_rating_counts_as_a_raw_score():
    assert ai_score(rated(64)) == 64 and ai_score(rated(0)) == 0
    assert ai_score(None) is None and ai_score({}) is None and ai_score({"title": "x"}) is None
    assert ai_score({"virality": {"score": 97}, "source": "signals"}) is None      # loudness alone is not a rating
    assert ai_score({"virality": {"score": "high"}, "source": "ai"}) is None


# ---- the API -------------------------------------------------------------------------------------------------

RAW = ("score", "virality", "rank", "rank_of", "index", "tier", "title", "start_sec", "end_sec")


def add_clips(job_id, scores) -> dict:
    """Give a finished job extra stored clips: {name: (pipeline score, meta)} -> {name: clip id}."""
    ids = {}
    with new_session() as db:
        first = db.query(Clip).filter(Clip.job_id == job_id).first()
        for n, (name, (score, meta)) in enumerate(scores.items()):
            ids[name] = new_id("clip")
            db.add(Clip(id=ids[name], job_id=job_id, idx=10 + n, start_sec=1 + n, end_sec=2 + n, score=score, signals={},
                        features={}, video_key=first.video_key, meta=meta))
        db.commit()
    return ids


def views(client, headers, upload_id, job_id) -> dict:
    """Every place a clip is returned, as {place: {clip id: clip}}."""
    out = {"job": client.get(f"/v1/jobs/{job_id}", headers=headers).json()["clips"],
           "project": client.get(f"/v1/projects/{upload_id}", headers=headers).json()["clips"],
           "library": client.get("/v1/clips", headers=headers).json()["clips"]}
    return {place: {c["id"]: c for c in clips} for place, clips in out.items()}


def test_every_clip_response_carries_the_display_score_and_the_raw_numbers_stay(client, video, transcriber):
    headers = new_user(client)
    up = upload(client, headers, video)
    job_a = make_clips(client, headers, up["upload_id"], transcriber, n=1)
    job_b = make_clips(client, headers, up["upload_id"], transcriber, n=1)
    with new_session() as db:
        first = db.query(Clip).filter(Clip.job_id == job_a).one()
        first.score, first.meta, first_id = 0.5, rated(64), first.id
        other = db.query(Clip).filter(Clip.job_id == job_b).one()
        other.meta, other_id = rated(30), other.id
        db.commit()
    before = views(client, headers, up["upload_id"], job_a)                # two clips so far, one per run
    for place, clips in before.items():
        assert clips[first_id]["display_score"] == 94, place                # alone in its run: the top for a raw 64 (94.32)
    ids = add_clips(job_a, {"best": (0.9, rated(88)), "low": (0.2, rated(40)), "unrated": (0.1, None),
                            "loud": (0.3, {"virality": {"score": 99}, "source": "signals"})})
    want = {ids["best"]: 99, first_id: 79, ids["low"]: 59, ids["unrated"]: None, ids["loud"]: None}
    after = views(client, headers, up["upload_id"], job_a)
    for place, clips in after.items():
        assert {i: clips[i]["display_score"] for i in want} == want, place          # the same answer everywhere
        assert {i: clips[i]["virality"] and clips[i]["virality"]["score"] for i in want} == \
            {ids["best"]: 88, first_id: 64, ids["low"]: 40, ids["unrated"]: None, ids["loud"]: 99}, place     # raw: untouched
        assert [clips[i]["rank"] for i in (ids["best"], first_id, ids["loud"], ids["low"], ids["unrated"])] == [1, 2, 3, 4, 5]
        assert {clips[i]["tier"] for i in (ids["best"], first_id, ids["low"])} == {"top", "strong", "solid"}
        assert clips[ids["best"]]["score"] == 0.9 and clips[first_id]["score"] == 0.5
    for place in ("project", "library"):
        assert after[place][other_id]["display_score"] == 90, place          # the other run has its own scale (raw 30)
        for key in RAW:                                                      # and nothing else about its clip moved
            assert after[place][other_id][key] == before[place][other_id][key], (place, key)
    for place in after:                                                      # its own raw numbers did not move either
        for key in set(RAW) - {"rank", "rank_of"}:
            assert after[place][first_id][key] == before[place][first_id][key], (place, key)
    assert all("display_score" in c for clips in after.values() for c in clips.values())

    patched = client.patch(f"/v1/clips/{first_id}", json={"title": "mine"}, headers=headers).json()
    assert (patched["display_score"], patched["rank"], patched["title"], patched["virality"]["score"]) == (79, 2, "mine", 64)

    with new_session() as db:                                                # the best clip is deleted: the others re-spread
        db.get(Clip, ids["best"]).deleted_at = utcnow()
        db.commit()
    for place, clips in views(client, headers, up["upload_id"], job_a).items():
        assert ids["best"] not in clips, place
        assert (clips[first_id]["display_score"], clips[ids["low"]]["display_score"]) == (94, 55), place   # top 94.32, floor 55
        assert clips[ids["unrated"]]["display_score"] is None, place


def test_a_job_the_ai_did_not_rate_has_no_display_scores(client, video, transcriber):
    headers = new_user(client)
    up = upload(client, headers, video)
    job_id = make_clips(client, headers, up["upload_id"], transcriber, n=1)      # no AI in this run
    for place, clips in views(client, headers, up["upload_id"], job_id).items():
        assert clips and all(c["display_score"] is None and c["tier"] is None for c in clips.values()), place
    queued = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()
    assert "clips" not in queued                                                 # a job without clips: nothing to score
    assert client.get(f"/v1/jobs/{queued['job_id']}", headers=headers).json()["clips"] == []
    client.post(f"/v1/jobs/{queued['job_id']}/cancel", headers=headers)
