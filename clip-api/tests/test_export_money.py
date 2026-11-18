"""The owner's conditions for the export price (PR #136): downloads are free, a repeated request is not charged
twice, the ledger stays one reserve, one settle and at most one refund per export, the quote is the price, the
API keeps rendering in full by default, an edit keeps the job's dead-air cuts, and the provisional layouts stay
off until they are turned on."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import ledger, worker
from app.config import get_settings
from app.db import new_session
from app.exports import export_items
from app.models import Clip, CreditLedger, Export, Job, new_id, utcnow
from app.storage import get_storage
from tests.test_api import balance, upload
from tests.test_export import local, run_clips


def add_clip(job_id: str, start: float, end: float, features: dict | None = None) -> str:
    """A clip in a finished job, with no video (as `render: none` leaves it)."""
    clip_id = new_id("clip")
    with new_session() as db:
        idx = db.execute(select(func.count()).select_from(Clip).where(Clip.job_id == job_id)).scalar_one() + 1
        db.add(Clip(id=clip_id, job_id=job_id, idx=idx, start_sec=start, end_sec=end, score=0.5, signals={},
                    features=features or {}, video_key=""))
        db.commit()
    return clip_id


def ledger_rows(job_id: str) -> list[tuple[str, int]]:
    with new_session() as db:
        return [(x.kind, x.delta) for x in db.execute(select(CreditLedger).where(CreditLedger.job_id == job_id)
                                                      .order_by(CreditLedger.id)).scalars()]


def jobs_of(client, headers) -> int:
    return len(client.get("/v1/jobs?limit=100", headers=headers).json()["jobs"])


def cancel(client, headers, job_id: str) -> None:
    """A queued job is cancelled and refunded, so no test leaves work for the next one's worker."""
    assert client.post(f"/v1/jobs/{job_id}/cancel", headers=headers).json()["status"] == "CANCELED"


@pytest.fixture
def none_job(client, user, video, transcriber):
    """(headers, finished job, its one clip) from `render: none`: 29 credits left."""
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "none"}, transcriber)
    return headers, job, job["clips"][0]


def post(client, headers, path, body, **kw):
    return client.post(path, json=body, headers={**headers, **kw.get("extra", {})})


# ---------- 1. downloading an existing full render is free ----------
def test_an_export_that_exists_already_is_handed_back_free(client, none_job, transcriber):
    headers, job, clip = none_job
    body = {"job_id": job["job_id"], "clips": [clip["id"]], "options": {"resolution": "480"}}
    r = post(client, headers, "/v1/clips/export", body)
    assert r.status_code == 202 and worker.run_once(transcriber) == "SUCCEEDED"
    assert balance(client, headers) == 28
    jobs = jobs_of(client, headers)
    done = client.get(f"/v1/jobs/{job['job_id']}", headers=headers).json()["clips"][0]

    q = post(client, headers, "/v1/clips/export/quote", body).json()
    assert q["credits_reserved"] == 0 and q["clips"] == [{"clip_id": clip["id"], "seconds": 0.0, "free": True}]
    again = post(client, headers, "/v1/clips/export", body)
    assert again.status_code == 200, again.text
    out = again.json()
    assert out["job_id"] is None and out["credits_reserved"] == 0 and [x["clip_id"] for x in out["existing"]] == [clip["id"]]
    assert client.get(local(out["existing"][0]["video_url"])).content == client.get(local(done["export_url"])).content
    assert balance(client, headers) == 28 and jobs_of(client, headers) == jobs       # no job, no credit

    other = post(client, headers, "/v1/clips/export", {**body, "options": {"resolution": "720"}})   # another size
    assert other.status_code == 202 and other.json()["credits_reserved"] == 1
    cancel(client, headers, other.json()["job_id"])


def test_a_clip_jobs_own_full_render_is_handed_back_free(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10}, transcriber)
    clip = job["clips"][0]
    r = post(client, headers, "/v1/clips/export", {"job_id": job["job_id"]})
    assert r.status_code == 200 and r.json()["job_id"] is None and r.json()["credits_reserved"] == 0
    assert client.get(local(r.json()["existing"][0]["video_url"])).content == client.get(local(clip["video_url"])).content
    edited = post(client, headers, "/v1/clips/export", {"job_id": job["job_id"], "clips": [clip["id"]],
                                                        "edit": {"trim": {"start": clip["start_sec"], "end": clip["end_sec"] - 2}}})
    assert edited.status_code == 202 and edited.json()["credits_reserved"] == 1       # an edit is a new render
    cancel(client, headers, edited.json()["job_id"])


