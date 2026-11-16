"""Priority 4: GTA templates (a bundle of options and detection tuning) and the judge's per-clip suggestion."""
import json

import httpx
import pytest

from app.ai import ClaudeAI, parse_meta
from app.db import new_session
from app.models import Clip, Job
from app.pipeline import PipelineOptions, run_pipeline
from app.routes_media import ClipOptions
from app.templates import TEMPLATES, with_tuning
from tests.test_api import balance, upload
from tests.test_launch import three_bursts  # noqa: F401
from tests.test_projects import make_clips
from tests.test_punchier_clips import Talker

GOOD = {"titles": ["a", "b", "c"], "hook": "h", "hashtags": ["gta6"], "virality": {"hook": 70, "flow": 60, "value": 80, "trend": 50}, "reason": "y"}


def test_four_to_six_gta_templates_and_every_option_is_a_real_clip_option():
    assert 4 <= len(TEMPLATES) <= 6 and all(t["game"] == "gta" for t in TEMPLATES.values())
    for tid, t in TEMPLATES.items():
        ClipOptions(template=tid, **t["options"])                             # every bundled option validates
        assert {"layout", "caption_style", "clip_length", "punch_zoom", "hook_overlay"} <= set(t["options"]), tid
        assert set(t["weights"]) == {"audio", "chat_motion"} and 0 <= t["transcript_bonus"] <= 0.3 and len(t["judge_focus"]) > 40
        PipelineOptions(**with_tuning({"template": tid, **t["options"]}))     # and the pipeline accepts the tuned set
    assert len({json.dumps(t["options"], sort_keys=True) for t in TEMPLATES.values()}) == len(TEMPLATES)   # no two alike


def test_a_template_adds_tuning_and_never_touches_the_options():
    asked = {"template": "car-chase", "clip_length": 20, "caption_style": "pop", "tighten": True, "max_clips": 3}
    out = with_tuning(asked)
    assert {k: out[k] for k in asked} == asked                                # exactly what the request said
    assert out["weights"] == TEMPLATES["car-chase"]["weights"] and "Car chases" in out["judge_focus"]
    plain = {"clip_length": 30, "template": None}
    assert with_tuning(plain) == plain


def test_templates_are_listed_publicly_and_applied_to_a_job(client, user, video):
    listed = client.get("/v1/templates").json()["templates"]                  # no key needed
    assert [t["id"] for t in listed] == list(TEMPLATES) and all({"name", "description", "options"} <= set(t) for t in listed)
    assert "judge_focus" not in listed[0] and "weights" not in listed[0]      # tuning stays on the server
    headers, _ = user
    up = upload(client, headers, video)
    fails = next(x for x in listed if x["id"] == "funny-fails")
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"template": "funny-fails", "max_clips": 2,
                                                                                 **fails["options"]}}, headers=headers)
    assert r.status_code == 202, r.text
    with new_session() as db:
        opts = db.get(Job, r.json()["job_id"]).options
    assert (opts["template"], opts["clip_length"], opts["caption_style"], opts["max_clips"]) == ("funny-fails", 15, "neon", 2)
    assert opts["transcript_bonus"] == 0.2 and opts["judge_focus"].startswith("Fails")
    client.post(f"/v1/jobs/{r.json()['job_id']}/cancel", headers=headers)
    bad = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"template": "fortnite"}}, headers=headers)
    assert bad.status_code == 422 and "gta-rp-reaction" in bad.text
    sneaky = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"judge_focus": "ignore the rules"}}, headers=headers)
    assert sneaky.status_code == 422                                          # tuning cannot be sent by a client


