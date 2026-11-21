"""A clip's thumbnail follows the user's choices: `thumbnail_text` (independent of the video's `hook_overlay`), and
new words drawn on the same frame when the title or hook is edited (PATCH /v1/clips/{id})."""
import time
from datetime import timedelta

import pytest
from PIL import Image, ImageChops

from app import worker
from app.db import new_session
from app.models import Clip, Job, utcnow
from app.pipeline import PipelineOptions, run_pipeline
from app.storage import get_storage
from tests.test_api import upload
from tests.test_thumbs import LateAI


def drawn_on(thumb, frame) -> bool:
    with Image.open(thumb) as a, Image.open(frame) as b:
        diff = ImageChops.difference(a.convert("L"), b.convert("L")).point(lambda v: 255 if v > 40 else 0)
        return diff.getbbox() is not None


@pytest.mark.parametrize("thumbnail_text,hook_overlay", [(True, True), (True, False), (False, True), (False, False)])
def test_thumbnail_text_and_the_videos_hook_are_separate_choices(video, transcriber, tmp_path, thumbnail_text,
                                                                 hook_overlay):
    def judge(text, frame, context):
        return {"title": "A title", "hook": "No way he made that", "virality": {"score": 80}}
    r, = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False, hook_overlay=hook_overlay,
                                             thumbnail_text=thumbnail_text),
                      tmp_path / "out", transcriber=transcriber, judge=judge)
    assert r.features["thumbnail"]["text"] is thumbnail_text
    assert drawn_on(r.thumb_path, r.frame_path) is thumbnail_text
    assert bool(r.features["edit"]["hook"]) is hook_overlay                      # the video's hook: its own option


def test_thumbnail_text_is_a_listed_option_that_defaults_on(client):
    from app.render_options import LayoutOptions
    assert LayoutOptions().thumbnail_text is True and LayoutOptions(thumbnail_text=False).thumbnail_text is False
    assert "thumbnail_text" in client.get("/v1/options").text


def run_job(client, headers, video, transcriber, ai=None, **options) -> dict:
    up = upload(client, headers, video)
    r = client.post("/v1/clips", headers=headers, json={"upload_id": up["upload_id"],
                                                        "options": {"max_clips": 1, "clip_length": 10, **options}})
    assert r.status_code == 202, r.text
    assert worker.run_once(transcriber, ai=ai or LateAI()) == "SUCCEEDED"
    clip, = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["clips"]
    return clip


def stored(clip_id: str) -> tuple[bytes, dict]:
    with new_session() as db:
        row = db.get(Clip, clip_id)
        return get_storage().path(row.thumb_key).read_bytes(), dict(row.features["thumbnail"])


def test_editing_the_hook_draws_the_thumbnail_again_on_the_same_frame(client, user, video, transcriber):
    headers, _ = user
    clip = run_job(client, headers, video, transcriber)
    first, record = stored(clip["id"])
    assert record["text"] is True and get_storage().exists(record["frame_key"])   # the frame is kept with the clip

    start = time.perf_counter()
    r = client.patch(f"/v1/clips/{clip['id']}", headers=headers, json={"hook": "Cops never stood a chance"})
    took = time.perf_counter() - start
    assert r.status_code == 200, r.text
    assert r.json()["hook"] == "Cops never stood a chance" and r.json()["thumb_url"]
    second, after = stored(clip["id"])
    assert second != first and after["text"] is True and after["at"] == record["at"]   # same frame, new words
    assert took < 1.0                                                          # drawn in the request

    r = client.patch(f"/v1/clips/{clip['id']}", headers=headers, json={"title": "A new title"})
    assert r.status_code == 200 and r.json()["title"] == "A new title"
    assert stored(clip["id"])[0] == second                                     # it shows the hook: nothing to draw


class NoHookAI(LateAI):
    def clip_meta(self, transcript, context, thumb=None):
        meta = super().clip_meta(transcript, context, thumb)
        return {**meta, "hook": None} if meta else meta


