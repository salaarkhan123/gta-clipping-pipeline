"""Reframe layouts: which ones exist, what each scene type gets, and the rule that people are never blurred,
cropped out or cut by a panel edge. Rendered checks use a colour-coded stream: gameplay with no green in it at
all, a pure green camera box over it and a yellow "face" inside the camera."""
import itertools
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from app.pipeline import facecam as F
from app.pipeline import layouts as L
from app.pipeline.captions import build_ass
from app.pipeline.ff import MediaInfo, PipelineError, probe
from app.pipeline.render import layout_filter, plan_for, render_clip
from app.render_options import LayoutOptions
from tests.test_facecam_rect import scene

SW, SH = 1280, 720
# Camera boxes (pixels in the 1280x720 stream) and the face inside each: a webcam in the top-right corner, one at
# the bottom left of centre (where the benchmark stream has it), and one in the middle of the frame.
CORNER = ((960, 0, 320, 180), (1090, 50, 60, 80))
BOTTOM = ((220, 566, 238, 152), (294, 590, 90, 100))
MIDDLE = ((538, 252, 204, 180), (610, 300, 60, 80))


def frac(box, w=SW, h=SH):
    return [box[0] / w, box[1] / h, box[2] / w, box[3] / h]


def face_of(box, w=SW, h=SH):
    """A pixel box as a detected face: (centre x, centre y, width, height) fractions."""
    return (box[0] + box[2] / 2) / w, (box[1] + box[3] / 2) / h, box[2] / w, box[3] / h


def make_stream(path, cam, face, size=(SW, SH), seconds=3):
    x, y, w, h = cam
    fx, fy, fw, fh = face
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"mandelbrot=size={size[0]}x{size[1]}:rate=15:end_scale=0.01,format=rgb24,lutrgb=g=0,trim=duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-vf", f"drawbox=x={x}:y={y}:w={w}:h={h}:color=0x00ff00:t=fill,"
                           f"drawbox=x={fx}:y={fy}:w={fw}:h={fh}:color=0xffff00:t=fill",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def streams(tmp_path_factory):
    d = tmp_path_factory.mktemp("layouts")
    return {name: make_stream(d / f"{name}.mp4", cam, face)
            for name, (cam, face) in (("corner", CORNER), ("bottom", BOTTOM), ("middle", MIDDLE))}


def frame(video, t=0.5) -> np.ndarray:
    info = probe(video)
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(info.height, info.width, 3).astype(int)


def camera(img):
    """Pixels that can only come from the camera: green, or the yellow face (the gameplay has no green at all)."""
    return (img[..., 1] > 150) & (img[..., 2] < 100)


def face_pixels(img):
    return (img[..., 0] > 180) & (img[..., 1] > 180) & (img[..., 2] < 100)


SHARP = 0.04      # the most of a camera picture that may be half-way between face and background


def smeared(img) -> float:
    """The share of the camera picture that is neither the green background nor the yellow face but something in
    between. A sharp camera has only the thin outline of the face (2% at most); a blurred one has the face smeared
    across it (11%: see test_the_sharpness_check_notices_a_blurred_camera)."""
    cam = camera(img)
    assert cam.sum(), "no camera in the picture at all"
    return float((cam & (img[..., 0] > 60) & (img[..., 0] < 190)).sum() / cam.sum())


def render(src, out, plan=None, **kw):
    info = probe(src)
    render_clip(src, 0.5, 1.5, out, src_w=info.width, src_h=info.height, vertical=kw.pop("vertical", True), zoom=1.0,
                chat="none", words=kw.pop("words", []), font="DejaVu Sans", plan=plan, **kw)
    return probe(out)


def rounded(src):
    """The crop ffmpeg really takes for a panel (render rounds every number down to an even one)."""
    return tuple(L.even(v) for v in src)


