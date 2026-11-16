"""S0: every job records where its time went, and scripts/job_timings.py turns two jobs into a before/after."""
import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest

from app import worker
from app.pipeline import PipelineError, PipelineOptions, Timer, run_pipeline
from tests.test_api import balance, upload
from tests.test_launch import three_bursts  # noqa: F401
from tests.test_punchier_clips import Talker

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "job_timings.py"
spec = importlib.util.spec_from_file_location("job_timings", SCRIPT)
jt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jt)


def test_timer_adds_up_repeats_counts_work_and_keeps_the_time_of_a_failed_stage():
    t = Timer()
    for _ in range(2):
        with t.stage("render"):
            time.sleep(0.02)
    with pytest.raises(ValueError), t.stage("judge_ai"):
        time.sleep(0.01)
        raise ValueError("boom")
    threads = [threading.Thread(target=lambda: [t.count("clips") for _ in range(100)]) for _ in range(4)]
    [x.start() for x in threads]
    [x.join() for x in threads]
    t.count("rendered_sec", 12.5)
    d = t.as_dict()
    assert 0.04 <= d["stages"]["render"] < 0.5 and d["stages"]["judge_ai"] >= 0.01
    assert d["counts"] == {"clips": 400, "rendered_sec": 12.5}


def test_the_pipeline_times_its_stages_and_they_cover_the_run(video, transcriber, tmp_path):
    timer, start = Timer(), time.monotonic()
    clips = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10), tmp_path / "o", transcriber=transcriber, timer=timer)
    wall = time.monotonic() - start
    d = timer.as_dict()
    assert {"probe", "facecam_detect", "audio_signal", "transcribe_rough", "dead_air", "render", "thumbnail"} <= set(d["stages"])
    assert "judge_ai" not in d["stages"] and "chat_motion" not in d["stages"]            # not used in this run
    assert 0.8 * wall <= sum(d["stages"].values()) <= wall + 0.05                        # flat stages: no double counting
    c = d["counts"]
    assert c["clips"] == len(clips) == 1 and c["source_sec"] == pytest.approx(40, abs=0.5) and c["candidates"] >= 1
    assert c["rendered_sec"] > 0 and c["transcribed_rough_sec"] >= 10
    assert clips[0].features["edit"]["render_sec"] == pytest.approx(d["stages"]["render"], abs=0.05)
    assert run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10), tmp_path / "p")   # the timer is optional


def test_the_judge_path_times_frames_ai_and_the_second_transcription(three_bursts, tmp_path):  # noqa: F811
    timer = Timer()

    def judge(text, frame, ctx):
        time.sleep(0.05)
        return {"title": "t", "virality": {"score": 80}}
    run_pipeline(three_bursts, PipelineOptions(max_clips=1, clip_length=20), tmp_path / "o", transcriber=Talker(), judge=judge,
                 fast_transcriber=Talker(), timer=timer)
    d = timer.as_dict()
    assert {"judge_frames", "judge_ai", "transcribe_rough", "transcribe_final"} <= set(d["stages"])
    assert d["stages"]["judge_ai"] >= 0.05 and d["counts"]["judged"] == d["counts"]["candidates"] >= 1
    assert d["counts"]["transcribed_final_sec"] > 0


def test_a_finished_job_reports_stages_counts_queue_and_end_to_end_time(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                         headers=headers).json()["job_id"]
    time.sleep(1.1)                                                     # the job waits in the queue
    assert worker.run_once(transcriber) == "SUCCEEDED"
    r = client.get(f"/v1/jobs/{job_id}", headers=headers).json()["result"]
    assert {"download", "probe", "audio_signal", "render", "titles", "store"} <= set(r["stages"])
    assert r["counts"]["clips"] == 1 and r["queue_sec"] >= 1.0
    assert r["total_sec"] == pytest.approx(r["queue_sec"] + r["elapsed_sec"], abs=0.3) and r["speed_x"] > 0
    assert "rendering" in r["timings"]                                  # the dashboard's coarse stages are still there