# ---------- 2. a repeated request is not charged twice ----------
def test_a_double_click_starts_one_export_and_reserves_once(client, none_job, transcriber):
    headers, job, clip = none_job
    body = {"job_id": job["job_id"], "clips": [clip["id"]], "options": {"resolution": "480"}}
    first = post(client, headers, "/v1/clips/export", body)
    second = post(client, headers, "/v1/clips/export", body)
    assert first.status_code == 202 and second.status_code == 200
    assert second.json()["job_id"] == first.json()["job_id"] and balance(client, headers) == 28
    assert ledger_rows(first.json()["job_id"]) == [("reserve", -1)]

    keyed = {"Idempotency-Key": "export-retry-1"}
    k1 = post(client, headers, "/v1/clips/export", {**body, "options": {"resolution": "720"}}, extra=keyed)
    k2 = post(client, headers, "/v1/clips/export", {**body, "options": {"resolution": "720"}}, extra=keyed)
    assert k1.status_code == 202 and k2.json()["job_id"] == k1.json()["job_id"] and balance(client, headers) == 27

    assert worker.run_once(transcriber) == "SUCCEEDED" and worker.run_once(transcriber) == "SUCCEEDED"
    assert post(client, headers, "/v1/clips/export", {**body, "options": {"resolution": "720"}},
                extra=keyed).json()["job_id"] == k1.json()["job_id"]                     # a retry after it finished
    assert balance(client, headers) == 27
    assert ledger_rows(first.json()["job_id"]) == [("reserve", -1), ("commit", 0)]
    assert ledger_rows(k1.json()["job_id"]) == [("reserve", -1), ("commit", 0)]


# ---------- 3. reserve, settle and refund are idempotent ----------
def test_an_export_picked_up_twice_settles_once_and_keeps_its_file(client, none_job, transcriber):
    headers, job, clip = none_job
    r = post(client, headers, "/v1/clips/export", {"job_id": job["job_id"]})
    export_job = r.json()["job_id"]
    assert worker.run_once(transcriber) == "SUCCEEDED"
    with new_session() as db:
        key = db.get(Clip, clip["id"]).export_key
    assert worker.process_job(export_job, transcriber) == "SUCCEEDED"     # a second worker runs it again
    with new_session() as db:
        assert db.get(Clip, clip["id"]).export_key == key
        assert len(db.execute(select(Export).where(Export.clip_id == clip["id"])).scalars().all()) == 1
    assert get_storage().exists(key)                                     # the second run did not overwrite it
    assert ledger_rows(export_job) == [("reserve", -1), ("commit", 0)] and balance(client, headers) == 28


def test_a_stale_sweep_racing_the_worker_refunds_once(client, none_job, transcriber, monkeypatch):
    headers, job, clip = none_job
    export_job = post(client, headers, "/v1/clips/export", {"job_id": job["job_id"]}).json()["job_id"]
    real = worker.run_export

    def slow_then_swept(*a, **k):
        out = real(*a, **k)
        with new_session() as db:                    # the worker looked dead: the sweep fails and refunds it
            db.get(Job, export_job).heartbeat_at = utcnow() - timedelta(hours=1)
            db.commit()
        assert worker.sweep_stale_jobs() == 1
        return out
    monkeypatch.setattr(worker, "run_export", slow_then_swept)
    assert worker.run_once(transcriber) == "FAILED"
    assert worker.sweep_stale_jobs() == 0
    assert ledger_rows(export_job) == [("reserve", -1), ("release", 1)] and balance(client, headers) == 29
    with new_session() as db:
        assert db.get(Clip, clip["id"]).export_key is None
        assert not db.execute(select(Export).where(Export.clip_id == clip["id"])).scalars().all()


