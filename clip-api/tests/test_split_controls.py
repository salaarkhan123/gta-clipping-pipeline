"""`camera` and `split_ratio`: which panel of a two-panel layout the camera is, and how the frame is shared.
Null keeps every layout exactly as it was; the camera panel stays tight on the person at every size."""
import json
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline import facecam as F
from app.pipeline import layouts as L
from app.pipeline import render as R
from app.pipeline.ff import MediaInfo
from app.pipeline.tools import RenderOptions, run_render
from app.render_options import LayoutOptions
from app.routes_media import ClipOptions
from tests.test_api import balance, upload
from tests.test_layouts import (BOTTOM, CORNER, SH, SHARP, SW, camera, check_people, expected_face_area, face_of,
                                face_pixels, frac, frame, make_stream, render, smeared)
from tests.test_tools import run

GOLDEN = Path(__file__).parent / "golden" / "layout_graphs_before_split_controls.json"
RATIOS = (0.25, 0.4, 0.6, 0.75)


# ---------- null changes nothing ----------
def test_without_the_two_options_every_two_panel_layout_draws_exactly_what_it_drew_before():
    """The golden file was written by the renderer as it was before `camera` and `split_ratio` existed."""
    golden = json.loads(GOLDEN.read_text())
    sw, sh = golden["source"]
    seen = set()
    for key, was in golden["plans"].items():
        aspect, name, cam_name = key.split("/")
        known = cam_name.endswith("+face")
        cam = golden["cams"][cam_name.removesuffix("+face")]
        if known:
            plan = L.compose(sw, sh, L.canonical(name, aspect), aspect, cam=cam, face=tuple(golden["face"]))
        else:
            plan = R.plan_for(sw, sh, name, cam, aspect)
        now = {"layout": plan.layout, "graph": L.layout_graph(plan), "caption_top": plan.caption_top,
               "hook_top": plan.hook_top, "text_span": list(plan.text_span)}
        assert now == was, key
        again = R.plan_for(sw, sh, name, cam, aspect, camera=None, split_ratio=None) if not known else plan
        assert L.layout_graph(again) == was["graph"]
        seen.add(name)
    assert seen == {"split", "split2", "gameplay_a", "gameplay_b", "screen_first"} and len(golden["plans"]) == 39
    # Two of them, spelled out: the graphs a request with neither option gets today.
    assert golden["plans"]["9:16/split/preset-top-right"]["graph"] == (
        "[0:v]split=2[a][b];[a]crop=546:324:1358:0,scale=1080:640,setsar=1[top];"
        "[b]crop=910:1080:394:0,scale=1080:1280,setsar=1[bot];[top][bot]vstack=inputs=2,format=yuv420p[v]")
    assert golden["plans"]["9:16/gameplay_b/preset-top-right"]["graph"].endswith(
        "scale=1080:960,setsar=1[bot];[top][bot]vstack=inputs=2,format=yuv420p[v]")
    assert (LayoutOptions().camera, LayoutOptions().split_ratio) == (None, None)
    assert ClipOptions().model_dump()["camera"] is None and ClipOptions().model_dump()["split_ratio"] is None


# ---------- what they do ----------
@pytest.mark.parametrize("name", ["split2", "gameplay_a", "gameplay_b", "screen_first"])
def test_the_top_panel_gets_the_share_asked_for_whichever_panel_the_camera_is(name):
    cam, face = frac(CORNER[0]), face_of(CORNER[1])
    own = L.compose(SW, SH, name, "9:16", cam=cam, face=face)
    own_first = own.panels[0].kind == "camera"
    for side in (None, "top", "bottom"):
        for ratio in (None,) + RATIOS:
            plan = L.compose(SW, SH, name, "9:16", cam=cam, face=face, camera=side, split_ratio=ratio)
            top, bottom = plan.panels
            assert plan.layout == name and top.out[:3] == (0, 0, 1080) and bottom.out[0] == 0
            assert top.out[3] + bottom.out[3] == 1920 and bottom.out[1] == top.out[3] == plan.seam
            cam_first = own_first if side is None else side == "top"
            assert (top.kind, bottom.kind) == (("camera", "gameplay") if cam_first else ("gameplay", "camera"))
            if ratio is not None:
                assert top.out[3] == L.even(1920 * ratio)
            elif side is None or cam_first == own_first:
                assert top.out[3] == own.panels[0].out[3]                      # the layout's own
            else:                                                             # flipped: the camera keeps its own share
                assert top.out[3] == 1920 - own.panels[0].out[3]
            check_people(plan)
            assert [p.punch for p in plan.panels] == [p.kind == "gameplay" for p in plan.panels]      # never zoom a person


