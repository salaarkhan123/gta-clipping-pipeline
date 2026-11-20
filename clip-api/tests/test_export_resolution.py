"""The resolution an export reports is the one it renders: the quote, the export job, the clip's `export_res` and
the Export row all say the size of the file, after the plan's cap and the source's own size. Before, a Free-plan
export asked for 1080 rendered 720 while every one of them said "1080"."""
from sqlalchemy import select

from app import worker
from app.db import new_session
from app.models import Account, Export
from app.pipeline import probe
from tests.test_api import balance
from tests.test_export import local
from tests.test_export_money import none_job, post  # noqa: F401  (fixture)


def export(client, headers, body, tmp_path):
    """(quote, the clip after the export, the Export row's resolution, the file's (width, height))."""
    q = post(client, headers, "/v1/clips/export/quote", body)
    assert q.status_code == 200, q.text
    r = post(client, headers, "/v1/clips/export", body)
    assert r.status_code == 202, r.text
    assert worker.run_once() == "SUCCEEDED"
    done = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["result"]["exports"]
    clip = next(c for c in client.get(f"/v1/jobs/{body['job_id']}", headers=headers).json()["clips"]
                if c["id"] == body["clips"][0])
    path = tmp_path / "x.mp4"
    path.write_bytes(client.get(local(clip["export_url"])).content)
    info = probe(path)
    with new_session() as db:
        row = db.execute(select(Export).where(Export.clip_id == clip["id"], Export.storage_key.is_not(None))).scalar_one()
    assert [x["resolution"] for x in done] == [row.resolution]          # the export job says it too
    return q.json(), clip, row.resolution, (info.width, info.height)


def test_a_free_plan_export_says_the_720_it_renders(client, none_job, tmp_path):
    headers, job, clip = none_job                      # a new account is on the Free plan: 720 at most
    body = {"job_id": job["job_id"], "clips": [clip["id"]], "options": {"layout": "fill"}}   # the 1080 canvas
    quote, after, row, size = export(client, headers, body, tmp_path)
    assert size == (720, 1280)
    assert quote["resolution"] == after["export_res"] == row == "720"
    assert balance(client, headers) == 29 - quote["credits_reserved"]      # the price is unchanged


def test_a_paid_plan_export_says_1080(client, user, none_job, tmp_path):
    headers, job, clip = none_job
    with new_session() as db:
        db.get(Account, user[1]["id"]).plan = "starter_v2"
        db.commit()
    body = {"job_id": job["job_id"], "clips": [clip["id"]], "options": {"layout": "fill"}}
    quote, after, row, size = export(client, headers, body, tmp_path)
    assert size == (1080, 1920)
    assert quote["resolution"] == after["export_res"] == row == "1080"


def test_an_export_never_says_more_than_its_source(client, none_job, tmp_path):
    headers, job, clip = none_job                      # the test video is 640x360
    body = {"job_id": job["job_id"], "clips": [clip["id"]], "options": {"resolution": "1080", "layout": "fill"}}
    quote, after, row, size = export(client, headers, body, tmp_path)
    assert size == (360, 640)
    assert quote["resolution"] == after["export_res"] == row == "360"

