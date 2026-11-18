"""Clip thumbnails (app/pipeline/thumbs.py): which frame is chosen, and how the hook text is laid out on it."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageChops

from app.pipeline import PipelineOptions, probe, run_pipeline
from app.pipeline import thumbs
from app.pipeline.thumbs import (Canvas, Frame, MAX_LINES, best, canvas_of, fit_text, make_thumbnail, score_frames,
                                 thumb_text, write_thumbnail)

H, W = 90, 160         # scan frames in these tests: small, so each test is quick
SIZES = {"9:16": (720, 1280), "4:5": (720, 900), "1:1": (720, 720), "16:9": (1280, 720)}


def textured(seed: int, shift: int = 0) -> np.ndarray:
    """A detailed gray picture, like a game world: smooth blobs and fine noise, never straight lines."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    g = 120 + 50 * np.sin((x + shift) / 7.0 + seed) * np.cos((y + shift) / 9.0 - seed) + rng.normal(0, 18, (H, W))
    return np.clip(g, 0, 255).astype(np.uint8)


def frames_at(pictures, start: float = 100.0, step: float = 2.0) -> list[Frame]:
    return [Frame(start + i * step, p) for i, p in enumerate(pictures)]


# --- choosing the frame --------------------------------------------------------------------------------------------
def test_no_camera_no_face_takes_a_clear_frame_and_reports_no_face():
    pics = [textured(i) for i in range(6)]
    pics[2] = np.full((H, W), 6, np.uint8)                                    # a black frame (a fade)
    scored = score_frames(frames_at(pics), cam=None, segments=[(99.0, 112.0)])
    assert all(s.face is None for s in scored)                                # no camera: no face to judge
    assert "dark" in scored[2].failed and not scored[2].ok
    pick = best(scored, 105.0)
    assert pick.ok and pick.t != 104.0


def test_a_static_scene_takes_the_frame_nearest_the_middle():
    same = textured(3)
    scored = score_frames(frames_at([same] * 7), segments=[(99.0, 114.0)])
    assert all(s.ok for s in scored)                                          # still, but a fine picture
    assert len({s.score for s in scored}) == 1
    assert best(scored, 106.0).t == 106.0                                     # nothing moves: the middle


def test_a_flash_between_two_alike_frames_is_a_transition():
    pics = [textured(1, k) for k in range(5)]
    pics[2] = np.full((H, W), 250, np.uint8) - (np.arange(W) % 5).astype(np.uint8)   # a white flash
    scored = score_frames(frames_at(pics), segments=[(99.0, 110.0)])
    assert {"transition", "bright"} & set(scored[2].failed)
    assert best(scored, 104.0).t != 104.0


def test_a_menu_or_results_card_is_not_chosen():
    pics = [textured(i) for i in range(5)]
    card = np.full((H, W), 30, np.uint8)
    card[20:70, 20:140] = 200                                                 # a panel with lines of "text"
    card[25:65:6, 30:130] = 20
    pics[3] = card
    scored = score_frames(frames_at(pics), segments=[(99.0, 110.0)])
    assert "menu" in scored[3].failed
    assert best(scored, 104.0).t != 106.0


def test_a_frame_on_a_cut_or_outside_the_kept_pieces_loses():
    pics = [textured(i) for i in range(5)]                                    # at 100, 102, 104, 106, 108
    scored = score_frames(frames_at(pics), segments=[(99.0, 102.1), (105.0, 109.0)])
    assert "cut" in scored[1].failed                                          # 0.1 s from the end of a piece
    assert "cut" in scored[2].failed                                          # in the part dead-air removal took out
    assert best(scored, 106.0).t in (100.0, 106.0, 108.0)


def test_the_judges_peak_and_loudness_pull_the_choice():
    pics = [textured(i) for i in range(6)]
    loud = {100: -40, 102: -40, 104: -40, 106: -8, 108: -40, 110: -40}
    pick = best(score_frames(frames_at(pics), segments=[(99.0, 112.0)], loudness=lambda t: loud[int(t)],
                             peak=106.0), 105.0)
    assert pick.t == 106.0


@pytest.fixture(scope="module")
def face_gray():
    skdata = pytest.importorskip("skimage.data")
    import cv2
    return cv2.cvtColor(skdata.astronaut(), cv2.COLOR_RGB2GRAY)              # 512x512, a real face near the top


def with_camera(face_gray, dx: int) -> np.ndarray:
    """A 640x360 frame of game texture with the person in a camera box at the bottom left, moved `dx` pixels."""
    import cv2
    frame = cv2.resize(np.tile(textured(5), (4, 4)), (640, 360))
    cam = cv2.resize(face_gray[0:300, 100:400], (200, 200))
    frame[160:360, 0:200] = np.roll(cam, dx, axis=1)
    return frame


