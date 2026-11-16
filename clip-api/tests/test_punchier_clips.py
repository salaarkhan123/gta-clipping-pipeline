"""Priority 2: the judge chooses the cut and the peak, dead air is removed, and the toggles switch it all off."""
import json
import subprocess

import httpx
import pytest

from app.ai import ClaudeAI, parse_meta
from app.pipeline import PipelineOptions, probe, run_pipeline
from app.pipeline.transcribe import Transcript
from tests.test_api import upload
from tests.test_launch import three_bursts  # noqa: F401  (fixture: 60 s, loud at 10-13, 30-33 and 48-51)

GOOD = {"title": "Clean getaway", "description": "d", "hashtags": ["gta6"],
        "virality": {"hook": 70, "flow": 60, "value": 80, "trend": 50}, "reason": "y"}


class Talker:
    """A line every 2 s for the whole excerpt, so the judge gets time marks and the edges have speech to snap to."""
    def transcribe(self, wav) -> Transcript:
        t = Transcript()
        for k in range(0, 60, 2):
            t.words += [(float(k), k + 0.4, "oh"), (k + 0.4, k + 0.9, "no")]
            t.segments.append((float(k), k + 0.9, "oh no"))
        return t


def judged(three_bursts, tmp_path, cut, **opts):  # noqa: F811
    seen = []

    def judge(text, frame, ctx):
        seen.append(ctx)
        a, b = ctx["window"]
        return {"title": "t", "virality": {"score": 80}, "trim": cut(a, b)} if cut else {"title": "t", "virality": {"score": 80}}
    res = run_pipeline(three_bursts, PipelineOptions(max_clips=1, clip_length=20, captions=True, tighten=False,
                                                     punch_zoom=False, **opts), tmp_path / "o", transcriber=Talker(), judge=judge)
    return res[0], seen


def test_the_judge_gets_time_marks_and_its_cut_and_peak_are_used(three_bursts, tmp_path):  # noqa: F811
    clip, seen = judged(three_bursts, tmp_path, lambda a, b: {"start": a + 2, "end": a + 18, "peak": a + 12})
    assert seen[0]["lines"][0] == (0.0, "oh no") and seen[0]["window"][1] - seen[0]["window"][0] == pytest.approx(20, abs=0.1)
    lo, hi = clip.features["nominated"]
    assert clip.start == pytest.approx(lo + 2, abs=1.0) and 15 <= clip.end - clip.start <= 45     # the judge's cut, snapped to speech
    edit = clip.features["edit"]
    assert edit["flash_forward"] is True and len(edit["segments"]) == 2
    peak = edit["segments"][0]
    assert peak[0] == pytest.approx(lo + 12, abs=1.0) and peak[1] - peak[0] == pytest.approx(1.5)   # 1.5 s of the peak first
    assert probe(clip.video_path).duration == pytest.approx((clip.end - clip.start) + 1.5, abs=0.2)
    assert "trim" not in clip.meta                                              # consumed, not stored as copy


@pytest.mark.parametrize("cut", [
    lambda a, b: {"start": a, "end": a + 6, "peak": a + 3},          # 6 s: too short
    lambda a, b: {"start": a - 40, "end": a - 20, "peak": a - 30},   # a different moment
    lambda a, b: {"start": "soon", "end": None, "peak": 1},          # not numbers
    None,                                                            # no cut at all
])
def test_a_bad_or_missing_cut_keeps_the_nominated_window(three_bursts, tmp_path, cut):  # noqa: F811
    clip, _ = judged(three_bursts, tmp_path, cut)
    edit = clip.features["edit"]
    assert "nominated" not in clip.features and edit["flash_forward"] is False
    assert edit["segments"] == [[clip.start, clip.end]] or edit["segments"] == [(clip.start, clip.end)]


def test_flash_forward_can_be_switched_off(three_bursts, tmp_path):  # noqa: F811
    clip, _ = judged(three_bursts, tmp_path, lambda a, b: {"start": a + 2, "end": a + 18, "peak": a + 12}, flash_forward=False)
    assert clip.features["edit"]["flash_forward"] is False
    assert probe(clip.video_path).duration == pytest.approx(clip.end - clip.start, abs=0.2)


@pytest.fixture(scope="module")
def gappy(tmp_path_factory):
    """40 s of talk-level tone with 3 s of dead air at 13-16 and a loud spike at 20-24, and a moving picture."""
    out = tmp_path_factory.mktemp("gap") / "gappy.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15:duration=40",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
                    "-af", "volume='if(between(t,13,16),0,if(between(t,20,24),4,1.5))':eval=frame",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


class UmTalker:
    def transcribe(self, wav) -> Transcript:      # clip-relative: the excerpt starts 4 s before the clip
        return Transcript(words=[(5.0, 5.4, "watch"), (6.0, 6.3, "um"), (6.5, 7.0, "this"), (20.0, 20.5, "wow")],
                          segments=[(5.0, 7.0, "watch um this"), (20.0, 20.5, "wow")])


