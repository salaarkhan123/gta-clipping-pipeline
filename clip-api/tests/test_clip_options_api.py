"""The Clip Maker's new options over the API (duration, limit, range, project_name), what a clip reports
(times in ms, virality_score, kind, why, rank_index, timeline_index), and the judge's `kind`.

Nothing here changes what a job costs: see test_the_new_options_never_change_what_a_job_reserves.
"""
import json
import typing

import httpx
import pytest

from app import worker
from app.ai import SYSTEM, TOOL, TRANSCRIPT_CHARS, ClaudeAI, parse_meta, system_for
from app.db import new_session
from app.models import Clip, Job, Upload, new_id, utcnow
from app.pipeline import PipelineOptions
from app.pipeline.moments import BUCKETS, KINDS
from app.routes_media import ClipOptions
from tests.test_api import balance, upload

BEFORE = {"id", "job_id", "index", "start_sec", "end_sec", "tier", "score", "signals", "kept", "reaction", "bookmarked",
          "title", "description", "hashtags", "virality", "reason", "titles", "hook", "hook_on_screen", "suggestion",
          "video_url", "thumb_url", "captions_url", "rank", "rank_of"}       # every clip field before this change
NEW = {"start_ms", "end_ms", "virality_score", "kind", "why", "rank_index", "timeline_index",
       "display_score", "scores", "editorial_scores", "gaming_scores", "scoring_version",
       # display_score: calibrated (app/scoring.py); scores / gaming_scores: AI quality (U4 / AS-1)
       "preview_url", "export_url", "export_res", "rendered", "edit", "segments"}   # render none / preview / full, export, edit
GOOD = {"titles": ["a", "b", "c"], "hook": "h", "hashtags": ["gta6"], "virality": {"hook": 70, "flow": 60, "value": 80, "trend": 50},
        "reason": "He never saw the cop coming."}


def submit(client, headers, upload_id, options, **kw):
    return client.post("/v1/clips", json={"upload_id": upload_id, "options": options}, headers=headers, **kw)


def cancel(client, headers, r):
    client.post(f"/v1/jobs/{r.json()['job_id']}/cancel", headers=headers)


def clips_of(client, headers, job_id):
    return client.get(f"/v1/jobs/{job_id}", headers=headers).json()["clips"]


# ---------- the options ----------
def test_the_duration_values_are_the_contracts_buckets():
    choices = typing.get_args(typing.get_args(ClipOptions.model_fields["duration"].annotation)[0])
    assert choices == tuple(BUCKETS)