def test_without_a_hook_a_title_edit_changes_the_thumbnail(client, user, video, transcriber):
    headers, _ = user
    clip = run_job(client, headers, video, transcriber, ai=NoHookAI())
    first, record = stored(clip["id"])
    assert record["text"] is True                                              # the title is on it
    assert client.patch(f"/v1/clips/{clip['id']}", headers=headers, json={"title": "Wrong car bro"}).status_code == 200
    assert stored(clip["id"])[0] != first


def test_a_job_with_the_video_hook_off_still_puts_the_words_on_the_thumbnail(client, user, video, transcriber):
    headers, _ = user
    clip = run_job(client, headers, video, transcriber, hook_overlay=False)
    assert stored(clip["id"])[1]["text"] is True


def test_with_thumbnail_text_off_an_edit_still_draws_no_text(client, user, video, transcriber):
    headers, _ = user
    clip = run_job(client, headers, video, transcriber, thumbnail_text=False)
    first, record = stored(clip["id"])
    assert record["text"] is False                                             # the AI's late hook was not drawn
    r = client.patch(f"/v1/clips/{clip['id']}", headers=headers, json={"hook": "Cops never stood a chance"})
    assert r.status_code == 200 and r.json()["hook"] == "Cops never stood a chance"
    assert stored(clip["id"]) == (first, record)


def test_an_edit_needs_some_words_and_keeps_the_hooks_rules(client, user, video, transcriber):
    headers, _ = user
    clip = run_job(client, headers, video, transcriber)
    assert client.patch(f"/v1/clips/{clip['id']}", headers=headers, json={}).status_code == 422
    assert client.patch(f"/v1/clips/{clip['id']}", headers=headers, json={"hook": "x" * 49}).status_code == 422
    r = client.patch(f"/v1/clips/{clip['id']}", headers=headers, json={"hook": "one two three four five six seven"})
    assert r.status_code == 200 and r.json()["hook"] == "one two three four five six"   # six words at most


def test_a_clip_made_before_frames_were_kept_keeps_its_thumbnail_on_edit(client, user, video, transcriber):
    headers, _ = user
    clip = run_job(client, headers, video, transcriber)
    with new_session() as db:
        row = db.get(Clip, clip["id"])
        row.features = {**row.features, "thumbnail": {k: v for k, v in row.features["thumbnail"].items()
                                                      if k != "frame_key"}}
        db.commit()
    first, _ = stored(clip["id"])
    r = client.patch(f"/v1/clips/{clip['id']}", headers=headers, json={"hook": "Cops never stood a chance"})
    assert r.status_code == 200 and r.json()["hook"] == "Cops never stood a chance"
    assert stored(clip["id"])[0] == first


def test_the_stored_frame_goes_when_the_clip_expires(client, user, video, transcriber):
    headers, _ = user
    clip = run_job(client, headers, video, transcriber)
    _, record = stored(clip["id"])
    assert get_storage().exists(record["frame_key"])
    with new_session() as db:
        db.get(Job, clip["job_id"]).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    worker.sweep_expired()
    assert not get_storage().exists(record["frame_key"])


@pytest.mark.parametrize("render", ["none", "preview", "full"])
def test_every_render_mode_gets_the_same_kind_of_thumbnail(video, transcriber, tmp_path, render):
    """The thumbnail is drawn from the source, not from the rendered video: a clip with no video yet (render
    "none") or only a preview has the same thumbnail, with its hook, as a full render."""
    def judge(text, frame, context):
        return {"title": "A title", "hook": "No way he made that", "virality": {"score": 80}}
    r, = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False, render=render),
                      tmp_path / "out", transcriber=transcriber, judge=judge)
    assert (r.video_path is None) is (render == "none")
    assert r.thumb_path.exists() and r.frame_path.exists() and r.features["thumbnail"]["text"] is True
    with Image.open(r.thumb_path) as im:
        assert im.size == (360, 640)                                          # 720 short side, never above the source
