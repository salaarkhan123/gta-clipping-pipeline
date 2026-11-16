"""scripts/bench_pipeline.py on a short generated clip with the stand-in transcriber."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bench_pipeline.py"
KEYS = {"source_minutes", "wall_seconds", "realtime_factor", "peak_rss_mb", "clips", "credits", "chat_region"}


def load_script():
    spec = importlib.util.spec_from_file_location("bench_pipeline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def clip20(tmp_path_factory) -> Path:
    """20 s synthetic video with a loud burst, so the audio signal finds a moment."""
    path = tmp_path_factory.mktemp("bench") / "clip20.mp4"
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15:duration=20",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
        "-af", "volume='if(between(t,10,13),1.0,0.02)':eval=frame",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ], check=True)
    return path


def test_benchmark_reports_every_key(clip20, transcriber):
    result = load_script().benchmark(clip20, chat_region="none", transcriber=transcriber)
    assert KEYS <= set(result)
    assert result["wall_seconds"] > 0
    assert result["realtime_factor"] > 0
    assert result["peak_rss_mb"] > 0
    assert result["clips"] >= 1
    assert result["credits"] == 1                      # 20 s rounds up to one credit minute
    assert result["chat_region"] == "none"
    assert result["stages"]["render"] > 0 and result["counts"]["clips"] == result["clips"]   # where the time went
    json.dumps(result)


def test_chat_region_is_passed_through_and_echoed(clip20, transcriber):
    result = load_script().benchmark(clip20, chat_region="top-right", transcriber=transcriber)
    assert result["chat_region"] == "top-right"


def test_cli_prints_one_json_line(clip20, capsys):
    assert load_script().main([str(clip20), "--chat-region", "top-right", "--transcriber", "none"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and KEYS <= set(json.loads(lines[0]))


def test_cli_rejects_missing_file(tmp_path, capsys):
    assert load_script().main([str(tmp_path / "nope.mp4")]) == 2
