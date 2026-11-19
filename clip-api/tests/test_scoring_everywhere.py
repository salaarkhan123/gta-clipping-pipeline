"""One scoring everywhere: Clip Maker clips, Find Moments clips and a finished clip rated on its own (what the
website's own clips use) all go through ClaudeAI.clip_meta, and everything that shows a rating reads it with
ai.rating_of: five sub-scores stored one by one, their plain mean as the AI rating, and the version that made it."""
import json

import httpx

from app import worker
from app.ai import LEGACY_VERSION, SCORES, SCORING_VERSION, ClaudeAI, parse_meta, rating_of, signal_meta
from tests.test_api import upload
from tests.test_punchier_clips import Talker

FIVE = {"hook": 82, "payoff": 91, "clarity": 64, "emotion": 77, "pacing": 56}        # mean 74
REPLY = {"content": [{"type": "tool_use", "name": "clip_meta", "input": {
    "titles": ["a", "b", "c"], "hook": "He never saw it", "hashtags": ["gta"], "reason": "r", "kind": "clutch",
    "virality": FIVE}}]}
EXPECTED = {"rating": 74, "scores": FIVE, "scoring_version": SCORING_VERSION}


def real_ai(seen=None):
    """The app's own AI client over a stand-in for the API: the code path of a paid call, without one."""
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY)
    return ClaudeAI("k", "claude-haiku-5-5", httpx.Client(transport=httpx.MockTransport(handler)))


# ---------- the one reader ----------

def test_a_v2_rating_is_five_sub_scores_their_plain_mean_and_a_version():
    meta = parse_meta(REPLY["content"][0]["input"])
    assert tuple(meta["scores"]) == SCORES == ("hook", "payoff", "clarity", "emotion", "pacing")
    assert meta["virality"]["score"] == round(sum(FIVE.values()) / 5) == 74          # equal weights
    assert meta["scoring_version"] == SCORING_VERSION == "judge-v2-equal"
    assert rating_of(meta) == EXPECTED


def test_a_clip_judged_before_v2_still_reads_and_an_unrated_one_has_no_rating():
    old = parse_meta({"titles": ["a"], "hashtags": [], "virality": {"hook": 90, "flow": 80, "value": 70, "trend": 60}})
    assert rating_of(old) == {"rating": 75, "scores": None, "scoring_version": LEGACY_VERSION}
    stored_long_ago = {"title": "t", "virality": {"score": 61, "hook": 70, "flow": 60, "value": 60, "trend": 54}}
    assert rating_of(stored_long_ago) == {"rating": 61, "scores": None, "scoring_version": LEGACY_VERSION}
    assert rating_of(signal_meta(0.8)) is None and rating_of(None) is None and rating_of({"title": "t"}) is None
    assert rating_of({"virality": {"score": 70}, "scores": {"hook": 1}}) == {"rating": 70, "scores": None,
                                                                             "scoring_version": LEGACY_VERSION}


# ---------- the same function for every kind of clip ----------

def shown(clip):
    return {"rating": clip["virality_score"], "scores": clip["scores"], "scoring_version": clip["scoring_version"]}


def test_clip_maker_clips_carry_the_v2_rating(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                    headers=headers)
    seen = []
    assert worker.run_once(Talker(), ai=real_ai(seen)) == "SUCCEEDED"
    clip = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["clips"][0]
    assert shown(clip) == EXPECTED and clip["virality"] == {"score": 74, **FIVE}
    assert clip["tier"] == "strong" and clip["display_score"] is not None            # made from the same rating
    assert seen and all(b["tools"][0]["input_schema"]["properties"]["virality"]["required"] == list(SCORES) for b in seen)


def test_find_moments_clips_carry_the_same_rating(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/find", json={"upload_id": up["upload_id"], "query": "No way!", "max_results": 1,
                                      "make_clips": True, "clip_length": 10}, headers=headers)
    assert r.status_code == 202, r.text
    assert worker.run_once(transcriber, ai=real_ai()) == "SUCCEEDED"
    clips = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["clips"]
    assert clips and all(shown(c) == EXPECTED for c in clips)


def test_a_finished_clip_rated_on_its_own_gets_the_same_rating(tmp_path):
    # The entry point for clips made outside a job (the website's own clips): the call the worker makes for a
    # rendered clip, then the one reader. No special prompt, no special weights.
    seen = []
    meta = real_ai(seen).clip_meta("no way he just did that", {"length": 30.0, "signals": {"audio": 1.0}}, None)
    assert rating_of(meta) == EXPECTED
    assert "payoff =" in seen[0]["system"] and seen[0]["tools"][0]["name"] == "clip_meta"


def test_older_stored_clips_still_show(client, user, video):
    from app.db import new_session
    from app.models import Clip
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                    headers=headers)
    assert worker.run_once(Talker(), ai=real_ai()) == "SUCCEEDED"
    job_id = r.json()["job_id"]
    with new_session() as db:              # as stored before v2: four parts, no scores, no version
        clip = db.query(Clip).filter(Clip.job_id == job_id).one()
        clip.meta = {"title": "Old one", "virality": {"score": 75, "hook": 90, "flow": 80, "value": 70, "trend": 60},
                     "source": "ai"}
        db.commit()
    got = client.get(f"/v1/jobs/{job_id}", headers=headers).json()["clips"][0]
    assert shown(got) == {"rating": 75, "scores": None, "scoring_version": LEGACY_VERSION}
    assert got["virality"]["flow"] == 80 and got["tier"] == "top"