def test_the_preset_proportions_from_the_screenshots():
    """docs/CONTRACTS.md "Game-type presets": each is a split with these two options."""
    cam, face = frac(BOTTOM[0]), face_of(BOTTOM[1])
    for side, ratio, want in (("bottom", 0.60, ("gameplay", 1152)), ("top", 0.33, ("camera", 632)),
                              ("bottom", 0.57, ("gameplay", 1094)), ("bottom", 0.63, ("gameplay", 1208)),
                              ("bottom", 0.66, ("gameplay", 1266))):
        plan = L.compose(SW, SH, "split2", "9:16", cam=cam, face=face, camera=side, split_ratio=ratio)
        assert (plan.layout, plan.panels[0].kind, plan.panels[0].out[3]) == ("split2",) + want
        check_people(plan)


def test_the_camera_panel_stays_tight_on_the_person_at_every_size():
    cam, face = frac(BOTTOM[0]), face_of(BOTTOM[1])
    head = L.head_box(face, SW, SH)
    box = L.cam_px(cam, SW, SH)
    for side in ("top", "bottom"):
        for ratio in RATIOS:
            plan = L.compose(SW, SH, "split2", "9:16", cam=cam, face=face, camera=side, split_ratio=ratio)
            (panel,) = [p for p in plan.panels if p.kind == "camera"]
            x, y, w, h = panel.src
            assert L._inside(head, panel.src, tol=1)                          # the whole head, always
            assert w / h == pytest.approx(panel.out[2] / panel.out[3], rel=0.01)      # never stretched
            # Tight: the crop is the camera box trimmed to the panel's shape, or, when the head needs more than
            # that, no bigger than what holds the head.
            fits_box = w <= box[2] + 1 and h <= box[3] + 1
            hugs_head = w == pytest.approx(head[2], abs=1) or h == pytest.approx(head[3], abs=1)
            assert fits_box or hugs_head, (side, ratio)
            assert w * h < 0.12 * SW * SH                                     # nowhere near the whole frame


def test_in_a_wide_frame_top_means_left_and_the_ratio_is_a_share_of_the_width():
    cam = frac(CORNER[0])
    own = L.compose(SW, SH, "split2", "16:9", cam=cam)
    assert [p.kind for p in own.panels] == ["camera", "gameplay"] and own.panels[0].out == (0, 0, 640, 1080)
    plan = L.compose(SW, SH, "split2", "16:9", cam=cam, camera="bottom", split_ratio=0.6)
    left, right = plan.panels
    assert (left.kind, left.out, right.kind, right.out) == ("gameplay", (0, 0, 1152, 1080), "camera", (1152, 0, 768, 1080))
    assert plan.seam is None and plan.text_span == (0.0, 0.6)                 # the text stays centred on the gameplay
    check_people(plan)


def test_every_other_layout_ignores_both_and_auto_uses_them_when_it_draws_two_panels():
    cam, face = frac(CORNER[0]), face_of(CORNER[1])
    for name, aspect in (("full", "9:16"), ("fit", "9:16"), ("pip", "9:16"), ("full", "16:9"), ("fit", "1:1"), ("auto", "16:9"),
                         ("full", "1:1")):
        assert L.compose(SW, SH, name, aspect, cam=cam, face=face, camera="bottom", split_ratio=0.6) == \
            L.compose(SW, SH, name, aspect, cam=cam, face=face), (name, aspect)
    assert L.compose(SW, SH, "auto", "9:16", camera="top", split_ratio=0.4) == L.compose(SW, SH, "auto", "9:16")      # no camera
    auto = L.compose(SW, SH, "auto", "9:16", cam=cam, face=face, camera="bottom", split_ratio=0.6)
    assert auto.layout == "split2" and auto.panels[0].kind == "gameplay" and auto.panels[0].out[3] == 1152
    for name, aspect in (("full", "9:16"), ("pip", "4:5"), ("fit", "1:1"), ("auto", "9:16"), ("classic", "9:16")):
        o = LayoutOptions(layout=name, aspect=aspect, camera="top", split_ratio=0.25)      # accepted, not a 422
        assert (o.camera, o.split_ratio) == ("top", 0.25)


