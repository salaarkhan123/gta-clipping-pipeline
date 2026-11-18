"""U4: judge v2 rates five sub-scores, cuts 15-60 s story clips on whole sentences, hears the signal timeline, and
a long video asked for every moment gets 30-50 clips when it has them."""
import json
from pathlib import Path

import httpx
import numpy as np
import pytest

import app.pipeline as P
from app.ai import SCORES, SCORING_VERSION, SYSTEM, TOOL, ClaudeAI, parse_meta, system_for
from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline.transcribe import Transcript, sentences, snap_to_sentences
from tests.test_launch import three_bursts  # noqa: F401  (fixture)
from tests.test_punchier_clips import Talker

V2 = {"titles": ["a", "b", "c"], "hook": "h", "hashtags": ["gta"], "reason": "r", "kind": "story",
      "virality": {"hook": 80, "payoff": 90, "clarity": 70, "emotion": 60, "pacing": 50}}


# ---------- the judge's answer ----------

def test_five_sub_scores_make_the_score_and_are_kept():
    meta = parse_meta(V2)
    assert meta["scores"] == {"hook": 80, "payoff": 90, "clarity": 70, "emotion": 60, "pacing": 50}
    assert meta["virality"] == {"score": 70, **meta["scores"]}                  # the plain mean
    assert TOOL["input_schema"]["properties"]["virality"]["required"] == list(SCORES)


def test_an_answer_in_the_older_four_part_shape_still_reads():
    meta = parse_meta({**V2, "virality": {"hook": 90, "flow": 80, "value": 70, "trend": 60}})
    assert meta["virality"]["score"] == 75 and "scores" not in meta


def test_the_prompt_asks_for_whole_sentences_and_story_cuts_up_to_60_s():
    assert "15 to 60 second" in SYSTEM and "whole sentences" in SYSTEM and "payoff =" in SYSTEM
    assert "clarity =" in SYSTEM and "emotion =" in SYSTEM and "pacing =" in SYSTEM
    assert "30 to 90 second" in system_for((30, 90)) and "15 to 60" not in system_for((30, 90))


def test_a_60_s_cut_is_taken_and_a_longer_one_is_not():
    c = P._Candidate(start=100.0, end=130.0, base=1.0, signals={}, features={}, offset=85.0)
    P._apply_trim(c, {"start": 12.0, "end": 73.0, "peak": 20.0}, 1000.0)          # 61 s
    assert (c.start, c.end) == (100.0, 130.0)
    P._apply_trim(c, {"start": 12.0, "end": 72.0, "peak": 20.0}, 1000.0)          # 60 s
    assert (c.start, c.end) == (97.0, 157.0)


# ---------- sentences ----------

WORDS = [(0.0, 0.4, "So"), (0.4, 0.8, "we"), (0.8, 1.2, "went."), (2.0, 2.3, "Then"), (2.3, 2.9, "boom!"),
         (5.0, 5.4, "no"), (5.4, 5.8, "way"), (7.0, 7.5, "okay.")]


def test_sentences_end_on_punctuation_or_a_pause():
    assert sentences(WORDS) == [(0.0, 1.2), (2.0, 2.9), (5.0, 5.8), (7.0, 7.5)]
    assert sentences([]) == []


def test_a_cut_moves_out_to_the_whole_sentences_it_cuts_into():
    assert snap_to_sentences(0.6, 5.5, WORDS, 0.0, 100.0, 1.0, 60.0) == (0.0, 5.8 + 0.25)
    assert snap_to_sentences(2.1, 7.2, WORDS, 0.0, 100.0, 1.0, 60.0) == (2.0 - 0.15, 7.5 + 0.25)
    assert snap_to_sentences(0.6, 5.5, WORDS, 0.0, 100.0, 1.0, 3.0) is None        # would be too long
    assert snap_to_sentences(0.6, 5.5, [], 0.0, 100.0, 1.0, 60.0) is None          # no word timings


def test_the_pipeline_snaps_on_sentences_and_falls_back_to_segments():
    c = P._Candidate(start=10.6, end=15.5, base=1.0, signals={}, features={}, offset=10.0,
                     transcript=Transcript(words=WORDS, segments=[(0.0, 2.9, "So we went. Then boom!"),
                                                                  (5.0, 7.5, "no way okay.")]))
    P._snap(c, 100.0, (1.0, 60.0))
    assert (c.start, c.end) == (pytest.approx(9.85), pytest.approx(16.05))       # sentence edges, 0.15 s lead-in
    c = P._Candidate(start=10.6, end=15.5, base=1.0, signals={}, features={}, offset=10.0,
                     transcript=Transcript(segments=[(0.0, 2.9, "a"), (5.0, 7.5, "b")]))
    P._snap(c, 100.0, (1.0, 60.0))
    assert (c.start, c.end) == (pytest.approx(9.85), pytest.approx(17.75))       # segment edges, as before


# ---------- the signal timeline ----------

