"""The shared frame pass: key frames are decoded once, next to the audio, and the picture signals come from it
(streamer reaction in the camera box, standby, repeated screens)."""
import subprocess

import numpy as np
import pytest

import app.pipeline as pipeline
import app.pipeline.frames as frames
from app.pipeline import PipelineError, PipelineOptions, Timer, run_pipeline
from app.pipeline.frames import REPEAT_GAP, frame_pass, per_second, picture, repeats, runs, spans

FAST = {"vertical": False, "captions": False, "punch_zoom": False, "tighten": False}


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def camera_only(tmp_path_factory):
    """40 s: a slowly moving picture with a busy inset in the top-left corner (where a facecam would be)."""
    out = tmp_path_factory.mktemp("v") / "cam.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10:duration=40",
           "-f", "lavfi", "-i", "color=c=gray:size=160x90:rate=10:duration=40,noise=alls=100:allf=t",
           "-f", "lavfi", "-i", "sine=frequency=330:duration=40",
           "-filter_complex", "[0:v][1:v]overlay=0:0[v]", "-map", "[v]", "-map", "2:a",
           "-af", "volume='if(between(t,20,24),1.0,0.05)':eval=frame", "-g", "20",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out))
    return out


@pytest.fixture(scope="module")
def lobby_twice(tmp_path_factory):
    """260 s: an animated "lobby" for 40 s, 160 s of other pictures, then the same lobby again. A loud burst in each
    showing of the lobby (10 s and 230 s) and one in the middle (120 s)."""
    d = tmp_path_factory.mktemp("v")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=40", "-g", "20", "-c:v", "libx264",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(d / "lobby.mp4"))
    ffmpeg("-f", "lavfi", "-i", "mandelbrot=size=320x180:rate=10", "-t", "160", "-g", "20", "-c:v", "libx264",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(d / "game.mp4"))
    out = d / "lobby-twice.mp4"
    ffmpeg("-i", str(d / "lobby.mp4"), "-i", str(d / "game.mp4"), "-i", str(d / "lobby.mp4"),
           "-f", "lavfi", "-i", "sine=frequency=330:duration=240",
           "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[v]", "-map", "[v]", "-map", "3:a",
           "-af", "volume='if(between(t,10,13)+between(t,120,123)+between(t,225,228),1.0,0.03)':eval=frame", "-g", "20",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out))
    return out


# ---------- the pass ----------

def test_key_frames_are_read_once_with_times_change_and_the_camera_box(camera_only):
    seen = []
    f = frame_pass(camera_only, cam=[0.0, 0.0, 0.25, 0.25], on_frame=lambda t, rgb: seen.append((t, rgb.shape)))
    assert len(f["t"]) >= 15 and all(b > a for a, b in zip(f["t"], f["t"][1:]))       # a key frame every 2 s
    assert len(seen) == len(f["t"]) and seen[0][1] == (frames.FRAME_H, frames.FRAME_W, 3)
    assert f["cam_change"][1:].mean() > 2 * f["change"][1:].mean() > 0                 # the camera moves most
    assert f["print"].shape == (len(f["t"]), frames.PRINT_W * frames.PRINT_H)
    part = frame_pass(camera_only, start=20.0, length=10.0)
    assert 3 <= len(part["t"]) <= 7 and 19.5 <= part["t"][0] <= 22.5 and not part["cam_change"].any()


def test_values_at_key_frames_become_one_value_per_second():
    t = np.array([0.0, 4.0, 6.0])
    assert per_second(t, [9, 1, 5], 0.0, 8).tolist() == [1, 1, 1, 1, 5, 5, 5, 5]       # second i: the next key frame
    assert per_second(np.zeros(0), [], 0.0, 3).tolist() == [0, 0, 0]
    flags = np.array([1, 1, 0, 1, 1, 1, 0], bool)
    assert runs(flags, 3).tolist() == [False, False, False, True, True, True, False]
    assert spans(flags, 100.0) == [[100.0, 102.0], [103.0, 106.0]]