def test_values_outside_the_range_are_refused_with_the_reason():
    for bad in (0.2, 0.249, 0.751, 0.8, 0, 1, "half"):
        with pytest.raises(ValidationError):
            LayoutOptions(split_ratio=bad)
    for bad in ("left", "right", "middle", "", True):
        with pytest.raises(ValidationError):
            LayoutOptions(camera=bad)
    for ok in (0.25, 0.5, 0.75):
        assert LayoutOptions(split_ratio=ok, camera="bottom").split_ratio == ok
    cam = frac(CORNER[0])
    for kw, reason in (({"split_ratio": 0.2}, "between 0.25 and 0.75"), ({"split_ratio": 0.9}, "between 0.25 and 0.75"),
                       ({"split_ratio": "x"}, "between 0.25 and 0.75"), ({"camera": "left"}, "Use one of: top, bottom")):
        with pytest.raises(L.PipelineError) as e:
            L.compose(SW, SH, "split2", "9:16", cam=cam, **kw)
        assert e.value.code == "bad_options" and reason in e.value.message
    assert L.SPLIT_RATIO == (0.25, 0.75) and L.CAMERA_SIDES == ("top", "bottom")


# ---------- rendered ----------
@pytest.fixture(scope="module")
def streams(tmp_path_factory):
    d = tmp_path_factory.mktemp("splits")
    return {"corner": make_stream(d / "corner.mp4", *CORNER), "bottom": make_stream(d / "bottom.mp4", *BOTTOM)}


@pytest.mark.parametrize("side", ["top", "bottom"])
def test_rendered_the_camera_is_on_the_side_asked_for_whole_and_sharp_at_every_ratio(side, streams, tmp_path):
    for which, (cam_px, face_px) in (("corner", CORNER), ("bottom", BOTTOM)):
        for ratio in RATIOS:
            plan = L.compose(SW, SH, "split2", "9:16", cam=frac(cam_px), face=face_of(face_px), camera=side, split_ratio=ratio)
            assert plan.layout == "split2", (which, ratio)
            info = render(streams[which], tmp_path / "s.mp4", plan=plan)
            img = frame(tmp_path / "s.mp4")
            assert (info.width, info.height) == (1080, 1920)
            seam = L.even(1920 * ratio)
            mine = img[:seam] if side == "top" else img[seam:]
            other = img[seam + 6:] if side == "top" else img[:seam - 6]
            want, _panel = expected_face_area(plan, face_px, (1080, 1920))
            assert face_pixels(mine).sum() == pytest.approx(want, rel=0.1), (which, ratio)      # the whole face, in its panel
            assert face_pixels(other).sum() == 0 and camera(other).sum() == 0                 # and nothing of it in the other
            assert smeared(img) < SHARP, (which, ratio)                                       # sharp: never a blurred copy
            ys, xs = np.nonzero(face_pixels(img))
            assert xs.min() > 2 and xs.max() < 1077                                           # not cut by a frame edge
            assert (ys.min() > 2 and ys.max() < seam - 2) if side == "top" else (ys.min() > seam + 2 and ys.max() < 1917)


def test_rendered_from_a_layout_name_the_way_a_job_does_it(streams, tmp_path):
    box = F.CamBox(frac(CORNER[0]), face_of(CORNER[1]), "gameplay_cam")
    render(streams["corner"], tmp_path / "own.mp4", layout="split", facecam=box)
    render(streams["corner"], tmp_path / "set.mp4", layout="split", facecam=box, camera="bottom", split_ratio=0.6)
    own, moved = camera(frame(tmp_path / "own.mp4")), camera(frame(tmp_path / "set.mp4"))
    assert np.nonzero(own)[0].max() < 640 + 2                                 # the layout's own: the top third
    assert np.nonzero(moved)[0].min() >= 1152 - 2 and np.nonzero(moved)[0].max() > 1800      # under 60% of gameplay


