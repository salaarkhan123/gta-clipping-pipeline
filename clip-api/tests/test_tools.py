"""Reframe, Captions and Video Finder."""
from app import worker
from app.pipeline.captions import CAPTION_STYLES, build_ass
from app.pipeline.ff import probe
from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline.tools import search_transcript
from tests.test_api import balance, upload


def run(client, headers, path, body, transcriber):
    r = client.post(path, json=body, headers=headers)
    assert r.status_code == 202, r.text
    assert worker.run_once(transcriber) == "SUCCEEDED"
    return client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()


def fetch(client, url, dest):
    dest.write_bytes(client.get(url.replace("http://localhost:8000", "")).content)
    return dest


def test_search_transcript_ranks_exact_phrase_first():
    t = {"segments": [{"start": 10, "end": 12, "text": "that was no good way to do it"},
                      {"start": 50, "end": 52, "text": "No way, bro!"},
                      {"start": 90, "end": 91, "text": "there is no"}, {"start": 91, "end": 93, "text": "way out"},
                      {"start": 200, "end": 202, "text": "completely unrelated"}]}
    hits = search_transcript(t, "no way", 5)
    assert [h["start"] for h in hits[:2]] == [50, 90] and hits[0]["score"] == 1.0   # exact, then straddling
    assert any(h["start"] == 10 and h["score"] < 1 for h in hits)                    # both words, not adjacent
    assert search_transcript(t, "banana", 5) == [] and search_transcript(t, "!!!", 5) == []
    assert len(search_transcript(t, "no way", 1)) == 1


def test_caption_styles_all_build(tmp_path):
    words = [(0.0, 0.4, "no"), (0.4, 0.8, "way"), (0.8, 1.2, "{bro}")]
    for style in CAPTION_STYLES:
        assert build_ass(words, tmp_path / f"{style}.ass", True, 1200, "DejaVu Sans", style) >= 1
        text = (tmp_path / f"{style}.ass").read_text()
        assert "Dialogue:" in text and "{bro}" not in text


def test_reframe_segment_split_layout(client, user, video, transcriber, tmp_path):
    headers, _ = user
    up = upload(client, headers, video)
    job = run(client, headers, "/v1/reframe", {"upload_id": up["upload_id"], "segments": [{"start": 5, "end": 17}],
                                               "options": {"facecam_region": "bottom-right"}}, transcriber)
    assert job["tool"] == "render" and job["credits_charged"] == 1 and len(job["clips"]) == 1
    clip = job["clips"][0]
    assert (clip["start_sec"], clip["end_sec"]) == (5.0, 17.0) and clip["captions_url"] is None
    info = probe(fetch(client, clip["video_url"], tmp_path / "r.mp4"))
    assert (info.width, info.height) == (720, 1280) and 11 <= info.duration <= 13   # free plan exports 720p
    assert balance(client, headers) == 29


def test_captions_whole_video_keeps_source_frame(client, user, video, transcriber, tmp_path):
    headers, _ = user
    up = upload(client, headers, video)
    job = run(client, headers, "/v1/captions", {"upload_id": up["upload_id"], "options": {"caption_style": "boxed"}},
              transcriber)
    clip = job["clips"][0]
    assert clip["captions_url"] and clip["end_sec"] >= 39
    info = probe(fetch(client, clip["video_url"], tmp_path / "c.mp4"))
    assert (info.width, info.height) == (640, 360)