def test_the_new_options_are_accepted_and_stored(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    r = submit(client, headers, up["upload_id"], {"duration": "0-30", "limit": 12, "range": {"start": 5, "end": 35.5},
                                                   "project_name": "  Friday   night stream "})
    assert r.status_code == 202, r.text
    opts = r.json()["options"]
    assert (opts["duration"], opts["limit"], opts["range"], opts["project_name"]) == \
        ("0-30", 12, {"start": 5.0, "end": 35.5}, "Friday night stream")
    with new_session() as db:
        job = db.get(Job, r.json()["job_id"])
        assert job.name == "Friday night stream" and job.options["duration"] == "0-30"
        PipelineOptions(**{k: v for k, v in job.options.items() if k != "tool"})      # what the worker builds
    cancel(client, headers, r)
    whole = submit(client, headers, up["upload_id"], {"duration": "30-60", "limit": None, "range": None, "project_name": " "})
    assert whole.status_code == 202 and whole.json()["options"]["project_name"] is None
    cancel(client, headers, whole)
    edge = submit(client, headers, up["upload_id"], {"range": {"start": 0, "end": up["duration_sec"] + 0.5}, "limit": 50})
    assert edge.status_code == 202, edge.text                                 # a rounded-up end is accepted (and clipped)
    cancel(client, headers, edge)


@pytest.mark.parametrize("options, code", [
    ({"duration": "45-60"}, "validation_error"), ({"duration": "0-30s"}, "validation_error"), ({"duration": 30}, "validation_error"),
    ({"limit": 0}, "validation_error"), ({"limit": -3}, "validation_error"), ({"limit": 51}, "validation_error"),
    ({"limit": "all"}, "validation_error"), ({"limit": 2.5}, "validation_error"),
    ({"range": {"start": 20, "end": 20}}, "validation_error"), ({"range": {"start": 30, "end": 10}}, "validation_error"),
    ({"range": {"start": -1, "end": 20}}, "validation_error"), ({"range": {"start": 5}}, "validation_error"),
    ({"range": {"start": 5, "end": 30, "unit": "ms"}}, "validation_error"), ({"range": [5, 30]}, "validation_error"),
    ({"range": {"start": 5, "end": 90}}, "bad_range"),                        # the video is 40 s long
    ({"range": {"start": 60, "end": 90}}, "bad_range"),
    ({"range": {"start": 5, "end": 12}}, "range_too_short"),
    ({"duration": "60-90"}, "too_short_for_duration"),                        # ... so it cannot hold a 60 s clip
    ({"duration": "30-60", "range": {"start": 5, "end": 30}}, "too_short_for_duration"),
    ({"project_name": "x" * 121}, "validation_error"), ({"project_name": 7}, "validation_error"),
])
def test_invalid_values_are_rejected_with_422_and_cost_nothing(client, user, video, options, code):
    headers, _ = user
    up = upload(client, headers, video)
    r = submit(client, headers, up["upload_id"], options)
    assert r.status_code == 422 and r.json()["error"]["code"] == code, r.text
    assert balance(client, headers) == 30 and client.get("/v1/jobs", headers=headers).json()["jobs"] == []


def test_a_request_without_the_new_options_is_stored_and_runs_as_before(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    r = submit(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10})
    opts = r.json()["options"]
    assert {k: opts[k] for k in ("duration", "limit", "range", "project_name")} == \
        {"duration": None, "limit": None, "range": None, "project_name": None}
    assert (opts["max_clips"], opts["clip_length"]) == (1, 10) and r.json()["credits_reserved"] == 1
    assert worker.run_once(transcriber) == "SUCCEEDED"
    with new_session() as db:
        assert db.get(Job, r.json()["job_id"]).name is None
    clip, = clips_of(client, headers, r.json()["job_id"])
    assert set(clip) == BEFORE | NEW                                          # every old field, plus the new ones
    assert 10 <= clip["end_sec"] - clip["start_sec"] <= 14 and clip["start_sec"] <= 24 <= clip["end_sec"] + 4      # the loud moment, 10 s (snapped to speech)
    assert (clip["index"], clip["rank"], clip["rank_of"]) == (1, 1, 1)


# ---------- money ----------
def test_what_a_job_reserves_with_the_new_options(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    extras = [{}, {"duration": "0-30"}, {"duration": "30-60", "limit": 50}, {"limit": 9}, {"range": {"start": 5, "end": 35}},
              {"duration": "0-30", "limit": 50, "range": {"start": 5, "end": 35}, "project_name": "all of it"}]

    def reserved(base: dict) -> list[int]:
        out = []
        for extra in extras:
            r = submit(client, headers, up["upload_id"], {**base, **extra})
            assert r.status_code == 202, r.text
            out.append(r.json()["credits_reserved"])
            cancel(client, headers, r)
        return out
    # First run on an upload: the video's length (40 s -> 1 credit), whatever the options.
    assert reserved({"max_clips": 2, "clip_length": 40}) == [1] * len(extras)
    with new_session() as db:
        db.get(Upload, up["upload_id"]).analyzed = True
        db.commit()
    # Already analysed, none of the new options: ceil(max_clips * clip_length / 60), as before. With one of them:
    # the most the request can render, never more than the video (40 s) or the range (30 s) holds: 1 credit here.
    # The rule itself is tested in test_rerun_charging.py.
    assert reserved({"max_clips": 2, "clip_length": 40}) == [2, 1, 1, 1, 1, 1]
    assert reserved({"max_clips": 3, "clip_length": 60}) == [3, 1, 1, 1, 1, 1]
    assert reserved({}) == [2, 1, 1, 1, 1, 1]                                 # the defaults: 3 clips of 30 s
    assert balance(client, headers) == 30                                     # every cancelled job was refunded in full


def test_a_job_whose_video_is_too_short_for_its_duration_fails_and_is_refunded(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    r = submit(client, headers, up["upload_id"], {"duration": "0-30"})
    assert r.status_code == 202 and balance(client, headers) == 29
    with new_session() as db:              # the API refuses this up front; this is the pipeline's own check
        job = db.get(Job, r.json()["job_id"])
        job.options = {**job.options, "duration": "60-90"}
        db.commit()
    assert worker.run_once(None) == "FAILED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert job["error"]["code"] == "too_short_for_duration" and job["credits_charged"] == 0 and job["clips"] == []
    assert balance(client, headers) == 30


# ---------- a job with the options, through the worker ----------
class KindAI:
    """Stands in for the AI client: rates every candidate and labels it."""
    def __init__(self, kind="fail"):
        self.kind, self.contexts = kind, []

    def clip_meta(self, transcript, context, thumb=None):
        self.contexts.append(context)
        return parse_meta({**GOOD, "kind": self.kind})


def test_a_job_with_a_bucket_a_limit_and_a_range(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    options = {"duration": "0-30", "limit": 2, "range": {"start": 8, "end": 36}, "project_name": "Heist night",
               "vertical": False, "punch_zoom": False}
    r = submit(client, headers, up["upload_id"], options)
    ai = KindAI()
    assert worker.run_once(transcriber, ai=ai) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert job["credits_charged"] == 1 and job["result"]["counts"]["analysed_sec"] == 28.0
    clips = job["clips"]
    assert 1 <= len(clips) <= 2
    for c in clips:
        assert 8000 <= c["start_ms"] < c["end_ms"] <= 36000 and 10000 <= c["end_ms"] - c["start_ms"] <= 30000
        assert (c["start_ms"], c["end_ms"]) == (round(c["start_sec"] * 1000), round(c["end_sec"] * 1000))
        assert c["kind"] == "fail" and c["why"] == c["reason"] == "He never saw the cop coming."
        assert c["virality_score"] == c["virality"]["score"] == 65 and c["tier"] == "strong"
    assert all(ctx["cut_range"] == (10, 28) for ctx in ai.contexts)           # the judge was told the bucket


def test_kind_score_and_why_are_null_when_the_ai_did_not_rate_the_clip(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    r = submit(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10})
    assert worker.run_once(transcriber) == "SUCCEEDED"                        # no AI
    clip, = clips_of(client, headers, r.json()["job_id"])
    assert (clip["kind"], clip["why"], clip["virality_score"]) == (None, None, None)

    def shown(meta, column=None):
        with new_session() as db:
            row = db.get(Clip, clip["id"])
            row.meta, row.kind = meta, column
            db.commit()
        c, = clips_of(client, headers, r.json()["job_id"])
        return c["kind"], c["why"], c["virality_score"]
    assert shown({"virality": {"score": 97}, "source": "signals"}) == (None, None, None)       # loudness is not a rating
    assert shown({"virality": {"score": 72}, "reason": "Great line.", "kind": "funny", "source": "ai"}) == ("funny", "Great line.", 72)
    assert shown({"virality": {"score": 72}, "reason": "", "kind": "boss fight", "source": "ai"}) == (None, None, 72)
    assert shown({"virality": {"score": 72}, "kind": "funny", "source": "ai"}, column="clutch") == ("clutch", None, 72)


# ---------- rank_index and timeline_index ----------
def test_rank_index_and_timeline_index_everywhere_and_after_a_clip_is_deleted(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job_a = submit(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10}).json()["job_id"]
    assert worker.run_once(transcriber) == "SUCCEEDED"
    job_b = submit(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10}).json()["job_id"]
    assert worker.run_once(transcriber) == "SUCCEEDED"
    with new_session() as db:              # job A as a three-clip run: the latest moment is the best, the earliest the worst
        mid = db.query(Clip).filter(Clip.job_id == job_a).one()
        mid.idx, mid.start_sec, mid.end_sec, mid.score = 2, 15.0, 25.0, 0.5
        ids = {"mid": mid.id}
        for name, idx, start, score in (("early", 1, 2.0, 0.1), ("late", 3, 28.0, 0.9)):
            ids[name] = new_id("clip")
            db.add(Clip(id=ids[name], job_id=job_a, idx=idx, start_sec=start, end_sec=start + 10, score=score,
                        signals={}, features={}, video_key=mid.video_key))
        db.commit()

    def views():
        job = {c["id"]: c for c in clips_of(client, headers, job_a)}
        project = {c["id"]: c for c in client.get(f"/v1/projects/{up['upload_id']}", headers=headers).json()["clips"]}
        library = {c["id"]: c for c in client.get("/v1/clips", headers=headers).json()["clips"]}
        return job, project, library

    def numbers(view, name):
        c = view[ids[name]]
        return c["rank_index"], c["rank"], c["rank_of"], c["timeline_index"], c["index"]
    for view in views():                                                      # the same answer in all three
        assert numbers(view, "late") == (0, 1, 3, 3, 3)                       # best: rank_index 0; last in the video
        assert numbers(view, "mid") == (1, 2, 3, 2, 2)
        assert numbers(view, "early") == (2, 3, 3, 1, 1)                      # worst; first in the video: timeline_index 1
    _job, project, library = views()
    other = next(c for c in project.values() if c["job_id"] == job_b)
    assert (other["rank_index"], other["rank"], other["timeline_index"], other["index"]) == (0, 1, 1, 1)     # per run
    assert all(c["rank_index"] == c["rank"] - 1 for c in library.values())

    with new_session() as db:                                                 # the earliest clip is deleted
        db.get(Clip, ids["early"]).deleted_at = utcnow()
        db.commit()
    for view in views():
        assert ids["early"] not in view
        assert numbers(view, "late") == (0, 1, 2, 2, 3)                       # both positions close the gap;
        assert numbers(view, "mid") == (1, 2, 2, 1, 2)                        # `index` is the stored number and stays
    with new_session() as db:                                                 # then the best one
        db.get(Clip, ids["late"]).deleted_at = utcnow()
        db.commit()
    for view in views():
        assert numbers(view, "mid") == (0, 1, 1, 1, 2)
    edited = client.patch(f"/v1/clips/{ids['mid']}", json={"title": "Mine"}, headers=headers).json()
    assert (edited["rank_index"], edited["timeline_index"], edited["title"]) == (0, 1, "Mine")


# ---------- the judge: kind, and the cut range of a bucket ----------
def test_the_judge_is_asked_for_a_kind_and_it_is_sanitised():
    schema = TOOL["input_schema"]
    assert schema["properties"]["kind"]["enum"] == list(KINDS) and "kind" in schema["required"]
    assert all(k in SYSTEM for k in KINDS)
    assert parse_meta({**GOOD, "kind": "clutch"})["kind"] == "clutch"
    assert parse_meta({**GOOD, "kind": " Fail "})["kind"] == "fail"
    for junk in ("boss fight", "", None, 3, ["funny"]):
        assert parse_meta({**GOOD, "kind": junk})["kind"] is None
    assert parse_meta(GOOD)["kind"] is None and parse_meta(GOOD)["reason"] == GOOD["reason"]       # older replies still parse


def ai_with(reply, seen):
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply)
    return ClaudeAI("k", "claude-haiku-5-5", httpx.Client(transport=httpx.MockTransport(handler)))


def test_the_judge_is_told_the_buckets_range_and_gets_more_transcript_for_long_clips():
    assert "15 to 60 second" in SYSTEM and system_for(None) == SYSTEM and system_for((0, 0)) == SYSTEM
    assert "180 to 298 second" in system_for((180, 298)) and "15 to 60" not in system_for((180, 298))
    reply = {"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "clip_meta",
                                                     "input": {**GOOD, "kind": "story", "cut": {"start": 4, "end": 250, "peak": 40}}}]}
    lines = [(float(k), "word " * 12) for k in range(0, 300, 2)]              # 5 minutes of talk: about 10,000 characters
    seen = []
    ai = ai_with(reply, seen)
    ctx = {"length": 240, "signals": {"audio": 1.0}, "lines": lines, "window": (30.0, 270.0)}
    meta = ai.clip_meta("", {**ctx, "cut_range": (180, 298)})
    plain = ai.clip_meta("", ctx)
    assert meta["kind"] == "story" and meta["trim"] == {"start": 4.0, "end": 250.0, "peak": 40.0}
    bucket, before = (s["messages"][0]["content"][-1]["text"] for s in seen)
    assert "180 to 298 second" in seen[0]["system"] and "The cut must be 180 to 298 seconds long." in bucket
    assert seen[1]["system"] == SYSTEM and "The cut must be" not in before and plain["kind"] == "story"
    said = [text.split("Transcript with time marks (seconds):\n")[1] for text in (bucket, before)]
    assert len(said[1]) == TRANSCRIPT_CHARS and len(said[0]) == 25 * 298      # TRANSCRIPT_CHARS at least; 25 per second of the longest cut
    short = ai.clip_meta("", {**ctx, "cut_range": (10, 28)})
    assert short is not None and len(seen[2]["messages"][0]["content"][-1]["text"].split("(seconds):\n")[1]) == TRANSCRIPT_CHARS