# ---------- the options reach the renderer, and cost nothing ----------
def test_a_jobs_options_decide_the_plan_and_the_renderer_rebuilds_the_same_one(monkeypatch):
    cam, face = frac(BOTTOM[0]), face_of(BOTTOM[1])
    info = MediaInfo(60, SW, SH, True)
    monkeypatch.setattr(F, "detect_scene", lambda *_a, **_k: F.Scene("gameplay_cam", cam, face))
    for layout, side, ratio in (("auto", "bottom", 0.6), ("split", "top", 0.33), ("gameplay_b", None, 0.75),
                                ("screen_first", "top", None), ("auto", None, None)):
        opts = SimpleNamespace(vertical=True, aspect="9:16", layout=layout, facecam_region="auto", facecam_box=None,
                               zoom=1.0, camera=side, split_ratio=ratio)
        plan = F.resolve_plan("x", info, opts)
        assert plan == L.compose(SW, SH, L.canonical(layout, "9:16"), "9:16", cam=cam, face=face, camera=side,
                                 split_ratio=ratio, requested=layout)
        name, box = F.resolve_facecam("x", info, opts)
        rebuilt = R.plan_for(SW, SH, name, box, "9:16", camera=side, split_ratio=ratio)
        assert replace(rebuilt, requested=layout) == plan, (layout, side, ratio)
    old = SimpleNamespace(vertical=True, aspect="9:16", layout="split", facecam_region="top-right", facecam_box=None, zoom=1.0)
    assert F.resolve_plan("x", info, old).panels[0].out == (0, 0, 1080, 640)      # options without the two fields: as before


def test_the_split_options_reach_the_renderer_from_the_pipeline_and_the_tools(video, transcriber, tmp_path, monkeypatch):
    seen = []
    real = R.render_clip

    def spy(*a, **kw):
        seen.append(kw)
        return real(*a, **kw)
    monkeypatch.setattr("app.pipeline.render_clip", spy)
    monkeypatch.setattr("app.pipeline.tools.render_clip", spy)
    sent = ClipOptions(max_clips=1, clip_length=10, facecam_region="top-right", camera="bottom", split_ratio=0.6).model_dump()
    assert {"camera", "split_ratio"} <= set(sent) <= {f.name for f in fields(PipelineOptions)}
    clip = run_pipeline(video, PipelineOptions(caption_font="DejaVu Sans", **sent), tmp_path / "a", transcriber=transcriber)[0]
    assert (seen[-1]["layout"], seen[-1]["camera"], seen[-1]["split_ratio"]) == ("split", "bottom", 0.6)
    rows = np.nonzero(np.abs(np.diff(frame(clip.video_path, 1.0).mean(axis=1), axis=0)).sum(axis=1) > 60)[0]
    assert any(abs(r - 1151) <= 2 for r in rows)                              # the line between the panels, 60% down
    run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10), tmp_path / "b", transcriber=transcriber)
    assert (seen[-1]["camera"], seen[-1]["split_ratio"]) == (None, None)
    opts = RenderOptions(facecam_region="top-right", camera="top", split_ratio=0.4)
    run_render(video, [(5, 9)], opts, tmp_path / "c")
    assert (seen[-1]["camera"], seen[-1]["split_ratio"]) == ("top", 0.4)
    assert {"camera", "split_ratio"} <= {f.name for f in fields(RenderOptions)}


def test_a_job_with_the_split_options_costs_what_it_cost_without_them(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    base = {"max_clips": 1, "clip_length": 10, "facecam_region": "top-right"}
    plain = run(client, headers, "/v1/clips", {"upload_id": up["upload_id"], "options": base}, transcriber)
    sized = run(client, headers, "/v1/clips", {"upload_id": up["upload_id"],
                                               "options": {**base, "camera": "bottom", "split_ratio": 0.6}}, transcriber)
    assert plain["status"] == sized["status"] == "SUCCEEDED"
    assert (sized["options"]["camera"], sized["options"]["split_ratio"]) == ("bottom", 0.6)
    assert (plain["options"]["camera"], plain["options"]["split_ratio"]) == (None, None)
    assert plain["credits_charged"] == sized["credits_charged"] > 0
    assert balance(client, headers) == 30 - 2 * plain["credits_charged"]
    reframe = run(client, headers, "/v1/reframe", {"upload_id": up["upload_id"], "segments": [{"start": 5, "end": 9}],
                                                   "options": {"facecam_region": "top-right", "camera": "bottom", "split_ratio": 0.75}},
                  transcriber)
    assert reframe["status"] == "SUCCEEDED" and reframe["credits_charged"] == 1      # the price of a reframe is not touched
    spent = balance(client, headers)
    for bad in ({"split_ratio": 0.2}, {"split_ratio": 0.8}, {"camera": "left"}):
        r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": bad}, headers=headers)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error", bad
    assert balance(client, headers) == spent                                  # refused before anything is reserved
    listed = client.get("/v1/options").json()["clips"]
    assert listed["camera"] == {"nullable": True, "type": "string", "values": ["top", "bottom"], "default": None}
    assert (listed["split_ratio"]["minimum"], listed["split_ratio"]["maximum"], listed["split_ratio"]["default"]) == (0.25, 0.75, None)
