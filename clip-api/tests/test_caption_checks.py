"""scripts/caption_checks.py: the numbers docs/CONTRACTS.md "Captions and on-screen text v1" defines, measured on
the ASS file the renderer writes."""
import importlib.util
from pathlib import Path

from app.pipeline import layouts as L

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location("caption_checks", SCRIPTS / "caption_checks.py")
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)

WORDS = [(0.0, 0.3, "Oh"), (0.32, 0.6, "my"), (0.62, 1.0, "god"), (1.02, 1.4, "he"), (1.42, 1.9, "sniped"),
         (1.92, 2.3, "me!"), (5.0, 5.4, "Thirty"), (5.42, 5.9, "kills")]
GAMEPLAY = {"width": 1920, "height": 1080, "scene": {"kind": "gameplay", "cam": None, "face": None}, "boxes": []}


def ev(start, end, text, name="", style="Cap"):
    return K.Event(0, start, end, style, name, text)


def test_a_word_lit_late_counts_its_delay_and_a_word_never_lit_is_not_active():
    events = [ev(0.0, 0.3, "OH MY", "w0"), ev(0.52, 0.6, "OH MY", "w1")]       # "my" lights 200 ms after it starts
    t = K.timing(WORDS[:2], events)
    assert t["active_share"] == 1.0 and t["active_p95_ms"] == 200
    t = K.timing(WORDS[:2], [ev(0.0, 0.6, "OH MY")])
    assert t["active_share"] == 0.0 and t["active_p95_ms"] is None
    assert t["appear_early_p95_ms"] == 320                                     # "my" was up 320 ms before it was said


def test_a_caption_held_across_a_long_silence_is_dead_air():
    held = K.dead_air(WORDS, [ev(0.0, 4.0, "OH MY GOD")])
    assert held["dead_air_s"] == 1.4 and held["dead_air_share"] == 0.35      # 2.6 s (+0.3 hold) to 4.0 s
    assert K.dead_air(WORDS, [ev(0.0, 2.5, "OH MY GOD")])["dead_air_s"] == 0.0


def test_reading_speed_and_flashes():
    r = K.reading([ev(0.0, 0.2, "UNBELIEVABLE"), ev(0.2, 1.2, "NO WAY")])
    assert r["cues"] == 2 and r["flash_share"] == 0.5 and r["over_cps_share"] == 0.5


def test_a_hud_box_counts_only_where_it_lands_on_the_canvas():
    plan = L.compose(1920, 1080, "full", "9:16", scene="gameplay")
    x0 = plan.panels[0].src[0] / 1920
    boxes = [{"kind": "minimap", "box": [0.0, 0.8, 0.15, 0.2]},                  # left of the 9:16 crop: gone
             {"kind": "hud", "box": [x0, 0.6, 0.05, 0.1]}]                      # inside it: scaled onto the canvas
    keep = K.keep_out_boxes(plan, boxes, (1920, 1080))
    assert len(keep) == 1 and keep[0][0] == 0 and abs(keep[0][1] - 1152) <= 1 and abs(keep[0][3] - 1344) <= 1


def test_an_impact_caption_over_a_box_is_counted_in_every_frame_it_shows(tmp_path):
    from app.pipeline import render as R
    path = tmp_path / "cap.ass"
    R.text_track(path, WORDS, src_w=1920, src_h=1080, vertical=True, zoom=1.0, chat="none",
                 plan=K.plan_for(GAMEPLAY, "9:16"), aspect="9:16", font="Arial", style="impact")
    styles, events = K.read_ass(path)
    rects = [K.text_rect(e, styles, (1080, 1920)) for e in events if e.style == "Cap"]
    assert all(0 < r[0] < r[2] < 1080 and 0 < r[1] < r[3] < 1920 for r in rects)
    row = (rects[0][1] + rects[0][3]) / 2
    over = K.overlap(events, styles, (1080, 1920), [(0, row - 5, 1080, row + 5)])
    clear = K.overlap(events, styles, (1080, 1920), [(0, 0, 1080, 100)])
    assert over["caption_overlap_share"] == 1.0 and clear["caption_overlap_share"] == 0.0


def test_check_window_reports_every_number_for_both_frames():
    for setup in K.SETUPS:
        r = K.check_window(GAMEPLAY, {"words": WORDS}, setup)
        assert r["timing"]["words"] == 8 and r["reading"]["cues"] >= 3
        assert r["placement"]["out_of_frame"] == 0 and r["placement"]["hook_frames"] > 0