def test_a_screen_repeats_only_when_it_was_shown_long_before():
    rng = np.random.default_rng(3)

    def unit(v):
        v = v - v.mean()
        return v / np.linalg.norm(v)
    lobby = unit(rng.normal(size=576))
    game = [unit(rng.normal(size=576)) for _ in range(6)]
    t = np.array([0.0, 2.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 302.0])
    prints = np.array([lobby, lobby, *game[:5], lobby, unit(lobby + 0.05 * game[5])])
    assert repeats(t, prints).tolist() == [0, 0, 0, 0, 0, 0, 0, 1, 1]                   # not the first showing
    assert REPEAT_GAP == 120.0


def test_the_picture_of_a_file_without_readable_key_frames_is_zeros(camera_only, monkeypatch):
    def broken(*a, **k):
        raise PipelineError("media_error", "no frames")
    monkeypatch.setattr(frames, "frame_pass", broken)
    seen = picture(camera_only, 40, 0)
    assert seen.keyframes == 0 and not seen.still.any() and not seen.repeat.any() and len(seen.change) == 40


# ---------- in the pipeline ----------

def test_the_frame_pass_runs_once_beside_the_audio_and_a_failure_does_not_fail_the_run(camera_only, tmp_path, monkeypatch):
    calls = []
    real = frames.frame_pass

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(frames, "frame_pass", counted)
    timer = Timer()
    clips = run_pipeline(camera_only, PipelineOptions(max_clips=1, clip_length=10, **FAST), tmp_path / "a", timer=timer)
    d = timer.as_dict()
    assert clips and calls == [1] and d["counts"]["keyframes"] >= 15 and "frame_pass" in d["stages"]

    def broken(*a, **k):
        raise PipelineError("media_error", "no frames")
    monkeypatch.setattr(frames, "frame_pass", broken)
    again = run_pipeline(camera_only, PipelineOptions(max_clips=1, clip_length=10, **FAST), tmp_path / "b")
    assert [(c.start, c.end) for c in again] == [(c.start, c.end) for c in clips]


def test_the_streamers_movement_is_a_signal_when_it_counts_and_there_is_a_camera(camera_only, tmp_path):
    opts = {"max_clips": 1, "clip_length": 10, **FAST}
    with_cam = run_pipeline(camera_only, PipelineOptions(facecam_box=[0.0, 0.0, 0.25, 0.25], layout="classic",
                                                         weights={"reaction": 0.5}, **opts), tmp_path / "a")
    assert "reaction" in with_cam[0].signals and "reaction_mean" in with_cam[0].features
    no_cam = run_pipeline(camera_only, PipelineOptions(weights={"reaction": 0.5}, **opts), tmp_path / "b")
    assert "reaction" not in no_cam[0].signals


def test_a_screen_that_comes_back_is_not_nominated_again(lobby_twice, tmp_path):
    timer, moments = Timer(), []
    clips = run_pipeline(lobby_twice, PipelineOptions(max_clips=3, clip_length=10, **FAST), tmp_path / "o", timer=timer,
                         on_moments=moments.extend)
    starts = sorted(c.start for c in clips)
    assert starts and all(s < 200 for s in starts)                         # nothing from the second showing
    assert any(s < 40 for s in starts)                                     # the first showing is a moment like any
    assert timer.as_dict()["counts"]["dead_sec"] >= 30
    assert all(m.features["repeat"] is False and m.features["repeat_share"] < 0.9 for m in moments)


def test_standby_spans_are_recorded_in_source_seconds(tmp_path, tmp_path_factory):
    out = tmp_path_factory.mktemp("v") / "part-still.mp4"
    ffmpeg("-f", "lavfi", "-i", "color=c=navy:size=320x240:rate=10:duration=30",
           "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=30",
           "-f", "lavfi", "-i", "sine=frequency=330:duration=60",
           "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a",
           "-af", "volume='if(lt(t,30),0.05,if(lt(mod(t,8),2),1.0,0.2))':eval=frame", "-g", "20",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out))
    clips = run_pipeline(out, PipelineOptions(max_clips=1, clip_length=20, range={"start": 20, "end": 40}, **FAST),
                         tmp_path / "o")
    f = clips[0].features
    assert 0 < f["standby_share"] < 0.9 and f["standby"] is False
    (a, b), = f["standby_spans"]
    assert 20 <= a < b <= 32 and b - a == pytest.approx(f["standby_share"] * (clips[0].end - clips[0].start), abs=2.5)


def test_the_weights_table_knows_every_picture_signal():
    assert {"reaction", "scene"} <= set(pipeline.WEIGHTS) and pipeline.DEAD_RUN == 30
