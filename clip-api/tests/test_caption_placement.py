"""Where captions and the hook sit (app/pipeline/placement.py): off every keep-out box of the clip's reframe boxes
(the head, a webcam in the picture, the game's HUD), the least distance from where they were asked to be."""
import importlib.util
from pathlib import Path

from app.pipeline import layouts as L
from app.pipeline import placement as P
from app.pipeline import render as R
from app.pipeline.captions import IMPACT_FILL, impact_size

_spec = importlib.util.spec_from_file_location("caption_checks", Path(__file__).resolve().parent.parent / "scripts" /
                                               "caption_checks.py")
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)

WORDS = [(round(0.4 * i, 2), round(0.4 * i + 0.35, 2), w) for i, w in
         enumerate("he just sniped me from across the map no way bro".split())]


def boxes(keep_out, canvas=(1080, 1920), seam=None, span=(0.0, 1.0)):
    return {"canvas": list(canvas), "keep_out": [list(b) for b in keep_out], "seam": seam, "text_span": list(span)}


def test_a_hud_box_on_the_caption_row_moves_it_the_least_distance_and_never_out_of_the_safe_rows():
    half = impact_size(1920).half
    gap = P.FACE_GAP
    y, _ = P.place(boxes([(0, 1350, 1080, 1450)]), "auto", half, IMPACT_FILL, 300)
    assert y == round(1350 - gap - half)                                      # up: nearer than down
    y, _ = P.place(boxes([(0, 1250, 1080, 1330)]), "auto", half, IMPACT_FILL, 300)
    assert y == round(1330 + gap + half)                                      # down: nearer than up
    y, _ = P.place(boxes([(0, 1300, 30, 1400)]), "auto", half, IMPACT_FILL, 300)
    assert y == 1344                                                          # beside the text: not moved
    y, _ = P.place(boxes([(0, 0, 1080, 1920)]), "center", half, IMPACT_FILL, 300)
    assert P.SAFE_ROWS[0] * 1920 + half - 1 <= y <= P.SAFE_ROWS[1] * 1920 - half + 1    # nowhere clear: inside the frame


def test_the_hook_keeps_off_a_box_and_off_the_caption():
    half = impact_size(1920).half
    _, hook = P.place(boxes([(700, 300, 1080, 420)]), "auto", half, IMPACT_FILL, 345)       # a kill feed under it
    assert hook >= 420 + P.FACE_GAP + P.HOOK_PAD or hook + P.HOOK_ROOM <= 300 - P.FACE_GAP
    y, hook = P.place(boxes([]), "auto", half, IMPACT_FILL, 1300)
    assert hook >= y + half + P.TEXT_GAP or hook + P.HOOK_ROOM <= y - half - P.TEXT_GAP


def test_a_webcam_in_the_original_frame_is_kept_clear(tmp_path):
    """Not reframed: the 16:9 source with the streamer's webcam where the caption would go."""
    cam = (0.3, 0.55, 0.4, 0.3)                                               # a webcam across the lower middle
    path = tmp_path / "cap.ass"
    R.text_track(path, WORDS, src_w=1920, src_h=1080, vertical=False, zoom=1.0, chat="none", plan=None,
                 aspect="16:9", font="Arial", style="impact", hook="he sniped me across the map", facecam=list(cam))
    styles, events = K.read_ass(path)
    keep = L.reframe_boxes(None, src=(1920, 1080), cam=cam)["keep_out"]
    assert keep and K.overlap(events, styles, (1920, 1080), keep)["caption_overlap_share"] == 0.0
    assert K.overlap(events, styles, (1920, 1080), keep)["hook_overlap_share"] == 0.0


def test_the_game_hud_reaches_the_captions_through_reframe_boxes(tmp_path, monkeypatch):
    """A game whose HUD sits on the lower third of the 9:16 crop: the captions and the hook keep off it."""
    monkeypatch.setitem(L.HUD_REGIONS, "valorant", (("hud", (0.3, 0.62, 0.4, 0.1)),))
    plan = L.compose(1920, 1080, "full", "9:16", scene="gameplay")
    for game, clear in ((None, False), ("valorant", True)):
        path = tmp_path / f"{game}.ass"
        R.text_track(path, WORDS, src_w=1920, src_h=1080, vertical=True, zoom=1.0, chat="none", plan=plan,
                     aspect="9:16", font="Arial", style="impact", hook="he sniped me", game=game)
        styles, events = K.read_ass(path)
        hud = L.reframe_boxes(plan, game="valorant")["keep_out"]
        share = K.overlap(events, styles, (1080, 1920), hud)["caption_overlap_share"]
        assert (share == 0.0) is clear, (game, share)