def test_a_refund_after_a_partial_settle_changes_nothing(client, none_job, transcriber):
    headers, job, _clip = none_job
    a, b = add_clip(job["job_id"], 0.0, 35.0), add_clip(job["job_id"], 5.0, 40.0)
    r = post(client, headers, "/v1/clips/export", {"job_id": job["job_id"], "clips": [a, b], "options": {"resolution": "480"}})
    export_job = r.json()["job_id"]
    assert r.json()["credits_reserved"] == 2 and balance(client, headers) == 27
    with new_session() as db:                                     # deleted before its turn: not rendered
        db.get(Clip, b).deleted_at = utcnow()
        db.commit()
    assert worker.run_once(transcriber) == "SUCCEEDED"
    assert ledger_rows(export_job) == [("reserve", -2), ("commit", 1)] and balance(client, headers) == 28
    with new_session() as db:                                     # every later refund attempt is a no-op
        assert ledger.settle(db, db.get(Job, export_job), success=False) is False
        db.commit()
    assert client.post(f"/v1/jobs/{export_job}/cancel", headers=headers).json()["status"] == "SUCCEEDED"
    assert worker.sweep_stale_jobs() == 0
    assert ledger_rows(export_job) == [("reserve", -2), ("commit", 1)] and balance(client, headers) == 28
    assert client.get(f"/v1/jobs/{export_job}", headers=headers).json()["credits_charged"] == 1


def test_a_cancel_racing_the_finish_refunds_and_changes_no_clip(client, none_job, transcriber, monkeypatch):
    headers, job, clip = none_job
    export_job = post(client, headers, "/v1/clips/export", {"job_id": job["job_id"]}).json()["job_id"]
    real, rendered = worker.run_export, []

    def cancelled_at_the_end(*a, **k):
        out = real(*a, **k)
        rendered.extend(out)
        assert client.post(f"/v1/jobs/{export_job}/cancel", headers=headers).status_code == 200   # still RUNNING
        return out
    monkeypatch.setattr(worker, "run_export", cancelled_at_the_end)
    assert worker.run_once(transcriber) == "CANCELED"
    assert client.post(f"/v1/jobs/{export_job}/cancel", headers=headers).json()["status"] == "CANCELED"
    assert ledger_rows(export_job) == [("reserve", -1), ("release", 1)] and balance(client, headers) == 29
    with new_session() as db:
        assert db.get(Clip, clip["id"]).export_key is None
    folder = get_storage().path(f"exports/{export_job}")              # the render it made is removed again
    assert rendered and (not folder.exists() or not any(folder.iterdir()))


# ---------- 4. the quote is the price ----------
def test_the_quote_is_what_the_export_reserves(client, user, video, transcriber, monkeypatch):
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "none"}, transcriber)
    preview = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "preview"},
                        transcriber)
    one = job["clips"][0]["id"]
    long_a, long_b = add_clip(job["job_id"], 0.0, 35.0), add_clip(job["job_id"], 5.0, 40.0)
    cases = {
        "single": {"job_id": job["job_id"], "clips": [one]},
        "multi": {"job_id": job["job_id"], "clips": [one, long_a, long_b]},
        "edited": {"job_id": job["job_id"], "clips": [long_a], "edit": {"trim": {"start": 0.0, "end": 30.0},
                                                                       "cuts": [[10.0, 12.0]]}},
        "preview": {"job_id": preview["job_id"], "options": {"caption_style": "karaoke"}},
    }
    for name, body in cases.items():
        q = post(client, headers, "/v1/clips/export/quote", body).json()
        r = post(client, headers, "/v1/clips/export", body)
        assert r.status_code == 202, (name, r.text)
        assert r.json()["credits_reserved"] == q["credits_reserved"] > 0, name
        cancel(client, headers, r.json()["job_id"])
    assert post(client, headers, "/v1/clips/export/quote", cases["multi"]).json()["credits_reserved"] == 2   # 80 s

    monkeypatch.setattr(get_settings(), "max_render_sec", 60)            # capped: both refuse alike
    q = post(client, headers, "/v1/clips/export/quote", cases["multi"])
    r = post(client, headers, "/v1/clips/export", cases["multi"])
    assert q.status_code == r.status_code == 413 and q.json() == r.json()


def test_a_full_export_is_charged_exactly_the_quote(client, none_job, transcriber):
    """Three clips of 20.04 s: 60.12 s quoted, 2 credits. Counting each clip's length rounded to 0.1 s (60.0 s)
    would have charged 1."""
    headers, job, _clip = none_job
    ids = [add_clip(job["job_id"], s, s + 20.04) for s in (0.0, 10.0, 19.9)]
    body = {"job_id": job["job_id"], "clips": ids, "options": {"resolution": "480"}}
    q = post(client, headers, "/v1/clips/export/quote", body).json()
    assert q["credits_reserved"] == 2 and q["seconds"] == 60.12
    r = post(client, headers, "/v1/clips/export", body).json()
    assert worker.run_once(transcriber) == "SUCCEEDED"
    done = client.get(f"/v1/jobs/{r['job_id']}", headers=headers).json()
    assert done["credits_charged"] == q["credits_reserved"] == 2 and balance(client, headers) == 27


