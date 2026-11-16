"""1.2: like, dislike, bookmark, keep/discard; the append-only clip_feedback log; library sort and filter."""
from sqlalchemy import select

from app.db import new_session
from app.models import ClipFeedback
from tests.test_projects import make_clips, new_user
from tests.test_api import upload


def clips_of(client, headers, video, transcriber, runs=2):
    up = upload(client, headers, video)
    for _ in range(runs):
        make_clips(client, headers, up["upload_id"], transcriber, n=1)
    return up, client.get(f"/v1/projects/{up['upload_id']}", headers=headers).json()["clips"]


def log_of(clip_id):
    with new_session() as db:
        return [(f.kind, f.value) for f in db.execute(select(ClipFeedback).where(ClipFeedback.clip_id == clip_id)
                                                      .order_by(ClipFeedback.id)).scalars()]


def test_reactions_are_stored_on_the_clip_and_logged_in_order(client, user, video, transcriber):
    headers, _ = user
    up, clips = clips_of(client, headers, video, transcriber, runs=1)
    cid = clips[0]["id"]
    assert (clips[0]["reaction"], clips[0]["bookmarked"], clips[0]["kept"]) == (None, False, None)
    fb = lambda body: client.post(f"/v1/clips/{cid}/feedback", json=body, headers=headers)   # noqa: E731
    assert fb({"reaction": "like"}).json() == {"id": cid, "kept": None, "reaction": "like", "bookmarked": False}
    assert fb({"reaction": "like"}).status_code == 200                       # same again: no new log row
    assert fb({"reaction": "dislike", "bookmarked": True}).json()["reaction"] == "dislike"
    assert fb({"kept": True}).json()["kept"] is True                         # the old body still works
    assert fb({"reaction": None, "bookmarked": False}).json() == {"id": cid, "kept": True, "reaction": None, "bookmarked": False}
    assert log_of(cid) == [("reaction", "like"), ("bookmarked", "true"), ("reaction", "dislike"), ("kept", "true"),
                           ("bookmarked", "false"), ("reaction", None)]
    clip = client.get(f"/v1/projects/{up['upload_id']}", headers=headers).json()["clips"][0]
    assert (clip["reaction"], clip["bookmarked"], clip["kept"]) == (None, False, True)


def test_bad_feedback_is_rejected_and_strangers_cannot_react(client, user, video, transcriber):
    headers, _ = user
    _, clips = clips_of(client, headers, video, transcriber, runs=1)
    cid = clips[0]["id"]
    for bad in ({}, {"reaction": "love"}, {"bookmarked": None}, {"stars": 5}):
        assert client.post(f"/v1/clips/{cid}/feedback", json=bad, headers=headers).status_code == 422, bad
    assert client.post(f"/v1/clips/{cid}/feedback", json={"reaction": "like"}, headers=new_user(client)).status_code == 404
    assert log_of(cid) == []


def test_library_sorts_and_filters(client, user, video, transcriber):
    headers, _ = user
    _, clips = clips_of(client, headers, video, transcriber, runs=3)
    a, b, c = [x["id"] for x in clips]
    client.post(f"/v1/clips/{a}/feedback", json={"kept": True, "bookmarked": True}, headers=headers)
    client.post(f"/v1/clips/{b}/feedback", json={"kept": False, "reaction": "like"}, headers=headers)
    ids = lambda q: [x["id"] for x in client.get(f"/v1/clips?{q}", headers=headers).json()["clips"]]   # noqa: E731
    assert ids("filter=kept") == [a] and ids("filter=discarded") == [b]
    assert ids("filter=bookmarked") == [a] and ids("filter=liked") == [b]
    assert client.get("/v1/clips?filter=kept", headers=headers).json()["total"] == 1
    by_score = client.get("/v1/clips?sort=score", headers=headers).json()["clips"]
    assert [x["score"] for x in by_score] == sorted((x["score"] for x in by_score), reverse=True) and len(by_score) == 3
    by_time = client.get("/v1/clips?sort=time", headers=headers).json()["clips"]
    assert [x["start_sec"] for x in by_time] == sorted(x["start_sec"] for x in by_time)
    assert client.get("/v1/clips?sort=random", headers=headers).status_code == 422
