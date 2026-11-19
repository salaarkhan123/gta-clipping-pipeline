"""Facecam detection: the looser second look for a streamer the strict face detector misses (looking down at the
keyboard, turned away), how sure each answer is, and that a game character never becomes a camera."""
import numpy as np

from app.pipeline import facecam as F
from app.pipeline import layouts as L
from tests.test_facecam_rect import px, scene

CAM = (20, 40, 132, 90)        # pixels of the 640x360 frames: a small top-left webcam, as on the Valorant stream


def test_a_streamer_the_strict_detector_misses_is_found_from_a_loose_face_inside_a_still_box(monkeypatch):
    frames, face = scene(CAM)
    monkeypatch.setattr(F, "stable_face", lambda _f: None)                 # looking down: the strict detector sees nothing
    monkeypatch.setattr(F, "weak_faces", lambda _f: [(3, face)])
    s = F.classify(frames)
    assert s.kind == "gameplay_cam" and all(abs(a - b) <= 2 for a, b in zip(px(s.cam), CAM))
    assert s.face == face and s.confidence == F.CONFIDENCE["weak_rect"]


def test_a_loose_face_with_no_still_box_around_it_is_a_game_character_not_a_camera(monkeypatch):
    frames, face = scene(CAM, cutout=True)                                 # nothing still around the face
    monkeypatch.setattr(F, "stable_face", lambda _f: None)
    monkeypatch.setattr(F, "weak_faces", lambda _f: [(3, face)])
    assert F.classify(frames) == F.Scene("gameplay")


def test_a_face_in_most_frames_over_a_room_is_a_person_filling_the_frame(monkeypatch):
    rng = np.random.default_rng(5)
    room = rng.integers(40, 200, (360, 640)).astype(np.float32)
    frames = [(room + rng.normal(0, 12, room.shape)).clip(0, 255).astype(np.uint8) for _ in range(12)]
    monkeypatch.setattr(F, "stable_face", lambda _f: None)
    monkeypatch.setattr(F, "find_cam_rect", lambda *_a: None)
    face = (0.58, 0.47, 0.12, 0.22)
    monkeypatch.setattr(F, "weak_faces", lambda _f: [(10, face)])
    s = F.classify(frames)
    assert (s.kind, s.face, s.confidence) == ("camera", face, F.CONFIDENCE["weak_camera"])
    monkeypatch.setattr(F, "weak_faces", lambda _f: [(3, face)])          # seen too rarely to be the picture
    assert F.classify(frames).kind == "gameplay"
    game, _ = scene(CAM)                                                   # gameplay changes far more than a room
    monkeypatch.setattr(F, "weak_faces", lambda _f: [(10, face)])
    assert F.median_change(game) > F.ROOM_CHANGE > F.median_change(frames)
    assert F.classify(game).kind == "gameplay"


def test_the_strict_path_is_unchanged_and_most_sure(monkeypatch):
    frames, face = scene(CAM)
    monkeypatch.setattr(F, "stable_face", lambda _f: face)
    monkeypatch.setattr(F, "weak_faces", lambda _f: (_ for _ in ()).throw(AssertionError("not needed")))
    s = F.classify(frames)
    assert s.kind == "gameplay_cam" and s.confidence == F.CONFIDENCE["rect"]


def test_confidence_reaches_the_plan_the_cambox_and_the_boxes(monkeypatch):
    frames, face = scene(CAM)
    monkeypatch.setattr(F, "detect_scene", lambda *_a, **_k: F.Scene("gameplay_cam", list(np.array(CAM) / [640, 360, 640, 360]),
                                                                      face, 0.75))
    from types import SimpleNamespace
    opts = SimpleNamespace(facecam_region="auto", facecam_box=None, vertical=True, aspect="9:16", layout="auto", zoom=1.0)
    info = SimpleNamespace(width=640, height=360, duration=60.0)
    plan = F.resolve_plan("x.mp4", info, opts)
    assert plan.confidence == 0.75 and L.reframe_boxes(plan)["facecam"]["confidence"] == 0.75
    _layout, box = F.resolve_facecam("x.mp4", info, opts)
    assert box.confidence == 0.75


# ---------- full asked for by name, with a camera that cannot be held whole ----------
def test_full_with_a_corner_camera_fills_the_frame_with_gameplay_instead_of_turning_into_pip():
    cam, face = (0.0, 0.62, 0.22, 0.38), (0.1, 0.78, 0.06, 0.11)          # bottom-left, far from the centre crop
    plan = L.compose(1920, 1080, "full", "9:16", scene="gameplay_cam", cam=cam, face=face)
    assert plan.layout == "full" and len(plan.panels) == 1 and plan.panels[0].kind == "gameplay"
    assert plan.note == L._NOTES["camera_left_out"]
    keep = L._keep_out(1920, 1080, cam, face)
    assert not L._overlaps(plan.panels[0].src, keep)                         # the person is left out whole, never cut
    pip = L.compose(1920, 1080, "pip", "9:16", scene="gameplay_cam", cam=cam, face=face)
    assert pip.layout == "pip" and L.layout_graph(pip) != L.layout_graph(plan)
    auto = L.compose(1920, 1080, "auto", "9:16", scene="gameplay_cam", cam=cam, face=face)
    assert auto.layout == "split2"                                           # auto still shows both


def test_full_holds_a_camera_that_fits_and_says_nothing():
    cam = (0.40, 0.70, 0.18, 0.28)                                           # just under the centre crop
    plan = L.compose(1920, 1080, "full", "9:16", scene="gameplay_cam", cam=cam)
    assert plan.layout == "full" and plan.note is None