def test_a_face_cut_by_the_camera_box_is_not_chosen(face_gray):
    cam = (0.0, 160 / 360, 200 / 640, 200 / 360)
    pics = [with_camera(face_gray, 0), with_camera(face_gray, 125), with_camera(face_gray, 5)]
    scored = score_frames(frames_at(pics), cam=cam, segments=[(99.0, 106.0)])
    assert scored[0].face is True and scored[2].face is True
    assert scored[1].face is False and {"face_cut", "no_face"} & set(scored[1].failed)
    assert best(scored, 102.0).t != 102.0


CAM = (0.0, 160 / 360, 200 / 640, 200 / 360)


def brb_screen() -> np.ndarray:
    """A "be right back" card at 640x360: a logo band of big letters on a plain backdrop, an empty camera box."""
    import cv2
    frame = np.full((360, 640), 60, np.uint8)
    cv2.putText(frame, "BE RIGHT BACK", (220, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 230, 4)
    frame[160:360, 0:200] = cv2.resize(textured(9), (200, 200))               # the chair, nobody in it
    return frame


def test_a_be_right_back_screen_with_an_empty_chair_is_standby_and_loses(face_gray):
    import cv2
    brb = brb_screen()
    live = [with_camera(face_gray, 0), cv2.flip(with_camera(face_gray, 0), 1)]
    live[1][160:360, 0:200] = with_camera(face_gray, 3)[160:360, 0:200]       # game moved, streamer back
    pics = [brb, brb, brb, brb, live[0], live[1]]
    loud = lambda t: -6.0                                                      # BRB music is loud: no help here
    scored = score_frames(frames_at(pics), cam=CAM, segments=[(99.0, 112.0)], loudness=loud)
    assert all("standby" in s.failed for s in scored[1:3])                     # frozen, no face in the camera
    assert best(scored, 104.0).t >= 108.0                                      # the streamer, not the card


def test_a_frozen_picture_is_standby_only_when_nobody_is_talking():
    still = [textured(4)] * 5
    quiet = score_frames(frames_at(still), segments=[(99.0, 110.0)], speech=[])
    talking = score_frames(frames_at(still), segments=[(99.0, 110.0)], speech=[(103.0, 105.5)])
    assert all("standby" in s.failed for s in quiet[1:4])
    assert "standby" not in talking[2].failed and "standby" not in talking[1].failed   # paused game, live commentary
    no_words = score_frames(frames_at(still), segments=[(99.0, 110.0)], loudness=lambda t: -70.0)
    assert "standby" in no_words[2].failed                                     # no transcript: silence by level


def test_a_paused_game_with_the_streamer_on_camera_is_not_standby(face_gray):
    pic = with_camera(face_gray, 0)
    scored = score_frames(frames_at([pic] * 4), cam=CAM, segments=[(99.0, 108.0)], speech=[(100.0, 107.0)])
    assert not any("standby" in s.failed for s in scored)


def test_without_a_camera_a_face_cut_by_the_layouts_crop_loses(face_gray):
    import cv2
    pic = cv2.resize(face_gray, (360, 360))
    frame = np.zeros((360, 640), np.uint8)
    frame[:, 140:500] = pic                                                   # the face is near the middle
    view_whole, view_cut = ((0.2, 0.0, 0.6, 1.0),), ((0.0, 0.0, 0.42, 1.0),)
    whole = score_frames(frames_at([frame] * 3), segments=[(99.0, 106.0)], view=view_whole)
    cut = score_frames(frames_at([frame] * 3), segments=[(99.0, 106.0)], view=view_cut)
    assert all(s.face is True for s in whole)
    assert all(s.face is False and "face_cut" in s.failed for s in cut)


# --- the text ------------------------------------------------------------------------------------------------------
def inside_safe(block, canvas: Canvas) -> None:
    w, h = canvas.size
    x0, y0, x1, y1 = block.box()
    span = (canvas.span[0] * w, canvas.span[1] * w)
    assert span[0] - 0.5 <= x0 and x1 <= span[1] + 0.5, (x0, x1)               # never past the margins
    assert 0 <= y0 and y1 <= h
    assert len(block.lines) <= MAX_LINES


@pytest.mark.parametrize("aspect", list(SIZES))
@pytest.mark.parametrize("text", ["Clean escape", "He did NOT see that coming",
                                  "Worst getaway driver in Los Santos history and the cops still did not catch him",
                                  " ".join(["unbelievable"] * 40), "A" * 120])
def test_text_wraps_or_shrinks_and_never_overflows(aspect, text):
    canvas = Canvas(SIZES[aspect])
    block = fit_text(text, canvas)
    assert block is not None
    inside_safe(block, canvas)
    if len(text) > 200:                                                       # cannot fit: cut short, not spilled
        assert block.lines[-1][-1].endswith("…")


def test_short_text_is_big_and_long_text_is_smaller_but_still_legible():
    canvas = Canvas(SIZES["9:16"])
    short = fit_text("Clean escape", canvas)
    hook = fit_text("Worst getaway driver in Los Santos history", canvas)
    title = fit_text("Worst getaway driver in Los Santos history and the cops never caught him", canvas)
    assert len(short.lines) == 1 and short.cap >= 0.09 * 720
    assert len(hook.lines) == 3 and hook.cap == short.cap                    # wraps first, at full size
    assert title.cap < short.cap and title.cap >= 0.055 * 720 - 1             # then shrinks: at 270 px, capitals >= 14 px
    for block in (hook, title):
        assert max(block.widths) - min(block.widths) < 0.5 * max(block.widths)   # balanced, no lone last word


def test_text_keeps_off_the_head_and_sits_on_the_seam_when_it_can():
    w, h = SIZES["9:16"]
    seam = Canvas((w, h), seam=427.0)
    block = fit_text("He did NOT see that coming", seam)
    assert abs((block.top + block.height / 2) - 427) < 2
    head = (150.0, 60.0, 570.0, 420.0)                                        # the head reaches down to the seam
    off = fit_text("He did NOT see that coming", Canvas((w, h), avoid=(head,), seam=427.0))
    x0, y0, x1, y1 = off.box()
    assert y0 >= head[3] or y1 <= head[1]
    inside_safe(off, Canvas((w, h)))


def test_the_text_stays_in_the_text_span_of_a_side_by_side_layout():
    canvas = Canvas(SIZES["16:9"], span=(0.3, 1.0))
    block = fit_text("Worst getaway driver in Los Santos history", canvas)
    inside_safe(block, canvas)
    assert block.center_x == pytest.approx(0.65 * 1280)


def test_no_text_or_no_font_for_its_letters_gives_no_block(monkeypatch):
    canvas = Canvas(SIZES["9:16"])
    assert fit_text(None, canvas) is None and fit_text("  ...  ", canvas) is None
    monkeypatch.setattr(thumbs, "FONTS", (thumbs.FONTS[0],))                 # Anton only: no Cyrillic, no CJK
    assert fit_text("Привет мир", canvas) is None and fit_text("最高の瞬間", canvas) is None
    assert fit_text("Ça part en vrille", canvas) is not None                 # Latin with accents is Anton's


def test_thumb_text_is_the_hook_then_the_title_and_censors():
    assert thumb_text({"hook": "No way", "title": "A title"}) == "No way"
    assert thumb_text({"hook": None, "title": "A title"}) == "A title"
    assert thumb_text({"hook": "", "title": ""}) is None and thumb_text(None) is None
    assert thumb_text({"hook": "what the fuck"}, censor=True) == "what the f***"


def test_write_thumbnail_draws_only_inside_the_block(tmp_path):
    frame = tmp_path / "f.jpg"
    Image.fromarray(np.dstack([textured(2)] * 3)).resize((720, 1280)).save(frame, quality=95)
    canvas = Canvas((720, 1280), seam=427.0)
    out = tmp_path / "t.jpg"
    assert write_thumbnail(frame, out, "He did NOT see that coming", canvas) is True
    with Image.open(out) as im, Image.open(frame) as before:
        assert im.size == (720, 1280)
        changed = ImageChops.difference(im.convert("L"), before.convert("L")).point(lambda v: 255 if v > 40 else 0)
    block = fit_text("He did NOT see that coming", canvas)
    x0, y0, x1, y1 = changed.getbbox()
    bx0, by0, bx1, by1 = block.box()
    slack = 0.15 * block.px                                                   # the soft shadow falls a little outside
    assert bx0 - slack <= x0 and x1 <= bx1 + slack and by0 - slack <= y0 and y1 <= by1 + slack
    assert write_thumbnail(frame, tmp_path / "none.jpg", None, canvas) is False


def test_a_canvas_survives_the_clips_features():
    canvas = Canvas((720, 1280), avoid=((1.0, 2.0, 3.0, 4.0),), seam=427.0, span=(0.0, 1.0))
    from dataclasses import asdict
    record = json.loads(json.dumps({"canvas": {**asdict(canvas), "size": [720, 1280]}}))
    assert canvas_of(record) == canvas
    assert canvas_of({}) is None and canvas_of({"canvas": {"size": "x"}}) is None


# --- the whole thumbnail on real video -------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def long_gop(tmp_path_factory) -> Path:
    """12 s of moving test pattern with one keyframe every 10 s: a 1 s clip has no keyframe inside it."""
    path = tmp_path_factory.mktemp("gop") / "gop.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=12",
                    "-c:v", "libx264", "-preset", "ultrafast", "-g", "300", "-keyint_min", "300", "-sc_threshold", "0",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_a_clip_shorter_than_the_keyframe_spacing_uses_its_middle(long_gop, tmp_path):
    info = probe(long_gop)
    made = make_thumbnail(long_gop, info, 3.0, 4.0, tmp_path / "clip-1.jpg", options=PipelineOptions(),
                          layout="fill", facecam=None, text="Tiny clip")
    assert made.path.exists() and made.frame.exists()
    assert made.record["frames"] == 0 and made.record["at"] == pytest.approx(3.5, abs=0.05)
    assert made.record["text"] is True
    with Image.open(made.path) as im:
        assert im.size == (360, 640)                                          # never above the source's own size
    assert not any(p.suffix == ".mp4" or p.name.endswith(".frames") for p in tmp_path.iterdir())   # scratch is gone


@pytest.mark.parametrize("aspect,vertical,size", [("9:16", True, (360, 640)), ("4:5", True, (360, 450)),
                                                  ("1:1", True, (360, 360)), ("9:16", False, (640, 360))])
def test_every_aspect_gets_a_thumbnail_of_its_own_shape(video, tmp_path, aspect, vertical, size):
    info = probe(video)
    made = make_thumbnail(video, info, 10.0, 30.0, tmp_path / "c.jpg", options=PipelineOptions(aspect=aspect, vertical=vertical),
                          layout="fill", facecam=None, text="He did NOT see that coming", loudness=[-40.0] * 40)
    with Image.open(made.path) as im:
        assert im.size == size
    assert made.record["frames"] >= 1 and 10.0 <= made.record["at"] <= 30.0 and made.record["text"] is True


def test_the_pipeline_gives_every_clip_a_thumbnail_with_its_hook(video, transcriber, tmp_path):
    def judge(text, frame, context):
        return {"title": "A title", "hook": "No way he made that", "virality": {"score": 80}}
    results = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False), tmp_path / "out",
                           transcriber=transcriber, judge=judge)
    r = results[0]
    assert r.thumb_path.exists() and r.frame_path.exists() and r.thumb_path != r.frame_path
    record = r.features["thumbnail"]
    assert record["text"] is True and r.start <= record["at"] <= r.end
    json.dumps(r.features)                                                    # stored as JSON with the clip
    with Image.open(r.thumb_path) as im:
        assert im.size == (360, 640)


