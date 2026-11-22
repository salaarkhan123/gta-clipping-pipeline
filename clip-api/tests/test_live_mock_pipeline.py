"""Local mock live pipeline (CPU, no GPU / ffmpeg)."""
from app.live.jobs import LIVE_CLIP_TOOL, is_live_clip_job, live_clip_options
from app.live.mock_pipeline import run_mock_live_pipeline


def test_mock_pipeline_finds_loud_windows_and_ranks():
    result = run_mock_live_pipeline(
        session_id="live_test",
        duration_sec=90.0,
        loud_windows=[(40.0, 48.0), (70.0, 76.0)],
        highlight_labels=[(40.0, 48.0), (70.0, 76.0)],
    )
    assert result.tool == LIVE_CLIP_TOOL
    assert result.mode == "mock"
    assert result.seconds_processed >= 88.0
    assert len(result.triggers) >= 1
    assert result.candidates
    assert result.candidates[0].rank == 0
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert "total_wall_ms" in result.timings_ms
    assert result.fpr["measured"] is True
    assert any("not a measured" in n for n in result.notes)
    d = result.as_dict()
    assert d["mode"] == "mock"
    assert "measured_realtime" not in d  # mock result must not advertise realtime success
    assert is_live_clip_job(result.options)


def test_live_clip_options_shape():
    opts = live_clip_options(session_id="ls_x", mode="mock", max_minutes=30, rights_confirmed=True)
    assert opts["tool"] == LIVE_CLIP_TOOL
    assert opts["live_session_id"] == "ls_x"
    assert opts["rights_confirmed"] is True
    assert is_live_clip_job(opts)
    assert not is_live_clip_job({"tool": "clips"})