def test_dead_air_and_fillers_are_cut_and_captions_follow(gappy, tmp_path):
    on = run_pipeline(gappy, PipelineOptions(max_clips=1, clip_length=20, punch_zoom=False), tmp_path / "on", transcriber=UmTalker())[0]
    off = run_pipeline(gappy, PipelineOptions(max_clips=1, clip_length=20, punch_zoom=False, tighten=False), tmp_path / "off",
                       transcriber=UmTalker())[0]
    assert (on.start, on.end) == (off.start, off.end) and on.start < 13 and on.end > 21      # same moment, silence inside it
    removed = on.features["edit"]["removed_sec"]
    assert 2.6 <= removed <= 3.3 and off.features["edit"]["removed_sec"] == 0                 # 3 s silence minus the kept pause, plus "um"
    assert probe(on.video_path).duration == pytest.approx(probe(off.video_path).duration - removed, abs=0.25)
    words_on = [w["text"] for w in json.loads(on.captions_path.read_text())["words"]]
    words_off = json.loads(off.captions_path.read_text())["words"]
    assert "um" not in words_on and [w["text"] for w in words_off] == ["watch", "um", "this", "wow"]
    wow_on = next(w for w in json.loads(on.captions_path.read_text())["words"] if w["text"] == "wow")
    wow_off = next(w for w in words_off if w["text"] == "wow")
    assert wow_off["start"] - wow_on["start"] == pytest.approx(removed, abs=0.4)             # captions moved with the cut
    assert all(w["end"] <= probe(on.video_path).duration + 0.1 for w in json.loads(on.captions_path.read_text())["words"])


def test_punch_zoom_marks_the_loud_spike_and_can_be_switched_off(gappy, tmp_path):
    on = run_pipeline(gappy, PipelineOptions(max_clips=1, clip_length=20, tighten=False), tmp_path / "z", transcriber=None)[0]
    zooms = on.features["edit"]["zoom_at"]
    assert 1 <= len(zooms) <= 3 and all(20 - on.start <= z <= 25 - on.start for z in zooms)   # inside the 20-24 s spike
    off = run_pipeline(gappy, PipelineOptions(max_clips=1, clip_length=20, tighten=False, punch_zoom=False), tmp_path / "nz")[0]
    assert off.features["edit"]["zoom_at"] == []
    flat = run_pipeline(gappy, PipelineOptions(max_clips=1, clip_length=20, tighten=False, vertical=False), tmp_path / "h")[0]
    assert flat.features["edit"]["zoom_at"] == []                                             # only on reframed clips


# ---------- the AI call ----------
def ai_with(reply, seen):
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply)
    return ClaudeAI("k", "claude-haiku-5-5", httpx.Client(transport=httpx.MockTransport(handler)))


def test_timed_lines_are_sent_and_the_cut_comes_back_as_trim():
    seen = []
    reply = {"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "clip_meta",
                                                     "input": {**GOOD, "cut": {"start": 6, "end": 31.5, "peak": 18}}}]}
    meta = ai_with(reply, seen).clip_meta("ignored when lines are given", {"length": 30, "signals": {"audio": 1.0},
                                          "lines": [(0.0, "wait"), (12.4, "NO WAY")], "window": (8.0, 38.0)})
    text = seen[0]["messages"][0]["content"][-1]["text"]
    assert "[12.4] NO WAY" in text and "between 8.0 and 38.0" in text and "ignored when lines" not in text
    assert meta["trim"] == {"start": 6.0, "end": 31.5, "peak": 18.0} and meta["title"] == "Clean getaway"
    assert "cut" in seen[0]["tools"][0]["input_schema"]["properties"] and "15 to 45 second" in seen[0]["system"]


def test_without_lines_the_request_and_reply_are_as_before():
    seen = []
    reply = {"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "clip_meta", "input": GOOD}]}
    meta = ai_with(reply, seen).clip_meta("plain words", {"length": 30})
    assert "Transcript of the clip:\nplain words" in seen[0]["messages"][0]["content"][-1]["text"] and "trim" not in meta
    assert "trim" not in parse_meta({**GOOD, "cut": {"start": "x", "end": 2, "peak": 1}})     # junk numbers are dropped


def test_api_accepts_the_three_toggles_and_stores_them(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"tighten": False, "punch_zoom": False,
                                                                                 "flash_forward": False}}, headers=headers)
    assert r.status_code == 202 and r.json()["options"]["tighten"] is False and r.json()["options"]["flash_forward"] is False
    client.post(f"/v1/jobs/{r.json()['job_id']}/cancel", headers=headers)
    bad = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"punch_zoom": "lots"}}, headers=headers)
    assert bad.status_code == 422
    default = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers)
    assert default.json()["options"]["tighten"] is True and default.json()["options"]["punch_zoom"] is True
    client.post(f"/v1/jobs/{default.json()['job_id']}/cancel", headers=headers)