def test_the_worker_sets_the_ais_title_on_a_thumbnail_made_without_one(video, tmp_path):
    """A clip whose words came after it was rendered (the find tool, or a judge that failed for it)."""
    info = probe(video)
    made = make_thumbnail(video, info, 10.0, 30.0, tmp_path / "c.jpg", options=PipelineOptions(), layout="fill",
                          facecam=None)
    assert made.record["text"] is False
    plain = made.path.read_bytes()
    canvas = canvas_of(json.loads(json.dumps(made.record)))
    assert write_thumbnail(made.frame, made.path, thumb_text({"title": "Clean escape"}), canvas) is True
    assert made.path.read_bytes() != plain


def test_a_failed_thumbnail_never_fails_the_clip(video, transcriber, tmp_path, monkeypatch):
    import app.pipeline as pipeline

    def broken(*args, **kwargs):
        raise thumbs.PipelineError("media_error", "Could not read this video.")
    monkeypatch.setattr(pipeline, "make_thumbnail", broken)
    results = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False), tmp_path / "out", transcriber=transcriber)
    assert results[0].video_path.exists() and results[0].thumb_path is None and "thumbnail" not in results[0].features


class LateAI:
    """The judge fails for every candidate, so the worker asks for each clip's title after it is rendered."""
    def __init__(self):
        self.title_frames = []

    def clip_meta(self, transcript, context, thumb=None):
        from app.ai import parse_meta
        if "window" in context:                                               # a judge call: no answer
            return None
        self.title_frames.append(thumb)
        return parse_meta({"titles": ["Clean escape", "b", "c"], "hook": "No way he made that", "hashtags": ["gta6"],
                           "virality": {"hook": 70, "flow": 60, "value": 80, "trend": 50}, "reason": "r",
                           "kind": "clutch"})


def test_a_worker_job_sets_the_ais_late_hook_on_the_thumbnail(client, user, video, transcriber):
    from app import worker
    from app.db import new_session
    from app.models import Clip
    from tests.test_api import upload
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/clips", headers=headers, json={"upload_id": up["upload_id"],
                                                        "options": {"max_clips": 1, "clip_length": 10}})
    assert r.status_code == 202, r.text
    ai = LateAI()
    assert worker.run_once(transcriber, ai=ai) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    clip, = job["clips"]
    assert clip["thumb_url"] and clip["hook"] == "No way he made that"
    assert [Path(p).name.endswith(".frame.jpg") for p in ai.title_frames] == [True]   # the AI saw the frame, no text
    with new_session() as db:
        assert db.get(Clip, clip["id"]).features["thumbnail"]["text"] is True