def check_people(plan: L.LayoutPlan, src_w=SW, src_h=SH) -> None:
    """The rule, on a plan: every panel either shows the whole person box (and the whole head) or none of it, at
    least one panel shows them, and the blurred backdrop never has them in it."""
    whole = [b for b in ([L.cam_px(plan.cam, src_w, src_h)] if plan.cam and plan.scene == "gameplay_cam" else [])]
    face = None
    if plan.face:
        cx, cy, fw, fh = plan.face
        face = ((cx - fw / 2) * src_w, (cy - fh / 2) * src_h, fw * src_w, fh * src_h)
    shown = 0
    for p in plan.panels:
        crop = rounded(p.src)
        if face is not None:
            assert L._inside(face, crop) or not L._overlaps(face, crop), (plan.layout, p.kind, "face cut by a panel edge")
            head = L.head_box(plan.face, src_w, src_h)
            assert L._inside(head, crop, tol=4) or not L._overlaps(head, crop), (plan.layout, p.kind, "head cut")
            shown += L._inside(face, crop)
        elif whole:
            # No face known (a preset or a box the user drew): the camera panel may trim the box to its own shape,
            # as it always has, but a gameplay picture never shows part of the camera.
            if p.kind != "camera":
                assert L._inside(whole[0], crop, tol=4) or not L._overlaps(whole[0], crop), (plan.layout, p.kind)
            shown += L._overlaps(whole[0], crop)
        assert not (p.punch and (face is not None and L._overlaps(face, crop))), "a panel with a person is never zoomed"
    if face is not None or whole:
        assert shown >= 1, (plan.layout, "the person was cropped out")
        if face is not None:
            assert shown == 1, (plan.layout, "the person is shown twice")
    if plan.background is not None:
        for box in whole + ([L.head_box(plan.face, src_w, src_h)] if plan.face else []):
            assert not L._overlaps(box, rounded(plan.background)), "a person in the blurred backdrop"


# ---------- which layouts exist ----------
def test_the_layout_names_and_the_allowed_set_per_aspect_are_the_contract():
    assert L.LAYOUTS == ("auto", "full", "fit", "split2", "trio", "grid4", "pip", "ots", "screen_first", "gameplay_a", "gameplay_b")
    assert {a: set(v) for a, v in L.ALLOWED.items()} == {
        "16:9": {"auto", "full", "fit", "grid4", "split2", "trio", "pip", "ots", "screen_first"},
        "9:16": {"auto", "full", "fit", "grid4", "split2", "trio", "pip", "screen_first", "gameplay_a", "gameplay_b"},
        "1:1": {"auto", "full", "fit", "grid4", "trio"},
        "4:5": {"auto", "full", "fit", "grid4", "split2", "trio", "pip", "screen_first", "gameplay_a", "gameplay_b"}}
    assert all(set(v) <= set(L.LAYOUTS) for v in L.ALLOWED.values()) and set(L.NOT_BUILT) == set()


BUILT_PAIRS = [(a, name) for a in L.ALLOWED for name in L.ALLOWED[a] if name in L.BUILT]
BAD_PAIRS = [(a, name) for a in L.ALLOWED for name in L.LAYOUTS if name not in L.ALLOWED[a]]


@pytest.mark.parametrize("aspect,name", BAD_PAIRS)
def test_a_layout_the_aspect_does_not_offer_is_rejected_with_a_clear_error(aspect, name):
    with pytest.raises(PipelineError) as e:
        L.check_layout(name, aspect)
    assert e.value.code == "bad_options" and f"not available in {aspect}" in e.value.message and "Use one of" in e.value.message
    with pytest.raises(PipelineError):
        L.plan_layout(MediaInfo(60, SW, SH, True), [], name, aspect)
    with pytest.raises(ValidationError) as v:
        LayoutOptions(layout=name, aspect=aspect)
    assert f"not available in {aspect}" in str(v.value)