def test_the_timeline_names_the_strongest_seconds_of_each_signal_in_the_window():
    audio = np.zeros(200)
    audio[[120, 121, 140, 150, 151, 152]] = [0.5, 0.6, 2.0, 1.0, 0.9, 0.95]
    audio[10] = 4.0                                                               # the video's peak, outside
    got = P._timeline({"audio": audio, "chat_motion": np.zeros(200)}, 110.0, 160.0, base=0)
    assert got == {"audio": [(11.0, 0.15), (30.0, 0.5), (40.0, 0.25)]}            # 3 s apart, seconds from 110
    assert P._timeline({"audio": audio}, 300.0, 400.0, base=0) == {}


def ai_seeing(seen):
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "clip_meta", "input": V2}]})
    return ClaudeAI("k", "claude-haiku-5-5", httpx.Client(transport=httpx.MockTransport(handler)))


def test_the_judge_reads_the_timeline_and_nothing_changes_without_one():
    seen = []
    ai = ai_seeing(seen)
    ai.clip_meta("x", {"length": 30, "timeline": {"audio": [(12.0, 0.9), (30.5, 0.4)]}})
    ai.clip_meta("x", {"length": 30})
    with_tl, without = (b["messages"][0]["content"][-1]["text"] for b in seen)
    assert "Signal peaks (time mark, strength 0-1):\naudio: [12.0] 0.90, [30.5] 0.40\n" in with_tl
    assert "Signal peaks" not in without


def test_the_pipeline_sends_the_timeline_to_the_judge(three_bursts, tmp_path):  # noqa: F811
    seen = []

    def judge(text, frame, ctx):
        seen.append(ctx)
        return {"title": "t", "virality": {"score": 70}}
    run_pipeline(three_bursts, PipelineOptions(max_clips=1, clip_length=10, tighten=False), tmp_path / "o",
                 transcriber=Talker(), judge=judge)
    assert seen and all("audio" in ctx["timeline"] for ctx in seen)
    a, b = seen[0]["window"]
    assert any(a - 3 <= t <= b + P.JUDGE_PAD for t, _v in seen[0]["timeline"]["audio"])


# ---------- automatic discovery: a quality floor, never a quota ----------

def run_judge(out_dir, scores, **kw):
    """_judge over one 30 s candidate every 100 s, the i-th rated scores[i] (no video: no frames)."""
    cands = [P._Candidate(start=100.0 * i, end=100.0 * i + 30, base=1.0, signals={"i": i}, features={})
             for i in range(len(scores))]

    def judge(text, frame, ctx):
        return {"title": "t", "virality": {"score": scores[ctx["signals"]["i"]]}}
    return P._judge(cands, judge, out_dir / "missing.mp4", out_dir, lambda *a: None, None, **kw)


def test_every_moment_means_every_moment_over_the_quality_floor_and_nothing_to_fill_a_quota(tmp_path):
    scores = [80] * 10 + [45] * 5 + [30] * 15 + [10] * 15         # 10 strong, 5 ordinary, 15 weak, 15 junk
    out = run_judge(tmp_path, scores, every=True)
    assert len(out) == 15 and all(c.features["judge_score"] >= P.QUALITY_FLOOR for c in out)
    assert P.QUALITY_FLOOR == 40                                    # stated in the PR; CLIP_QUALITY_FLOOR sets it
    assert len(run_judge(tmp_path, scores, every=True, quality_floor=60)) == 10
    assert run_judge(tmp_path, [30] * 40, every=True) == []          # no clip rather than filler


def test_a_count_asked_for_still_fills_it_from_the_best_above_the_junk_floor(tmp_path):
    out = run_judge(tmp_path, [80] * 2 + [30] * 5 + [10] * 3)       # not automatic: as before
    assert len(out) == 7 and min(c.features["judge_score"] for c in out) >= P.JUDGE_FLOOR


def test_no_moment_over_the_floor_fails_the_job_and_refunds_it(client, user, video, monkeypatch):
    from app import worker
    from tests.test_api import balance, upload
    from tests.test_launch import FakeAI

    class Weak(FakeAI):
        def clip_meta(self, transcript, context, thumb=None):
            meta = super().clip_meta(transcript, context, thumb)
            return {**meta, "virality": {"score": 30}}
    headers, _ = user
    up = upload(client, headers, video)
    before = balance(client, headers)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"duration": "0-30"}}, headers=headers)
    assert r.status_code == 202, r.text
    assert worker.run_once(Talker(), ai=Weak()) == "FAILED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert job["error"]["code"] == "no_moments" and job["clips"] == [] and balance(client, headers) == before


def test_the_worker_hands_over_the_configured_floor(monkeypatch):
    from app.config import get_settings
    assert get_settings().clip_quality_floor == P.QUALITY_FLOOR
    assert PipelineOptions().quality_floor == P.QUALITY_FLOOR


def test_the_clip_object_carries_the_five_scores():
    from app.routes_media import clip_json
    from app.models import Clip

    class Storage:
        def url(self, key):
            return f"/files/{key}"
    c = Clip(id="clip_x", job_id="job_x", idx=1, start_sec=1.0, end_sec=31.0, score=0.8, signals={}, features={},
             meta=parse_meta(V2), video_key="v.mp4", thumb_key=None, captions_key=None)
    out = clip_json(c, Storage())
    assert out["scores"] == {"hook": 80, "payoff": 90, "clarity": 70, "emotion": 60, "pacing": 50}
    assert out["virality"]["score"] == 70 and out["virality_score"] == 70 and out["scoring_version"] == SCORING_VERSION