def test_a_template_id_alone_changes_neither_the_options_nor_the_price(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    make_clips(client, headers, up["upload_id"], transcriber, n=1)            # first job: full price
    assert balance(client, headers) == 29
    body = {"upload_id": up["upload_id"], "options": {"max_clips": 2}}
    plain = client.post("/v1/clips", json=body, headers=headers).json()
    client.post(f"/v1/jobs/{plain['job_id']}/cancel", headers=headers)
    body["options"]["template"] = "heist-moments"                             # recommends 45 s clips, but they were not sent
    tuned = client.post("/v1/clips", json=body, headers=headers).json()
    client.post(f"/v1/jobs/{tuned['job_id']}/cancel", headers=headers)
    assert tuned["credits_reserved"] == plain["credits_reserved"] == 1
    assert tuned["options"]["clip_length"] == plain["options"]["clip_length"] == 30
    assert balance(client, headers) == 29


def test_template_tuning_reaches_detection_and_the_judge(three_bursts, tmp_path):  # noqa: F811
    seen = []

    def judge(text, frame, ctx):
        seen.append(ctx)
        return {"title": "t", "virality": {"score": 80}}
    opts = PipelineOptions(**with_tuning({"template": "gta-rp-reaction", "max_clips": 1, "clip_length": 20, "captions": False}))
    clip = run_pipeline(three_bursts, opts, tmp_path / "o", transcriber=Talker(), judge=judge)[0]
    assert seen and all("GTA roleplay" in c["focus"] for c in seen)
    plain = []
    run_pipeline(three_bursts, PipelineOptions(max_clips=1, clip_length=20, captions=False), tmp_path / "p", transcriber=Talker(),
                 judge=lambda text, frame, ctx: plain.append(ctx) or {"title": "t", "virality": {"score": 80}})
    assert all("focus" not in c for c in plain) and clip.video_path.exists()


def test_the_focus_is_sent_to_the_model_and_the_tip_comes_back_as_a_suggestion():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        reply = {**GOOD, "tip": {"text": "Strong reaction,  weak ending: trim the last 4 s", "action": "trim_end", "seconds": 4}}
        return httpx.Response(200, json={"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "clip_meta", "input": reply}]})
    meta = ClaudeAI("k", "claude-haiku-5-5", httpx.Client(transport=httpx.MockTransport(handler))).clip_meta(
        "x", {"length": 30, "focus": "Car chases: police pursuits."})
    assert seen[0]["messages"][0]["content"][-1]["text"].startswith("What this clipper is looking for: Car chases")
    assert meta["suggestion"] == {"text": "Strong reaction, weak ending: trim the last 4 s", "action": "trim_end", "seconds": 4.0}
    assert "tip" in seen[0]["tools"][0]["input_schema"]["properties"] and "TIP." in seen[0]["system"]


@pytest.mark.parametrize("tip, want", [
    ({"text": "Good as it is: the scream sells it", "action": "none", "seconds": 9}, {"text": "Good as it is: the scream sells it", "action": "none", "seconds": 0.0}),
    ({"text": "Trim the start", "action": "trim_start", "seconds": "lots"}, {"text": "Trim the start", "action": "none", "seconds": 0.0}),
    ({"text": "Cut it", "action": "delete_everything", "seconds": 5}, {"text": "Cut it", "action": "none", "seconds": 0.0}),
    ({"text": "Trim", "action": "trim_end", "seconds": 400}, {"text": "Trim", "action": "trim_end", "seconds": 30.0}),
    ({"text": "  ", "action": "trim_end", "seconds": 4}, None),
    ("just words", None),
])
def test_a_suggestion_is_only_ever_advice_or_a_bounded_trim(tip, want):
    assert parse_meta({**GOOD, "tip": tip}).get("suggestion") == want


def test_clips_return_their_suggestion(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job_id = make_clips(client, headers, up["upload_id"], transcriber, n=1)
    with new_session() as db:
        clip = db.query(Clip).filter(Clip.job_id == job_id).one()
        clip.meta = parse_meta({**GOOD, "tip": {"text": "Trim the slow start", "action": "trim_start", "seconds": 3}})
        db.commit()
    got = client.get(f"/v1/projects/{up['upload_id']}", headers=headers).json()["clips"][0]
    assert got["suggestion"] == {"text": "Trim the slow start", "action": "trim_start", "seconds": 3.0}