@pytest.mark.parametrize("name", L.NOT_BUILT)
def test_trio_grid4_and_ots_are_not_built_and_are_never_faked(name, streams, tmp_path):
    info = MediaInfo(60, SW, SH, True)
    for call in (lambda: L.plan_layout(info, [], name, "16:9"), lambda: L.compose(SW, SH, name, "16:9", cam=frac(CORNER[0])),
                 lambda: render(streams["corner"], tmp_path / "x.mp4", layout=name, aspect="16:9"),
                 lambda: F.resolve_facecam(streams["corner"], info, SimpleNamespace(
                     vertical=True, aspect="16:9", layout=name, facecam_region="auto", facecam_box=None, zoom=1.0))):
        with pytest.raises(PipelineError) as e:
            call()
        assert e.value.code == "layout_unavailable" and "not available yet" in e.value.message
    assert not (tmp_path / "x.mp4").exists()
    with pytest.raises(ValidationError) as v:
        LayoutOptions(layout=name, aspect="16:9")
    assert "not available yet" in str(v.value)


# ---------- scene type ----------
def test_scene_type_gameplay_with_a_webcam_a_camera_that_fills_the_frame_or_gameplay_alone(monkeypatch):
    info = MediaInfo(600, 640, 360, True)
    frames, face = scene((400, 60, 180, 120))                           # a webcam box over changing gameplay
    monkeypatch.setattr(F, "stable_face", lambda _f: face)
    s = F.classify(frames)
    assert s.kind == "gameplay_cam" and s.face == face and all(abs(a - b) < 0.01 for a, b in zip(s.cam, frac((400, 60, 180, 120), 640, 360)))
    assert L.plan_layout(info, frames, "auto", "9:16").layout == "split2"     # both in view
    assert L.plan_layout(info, frames, "auto", "16:9").layout == "full"       # a wide frame already holds both

    cut, cut_face = scene((300, 180, 180, 120), cutout=True)            # a cut-out camera: no rectangle to find
    monkeypatch.setattr(F, "stable_face", lambda _f: cut_face)
    s = F.classify(cut)
    assert s.kind == "gameplay_cam" and s.cam == F.face_crop(cut_face)

    room, room_face = scene((0, 0, 640, 360))                           # the room is the whole picture
    monkeypatch.setattr(F, "stable_face", lambda _f: room_face)
    assert F.classify(room).kind == "camera" and F.still_share(room) > 0.8 and F.still_share(frames) < 0.3
    plan = L.plan_layout(info, room, "auto", "9:16")
    assert (plan.scene, plan.layout) == ("camera", "full")
    check_people(plan, 640, 360)

    monkeypatch.setattr(F, "stable_face", lambda _f: (0.5, 0.45, 0.4, 0.6))   # a face this big is a full-screen camera
    assert F.classify(frames).kind == "camera" and F.find_face(frames) is None

    monkeypatch.setattr(F, "stable_face", lambda _f: None)
    assert F.classify(frames) == F.Scene("gameplay")
    plan = L.plan_layout(info, frames, "auto", "9:16")
    assert (plan.scene, plan.layout, plan.note) == ("gameplay", "full", None)
    plan = L.plan_layout(info, frames, "pip", "9:16")                   # nothing to inset: the gameplay fills the frame
    assert (plan.requested, plan.layout) == ("pip", "full") and "No webcam" in plan.note


def test_a_camera_that_fills_the_frame_is_centred_on_the_person_or_shown_whole():
    face = (0.72, 0.4, 0.12, 0.2)                                       # sitting to the right of a full-screen camera
    plan = L.compose(1920, 1080, "full", "9:16", scene="camera", face=face)
    x, _y, w, _h = plan.panels[0].src
    assert plan.layout == "full" and abs((x + w / 2) / 1920 - 0.72) < 0.01 and not plan.panels[0].punch
    check_people(plan, 1920, 1080)
    assert L.compose(1920, 1080, "full", "9:16", scene="gameplay").panels[0].src[0] == pytest.approx((1920 - 607.5) / 2)
    close = L.compose(1920, 1080, "full", "9:16", scene="camera", face=(0.5, 0.5, 0.36, 0.6))    # too big for a 9:16 crop
    assert close.layout == "fit" and close.background is None and "boxblur" not in L.layout_graph(close)
    check_people(close, 1920, 1080)
    for name in ("split2", "pip", "gameplay_a"):                        # there is no separate gameplay to place
        assert L.compose(1920, 1080, name, "9:16", scene="camera", face=face).layout == "full"


