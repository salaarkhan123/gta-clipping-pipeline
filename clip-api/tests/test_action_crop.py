"""Action-aware crop: calm, follows the subject, jumps at cuts, keeps off the webcam, and is drawn by render_clip."""
import subprocess
from dataclasses import replace

import numpy as np

from app.pipeline import action as A
from app.pipeline import layouts as L
from app.pipeline.ff import probe
from app.pipeline.render import render_clip

SW, CW = 1920, 608.0          # a 9:16 crop of a 1080p source is about 608 px wide


def inside(points, samples):
    return np.mean([abs(A.at(points, t) + CW / 2 - x) <= CW / 2 for t, x in samples])


def test_a_subject_that_stays_near_the_middle_never_moves_the_crop():
    rng = np.random.default_rng(1)
    samples = [(t / 4, 960 + rng.normal(0, 40)) for t in range(120)]
    (point,) = A.follow(samples, CW, SW, 30.0)
    assert abs(point[1] + CW / 2 - 960) < 30
    plan = L.compose(SW, 1080, "full", "9:16", scene="gameplay")
    tr = A.Track(tuple(t for t, _ in samples), tuple(x / SW for _, x in samples), ("motion",) * len(samples), ())
    assert A.crop_path(plan, tr, 30.0) == plan


def test_follows_a_subject_that_walks_across_the_frame_smoothly():
    rng = np.random.default_rng(2)
    samples = [(t / 4, 500 + 40 * (t / 4) + rng.normal(0, 25)) for t in range(80)]     # 500 -> 1290 px over 20 s
    path = A.follow(samples, CW, SW, 20.0)
    assert path is not None and inside(path, samples) >= 0.95
    speed, jitter = A.motion(path, 20.0)
    assert speed < 3.0 and jitter < 0.2                       # px per output frame
    naive = [(t, x - CW / 2) for t, x in samples]             # the noisy samples followed one by one shake far more
    assert A.motion(naive, 20.0)[1] > 5 * jitter


def test_never_pans_faster_than_the_limit_and_stays_in_the_frame():
    samples = [(0.0, 300.0), (1.0, 300.0), (1.5, 1700.0), (6.0, 1700.0)]
    path = A.follow(samples, CW, SW, 6.0)
    xs = [A.at(path, t) for t in np.arange(0, 6, 1 / 30)]
    assert min(xs) >= 0 and max(xs) <= SW - CW
    assert max(abs(b - a) for a, b in zip(xs, xs[1:])) <= A.MAX_PAN * SW / 30 + 1


def test_a_hard_cut_jumps_instead_of_sweeping():
    samples = [(t / 4, 400.0 if t < 20 else 1500.0) for t in range(40)]
    path = A.follow(samples, CW, SW, 10.0, cuts=[5.0])
    assert abs(A.at(path, 4.9) + CW / 2 - 400) < 150 and abs(A.at(path, 5.05) + CW / 2 - 1500) < CW / 2


def test_crop_path_moves_only_a_gameplay_panel_and_never_onto_the_webcam():
    still = A.Track(tuple(t / 4 for t in range(40)), tuple(0.2 for _ in range(40)), ("face",) * 40, ())
    plan = L.compose(SW, 1080, "full", "9:16", scene="gameplay")
    moved = A.crop_path(plan, still, 10.0)                     # a still subject off the middle: a still crop on it
    assert moved.panels[0].path is None and abs(moved.panels[0].src[0] + CW / 2 - 0.2 * SW) < 2
    tr = A.Track(tuple(t / 4 for t in range(40)), tuple(0.5 if t < 12 else 0.2 for t in range(40)), ("motion",) * 40, ())
    moved = A.crop_path(plan, tr, 10.0)
    assert moved.panels[0].path and L.reframe_boxes(moved)["crop_path"]
    assert abs(A.at([(t, r[0]) for t, r in moved.panels[0].path], 9.5) + CW / 2 - 0.2 * SW) < CW / 2
    split = L.compose(SW, 1080, "split2", "9:16", scene="gameplay_cam", cam=(0.0, 0.0, 0.25, 0.3))
    moved = A.crop_path(split, tr, 10.0)                       # sliding left would run into the top-left webcam
    assert all(p.path is None for p in moved.panels)
    wide = L.compose(SW, 1080, "full", "16:9", scene="gameplay")
    assert A.crop_path(wide, tr, 10.0) == wide                 # nothing to move: the crop is the whole width


def test_crosshair_games_stay_centred_without_decoding():
    tr = A.track("missing.mp4", 0.0, 10.0, game="valorant")
    assert set(tr.xs) == {0.5} and tr.seconds == 0.0


def test_layout_graph_draws_the_path():
    plan = L.compose(SW, 1080, "full", "9:16", scene="gameplay")
    (p,) = plan.panels
    moved = replace(plan, panels=(replace(p, path=((0.0, p.src), (2.0, (100.0, 0.0, p.src[2], p.src[3])))),))
    assert "if(lt(t,2.000)" in L.layout_graph(moved)


def _moving_square(path, seconds=4, size=(640, 360)):
    """A dark noisy field with a bright square sliding from the left to the right edge."""
    w, h = size
    expr = f"if(between(X,{w * 0.1}+T*{w * 0.7 / seconds},{w * 0.1 + 60}+T*{w * 0.7 / seconds})*between(Y,150,210),235,30)"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"nullsrc=s={w}x{h}:r=30:d={seconds},geq=lum='{expr}':cb=128:cr=128",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def test_render_follows_a_moving_subject(tmp_path):
    src, out = tmp_path / "src.mp4", tmp_path / "out.mp4"
    _moving_square(src)
    info = probe(src)
    tr = A.track(src, 0.0, info.duration)
    assert sum(k == "motion" for k in tr.kinds) >= len(tr.kinds) // 2
    render_clip(src, 0.0, info.duration, out, src_w=info.width, src_h=info.height, vertical=True, zoom=1.0,
                chat="none", words=[], font="DejaVu Sans", layout="full", aspect="9:16", follow=True, loudness=False,
                has_audio=False, preview=True)
    for t in (0.5, info.duration - 0.5):           # the square stays in the picture at the start and the end
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1",
                              "-vf", "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        o = probe(out)
        frame = np.frombuffer(raw, np.uint8).reshape(o.height, o.width)
        assert frame.max() > 180, t
