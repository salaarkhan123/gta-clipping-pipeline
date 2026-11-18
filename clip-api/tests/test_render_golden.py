"""The render output that existed before trio, grid4, ots, export and the hook options stays byte for byte the same."""
import json
from pathlib import Path

from app.pipeline import captions as C
from app.pipeline import layouts as L

GOLDEN = json.loads((Path(__file__).parent / "golden" / "render_before_b3.json").read_text())
SOURCE = (1280, 720)


def test_every_layout_graph_built_before_is_unchanged():
    assert len(GOLDEN["graphs"]) == 75
    for key, was in GOLDEN["graphs"].items():
        aspect, layout, cam_name = key.split("/")
        cam, face = GOLDEN["cams"][cam_name]
        plan = L.compose(*SOURCE, layout, aspect, cam=cam, face=face)
        now = {"layout": plan.layout, "graph": L.layout_graph(plan), "caption_top": plan.caption_top,
               "hook_top": plan.hook_top, "seam": plan.seam, "text_span": list(plan.text_span),
               "head": list(plan.head) if plan.head else None}
        assert now == was, key


def test_every_caption_style_built_before_is_unchanged(tmp_path):
    words = [tuple(w) for w in GOLDEN["words"]]
    assert len(GOLDEN["ass"]) == 30
    for key, was in GOLDEN["ass"].items():
        style, case = key.split("/")
        kw = dict(GOLDEN["cases"][case])
        vertical, top = kw.pop("vertical"), kw.pop("caption_top")
        for name in ("play", "span"):
            if name in kw:
                kw[name] = tuple(kw[name])
        n = C.build_ass(words, tmp_path / "c.ass", vertical, top, "DejaVu Sans", style, **kw)
        assert (n, (tmp_path / "c.ass").read_text(encoding="utf-8")) == (was["chunks"], was["ass"]), key


def test_auto_draws_one_layout_per_video_while_provisional_layouts_are_off(client, user, video, transcriber, monkeypatch):
    """PROVISIONAL_LAYOUTS off (the default): auto is what it was before #136, one layout for the whole video (the
    graphs above), never chosen again per moment. On: each moment is looked at (facecam.moment_facecam)."""
    import app.pipeline as P
    from app import worker
    from app.config import get_settings
    from app.pipeline import facecam
    from app.pipeline.tools import RenderOptions
    from tests.test_api import upload
    from tests.test_export import run_clips

    assert get_settings().provisional_layouts is False
    assert P.PipelineOptions().moment_layout is False and RenderOptions().moment_layout is False
    looked = []

    def moment(src, info, start, end, layout, cam, deadline=None):
        looked.append((start, end))
        return layout, cam
    monkeypatch.setattr(P, "moment_facecam", moment)          # run_pipeline's
    monkeypatch.setattr(facecam, "moment_facecam", moment)    # run_export's
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "layout": "auto"}, transcriber)
    export = client.post("/v1/clips/export", json={"job_id": job["job_id"], "options": {"resolution": "480"}},
                         headers=headers)
    assert export.status_code == 202 and worker.run_once(transcriber) == "SUCCEEDED"
    assert looked == []

    monkeypatch.setattr(get_settings(), "provisional_layouts", True)
    run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "layout": "auto"}, transcriber)
    export = client.post("/v1/clips/export", json={"job_id": job["job_id"], "options": {"resolution": "720"}},
                         headers=headers)
    assert export.status_code == 202 and worker.run_once(transcriber) == "SUCCEEDED"
    assert len(looked) == 2                                   # one moment in the clip job, one in the export
