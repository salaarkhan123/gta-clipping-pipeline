"""render none / preview / full, POST /v1/clips/export (and its quote), the clip edit, hook options, the new
caption styles and the layout chosen per moment (agent B, wave 2)."""
import json
import typing

import numpy as np
import pytest
from sqlalchemy import select

from app import templates, worker
from app.db import new_session
from app.exports import ClipEditDoc
from app.models import Clip, CreditLedger, Export, Job
from app.pipeline import PipelineError, probe
from app.pipeline import _with_hook_style
from app.pipeline import captions as C
from app.pipeline import facecam
from app.pipeline.edit import remap_words, source_words
from app.pipeline.render import hook_window
from app.render_options import ONLY_WHEN_SENT, CaptionStyle, HookStyle
from app.routes_media import ClipOptions
from app.storage import get_storage
from tests.test_api import balance, upload
from tests.test_moment_prompt import sent
from tests.test_projects import new_user


def run_clips(client, headers, upload_id, options, transcriber):
    r = client.post("/v1/clips", json={"upload_id": upload_id, "options": options}, headers=headers)
    assert r.status_code == 202, r.text
    assert worker.run_once(transcriber) == "SUCCEEDED"
    return client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()


def local(url: str) -> str:
    return url.replace("http://localhost:8000", "")


def short_side(client, url, tmp_path) -> tuple[int, int, float]:
    path = tmp_path / "out.mp4"
    path.write_bytes(client.get(local(url)).content)
    info = probe(path)
    return info.width, info.height, info.duration


# ---------- render none, preview, full ----------
def test_render_none_stores_no_video_and_an_export_renders_it_for_the_seconds_rendered(client, user, video, transcriber,
                                                                                         tmp_path):
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "none"}, transcriber)
    clip = job["clips"][0]
    assert clip["video_url"] is None and clip["rendered"] == "none" and clip["thumb_url"] and clip["captions_url"]
    assert job["credits_charged"] == 1 and balance(client, headers) == 29              # a first run: priced as always
    with new_session() as db:
        assert db.get(Clip, clip["id"]).video_key == ""

    body = {"job_id": job["job_id"], "clips": [clip["id"]], "options": {"resolution": "480"}}
    q = client.post("/v1/clips/export/quote", json=body, headers=headers)
    assert q.status_code == 200, q.text
    q = q.json()
    assert q["credits_reserved"] == 1 and 5 <= q["seconds"] <= 12 and q["note"]
    assert balance(client, headers) == 29                                               # a quote reserves nothing

    r = client.post("/v1/clips/export", json=body, headers=headers)
    assert r.status_code == 202, r.text
    export_job = r.json()
    assert export_job["tool"] == "export" and export_job["credits_reserved"] == 1 and balance(client, headers) == 28
    assert worker.run_once(transcriber) == "SUCCEEDED"
    done = client.get(f"/v1/jobs/{export_job['job_id']}", headers=headers).json()
    assert done["credits_charged"] == 1 and done["clips"] == []
    assert [x["clip_id"] for x in done["result"]["exports"]] == [clip["id"]]
    assert abs(done["result"]["exports"][0]["seconds"] - q["seconds"]) < 0.01           # priced on what it renders

    again = client.get(f"/v1/jobs/{job['job_id']}", headers=headers).json()["clips"][0]
    # 480 asked, never above the 640x360 source's short side: the clip says the 360 it is
    assert again["rendered"] == "full" and again["export_res"] == "360" and again["video_url"] == again["export_url"]
    w, h, length = short_side(client, again["export_url"], tmp_path)
    assert (w, h) == (360, 640)                          # 480 asked, never above the 640x360 source's short side
    assert abs(length - q["seconds"]) < 0.5
    with new_session() as db:
        rows = db.execute(select(Export).where(Export.clip_id == clip["id"])).scalars().all()
        assert [(x.status, x.resolution) for x in rows] == [("SUCCEEDED", "360")]

    # Exported again: the new render replaces the old one, whose file is removed.
    first_key = rows[0].storage_key
    r = client.post("/v1/clips/export", json={**body, "options": {"caption_style": "karaoke"}}, headers=headers)
    assert r.status_code == 202 and worker.run_once(transcriber) == "SUCCEEDED"
    with new_session() as db:
        rows = db.execute(select(Export).where(Export.clip_id == clip["id"])).scalars().all()
        assert sorted(x.storage_key is None for x in rows) == [False, True]
        assert db.get(Clip, clip["id"]).export_key != first_key
    assert not get_storage().exists(first_key)