# ---------- the rule: people are never blurred, cropped out or cut ----------
def test_a_face_is_never_cut_by_a_panel_edge_wherever_the_camera_is():
    checked, drawn = 0, set()
    sources = ((1920, 1080), (1280, 720), (1080, 1920))
    cams = [(x, y, w, h) for w, h in ((0.16, 0.25), (0.25, 0.25), (0.30, 0.30), (0.20, 0.36), (0.45, 0.4))
            for x in (0.0, 0.17, 0.42, 1 - w) for y in (0.0, 0.35, 1 - h)]
    spots = ((0.5, 0.45), (0.2, 0.2), (0.8, 0.25), (0.5, 0.8))          # where in the camera box the face is
    names = [n for n in L.BUILT] + ["split", "fill"]
    # The two-panel layouts are also checked with the camera on either side and at every panel size a user can ask for.
    plain = [(None, None)]
    adjusted = [(side, ratio) for side in (None, "top", "bottom") for ratio in (None, 0.25, 0.4, 0.6, 0.75)]
    resized = 0
    for (sw, sh), cam, spot, aspect, name in itertools.product(sources, cams, spots, L.ALLOWED, names):
        fw, fh = 0.3 * cam[2], 0.3 * cam[2] * sw / sh * 1.2
        if fh > 0.8 * cam[3]:
            continue
        cx = cam[0] + fw / 2 + spot[0] * (cam[2] - fw)
        cy = cam[1] + fh / 2 + spot[1] * (cam[3] - fh)
        for face in ((cx, cy, fw, fh), None):
            for side, ratio in (adjusted if name in L.TWO_PANEL + ("split", "auto") else plain):
                plan = L.compose(sw, sh, name, aspect, cam=cam, face=face, camera=side, split_ratio=ratio)
                check_people(plan, sw, sh)
                assert "boxblur" not in L.layout_graph(plan) or plan.layout == "fit"
                checked, _ = checked + 1, drawn.add(plan.layout)
                if plan.layout in L.TWO_PANEL and (side or ratio):
                    first, second = plan.panels
                    stacked = first.out[2] == plan.size[0]
                    if side:
                        assert (first.kind == "camera") == (side == "top")
                    if ratio:
                        length = plan.size[1] if stacked else plan.size[0]
                        assert first.out[3 if stacked else 2] == L.even(length * ratio)
                    assert first.out[2] * first.out[3] + second.out[2] * second.out[3] == plan.size[0] * plan.size[1]
                    resized += 1
    assert checked > 50000 and resized > 10000 and drawn == set(L.BUILT) - {"auto"}


def test_the_camera_that_used_to_be_blurred_is_now_shown_where_it_is(streams, tmp_path):
    cam, face = frac(MIDDLE[0]), face_of(MIDDLE[1])
    how, rect = L.avoid_camera(SW, SH, 1080, 1280, 1.0, cam, max_zoom=L.MAX_AVOID_ZOOM)
    assert (how, rect) == ("blocked", None)                             # no step and no zoom clears it
    for name in ("split2", "gameplay_a", "gameplay_b", "screen_first", "pip", "full", "auto"):
        plan = L.compose(SW, SH, name, "9:16", cam=cam, face=face)
        assert plan.layout == "full" and "boxblur" not in L.layout_graph(plan), name
        assert (plan.note is None) == (name == "full")                  # the plan says when it drew something else
        check_people(plan)
    info = render(streams["middle"], tmp_path / "m.mp4", layout="split", facecam=F.CamBox(cam, face, "gameplay_cam"))
    img = frame(tmp_path / "m.mp4")
    assert (info.width, info.height) == (1080, 1920) and smeared(img) < SHARP
    k = 1920 / 720                                                      # the full-height crop, scaled to the frame
    assert camera(img).sum() == pytest.approx(MIDDLE[0][2] * MIDDLE[0][3] * k * k, rel=0.05)     # all of it, once
    assert face_pixels(img).sum() == pytest.approx(MIDDLE[1][2] * MIDDLE[1][3] * k * k, rel=0.08)