def test_a_failed_job_still_reports_its_time_and_is_refunded(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    job_id = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()["job_id"]

    def slow_then_broken(src, opts, out, progress, transcriber, deadline, timer=None, **k):
        with timer.stage("audio_signal"):
            time.sleep(0.2)
        raise PipelineError("media_error", "broken file")
    assert worker.run_once(None, pipeline=slow_then_broken) == "FAILED"
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["error"]["code"] == "media_error" and job["credits_charged"] == 0 and balance(client, headers) == 30
    assert job["result"]["stages"]["audio_signal"] >= 0.2 and job["result"]["elapsed_sec"] >= 0.2 and "total_sec" in job["result"]


# ---------- scripts/job_timings.py ----------
def job(tmp_path, name, result, clips=10, status="SUCCEEDED"):
    p = tmp_path / name
    p.write_text(json.dumps({"job_id": name, "status": status, "clips": [{}] * clips, "result": result}))
    return p


OLD = {"elapsed_sec": 932.7, "speed_x": 7.7, "timings": {"audio": 60.0, "transcribing": 257.0, "rendering": 578.0, "uploading": 20.0}}
NEW = {"elapsed_sec": 400.0, "speed_x": 18.0, "queue_sec": 5.0, "total_sec": 405.0,
       "timings": {"audio": 50.0, "transcribing": 120.0, "rendering": 200.0, "uploading": 10.0},
       "stages": {"download": 5.0, "audio_signal": 50.0, "transcribe_rough": 90.0, "transcribe_final": 30.0, "judge_ai": 10.0,
                  "dead_air": 8.0, "render": 180.0, "thumbnail": 12.0, "store": 10.0},
       "counts": {"source_sec": 7200.0, "clips": 10, "rendered_sec": 300.0, "transcribed_rough_sec": 1380.0, "transcribed_final_sec": 380.0}}


def test_targets_follow_the_goal():
    assert jt.target_sec(2 * 3600) == 600 and jt.target_sec(4 * 3600) == 900 and jt.target_sec(3 * 3600) == 750
    assert jt.target_sec(3600) == 300                                    # proportional below two hours


def test_one_job_gives_stage_shares_rates_and_the_target(tmp_path):
    c = jt.compare(jt.load(job(tmp_path, "new.json", NEW)))
    assert (c["detail"], c["source_min"], c["clips"], c["total_sec"], c["target_sec"], c["meets_target"]) == ("fine", 120.0, 10, 405.0, 600.0, True)
    assert c["stages"][0] == {"stage": "render", "sec": 180.0, "share": 0.45}
    assert c["stages"][-1]["stage"] == "(not in a stage)" and c["stages"][-1]["sec"] == 5.0     # 400 - 395 timed
    assert c["rates"] == {"render_sec_per_clip": 18.0, "render_x_realtime": 1.67, "transcribe_x_realtime": 14.7}


def test_an_older_job_is_compared_on_the_coarse_stages(tmp_path):
    c = jt.compare(jt.load(job(tmp_path, "new.json", NEW)), jt.load(job(tmp_path, "old.json", OLD)))
    assert c["detail"] == "coarse" and c["baseline"] == {"job_id": "old.json", "total_sec": 932.7, "clips": 10, "change_sec": -527.7}
    rows = {r["stage"]: r for r in c["stages"]}
    assert rows["rendering"] == {"stage": "rendering", "sec": 200.0, "share": 0.5, "before": 578.0, "change": -378.0}   # dead_air + render + thumbnail
    assert rows["transcribing"]["change"] == -137.0 and rows["judging"]["before"] == 0.0
    assert jt.load(job(tmp_path, "old.json", OLD))["source"] == pytest.approx(7.7 * 932.7)    # length backed out of the speed factor


def test_cli_prints_a_table_markdown_or_json_and_refuses_an_unfinished_job(tmp_path, capsys):
    new, old = job(tmp_path, "new.json", NEW), job(tmp_path, "old.json", OLD)
    assert jt.main([str(new), "--baseline", str(old)]) == 0
    out = capsys.readouterr().out
    assert "405 s end to end (5 s queued + 400 s running). Target 600 s: meets the target." in out
    assert "Before: 933 s for 10 clips. Change: -528 s." in out and "rendering" in out and "-378.0" in out
    assert jt.main([str(old)]) == 0 and "misses the target by" in capsys.readouterr().out
    assert jt.main([str(new), "--md"]) == 0 and "| stage | seconds | share |" in capsys.readouterr().out
    assert jt.main([str(new), "--json"]) == 0 and json.loads(capsys.readouterr().out)["meets_target"] is True
    running = job(tmp_path, "run.json", None, status="RUNNING")
    assert jt.main([str(running)]) == 2 and "has to finish first" in capsys.readouterr().err