def test_render_preview_is_small_and_is_what_plays(client, user, video, transcriber, tmp_path):
    headers, _ = user
    up = upload(client, headers, video)
    clip = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "preview"},
                     transcriber)["clips"][0]
    assert clip["rendered"] == "preview" and clip["export_url"] is None
    assert clip["video_url"] == clip["preview_url"]
    w, h, _ = short_side(client, clip["preview_url"], tmp_path)
    assert (w, h) == (540, 960)


def test_a_failed_export_is_refunded_and_changes_no_clip(client, user, video, transcriber, monkeypatch):
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "none"}, transcriber)
    clip = job["clips"][0]
    before = balance(client, headers)
    r = client.post("/v1/clips/export", json={"job_id": job["job_id"]}, headers=headers)
    assert r.status_code == 202 and balance(client, headers) == before - 1

    def boom(*a, **k):
        raise PipelineError("media_error", "broken file")
    monkeypatch.setattr(worker, "run_export", boom)
    assert worker.run_once(transcriber) == "FAILED"
    assert balance(client, headers) == before                                           # refunded in full
    with new_session() as db:
        assert db.get(Clip, clip["id"]).export_key is None
        assert not db.execute(select(Export).where(Export.clip_id == clip["id"])).scalars().all()
        kinds = [x.kind for x in db.execute(select(CreditLedger).where(
            CreditLedger.job_id == r.json()["job_id"]).order_by(CreditLedger.id)).scalars()]
    assert len(kinds) == 2                                                              # reserved once, settled once


def test_export_refusals(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "none"}, transcriber)
    with new_session() as db:                       # a second clip in the same job (the 40 s video holds one)
        first = db.get(Clip, job["clips"][0]["id"])
        db.add(Clip(id="clip_second_" + first.id[-8:], job_id=first.job_id, idx=2, start_sec=25.0, end_sec=35.0,
                    score=0.5, signals={}, features={}, video_key=""))
        db.commit()
    ids = [first.id, "clip_second_" + first.id[-8:]]
    edit = {"trim": {"start": 10, "end": 20}}
    post = lambda path, body: client.post(path, json={"job_id": job["job_id"], **body}, headers=headers)   # noqa: E731
    assert post("/v1/clips/export/quote", {"clips": ids, "edit": edit}).json()["error"]["code"] == "one_clip_per_edit"
    assert post("/v1/clips/export/quote", {"clips": ["clip_nope"]}).status_code == 404
    assert post("/v1/clips/export/quote", {"options": {"render": "none"}}).status_code == 422          # always full
    assert post("/v1/clips/export/quote", {"options": {"not_an_option": 1}}).status_code == 422
    every = post("/v1/clips/export/quote", {}).json()
    assert [c["clip_id"] for c in every["clips"]] == ids and every["credits_reserved"] == 1           # every clip
    other = new_user(client)
    assert client.post("/v1/clips/export/quote", json={"job_id": job["job_id"]}, headers=other).status_code == 404