def test_the_sharpness_check_notices_a_blurred_camera(streams, tmp_path):
    """The patch the split layout used to put over a camera it could not step around, applied by hand: the
    check the other tests rely on has to fail on it."""
    x, y, w, h = CORNER[0]
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(streams["corner"]), "-filter_complex",
                    f"[0:v]split=2[b0][b1];[b1]crop={w}:{h}:{x}:{y},boxblur=20:3[cam];[b0][cam]overlay={x}:{y},"
                    "crop=404:720:876:0,scale=1080:1920[v]", "-map", "[v]", "-t", "1", "-c:v", "libx264", "-preset", "ultrafast",
                    str(tmp_path / "blur.mp4")], check=True)
    assert smeared(frame(tmp_path / "blur.mp4")) > 2 * SHARP             # 0.11; the sharpest real render is 0.00, the softest 0.02


def test_a_gameplay_panel_zooms_in_a_little_rather_than_give_up_on_a_camera_at_the_bottom():
    cam, face = frac(BOTTOM[0]), face_of(BOTTOM[1])
    assert L.avoid_camera(SW, SH, 1080, 960, 1.0, cam, face)[0] == "blocked"
    how, rect = L.avoid_camera(SW, SH, 1080, 960, 1.0, cam, face, L.MAX_AVOID_ZOOM)
    assert how == "zoomed" and rect[3] >= SH / L.MAX_AVOID_ZOOM - 1                 # never more than the limit
    assert not L._overlaps(rect, BOTTOM[0]) and L._inside(rect, (0, 0, SW, SH))     # the camera is out, all of it
    assert L.compose(SW, SH, "gameplay_a", "9:16", cam=cam, face=face).layout == "gameplay_a"
    assert L.avoid_camera(SW, SH, 1080, 1280, 1.0, cam)[0] == "shifted"         # the split panel still only steps aside


# ---------- every layout, rendered ----------
def expected_face_area(plan, face_px, size):
    """The face's size in the output, from the one panel that shows it."""
    sx, sy = size[0] / plan.size[0], size[1] / plan.size[1]
    (p,) = [p for p in plan.panels if L._inside(face_px, rounded(p.src))]
    _x, _y, w, h = L._scaled(p.out, sx, sy)
    crop = rounded(p.src)
    return face_px[2] * face_px[3] * (w / crop[2]) * (h / crop[3]), p


@pytest.mark.parametrize("aspect,name", BUILT_PAIRS)
def test_every_layout_renders_at_the_right_size_with_the_camera_whole_and_sharp(aspect, name, streams, tmp_path):
    for which, (cam_px, face_px) in (("corner", CORNER), ("bottom", BOTTOM)):
        if which == "bottom" and aspect not in ("9:16", "16:9"):
            continue                                                    # the plan-level test covers every position
        plan = L.compose(SW, SH, name, aspect, cam=frac(cam_px), face=face_of(face_px))
        check_people(plan)
        out = tmp_path / f"{which}.mp4"
        info = render(streams[which], out, plan=plan)
        assert (info.width, info.height) == L.ASPECTS[aspect] and info.has_audio
        img = frame(out)
        want, panel = expected_face_area(plan, face_px, L.ASPECTS[aspect])
        assert face_pixels(img).sum() == pytest.approx(want, rel=0.1), (which, plan.layout)      # the whole face, once
        ys, xs = np.nonzero(face_pixels(img))
        shape = (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)
        crop = rounded(panel.src)
        assert shape == pytest.approx(face_px[2] / face_px[3] * (panel.out[2] / crop[2]) / (panel.out[3] / crop[3]), rel=0.1)
        assert smeared(img) < SHARP, (which, plan.layout)               # sharp: never a blurred copy
        for p in plan.panels:                                           # and no gameplay picture shows the camera again
            if p.punch:
                x, y, w, h = p.out
                area = camera(img)[y + 4:y + h - 4, x + 4:x + w - 4].copy()
                for q in plan.panels:
                    if q is not p:                                      # the inset sits on top of the gameplay
                        qx, qy, qw, qh = q.out
                        area[max(0, qy - y - 8):qy - y + qh + 8, max(0, qx - x - 8):qx - x + qw + 8] = False
                assert area.sum() == 0, (which, plan.layout)


