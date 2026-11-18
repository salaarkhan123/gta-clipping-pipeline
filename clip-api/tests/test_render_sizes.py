"""Export resolution (never above the source), preview renders, and the options that ask for them."""
import subprocess
import time
from dataclasses import fields

import numpy as np
import pytest
from pydantic import ValidationError

from app.pipeline import layouts as L
from app.pipeline.ff import PipelineError, probe
from app.pipeline.render import PREVIEW_SIDE, RESOLUTIONS, output_size, render_clip
from app.pipeline.tools import RenderOptions
from app.render_options import LayoutOptions
from app.routes_media import ClipOptions
from app.routes_tools import ReframeOptions
from tests.test_api import balance, upload
from tests.test_layouts import CORNER, camera, face_of, frac, frame, make_stream
from tests.test_tools import fetch, run


def source(path, size, seconds=6):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def hd(tmp_path_factory):
    return source(tmp_path_factory.mktemp("sizes") / "hd.mp4", "1280x720")


def render(src, out, start=1.0, end=2.0, **kw):
    info = probe(src)
    render_clip(src, start, end, out, src_w=info.width, src_h=info.height, vertical=kw.pop("vertical", True), zoom=1.0,
                chat="none", words=kw.pop("words", []), font="DejaVu Sans", **kw)
    got = probe(out)
    return got.width, got.height


def test_the_size_for_every_resolution_aspect_and_source():
    assert RESOLUTIONS == {"480": 480, "720": 720, "1080": 1080, "2k": 1440, "4k": 2160}
    hd, uhd = (1920, 1080), (3840, 2160)
    assert output_size(*hd, True, "9:16") == (1080, 1920)                    # no resolution: what it always was
    assert output_size(640, 360, True, "9:16") == (1080, 1920) and output_size(640, 360, False) == (640, 360)
    want = {"480": (480, 852), "720": (720, 1280), "1080": (1080, 1920), "2k": (1440, 2560), "4k": (2160, 3840)}
    for name, size in want.items():
        assert output_size(*uhd, True, "9:16", name) == size                 # a 4K source allows every one of them
        assert output_size(*hd, True, "9:16", name) == min(size, (1080, 1920))        # a 1080p source stops at 1080
        assert output_size(1280, 720, True, "9:16", name) == min(size, (720, 1280))
    assert [output_size(*uhd, True, a, "2k") for a in ("4:5", "1:1", "16:9")] == [(1440, 1800), (1440, 1440), (2560, 1440)]
    assert output_size(1080, 1920, True, "9:16", "4k") == (1080, 1920)       # a phone recording: its short side is 1080
    assert output_size(*uhd, False, resolution="1080") == (1920, 1080)       # source framing: scaled down, never up
    assert output_size(*hd, False, resolution="4k") == hd and output_size(1280, 720, False, resolution="480") == (852, 480)
    for aspect, size in (("9:16", (540, 960)), ("4:5", (540, 674)), ("1:1", (540, 540)), ("16:9", (960, 540))):
        assert output_size(*hd, True, aspect, preview=True) == size          # a preview: 540 on the short side
        assert output_size(*hd, True, aspect, "4k", preview=True) == size
    assert PREVIEW_SIDE == 540 and output_size(*hd, False, preview=True) == (960, 540)
    assert output_size(320, 180, False, preview=True) == (320, 180)          # already smaller than a preview
    with pytest.raises(PipelineError) as e:
        output_size(*hd, True, "9:16", "8k")
    assert e.value.code == "bad_options"


def test_the_plan_cap_keeps_working_and_always_wins():
    hd, uhd = (1920, 1080), (3840, 2160)
    assert output_size(*hd, True, "9:16", max_side=720) == (720, 1280)       # as before the option existed
    assert output_size(*hd, True, "9:16", max_side=1080) == (1080, 1920) and output_size(*hd, False, max_side=720) == (1280, 720)
    for name in RESOLUTIONS:
        w, h = output_size(*uhd, True, "9:16", name, max_side=720)
        assert min(w, h) == min(RESOLUTIONS[name], 720)                      # never above the cap, whatever was asked
    assert output_size(*uhd, True, "9:16", "4k", preview=True, max_side=360) == (360, 640)
    assert output_size(*uhd, False, resolution="4k", max_side=720) == (1280, 720)