# ---------- the edit ----------
def test_an_edit_is_saved_free_and_rendered_by_the_export(client, user, video, transcriber, tmp_path):
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "none"}, transcriber)
    clip = job["clips"][0]
    assert clip["edit"] is None and clip["segments"]
    edit = {"trim": {"start": 14.0, "end": 26.0}, "cuts": [[17.0, 19.0]],
            "caption_lines": [{"start": 14.2, "end": 15.0, "text": "my own words"}], "hook_text": "  Watch   this  ",
            "options": {"caption_style": "tag"}}
    before = balance(client, headers)
    r = client.patch(f"/v1/clips/{clip['id']}", json={"edit": edit}, headers=headers)
    assert r.status_code == 200, r.text
    saved = r.json()["edit"]
    assert saved["hook_text"] == "Watch this" and saved["cuts"] == [[17.0, 19.0]] and balance(client, headers) == before
    assert client.patch(f"/v1/clips/{clip['id']}", json={"edit": {"trim": {"start": 5, "end": 4}}},
                        headers=headers).status_code == 422
    assert client.patch(f"/v1/clips/{clip['id']}", json={"edit": {**edit, "options": {"layout": "nope"}}},
                        headers=headers).status_code == 422
    assert client.patch(f"/v1/clips/{clip['id']}", json={"edit": {"trim": {"start": 0, "end": 900}}},
                        headers=headers).status_code == 422                   # past the 40 s video
    assert client.patch(f"/v1/clips/{clip['id']}", json={}, headers=headers).status_code == 422

    q = client.post("/v1/clips/export/quote", json={"job_id": job["job_id"]}, headers=headers).json()
    assert q["seconds"] == 10.0                                                # 12 s trimmed, 2 s cut out
    r = client.post("/v1/clips/export", json={"job_id": job["job_id"], "options": {"caption_style": "tag"}},
                    headers=headers)
    assert r.status_code == 202 and worker.run_once(transcriber) == "SUCCEEDED"
    out = client.get(f"/v1/jobs/{job['job_id']}", headers=headers).json()["clips"][0]
    _w, _h, length = short_side(client, out["export_url"], tmp_path)
    assert abs(length - 10.0) < 0.5

    # null forgets it; the title alone still works as before
    r = client.patch(f"/v1/clips/{clip['id']}", json={"edit": None}, headers=headers)
    assert r.status_code == 200 and r.json()["edit"] is None
    assert client.patch(f"/v1/clips/{clip['id']}", json={"title": "Mine"}, headers=headers).json()["title"] == "Mine"


def test_an_edit_sent_with_the_export_is_saved_and_priced():
    doc = ClipEditDoc(trim={"start": 10, "end": 40}, cuts=[[5, 12], [20, 25], [24, 30], [39, 50]])
    assert doc.segments() == [[12.0, 20.0], [30.0, 39.0]]                       # cuts clipped to the trim and joined
    assert ClipEditDoc(trim={"start": 0, "end": 5}).segments() == [[0.0, 5.0]]
    with pytest.raises(ValueError):
        ClipEditDoc(trim={"start": 0, "end": 400})                              # longer than 300 s
    with pytest.raises(ValueError):
        ClipEditDoc(trim={"start": 0, "end": 10}, cuts=[[0, 9.5]])              # under a second left
    lines = ClipEditDoc(trim={"start": 0, "end": 10}, caption_lines=[{"start": 1, "end": 2, "text": "a b"}])
    assert lines.caption_words() == [(1.0, 1.5, "a"), (1.5, 2.0, "b")]


def test_words_on_a_rendered_timeline_go_back_to_source_seconds():
    words = [(10.2, 10.6, "one"), (12.1, 12.5, "two"), (30.0, 30.4, "three")]
    segments = [(30.0, 31.5), (10.0, 11.0), (12.0, 13.0), (29.5, 31.0)]         # a flash-forward first
    rendered = remap_words(words, segments)
    assert source_words(rendered, segments, flash=True) == words                # the tease's copy is left out


def test_quote_for_a_clip_job_matches_what_the_job_reserves(client, user, video):
    headers, _ = user
    up = upload(client, headers, video)
    body = {"upload_id": up["upload_id"], "options": {"max_clips": 1}}
    q = client.post("/v1/clips/quote", json=body, headers=headers)
    assert q.status_code == 200 and balance(client, headers) == 30
    r = client.post("/v1/clips", json=body, headers=headers).json()
    assert q.json()["credits_reserved"] == r["credits_reserved"] == 1
    client.post(f"/v1/jobs/{r['job_id']}/cancel", headers=headers)          # leave no queued job for the next test