def test_the_panels_are_where_each_layout_says(streams, tmp_path):
    cam, face = frac(CORNER[0]), face_of(CORNER[1])

    def where(name, aspect="9:16"):
        plan = L.compose(SW, SH, name, aspect, cam=cam, face=face)
        assert plan.layout == name
        render(streams["corner"], tmp_path / "w.mp4", plan=plan)
        ys, xs = np.nonzero(camera(frame(tmp_path / "w.mp4")))
        h, w = L.ASPECTS[aspect][1], L.ASPECTS[aspect][0]
        return ys.min() / h, ys.max() / h, xs.min() / w, xs.max() / w, plan

    top, bottom, _l, _r, plan = where("split2")
    assert top < 0.01 and bottom < 1 / 3 + 0.01 and plan.panels[0].kind == "camera"          # camera above, a third
    top, bottom, _l, _r, _p = where("gameplay_a")                       # PROVISIONAL: camera on top, half the frame
    assert top < 0.01 and 0.4 < bottom <= 0.5
    top, bottom, _l, _r, _p = where("gameplay_b")                       # PROVISIONAL: gameplay on top, camera below
    assert 0.5 <= top < 0.6 and bottom > 0.99
    top, bottom, _l, _r, _p = where("screen_first")                     # gameplay large, the camera in a strip under it
    assert top >= 0.69 and bottom > 0.99
    top, bottom, left, right, plan = where("pip")                       # a small inset, the gameplay behind it
    assert 0.04 < top and bottom < 0.25 and 0.03 < left and right < 0.42 and plan.panels[0].out == (0, 0, 1080, 1920)
    _t, _b, left, right, _p = where("split2", "16:9")                   # a wide frame: side by side
    assert left < 0.01 and right < 1 / 3 + 0.01
    _t, _b, left, right, plan = where("screen_first", "16:9")
    assert left >= 0.71 and right > 0.99 and plan.text_span == (0.0, pytest.approx(0.72, abs=0.01))


def test_fit_shows_the_whole_source_over_a_blurred_piece_of_gameplay_never_of_a_person(streams, tmp_path):
    cam, face = frac(CORNER[0]), face_of(CORNER[1])
    plan = L.compose(SW, SH, "fit", "9:16", cam=cam, face=face)
    (main,) = plan.panels
    assert main.kind == "source" and main.src == (0.0, 0.0, SW, SH) and main.out == (0, 656, 1080, 608)
    assert plan.background is not None and not L._overlaps(plan.background, L.cam_px(cam, SW, SH))
    assert "boxblur" in L.layout_graph(plan)
    render(streams["corner"], tmp_path / "fit.mp4", plan=plan)
    img = frame(tmp_path / "fit.mp4")
    bars = np.concatenate([img[:650], img[1270:]])
    assert (bars[..., 1] > 60).sum() == 0                               # not a trace of the camera in the bars
    assert bars.std() > 2                                               # and they are a picture, not black
    k = 1080 / SW
    assert camera(img[656:1264]).sum() == pytest.approx(CORNER[0][2] * CORNER[0][3] * k * k, rel=0.05)
    assert smeared(img) < SHARP
    same =L.compose(SW, SH, "fit", "16:9", cam=cam, face=face)         # nothing to letterbox: just the source
    assert same.panels[0].out == (0, 0, 1920, 1080) and same.background is None
    middle = L.compose(SW, SH, "fit", "1:1", cam=[0.1, 0.1, 0.8, 0.8])  # no camera-free piece: plain black bars
    assert middle.background is None and "pad=" in L.layout_graph(middle)


