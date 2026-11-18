"""The clip pipeline and worker accept the render options the API accepts: resolution and the reframe layouts."""
from dataclasses import fields

from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline.ff import probe
from app.routes_media import ClipOptions
from tests.test_api import balance, upload
from tests.test_punchier_clips import gappy  # noqa: F401  (fixture)
from tests.test_tools import fetch, run


def test_the_pipeline_knows_every_option_a_clip_request_can_store():
    """The worker builds PipelineOptions(**stored options): a stored key it does not know crashes the job."""
    known = {f.name for f in fields(PipelineOptions)}
    assert set(ClipOptions.model_fields) <= known
    sent = ClipOptions(resolution="720", layout="gameplay_b").model_dump()
    assert sent["resolution"] == "720" and set(sent) <= known
    PipelineOptions(caption_font="DejaVu Sans", **sent)


def test_run_pipeline_renders_at_the_resolution_asked(video, tmp_path):
    out = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False, resolution="480"), tmp_path / "a")[0]
    info = probe(out.video_path)
    assert (info.width, info.height) == (360, 640)            # 480 asked, the 640x360 source has 360: no upscaling
    capped = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False, resolution="1080", max_side=240),
                          tmp_path / "b")[0]
    assert min(probe(capped.video_path).width, probe(capped.video_path).height) == 240      # the plan cap wins


def test_a_clip_job_with_a_resolution_runs_and_costs_the_same(client, user, video, transcriber, tmp_path):
    headers, _ = user
    up = upload(client, headers, video)
    job = run(client, headers, "/v1/clips", {"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10,
                                                                                       "resolution": "720"}}, transcriber)
    assert job["status"] == "SUCCEEDED" and job["options"]["resolution"] == "720"
    info = probe(fetch(client, job["clips"][0]["video_url"], tmp_path / "c.mp4"))
    assert min(info.width, info.height) == 360                # capped at the source
    first = job["credits_charged"]
    again = run(client, headers, "/v1/clips", {"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                transcriber)
    with_res = run(client, headers, "/v1/clips", {"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10,
                                                                                            "resolution": "4k"}}, transcriber)
    assert again["credits_charged"] == with_res["credits_charged"] and first >= again["credits_charged"]
    assert balance(client, headers) == 30 - first - 2 * again["credits_charged"]


def test_punch_ins_are_planned_for_the_reframe_layouts_and_never_for_classic(gappy, tmp_path):  # noqa: F811
    def zooms(name, **kw):
        return run_pipeline(gappy, PipelineOptions(max_clips=1, clip_length=20, tighten=False, **kw), tmp_path / name)[0] \
            .features["edit"]["zoom_at"]
    assert zooms("gb", layout="gameplay_b", facecam_region="bottom-right")
    assert zooms("full", layout="full")
    assert zooms("classic", layout="classic") == []