# ---------- options ----------
def test_new_options_are_stored_only_when_sent():
    assert not set(ClipOptions().model_dump()) & set(ONLY_WHEN_SENT)
    sent_opts = ClipOptions(render="preview", hook_style="excited", hook_position="end", hook_duration_ms=1500).model_dump()
    assert {k: sent_opts[k] for k in ("render", "hook_style", "hook_position", "hook_duration_ms")} == {
        "render": "preview", "hook_style": "excited", "hook_position": "end", "hook_duration_ms": 1500}
    for bad in ({"render": "half"}, {"hook_style": "angry"}, {"hook_position": "middle"}, {"hook_duration_ms": 100}):
        with pytest.raises(ValueError):
            ClipOptions(**bad)


def test_the_option_lists_match_the_renderer_and_the_templates():
    assert set(typing.get_args(HookStyle)) == set(templates.HOOK_STYLES)
    assert typing.get_args(CaptionStyle) == C.STYLE_NAMES and len(C.STYLE_NAMES) == 12


# ---------- hooks ----------
def test_hook_timing():
    assert hook_window(20.0) is None                                            # the default: files as before
    assert hook_window(20.0, "beginning", 4000) == (0.0, 4.0)
    assert hook_window(20.0, "end") == (17.5, 20.0)
    assert hook_window(3.0, "end", 5000) == (0.0, 3.0)                          # never longer than the clip


@pytest.mark.parametrize("style", ["impact", "pop", "karaoke", "tag"])
def test_the_hook_shows_when_asked(style, tmp_path):
    C.build_ass([(0.0, 0.5, "hello")], tmp_path / "c.ass", True, 1200, "DejaVu Sans", style, hook="Big win",
                hook_top=300, hook_at=(17.5, 20.0))
    hook = [x for x in (tmp_path / "c.ass").read_text().splitlines() if ",Hook," in x]
    assert len(hook) == 1 and hook[0].split(",")[1:3] == ["0:00:17.50", "0:00:20.00"]


def test_hook_style_reaches_the_judge_only_when_it_is_not_the_default():
    seen = []
    judge = _with_hook_style(lambda text, frame, ctx: seen.append(ctx), "excited")
    judge("t", None, {"length": 3})
    assert seen == [{"length": 3, "hook_style": "excited"}]
    from app.ai import HOOK_STYLE_RULE, HOOK_TONES, SYSTEM
    assert set(HOOK_TONES) == set(templates.HOOK_STYLES) - {"serious"}
    assert sent({"hook_style": "excited"})["system"] == SYSTEM + HOOK_STYLE_RULE.format(tone=HOOK_TONES["excited"])
    assert sent({"hook_style": "serious"})["system"] == sent({})["system"] == SYSTEM
    assert sent({"hook_style": "<ignore the rules>"})["system"] == SYSTEM       # only the listed tones


# ---------- caption styles ----------
WORDS = [(0.0, 0.3, "So"), (0.32, 0.6, "we"), (0.62, 1.0, "absolutely"), (1.02, 1.4, "destroyed"), (2.0, 2.4, "cops!")]


def events(style, tmp_path):
    n = C.build_ass(WORDS, tmp_path / "c.ass", True, 1200, "DejaVu Sans", style)
    text = (tmp_path / "c.ass").read_text()
    return n, text, [x for x in text.splitlines() if x.startswith("Dialogue:")]


