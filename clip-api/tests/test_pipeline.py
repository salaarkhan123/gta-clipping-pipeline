import numpy as np

from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline.ff import probe
from app.pipeline.render import layout_filter, vertical_filter, video_bottom
from app.pipeline.signals import baseline_z, normalise
from app.pipeline.transcribe import exclamation_hits, snap_to_speech
from app.pipeline.windows import pick_windows


def test_pick_windows_finds_peak_and_keeps_clips_apart():
    scores = np.zeros(600)
    scores[300:310] = 5.0
    scores[320:325] = 4.0      # too close to the first peak to be a separate clip
    scores[500:505] = 3.0
    picks = pick_windows(scores, 30, 3, 600.0)
    starts = sorted(p[0] for p in picks)
    assert len(picks) == 2
    assert starts[0] <= 300 < starts[0] + 30 and starts[1] <= 500 < starts[1] + 30
    assert picks[0][2] >= picks[1][2]                      # sorted by score


def test_pick_windows_skips_intro_and_outro():
    scores = np.zeros(1000)
    scores[0:5] = 10.0         # intro sting
    scores[400:410] = 2.0
    picks = pick_windows(scores, 30, 1, 1000.0)
    assert picks[0][0] > 30


def test_baseline_z_is_relative_to_local_level():
    quiet = [-50.0] * 400
    quiet[200] = -30.0         # +20 dB over a quiet baseline
    loud = [-12.0] * 400
    loud[200] = -10.0          # +2 dB over a loud baseline
    assert baseline_z(quiet)[200] > baseline_z(loud)[200] * 5
    assert baseline_z([])  is not None and len(baseline_z([1.0])) == 1


def test_normalise_scales_and_shifts():
    vals = [0.0] * 100
    vals[50] = 10.0
    out = normalise(vals, 100, shift=4, smooth=1)
    assert out.argmax() == 46 and out.max() <= 1.5 and len(out) == 100


def test_snap_and_exclamations():
    segs = [(97.0, 101.5, "a"), (102.0, 128.0, "b"), (128.5, 140.0, "c")]
    s, e = snap_to_speech(100.0, 130.0, segs, 0, 600, 10, 60)
    assert abs(s - 101.85) < 0.01 and abs(e - 128.25) < 0.01
    assert snap_to_speech(100.0, 130.0, [], 0, 600, 10, 60) == (100.0, 130.0)
    assert exclamation_hits("Oh my GOD no way, let's go") == 3


def test_vertical_layout_fits_frame():
    for chat in ("none", "top-right", "top-center", "bottom-left"):
        graph = vertical_filter(1920, 1080, 1.0, chat)
        assert graph.endswith("[v]") and "1080" in graph
        assert 0 < video_bottom(1920, 1080, 1.0, chat) <= 1920


def test_run_pipeline_end_to_end(video, transcriber, tmp_path):
    stages = []
    results = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, chat_region="top-right"),
                           tmp_path / "out", lambda stage, pct: stages.append(stage), transcriber)
    assert len(results) == 1
    r = results[0]
    assert 10 <= r.start <= 24 and r.end - r.start >= 10
    info = probe(r.video_path)
    assert (info.width, info.height) == (1080, 1920) and 9 <= info.duration <= 16
    assert r.thumb_path.exists() and r.captions_path.exists()
    assert abs(sum(r.signals.values()) - 1.0) < 0.02 and "exclamation_hits" in r.features
    assert stages[0] == "probing" and stages[-1] == "done"


def test_run_pipeline_horizontal_without_transcriber(video, tmp_path):
    results = run_pipeline(video, PipelineOptions(max_clips=2, clip_length=10, vertical=False), tmp_path / "out")
    assert 1 <= len(results) <= 2
    info = probe(results[0].video_path)
    assert (info.width, info.height) == (640, 360) and results[0].captions_path is None


def test_layout_filters_build():
    assert "vstack" in layout_filter(1920, 1080, "split", 1.0, "none", "top-left")
    assert "vstack" in layout_filter(1920, 1080, "split", 1.0, "none", [0.05, 0.6, 0.25, 0.3])
    assert "boxblur" not in layout_filter(1920, 1080, "fill", 1.0, "none", None)


def test_split_layout_renders_full_frame(video, transcriber, tmp_path):
    results = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, layout="split",
                                                  facecam_region="bottom-right"), tmp_path / "out", None, transcriber)
    info = probe(results[0].video_path)
    assert (info.width, info.height) == (1080, 1920)