def test_a_render_is_capped_at_the_source_resolution(hd, tmp_path):
    assert render(hd, tmp_path / "a.mp4") == (1080, 1920)                                    # default: unchanged
    assert render(hd, tmp_path / "b.mp4", resolution="1080") == (720, 1280)                  # a 720p source gives 720p
    assert render(hd, tmp_path / "c.mp4", resolution="4k") == (720, 1280)
    assert render(hd, tmp_path / "d.mp4", resolution="480") == (480, 852)
    assert render(hd, tmp_path / "e.mp4", resolution="480", aspect="16:9") == (852, 480)
    assert render(hd, tmp_path / "f.mp4", resolution="480", vertical=False) == (852, 480)
    assert render(hd, tmp_path / "g.mp4", vertical=False) == (1280, 720)
    assert render(hd, tmp_path / "h.mp4", resolution="1080", max_side=480) == (480, 852)     # the plan cap wins
    assert render(hd, tmp_path / "i.mp4", max_side=720) == (720, 1280)
    assert render(hd, tmp_path / "j.mp4", resolution="720", layout="classic") == (720, 1280)  # the old layout too
    with pytest.raises(PipelineError):
        render(hd, tmp_path / "k.mp4", resolution="8k")


def test_2k_comes_out_at_2k_only_from_a_source_that_has_it(tmp_path):
    qhd = source(tmp_path / "qhd.mp4", "2560x1440", seconds=2)
    assert render(qhd, tmp_path / "a.mp4", 0.5, 1.5, resolution="2k") == (1440, 2560)
    assert render(qhd, tmp_path / "b.mp4", 0.5, 1.5, resolution="4k") == (1440, 2560)        # not above the source
    assert render(qhd, tmp_path / "c.mp4", 0.5, 1.5, resolution="1080") == (1080, 1920)
    assert render(qhd, tmp_path / "d.mp4", 0.5, 1.5, resolution="2k", layout="split", facecam="top-right", segments=[(0.2, 0.8), (1.0, 1.6)]) == (1440, 2560)


def test_a_preview_is_smaller_and_faster_than_the_full_render(hd, tmp_path):
    def timed(out, **kw):
        best = float("inf")
        for _ in range(2):                                                    # the better of two: other work shares this machine
            t0 = time.monotonic()
            size = render(hd, out, 0.5, 5.5, **kw)
            best = min(best, time.monotonic() - t0)
        return size, best
    full_size, full_sec = timed(tmp_path / "full.mp4")
    prev_size, prev_sec = timed(tmp_path / "prev.mp4", preview=True)
    assert full_size == (1080, 1920) and prev_size == (540, 960)
    assert prev_sec < full_sec, (prev_sec, full_sec)
    assert (tmp_path / "prev.mp4").stat().st_size < (tmp_path / "full.mp4").stat().st_size
    full, prev = probe(tmp_path / "full.mp4"), probe(tmp_path / "prev.mp4")
    assert prev.has_audio and prev.duration == pytest.approx(full.duration, abs=0.1)
    for aspect, size in (("4:5", (540, 674)), ("1:1", (540, 540)), ("16:9", (960, 540))):
        assert render(hd, tmp_path / "p.mp4", preview=True, aspect=aspect) == size
    assert render(hd, tmp_path / "p.mp4", preview=True, vertical=False) == (960, 540)
    assert render(hd, tmp_path / "p.mp4", preview=True, max_side=360) == (360, 640)          # the plan cap still wins


def white(img):
    return (img[..., 0] > 215) & (img[..., 1] > 215) & (img[..., 2] > 215)


def test_the_picture_and_the_captions_are_in_the_same_place_at_every_size(tmp_path):
    src = make_stream(tmp_path / "cam.mp4", *CORNER)
    plan = L.compose(1280, 720, "split2", "9:16", cam=frac(CORNER[0]), face=face_of(CORNER[1]))
    words = [(0.0, 0.9, "clean"), (0.0, 0.9, "win")]
    places = {}
    for name, kw in (("full", {}), ("preview", {"preview": True}), ("480", {"resolution": "480"}), ("capped", {"max_side": 720})):
        size = render(src, tmp_path / f"{name}.mp4", 0.5, 1.5, plan=plan, words=words, style="bold", **kw)
        img = frame(tmp_path / f"{name}.mp4", 0.4)
        cam_rows = np.nonzero(camera(img).any(axis=1))[0]
        text_rows, text_cols = np.nonzero(white(img))
        assert len(text_rows) > 200, name                                    # the caption was burned in
        places[name] = (size, cam_rows.max() / size[1], text_rows.mean() / size[1], (text_cols.max() - text_cols.min()) / size[0])
    assert [places[n][0] for n in ("full", "preview", "480", "capped")] == [(1080, 1920), (540, 960), (480, 852), (720, 1280)]
    for name in ("preview", "480", "capped"):
        assert places[name][1] == pytest.approx(places["full"][1], abs=0.01)     # the camera ends at the same third
        assert places[name][2] == pytest.approx(places["full"][2], abs=0.01)     # the caption sits on the same seam
        assert places[name][3] == pytest.approx(places["full"][3], abs=0.03)     # and is the same size on screen