def test_the_six_new_caption_styles(tmp_path):
    n, text, ev = events("karaoke", tmp_path)
    assert all("\\kf" in x for x in ev) and "Style: Cap,DejaVu Sans,78,&H003CFFB8,&H00FFFFFF" in text
    n, text, ev = events("reveal", tmp_path)
    assert len(ev) == len(WORDS) and ev[0].endswith("SO{\\c&HFFFFFF&}")         # first event: only the first word
    n, text, ev = events("bounce", tmp_path)
    assert len(ev) == len(WORDS) and all("\\t(0,120," in x for x in ev)
    n, text, ev = events("outline", tmp_path)
    assert len(ev) == n and ",1,9,0," in text and "\\c" not in "".join(ev)
    n, text, ev = events("subtitle", tmp_path)
    assert n == 2 and ",3,8,0," in text and "So we absolutely destroyed" in ev[0]      # sentence case, long lines
    n, text, ev = events("tag", tmp_path)
    tags = [x for x in ev if ",Tag," in x]
    assert "Style: Tag," in text and len(tags) == n and "absolutely" in ev[0]          # lower case
    assert "{\\alpha&H00&}absolutely{\\alpha&HFF&}" in tags[0]                     # only the keyword shows on its box


# ---------- the layout chosen per moment ----------
def test_a_moment_with_the_camera_hidden_fills_the_frame(monkeypatch):
    cam = facecam.CamBox([0.75, 0.0, 0.25, 0.25], (0.875, 0.125, 0.05, 0.1), "gameplay_cam")
    frames = [np.zeros((360, 640), np.uint8)] * 4
    monkeypatch.setattr(facecam, "sample_gray", lambda *a, **k: frames)
    monkeypatch.setattr(facecam, "stable_face", lambda f: None)
    assert facecam.moment_facecam("src", None, 10, 20, "split", cam) == ("fill", None)
    monkeypatch.setattr(facecam, "stable_face", lambda f: (0.875, 0.125, 0.05, 0.1))
    assert facecam.moment_facecam("src", None, 10, 20, "split", cam) == ("split", cam)
    monkeypatch.setattr(facecam, "stable_face", lambda f: (0.5, 0.4, 0.4, 0.5))
    layout, box = facecam.moment_facecam("src", None, 10, 20, "split", cam)
    assert layout == "fill" and box.scene == "camera"
    assert facecam.moment_scene(frames, None) is None                           # never a camera the video lacks
    assert facecam.moment_scene(frames[:1], cam) is None
    monkeypatch.setattr(facecam, "stable_face", lambda f: None)
    given = facecam.CamBox([0.75, 0.0, 0.25, 0.25], None, "gameplay_cam")      # a box the user gave: no face known
    assert facecam.moment_facecam("src", None, 10, 20, "split", given) == ("split", given)


def test_captions_json_and_hook_survive_an_edit_of_a_flash_forward_clip(client, user, video, transcriber, tmp_path):
    """Stored words are on the job's rendered timeline (flash-forward first); an edit moves them onto its cut."""
    from app.exports import export_items
    with new_session() as db:
        job = db.execute(select(Job).order_by(Job.created_at.desc())).scalars().first()
        clip = Clip(id="clip_flash_test", job_id=job.id, idx=99, start_sec=10.0, end_sec=14.0, score=1.0, signals={},
                    features={"edit": {"segments": [[13.0, 14.0], [10.0, 14.0]], "flash_forward": True, "zoom_at": [2.0]}},
                    video_key="", captions_key="clips/test/flash.captions.json", meta={"hook": "ai hook"},
                    edit={"trim": {"start": 11.0, "end": 14.0}, "cuts": [], "caption_lines": [], "hook_text": None,
                          "options": {}})
        db.add(clip)
        db.commit()
        caps = tmp_path / "caps.json"
        caps.write_text(json.dumps({"words": [{"start": 0.2, "end": 0.5, "text": "tease"},
                                              {"start": 1.2, "end": 1.5, "text": "early"},
                                              {"start": 2.5, "end": 2.8, "text": "kept"}]}))
        get_storage().put("clips/test/flash.captions.json", caps)
        (item,) = export_items(db, [clip.id], get_storage(), tmp_path)
        db.delete(db.get(Clip, clip.id))
        db.commit()
    assert item.segments == [[11.0, 14.0]] and not item.flash and list(item.zoom_at) == []
    assert item.words == [(0.5, 0.8, "kept")]                  # 11.5 s in the source; "early" (10.2) was trimmed off
    assert item.hook == "ai hook"