def test_render_validation(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    bad = [({"segments": [{"start": 100, "end": 120}]}, 422, "bad_segment"),
           ({"segments": [{"start": 5, "end": 5.5}]}, 422, "validation_error"),
           ({"options": {"layout": "split", "facecam_region": None}}, 422, "validation_error"),
           ({"options": {"facecam_box": [0.9, 0.9, 0.5, 0.5]}}, 422, "validation_error")]
    for extra, code, err in bad:
        r = client.post("/v1/reframe", json={"upload_id": up["upload_id"], **extra}, headers=headers)
        assert r.status_code == code and r.json()["error"]["code"] == err, (extra, r.text)
    assert balance(client, headers) == 30


def test_find_transcribes_once_then_searches_free(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    uid = up["upload_id"]
    assert client.get(f"/v1/uploads/{uid}/search?q=no+way", headers=headers).status_code == 409

    job = run(client, headers, "/v1/find", {"upload_id": uid, "query": "No way!", "max_results": 3,
                                            "clip_length": 10}, transcriber)
    assert job["tool"] == "find" and job["result"]["transcript_cached"] is False
    m = job["result"]["matches"]
    assert len(m) == 1 and m[0]["start"] == 5.0 and m[0]["score"] == 1.0
    assert len(job["clips"]) == 1 and job["clips"][0]["signals"] == {"speech": 1.0}
    assert job["clips"][0]["start_sec"] <= 5.0 < job["clips"][0]["end_sec"]

    # Transcript is cached: free instant search, and a second find job never calls the transcriber.
    r = client.get(f"/v1/uploads/{uid}/search?q=oh+my+god", headers=headers).json()
    assert r["matches"][0]["start"] == 1.0
    again = client.post("/v1/find", json={"upload_id": uid, "query": "god", "make_clips": False}, headers=headers)
    assert again.status_code == 202 and again.json()["credits_reserved"] == 1
    assert worker.run_once(None) == "SUCCEEDED"
    done = client.get(f"/v1/jobs/{again.json()['job_id']}", headers=headers).json()
    assert done["result"]["transcript_cached"] is True and done["clips"] == [] and done["result"]["matches"]


def test_find_no_match_and_other_account(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job = run(client, headers, "/v1/find", {"upload_id": up["upload_id"], "query": "pineapple"}, transcriber)
    assert job["result"]["matches"] == [] and job["clips"] == []
    other = client.post("/v1/auth/signup", json={"email": f"x{up['upload_id']}@example.org",
                                                 "password": "correct-horse-9"}).json()
    oh = {"Authorization": f"Bearer {other['token']}"}
    assert client.get(f"/v1/uploads/{up['upload_id']}/search?q=god", headers=oh).status_code == 404
    assert client.post("/v1/find", json={"upload_id": up["upload_id"], "query": "god"}, headers=oh).status_code == 404
    assert [u["upload_id"] for u in client.get("/v1/uploads", headers=headers).json()["uploads"]] == [up["upload_id"]]


# ---------- facecam detection, visual search, pay-once pricing, timings ----------
import subprocess

import numpy as np
import pytest

from app.db import new_session
from app.models import Upload
from app.pipeline.facecam import detect_facecam
from app.pipeline.visual import build_visual_index, keyframe_gap, search_visual


class FakeEmbedder:
    """Stands in for CLIP: an image is its mean colour; a text is the colour it names."""
    COLORS = {"red": (1.0, 0.0, 0.0), "blue": (0.0, 0.0, 1.0)}

    def embed_images(self, frames):
        v = frames.reshape(len(frames), -1, 3).mean(axis=1).astype(np.float32) + 1e-3
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def embed_text(self, texts):
        out = []
        for t in texts:
            c = next((v for k, v in self.COLORS.items() if k in t.lower()), (0.577, 0.577, 0.577))
            out.append(c)
        return np.asarray(out, dtype=np.float32)


def make_video(path, extra_inputs=(), vf="null", gop=None, size="640x360", dur=40):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=15:duration={dur}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", *extra_inputs,
                    "-filter_complex", vf, "-map", "[v]", "-map", "1:a", *(["-g", str(gop)] if gop else []),
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def red_video(tmp_path_factory):
    """Test pattern with a solid red screen from 20 s to 26 s. Keyframe every second."""
    p = tmp_path_factory.mktemp("v") / "red.mp4"
    return make_video(p, vf="[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=red:t=fill:enable='between(t,20,26)'[v]", gop=15)


def test_facecam_auto_detects_static_face_overlay(tmp_path):
    skdata = pytest.importorskip("skimage.data")
    import cv2
    cv2.imwrite(str(tmp_path / "face.png"), cv2.cvtColor(skdata.astronaut(), cv2.COLOR_RGB2BGR))
    src = make_video(tmp_path / "cam.mp4", ("-loop", "1", "-i", str(tmp_path / "face.png")), size="1280x720",
                     vf="[2:v]scale=400:400[f];[0:v][f]overlay=880:320:shortest=1[v]")
    box = detect_facecam(src, probe(src))
    assert box is not None
    x, y, w, h = box
    assert x + w / 2 > 0.6 and y + h / 2 > 0.4 and 0.1 < w < 0.6       # camera found in the bottom-right
    results = run_pipeline(src, PipelineOptions(max_clips=1, clip_length=10, facecam_region="auto"), tmp_path / "o")
    assert probe(results[0].video_path).height == 1920


def test_facecam_auto_falls_back_when_no_face(video, tmp_path):
    assert detect_facecam(video, probe(video)) is None
    results = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, layout="split", facecam_region="auto"),
                           tmp_path / "o")
    assert len(results) == 1                                             # no camera found: fill layout, no error


def test_visual_index_and_search(red_video, video):
    info = probe(red_video)
    assert keyframe_gap(red_video) == pytest.approx(1.0, abs=0.2)        # dense keyframes: fast path
    emb, step = build_visual_index(red_video, info, FakeEmbedder())
    assert emb.dtype == np.float16 and 17 <= len(emb) <= 21 and step == 2.0
    hits = search_visual(emb, step, FakeEmbedder(), "red", 5, info.duration)
    assert len(hits) == 1 and hits[0]["kind"] == "visual" and 18 <= hits[0]["start"] <= 22 and hits[0]["end"] <= 28
    assert search_visual(emb, step, FakeEmbedder(), "blue", 5, info.duration) == []
    emb2, _ = build_visual_index(video, probe(video), FakeEmbedder())    # sparse keyframes: full-decode path
    assert 17 <= len(emb2) <= 21


def test_find_visual_end_to_end_and_index_cached(client, user, red_video, transcriber):
    headers, _ = user
    up = upload(client, headers, red_video)
    body = {"upload_id": up["upload_id"], "query": "red", "mode": "visual", "clip_length": 10}
    r = client.post("/v1/find", json=body, headers=headers)
    assert r.status_code == 202
    assert worker.run_once(transcriber, embedder=FakeEmbedder()) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    m = job["result"]["matches"]
    assert len(m) == 1 and m[0]["kind"] == "visual" and job["result"]["visual_cached"] is False
    assert job["clips"][0]["start_sec"] <= m[0]["start"] < job["clips"][0]["end_sec"]
    assert job["clips"][0]["signals"] == {"visual": 1.0}
    assert "indexing_frames" in job["result"]["timings"] and job["result"]["speed_x"] > 0

    class NoImages(FakeEmbedder):                    # second search must reuse the stored index
        def embed_images(self, frames):
            raise AssertionError("index was rebuilt")
    r2 = client.post("/v1/find", json={**body, "make_clips": False}, headers=headers)
    assert worker.run_once(None, embedder=NoImages()) == "SUCCEEDED"
    done = client.get(f"/v1/jobs/{r2.json()['job_id']}", headers=headers).json()
    assert done["result"]["visual_cached"] is True and len(done["result"]["matches"]) == 1


def test_find_auto_survives_broken_visual_model(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)

    class Broken:
        def embed_images(self, frames):
            raise RuntimeError("model failed to load")
        embed_text = embed_images
    r = client.post("/v1/find", json={"upload_id": up["upload_id"], "query": "no way", "make_clips": False}, headers=headers)
    assert worker.run_once(transcriber, embedder=Broken()) == "SUCCEEDED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert [m["kind"] for m in job["result"]["matches"]] == ["speech"]
    r = client.post("/v1/find", json={"upload_id": up["upload_id"], "query": "x", "mode": "visual"}, headers=headers)
    assert worker.run_once(transcriber, embedder=Broken()) == "FAILED"
    assert client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["error"]["code"] == "visual_unavailable"
    assert balance(client, headers) == 29            # the failed job was refunded


def test_video_is_charged_once(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    with new_session() as db:                        # pretend this is a 10-minute video
        db.get(Upload, up["upload_id"]).duration_sec = 600
        db.commit()
    first = client.post("/v1/clips", json={"upload_id": up["upload_id"]}, headers=headers).json()
    assert first["credits_reserved"] == 10
    client.post(f"/v1/jobs/{first['job_id']}/cancel", headers=headers)
    with new_session() as db:                        # ...and a full-price job has since succeeded on it
        db.get(Upload, up["upload_id"]).analyzed = True
        db.commit()
    again = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 2, "clip_length": 30}},
                        headers=headers).json()
    assert again["credits_reserved"] == 1            # 2 x 30 s rendered
    client.post(f"/v1/jobs/{again['job_id']}/cancel", headers=headers)
    find = client.post("/v1/find", json={"upload_id": up["upload_id"], "query": "x", "make_clips": False},
                       headers=headers).json()
    assert find["credits_reserved"] == 1             # index not built yet, but the video is already paid for
    client.post(f"/v1/jobs/{find['job_id']}/cancel", headers=headers)
    whole = client.post("/v1/reframe", json={"upload_id": up["upload_id"]}, headers=headers)
    assert whole.status_code == 202 and whole.json()["credits_reserved"] == 10   # no 30-minute cap; pay per rendered minute
    client.post(f"/v1/jobs/{whole.json()['job_id']}/cancel", headers=headers)
    assert balance(client, headers) == 30
