"""Priority 3: three GTA-style title options, one on-screen hook, the hook overlay, and picking a title."""
import json
import subprocess

import httpx
import numpy as np

from app.ai import SYSTEM, TOOL, ClaudeAI, parse_meta
from app.db import new_session
from app.models import Clip
from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline.captions import HOOK_SECONDS, build_ass
from tests.test_api import upload
from tests.test_projects import make_clips, new_user
from tests.test_punchier_clips import Talker
from tests.test_launch import three_bursts  # noqa: F401

REPLY = {"titles": ["The cop never saw the ramp", '"WHY is he FLYING"', "the cop never saw the ramp", "Did he stick the landing?"],
         "hook": "wait for the cop car... #gta {\\an8}", "description": "d", "hashtags": ["gta6"],
         "virality": {"hook": 70, "flow": 60, "value": 80, "trend": 50}, "reason": "y"}


def test_three_distinct_titles_and_a_clean_hook_come_back():
    meta = parse_meta(REPLY)
    assert meta["titles"] == ["The cop never saw the ramp", "WHY is he FLYING", "Did he stick the landing?"]   # deduped, unquoted
    assert meta["title"] == meta["titles"][0]
    assert meta["hook"] == "wait for the cop car... gta" and len(meta["hook"].split()) <= 6      # no markup, no hashtag sign
    assert parse_meta({**REPLY, "hook": "one two three four five six seven eight"})["hook"] == "one two three four five six"
    old = parse_meta({"title": "Clean getaway", "hashtags": [], "virality": {}, "reason": ""})   # the older reply shape
    assert old["titles"] == ["Clean getaway"] and old["hook"] is None
    assert parse_meta({"titles": [], "hashtags": []}) is None


def test_the_prompt_asks_for_gta_style_and_forbids_templates_and_misleading_titles():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "clip_meta", "input": REPLY}]})
    meta = ClaudeAI("k", "claude-haiku-5-5", httpx.Client(transport=httpx.MockTransport(handler))).clip_meta("x", {"length": 30})
    assert len(meta["titles"]) == 3
    schema = seen[0]["tools"][0]["input_schema"]
    assert schema["properties"]["titles"]["minItems"] == schema["properties"]["titles"]["maxItems"] == 3
    assert {"titles", "hook"} <= set(schema["required"]) and TOOL["name"] == seen[0]["tool_choice"]["name"]
    for rule in ("GTA RP and GTA Online Shorts", "Streamer does X in GTA", "must not promise anything the clip does not show",
                 "6 words at most", "Do not invent events"):
        assert rule in SYSTEM, rule


def test_hook_is_one_boxed_line_for_the_first_seconds_even_without_captions(tmp_path):
    build_ass([], tmp_path / "h.ass", True, 580, "DejaVu Sans", hook="he did not see that", hook_top=760)
    text = (tmp_path / "h.ass").read_text()
    assert "Style: Hook," in text and ",8,90,90,760,1" in text                       # top-centred, 760 px down
    events = [ln for ln in text.splitlines() if ln.startswith("Dialogue:")]
    assert len(events) == 1 and events[0].startswith("Dialogue: 1,0:00:00.00,0:00:02.50,Hook") and events[0].endswith("HE DID NOT SEE THAT")
    assert HOOK_SECONDS == 2.5
    build_ass([(0.0, 0.5, "hi")], tmp_path / "n.ass", True, 580, "DejaVu Sans")
    assert "Dialogue: 1," not in (tmp_path / "n.ass").read_text()                    # no hook asked for: none drawn


def lime(video, t) -> float:
    """Share of the gameplay area (below the caption seam) that is the hook box's lime."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-i", str(video), "-frames:v", "1",
                          "-vf", "scale=270:480", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    img = np.frombuffer(raw, np.uint8).reshape(480, 270, 3).astype(int)
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    return float(((g > 200) & (r > 120) & (r < 235) & (b < 130)).mean())


def judged(three_bursts, out, **opts):  # noqa: F811
    judge = lambda text, frame, ctx: {"title": "t", "titles": ["t", "u", "v"], "hook": "watch the shit ramp", "virality": {"score": 80}}   # noqa: E731
    return run_pipeline(three_bursts, PipelineOptions(max_clips=1, clip_length=20, captions=False, tighten=False, punch_zoom=False,
                                                      layout="fill", **opts), out, transcriber=Talker(), judge=judge)[0]


def test_the_hook_is_burned_in_for_the_first_seconds_only_and_can_be_switched_off(three_bursts, tmp_path):  # noqa: F811
    on = judged(three_bursts, tmp_path / "on")
    off = judged(three_bursts, tmp_path / "off", hook_overlay=False)
    assert on.features["edit"]["hook"] == "watch the shit ramp" and off.features["edit"]["hook"] is None
    # The test pattern has a little lime of its own, so compare with the same frames rendered without the hook.
    assert lime(on.video_path, 1.0) > lime(off.video_path, 1.0) + 0.02               # the box is there at 1 s
    assert abs(lime(on.video_path, 4.0) - lime(off.video_path, 4.0)) < 0.002         # and gone after 2.5 s
    assert off.meta["hook"] == "watch the shit ramp"                                  # still offered, just not burned in
    clean = judged(three_bursts, tmp_path / "clean", censor=True)
    assert clean.features["edit"]["hook"] == "watch the s*** ramp"


def test_clips_list_their_titles_and_the_owner_can_pick_one(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job_id = make_clips(client, headers, up["upload_id"], transcriber, n=1)
    with new_session() as db:
        clip = db.query(Clip).filter(Clip.job_id == job_id).one()
        clip.meta = parse_meta(REPLY)
        clip_id = clip.id
        db.commit()
    got = client.get(f"/v1/jobs/{job_id}", headers=headers).json()["clips"][0]
    assert got["titles"] == parse_meta(REPLY)["titles"] and got["title"] == got["titles"][0] and got["hook"].startswith("wait for")
    picked = client.patch(f"/v1/clips/{clip_id}", json={"title": got["titles"][2]}, headers=headers)
    assert picked.status_code == 200 and picked.json()["title"] == "Did he stick the landing?" and picked.json()["rank"] == 1
    own = client.patch(f"/v1/clips/{clip_id}", json={"title": "  my   own words  "}, headers=headers).json()
    assert own["title"] == "my own words" and own["titles"] == got["titles"]         # the options stay on offer
    project = client.get(f"/v1/projects/{up['upload_id']}", headers=headers).json()["clips"][0]
    assert project["title"] == "my own words" and project["virality"]["score"] == got["virality"]["score"]
    for bad in ({"title": ""}, {"title": "   "}, {"title": "x" * 81}, {"hook": "nope"}, {}):
        assert client.patch(f"/v1/clips/{clip_id}", json=bad, headers=headers).status_code == 422, bad
    assert client.patch(f"/v1/clips/{clip_id}", json={"title": "mine now"}, headers=new_user(client)).status_code == 404
