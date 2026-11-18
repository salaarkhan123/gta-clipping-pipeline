"""Reframe boxes v1 (docs/CONTRACTS.md): where the camera, the head and the HUD land on the output, for captions."""
from dataclasses import replace

import pytest

from app.pipeline import layouts as L

SW, SH = 1920, 1080
CAM = (0.75, 0.0, 0.25, 0.3)                  # a webcam in the top-right corner
FACE = (0.875, 0.14, 0.06, 0.11)


def inside(inner, outer):
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_split_reports_panels_seam_and_the_head_inside_the_camera_panel():
    plan = L.compose(SW, SH, "split2", "9:16", scene="gameplay_cam", cam=CAM, face=FACE)
    box = L.reframe_boxes(plan, confidence=0.9)
    assert box["v"] == 1 and box["canvas"] == [1080, 1920] and box["layout"] == "split2"
    assert box["seam"] == plan.seam
    roles = {p["role"]: p["out"] for p in box["panels"]}
    assert roles["camera"] == [0, 0, 1080, plan.seam] and roles["gameplay"] == [0, plan.seam, 1080, 1920]
    assert box["facecam"] == {"src": list(CAM), "out": roles["camera"], "confidence": 0.9}
    assert box["head"] and inside(box["head"], roles["camera"])
    # A stacked camera panel keeps only the head out of bounds, so the caption can still sit on the seam.
    assert box["keep_out"] == [box["head"]]
    assert box["hud"] == [] and box["crop_path"] is None and box["text_span"] == [0.0, 1.0]


def test_pip_inset_is_kept_out_whole():
    plan = L.compose(SW, SH, "pip", "9:16", scene="gameplay_cam", cam=CAM, face=FACE)
    box = L.reframe_boxes(plan)
    inset = box["facecam"]["out"]
    assert inset in box["keep_out"] and box["facecam"]["confidence"] is None


def test_camera_inside_the_gameplay_picture_is_mapped_onto_the_canvas():
    # full in 16:9 shows the whole source: the camera lands where the streamer put it.
    plan = L.compose(SW, SH, "full", "16:9", scene="gameplay_cam", cam=CAM, face=FACE)
    box = L.reframe_boxes(plan)
    assert box["facecam"]["out"] == [1440, 0, 1920, 324]
    assert box["facecam"]["out"] in box["keep_out"]


def test_hud_lands_on_the_canvas_or_is_reported_cropped_away(monkeypatch):
    monkeypatch.setitem(L.HUD_REGIONS, "valorant", (("killfeed", (0.80, 0.07, 0.19, 0.2)), ("minimap", (0.4, 0.4, 0.2, 0.2))))
    plan = L.compose(SW, SH, "full", "9:16", scene="gameplay")
    box = L.reframe_boxes(plan, game="valorant")
    feed, mini = box["hud"]
    assert feed["kind"] == "killfeed" and feed["out"] is None            # a centred 9:16 crop loses the right edge
    assert mini["out"] is not None and mini["out"] in box["keep_out"]
    assert L.reframe_boxes(plan, game="other")["hud"] == [] and L.reframe_boxes(plan)["hud"] == []


def test_games_that_share_a_hud_fold_to_one_table(monkeypatch):
    monkeypatch.setitem(L.HUD_REGIONS, "gta5", (("minimap", (0.01, 0.75, 0.15, 0.22)),))
    assert L.hud_regions("gta6") == L.hud_regions("gta-online") == L.hud_regions("gta5")
    assert L.hud_regions("lol") == ()


def test_moving_crop_reports_its_path_and_worst_case_keep_out(monkeypatch):
    monkeypatch.setitem(L.HUD_REGIONS, "gta5", (("minimap", (0.20, 0.75, 0.10, 0.2)),))
    plan = L.compose(SW, SH, "full", "9:16", scene="gameplay")
    (p,) = plan.panels
    left = (p.src[0] - 300, *p.src[1:])
    moved = replace(plan, panels=(replace(p, path=((0.0, p.src), (2.0, left))),))
    still, box = L.reframe_boxes(plan, game="gta5"), L.reframe_boxes(moved, game="gta5")
    assert still["hud"][0]["out"] is None                                 # the centred crop never shows it
    assert box["hud"][0]["out"] is not None                               # the crop slides over it at some point
    assert [pt["t"] for pt in box["crop_path"]] == [0.0, 2.0]
    assert box["crop_path"][1]["box"][0] == pytest.approx(left[0] / SW, abs=1e-4)


def test_original_picture_without_a_plan():
    box = L.reframe_boxes(None, src=(SW, SH), cam=CAM, face=FACE)
    assert box["canvas"] == [SW, SH] and box["layout"] == "original"
    assert box["panels"] == [{"role": "gameplay", "out": [0, 0, SW, SH]}]
    assert box["facecam"]["out"] == [1440, 0, 1920, 324]
    assert box["head"] and inside(box["head"], box["facecam"]["out"])
    assert overlaps(box["keep_out"][0], box["facecam"]["out"])
    with pytest.raises(ValueError):
        L.reframe_boxes(None)


def test_the_layout_graph_draws_a_moving_crop():
    plan = L.compose(SW, SH, "full", "9:16", scene="gameplay")
    (p,) = plan.panels
    moved = replace(plan, panels=(replace(p, path=((0.0, p.src), (2.0, (100.0, 0.0, p.src[2], p.src[3])))),))
    graph = L.layout_graph(moved)
    assert "crop=w=" in graph and "if(lt(t,2.000)" in graph
    assert "crop=w=" not in L.layout_graph(plan)                  # a still crop draws exactly as before
    assert L.path_expr([(0.0, 5.0)]) == "if(lt(t,0.000),5.0,5.0)"