# ---------- the options ----------
def test_the_new_options_change_no_default_and_no_stored_job():
    o = LayoutOptions()
    # The one default that has changed since: the caption style is impact (tests/test_impact_captions.py).
    assert (o.layout, o.resolution, o.aspect, o.vertical, o.captions, o.caption_style, o.facecam_region) == (
        "auto", "1080", "9:16", True, True, "impact", "auto")
    # What a job stores when the request names no resolution has no resolution in it, and every key it does have
    # is one the worker's RenderOptions(**options) and PipelineOptions(**options) know.
    assert set(o.model_dump()) == {"vertical", "aspect", "chat_region", "zoom", "captions", "caption_style", "censor",
                                   "layout", "facecam_region", "facecam_box", "caption_position", "caption_accent",
                                   "camera", "split_ratio"}
    assert set(o.model_dump()) <= {f.name for f in fields(RenderOptions)}
    assert "resolution" not in ClipOptions().model_dump() and "resolution" not in ReframeOptions().model_dump()
    sent = ReframeOptions(resolution="720", layout="pip").model_dump()
    assert sent["resolution"] == "720" and sent["layout"] == "pip"
    known = {f.name for f in fields(RenderOptions)}
    assert set(sent) <= known and RenderOptions(**sent, max_side=720).resolution == "720"
    assert RenderOptions().resolution is None and RenderOptions().preview is False


def test_layout_and_resolution_are_validated_with_the_reason(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "provisional_layouts", True)       # every built layout, trio, grid4, ots too
    for aspect in L.ALLOWED:
        for name in L.ALLOWED[aspect]:
            if name in L.BUILT:
                assert LayoutOptions(layout=name, aspect=aspect).layout == name
    for res in ("480", "720", "1080", "2k", "4k"):
        assert LayoutOptions(resolution=res).resolution == res
    for bad, reason in (({"resolution": "8k"}, "resolution"), ({"resolution": 1080}, "resolution"),
                        ({"layout": "pip", "aspect": "1:1"}, "not available in 1:1"),
                        ({"layout": "ots"}, "not available in 9:16"), ({"layout": "trio", "aspect": "1:1",
                                                                         "facecam_region": None}, "needs facecam_region"),
                        ({"layout": "sideways"}, "layout"), ({"layout": "pip", "facecam_region": None}, "needs facecam_region"),
                        ({"layout": "split", "facecam_region": None}, "needs facecam_region")):
        with pytest.raises(ValidationError) as e:
            LayoutOptions(**bad)
        assert reason in str(e.value), bad


def test_reframe_with_a_layout_and_a_resolution_end_to_end(client, user, video, transcriber, tmp_path):
    headers, _ = user
    up = upload(client, headers, video)                                       # a 640x360 upload
    bad = [({"layout": "pip", "aspect": "1:1"}, "not available in 1:1"), ({"layout": "ots"}, "not available in 9:16"),
           ({"resolution": "8k"}, "resolution")]
    for options, reason in bad:
        r = client.post("/v1/reframe", json={"upload_id": up["upload_id"], "options": options}, headers=headers)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error" and reason in r.text, r.text
    assert balance(client, headers) == 30                                     # refused before anything is reserved
    job = run(client, headers, "/v1/reframe", {"upload_id": up["upload_id"], "segments": [{"start": 5, "end": 9}],
                                               "options": {"layout": "pip", "facecam_region": "top-right", "resolution": "720"}},
              transcriber)
    info = probe(fetch(client, job["clips"][0]["video_url"], tmp_path / "r.mp4"))
    assert (info.width, info.height) == (360, 640)                            # 720 asked, the source has 360: no upscaling
    assert job["credits_charged"] == 1                                        # the price of a job is not touched
