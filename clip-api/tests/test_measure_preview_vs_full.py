"""Wave A1 / S2: scripts/measure_preview_vs_full.py parsing and compare helpers."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "measure_preview_vs_full.py"


def load_script():
    spec = importlib.util.spec_from_file_location("measure_preview_vs_full", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def job_payload(*, job_id: str, render: str, elapsed: float, queue: float, first_clip: float,
                render_stage: float, source_sec: float, clips: int = 3) -> dict:
    return {
        "job_id": job_id,
        "status": "SUCCEEDED",
        "clips": [{}] * clips,
        "result": {
            "elapsed_sec": elapsed,
            "speed_x": source_sec / elapsed if elapsed else 0,
            "queue_sec": queue,
            "total_sec": elapsed + queue,
            "first_clip_sec": first_clip,
            "stages": {
                "download": 2.0,
                "probe": 1.0,
                "audio_signal": 5.0,
                "transcribe_rough": 20.0,
                "dead_air": 3.0,
                "render": render_stage,
                "thumbnail": 2.0,
                "store": 1.0,
            },
            "counts": {"source_sec": source_sec, "clips": clips, "rendered_sec": clips * 30.0},
            "render": render,
        },
    }


@pytest.fixture
def harness():
    return load_script()


def test_pick_metrics_and_delta_from_job_timings_shape(harness, tmp_path):
    preview = tmp_path / "preview.json"
    full = tmp_path / "full.json"
    # Short fixture (~10 min): 2h_vod stays not measured.
    preview.write_text(json.dumps(job_payload(
        job_id="p", render="preview", elapsed=80.0, queue=4.0, first_clip=30.0,
        render_stage=25.0, source_sec=600.0,
    )))
    full.write_text(json.dumps(job_payload(
        job_id="f", render="full", elapsed=140.0, queue=4.0, first_clip=70.0,
        render_stage=80.0, source_sec=600.0,
    )))
    report = harness.compare_job_files(preview, full)
    assert report["compare_fields"] == ["first_clip_sec", "stages.render", "total_sec"]
    assert report["claim"]["2h_vod"] == "not measured"
    assert report["claim"]["pair"] == "measured"
    assert report["preview"]["first_clip_sec"] == 34.0          # queue included
    assert report["full"]["first_clip_sec"] == 74.0
    assert report["preview"]["render_sec"] == 25.0
    assert report["full"]["render_sec"] == 80.0
    assert report["preview"]["total_sec"] == 84.0
    assert report["full"]["total_sec"] == 144.0
    assert report["delta_preview_minus_full"] == {
        "first_clip_sec": -40.0,
        "render_sec": -55.0,
        "total_sec": -60.0,
        "run_sec": -60.0,
    }


def test_two_hour_source_marks_2h_vod_measured(harness, tmp_path):
    preview = tmp_path / "preview.json"
    full = tmp_path / "full.json"
    preview.write_text(json.dumps(job_payload(
        job_id="p2h", render="preview", elapsed=400.0, queue=5.0, first_clip=90.0,
        render_stage=180.0, source_sec=7200.0, clips=10,
    )))
    full.write_text(json.dumps(job_payload(
        job_id="f2h", render="full", elapsed=900.0, queue=5.0, first_clip=500.0,
        render_stage=550.0, source_sec=7200.0, clips=10,
    )))
    report = harness.compare_job_files(preview, full)
    assert report["claim"]["2h_vod"] == "measured"
    assert report["preview"]["source_min"] == 120.0
    assert report["delta_preview_minus_full"]["render_sec"] == -370.0


def test_local_run_to_job_shape_is_job_timings_loadable(harness, tmp_path):
    jt = harness._load_job_timings()
    shaped = harness.local_run_to_job_shape(
        job_id="local-preview",
        render="preview",
        wall_sec=12.5,
        timer_dict={"stages": {"probe": 0.5, "render": 8.0}, "counts": {"source_sec": 40.0, "clips": 1}},
        first_clip_sec=9.2,
    )
    path = tmp_path / "local-preview.json"
    path.write_text(json.dumps(shaped))
    loaded = jt.load(path)
    compared = jt.compare(loaded)
    assert compared["job_id"] == "local-preview"
    assert compared["first_clip_sec"] == 9.2
    assert harness.stage_render_sec(compared) == 8.0


def test_dry_run_prints_recipe_and_not_measured_claim(harness, capsys):
    assert harness.main(["--dry-run", "--api", "https://staging.test", "--upload-id", "up_1"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "dry-run"
    assert report["claim"] == {"2h_vod": "not measured", "pair": "dry-run"}
    assert report["compare_fields"] == ["first_clip_sec", "stages.render", "total_sec"]
    assert report["upload_id"] == "up_1"
    assert any("POST" in step and "preview" in step for step in report["recipe"])
    assert any("measure_preview_vs_full.py --preview-job" in step for step in report["recipe"])


def test_cli_compare_two_jobs(harness, tmp_path, capsys):
    preview = tmp_path / "preview.json"
    full = tmp_path / "full.json"
    preview.write_text(json.dumps(job_payload(
        job_id="p", render="preview", elapsed=50.0, queue=2.0, first_clip=20.0,
        render_stage=15.0, source_sec=120.0,
    )))
    full.write_text(json.dumps(job_payload(
        job_id="f", render="full", elapsed=90.0, queue=2.0, first_clip=40.0,
        render_stage=50.0, source_sec=120.0,
    )))
    assert harness.main(["--preview-job", str(preview), "--full-job", str(full)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["preview"]["job_id"] == "p"
    assert report["full"]["job_id"] == "f"
    assert report["claim"]["2h_vod"] == "not measured"


def test_cli_refuses_unfinished_job(harness, tmp_path, capsys):
    preview = tmp_path / "preview.json"
    full = tmp_path / "full.json"
    preview.write_text(json.dumps({"job_id": "p", "status": "RUNNING", "result": {}}))
    full.write_text(json.dumps(job_payload(
        job_id="f", render="full", elapsed=90.0, queue=2.0, first_clip=40.0,
        render_stage=50.0, source_sec=120.0,
    )))
    assert harness.main(["--preview-job", str(preview), "--full-job", str(full)]) == 2
    assert "has to finish first" in capsys.readouterr().err


def test_cli_needs_a_mode(harness, capsys):
    assert harness.main([]) == 2
    assert "Need --dry-run" in capsys.readouterr().err
