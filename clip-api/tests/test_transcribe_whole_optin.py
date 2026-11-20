"""C3: whole-transcript mode stays opt-in (env default false + per-job ClipOptions.transcribe_whole)."""
import pytest
from fastapi.testclient import TestClient

from app import worker
from app.config import Settings, get_settings
from app.main import app
from app.routes_media import ClipOptions
from app.routes_meta import clip_options
from tests.test_api import upload
from tests.test_launch import FakeAI, three_bursts  # noqa: F401
from tests.test_llm_pass import run as llm_run, story_proposer
from tests.test_upload_transcript import Recording, clip_job, finished, stored


def test_settings_and_clip_options_default_transcribe_whole_false():
    assert Settings().transcribe_whole is False
    assert get_settings().transcribe_whole is False
    assert ClipOptions().transcribe_whole is False
    assert "transcribe_whole" not in ClipOptions().model_dump()          # ONLY_WHEN_SENT: absent unless opted in
    listed = clip_options()["transcribe_whole"]
    assert listed == {"type": "boolean", "default": False}
    public = TestClient(app).get("/v1/options").json()["clips"]["transcribe_whole"]
    assert public["default"] is False and public["type"] == "boolean"


def test_per_job_opt_in_is_accepted_listed_and_stored(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"],
                                       "options": {"max_clips": 1, "clip_length": 10, "transcribe_whole": True}},
                    headers=headers)
    assert r.status_code == 202, r.text
    assert r.json()["options"]["transcribe_whole"] is True
    assert ClipOptions(transcribe_whole=True).model_dump()["transcribe_whole"] is True
    client.post(f"/v1/jobs/{r.json()['job_id']}/cancel", headers=headers)


def test_job_opt_in_runs_whole_transcript_when_env_is_off(client, user, three_bursts, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "transcribe_whole", False)
    headers, _ = user
    up = upload(client, headers, three_bursts)
    rough, final = Recording(), Recording()
    rough.model_name, final.model_name = "base.en", "small.en"
    job = clip_job(client, headers, up["upload_id"], clip_length=20, transcribe_whole=True)
    assert worker.run_once(final, indexer=rough, ai=FakeAI()) == "SUCCEEDED"
    result = finished(client, headers, job)["result"]
    assert "transcribe_rough" not in result["stages"] and result["stages"]["transcribe_whole"] >= 0
    assert sum(rough.seconds) == pytest.approx(60.0, abs=1.0)
    assert stored(up["upload_id"])["model"] == "base.en"


def test_without_heard_coverage_llm_pass_is_skipped(video, tmp_path):
    """U3: proposer is not called when Heard does not cover the analysed range (existing gate)."""
    calls = []
    before, _ = llm_run(video, tmp_path / "before")
    after, counts = llm_run(video, tmp_path / "after", proposer=story_proposer(calls))
    assert calls == [] and counts["llm_pass_skipped"] == 1
    assert [(c.start, c.end, c.score) for c in after] == [(c.start, c.end, c.score) for c in before]