# ---------- 5. the API still renders in full by default ----------
def test_a_job_without_render_is_rendered_in_full(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10}, transcriber)
    assert "render" not in job["options"]
    clip = job["clips"][0]
    assert clip["rendered"] == "full" and clip["preview_url"] is None and clip["video_url"]
    with new_session() as db:
        assert db.get(Clip, clip["id"]).video_key.endswith(f"{clip['id']}.mp4")
    assert client.get("/v1/options").json()["clips"]["render"]["default"] == "full"


# ---------- 6. an edit keeps the job's dead-air cuts ----------
def test_an_edit_without_cuts_keeps_the_dead_air_the_job_cut(client, none_job, tmp_path):
    headers, job, _clip = none_job
    plain = add_clip(job["job_id"], 10.0, 20.0, {"edit": {"segments": [[10.0, 14.0], [15.5, 20.0]], "flash_forward": False}})
    flash = add_clip(job["job_id"], 10.0, 20.0, {"edit": {"segments": [[18.0, 19.0], [10.0, 14.0], [15.5, 20.0]],
                                                          "flash_forward": True}})
    quote = lambda clip, **body: post(client, headers, "/v1/clips/export/quote",            # noqa: E731
                                      {"job_id": job["job_id"], "clips": [clip], **body}).json()
    assert quote(plain)["seconds"] == 8.5                                    # no edit: the job's cut
    assert quote(plain, edit={"trim": {"start": 10.0, "end": 20.0}})["seconds"] == 8.5
    assert quote(plain, edit={"trim": {"start": 10.0, "end": 20.0}, "cuts": []})["seconds"] == 10.0   # restored
    assert quote(flash, edit={"trim": {"start": 12.0, "end": 20.0}})["seconds"] == 6.5   # the tease left aside

    r = client.patch(f"/v1/clips/{plain}", json={"edit": {"trim": {"start": 10.0, "end": 20.0}}}, headers=headers)
    assert r.status_code == 200 and r.json()["edit"]["cuts"] == [[14.0, 15.5]]           # shown as a cut
    with new_session() as db:
        (item,) = export_items(db, [plain], get_storage(), tmp_path)
    assert item.segments == [[10.0, 14.0], [15.5, 20.0]]


# ---------- 7. provisional layouts stay off until turned on ----------
PROVISIONAL = {"trio", "grid4", "ots"}


def test_provisional_layouts_are_off_by_default(client, none_job):
    headers, job, _clip = none_job
    assert get_settings().provisional_layouts is False
    layout = client.get("/v1/options").json()["clips"]["layout"]
    assert not PROVISIONAL & set(layout["values"]) and not any(PROVISIONAL & set(v) for v in layout["by_aspect"].values())
    asks = [("/v1/clips/quote", {"upload_id": job["upload_id"], "options": {"layout": "trio"}}),
            ("/v1/clips", {"upload_id": job["upload_id"], "options": {"layout": "grid4", "aspect": "1:1"}}),
            ("/v1/reframe", {"upload_id": job["upload_id"], "segments": [{"start": 5, "end": 9}],
                             "options": {"layout": "ots", "aspect": "16:9"}}),
            ("/v1/templates/custom", {"name": "x", "options": {"layout": "trio"}}),
            ("/v1/clips/export/quote", {"job_id": job["job_id"], "options": {"layout": "grid4"}}),
            ("/v1/clips/export", {"job_id": job["job_id"], "options": {"layout": "trio"}})]
    before = balance(client, headers)
    for path, body in asks:
        r = post(client, headers, path, body)
        assert r.status_code == 400 and r.json()["error"]["code"] == "layout_not_available", (path, r.text)
        assert "not available yet" in r.json()["error"]["message"]
    assert balance(client, headers) == before


def test_provisional_layouts_are_offered_with_the_setting_on(client, none_job, monkeypatch):
    headers, job, _clip = none_job
    monkeypatch.setattr(get_settings(), "provisional_layouts", True)
    layout = client.get("/v1/options").json()["clips"]["layout"]
    assert PROVISIONAL <= set(layout["values"]) and {"trio", "grid4"} <= set(layout["by_aspect"]["1:1"])
    assert post(client, headers, "/v1/clips/quote", {"upload_id": job["upload_id"], "options": {"layout": "trio"}}).status_code == 200
    assert post(client, headers, "/v1/clips/export/quote", {"job_id": job["job_id"], "options": {"layout": "grid4"}}).status_code == 200