def test_punch_in_zooms_only_ever_play_on_a_panel_with_no_person_in_it():
    expr = "1+0.150*min(1,max(0,1-abs(t-4.20)/0.6))"
    cam, face = frac(CORNER[0]), face_of(CORNER[1])
    for name in ("split2", "gameplay_a", "gameplay_b", "screen_first", "pip"):
        plan = L.compose(SW, SH, name, "9:16", cam=cam, face=face)
        assert [p.punch for p in plan.panels] == [p.kind == "gameplay" for p in plan.panels]
        graph = L.layout_graph(plan, punch=expr)
        assert graph.count("eval=frame") == 1
    held = L.compose(SW, SH, "full", "1:1", cam=frac(BOTTOM[0]), face=face_of(BOTTOM[1]))    # the camera stays in the picture
    assert held.layout == "full" and "eval=frame" not in L.layout_graph(held, punch=expr)
    assert "eval=frame" in L.layout_graph(L.compose(SW, SH, "full", "9:16"), punch=expr)     # gameplay alone


def test_captions_and_the_hook_stay_off_the_camera_when_it_is_under_the_gameplay():
    cam, face = frac(CORNER[0]), face_of(CORNER[1])
    for name in ("gameplay_b", "screen_first"):
        plan = L.compose(SW, SH, name, "9:16", cam=cam, face=face)
        seam = plan.panels[1].out[1]
        assert plan.caption_top + 78 + 20 < seam and plan.hook_top < plan.caption_top     # all text on the gameplay
    pip = L.compose(SW, SH, "pip", "9:16", cam=cam, face=face)
    inset = pip.panels[1].out
    assert pip.hook_top >= inset[1] + inset[3]                          # the hook goes under the inset, not over it


def test_text_is_centred_on_the_gameplay_when_the_camera_panel_is_beside_it(tmp_path):
    words = [(0.0, 0.5, "hi")]
    build_ass(words, tmp_path / "wide.ass", True, 756, "DejaVu Sans", play=(1920, 1080), hook="look", hook_top=194, span=(1 / 3, 1.0))
    styles = [line for line in (tmp_path / "wide.ass").read_text().splitlines() if line.startswith("Style:")]
    assert ",2,700,60," in styles[0] and ",8,730,90,194," in styles[1]          # left margin moved in by the camera panel
    build_ass(words, tmp_path / "plain.ass", True, 756, "DejaVu Sans", play=(1920, 1080), hook="look", hook_top=194)
    styles = [line for line in (tmp_path / "plain.ass").read_text().splitlines() if line.startswith("Style:")]
    assert ",2,60,60," in styles[0] and ",8,90,90,194," in styles[1]            # everywhere else: as before


# ---------- old names ----------
def test_the_old_layout_names_still_work_and_draw_what_they_always_drew(streams, tmp_path):
    for aspect in L.ALLOWED:
        for old in L.LEGACY:
            assert LayoutOptions(layout=old, aspect=aspect).layout == old       # accepted in every shape, as before
    assert L.canonical("split", "9:16") == "split2" and L.canonical("fill", "9:16") == "full"
    assert L.canonical("split", "16:9") == "full" and L.canonical("classic", "1:1") == "full"
    assert L.canonical("classic", "9:16") == "classic" and L.legacy_name("split2") == "split" and L.legacy_name("full") == "fill"
    assert layout_filter(1920, 1080, "split", 1.0, "none", "top-right") == layout_filter(1920, 1080, "split2", 1.0, "none", "top-right")
    assert layout_filter(1920, 1080, "fill", 1.0, "none", None) == layout_filter(1920, 1080, "full", 1.0, "none", None)
    # The graphs themselves have not changed shape.
    assert layout_filter(1920, 1080, "fill", 1.0, "none", None) == "[0:v]crop=606:1080:656:0,scale=1080:1920,setsar=1,format=yuv420p[v]"
    assert layout_filter(1920, 1080, "split", 1.0, "none", "top-right") == (
        "[0:v]split=2[a][b];[a]crop=546:324:1358:0,scale=1080:640,setsar=1[top];"
        "[b]crop=910:1080:394:0,scale=1080:1280,setsar=1[bot];[top][bot]vstack=inputs=2,format=yuv420p[v]")
    assert "boxblur=25:2" in layout_filter(1920, 1080, "classic", 1.0, "none", None)             # the old blurred layout
    plan = plan_for(1920, 1080, "split", "top-right")
    assert (plan.layout, plan.caption_top, plan.hook_top) == ("split2", 580, 760)                # captions on the seam
    assert (plan_for(1920, 1080, "fill", None).caption_top, plan_for(1920, 1080, "fill", None).hook_top) == (1344, 345)
    for old, size in (("split", (1080, 1920)), ("fill", (1080, 1920)), ("classic", (1080, 1920))):
        info = render(streams["corner"], tmp_path / f"{old}.mp4", layout=old, facecam="top-right" if old == "split" else None)
        assert (info.width, info.height) == size


def test_resolve_facecam_gives_old_callers_the_names_they_know_and_a_plain_box():
    info = MediaInfo(60, SW, SH, True)

    def options(**kw):
        return SimpleNamespace(**{"vertical": True, "aspect": "9:16", "layout": "auto", "facecam_region": None,
                                  "facecam_box": None, "zoom": 1.0, **kw})
    assert F.resolve_facecam("x", info, options()) == ("fill", None)
    layout, cam = F.resolve_facecam("x", info, options(facecam_region="top-right"))
    assert layout == "split" and cam == list(L.FACECAM_REGIONS["top-right"]) and isinstance(cam, list)
    assert F.resolve_facecam("x", info, options(layout="pip", facecam_box=frac(CORNER[0])))[0] == "pip"
    assert F.resolve_facecam("x", info, options(layout="split", aspect="16:9", facecam_region="top-left"))[0] == "fill"
    assert F.resolve_facecam("x", info, options(layout="fit"))[0] == "fit"
    assert F.resolve_facecam("x", info, options(vertical=False, layout="auto")) == ("fill", None)
    for name in ("split", "split2", "pip", "gameplay_a"):               # a camera layout with the camera switched off
        with pytest.raises(PipelineError) as e:
            F.resolve_facecam("x", info, options(layout=name))
        assert e.value.code == "bad_options" and "facecam_region" in e.value.message
    with pytest.raises(PipelineError) as e:
        F.resolve_facecam("x", info, options(layout="gameplay_a", aspect="1:1"))
    assert e.value.code == "bad_options"
    plan = F.resolve_plan("x", info, options(layout="screen_first", facecam_box=frac(BOTTOM[0])))
    assert plan.layout == "screen_first" and plan.requested == "screen_first"
    assert F.resolve_plan("x", info, options(layout="classic")) is None


def test_a_camera_found_by_detection_carries_its_face_to_the_renderer(monkeypatch):
    cam, face = frac(BOTTOM[0]), face_of(BOTTOM[1])
    monkeypatch.setattr(F, "detect_scene", lambda *_a, **_k: F.Scene("gameplay_cam", cam, face))
    opts = SimpleNamespace(vertical=True, aspect="4:5", layout="auto", facecam_region="auto", facecam_box=None, zoom=1.0)
    layout, box = F.resolve_facecam("x", MediaInfo(60, SW, SH, True), opts)
    assert layout == "split" and box == cam and box.face == face
    # What the renderer rebuilds from (layout, box) is the plan that was decided here, box for box.
    assert replace(plan_for(SW, SH, layout, box, "4:5"), requested="auto") == F.resolve_plan("x", MediaInfo(60, SW, SH, True), opts)
    check_people(plan_for(SW, SH, layout, box, "4:5"))
    # Without the face the 4:5 camera band (2.4 to 1) would be the middle of the box and cut the top of the head.
    blind = plan_for(SW, SH, "split", cam, "4:5").panels[0].src
    assert not L._inside(L.head_box(face, SW, SH), blind)
    monkeypatch.setattr(F, "detect_scene", lambda *_a, **_k: F.Scene("camera", None, (0.7, 0.4, 0.12, 0.2)))
    layout, box = F.resolve_facecam("x", MediaInfo(60, 1920, 1080, True), SimpleNamespace(**{**opts.__dict__, "aspect": "9:16"}))
    assert layout == "fill" and box.scene == "camera"
    plan = plan_for(1920, 1080, layout, box)
    assert plan.scene == "camera" and abs((plan.panels[0].src[0] + plan.panels[0].src[2] / 2) / 1920 - 0.7) < 0.01
