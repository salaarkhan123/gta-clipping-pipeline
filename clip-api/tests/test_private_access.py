"""Private media stays private (ticket #144).

User A makes an upload, clip jobs (clips, thumbnails, captions), a transcript, an import and a saved template.
Every route that takes an id, read from the OpenAPI document, is then called with A's ids as nobody, as user B
(website login and API key) and with a guessed id. None of them may answer with A's content or a file link.
Signed file links are checked for expiry and tampering, and links stop for uploads that expired or were taken
down. A route added later with an id in it fails `test_every_id_route_has_an_access_case` until it gets a case
in ROUTES (or BODY_ROUTES) below.
"""
import base64
import json
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import jwt
import pytest
from sqlalchemy import select, update

from app import worker
from app.config import get_settings
from app.db import new_session
from app.ingest import platforms
from app.ingest.takedown import takedown
from app.main import app
from app.models import ClipThumbnail, Job, Upload, new_id, utcnow
from app.security import make_token
from tests.conftest import FakeTranscriber
from tests.ingest_support import FakeYDL
from tests.test_api import balance, upload

FILE_LINK = "/v1/files/"
DONE = ("SUCCEEDED", "FAILED", "CANCELED")


@dataclass
class Case:
    """How to call one id route. `owner` is what A gets back on a read, or None for a route that changes
    something (B's attempts are checked, A's own call is not made)."""
    body: dict | None = None
    query: str = ""
    owner: tuple[int, str | None] | None = None


# Every route with an id in its path. Denial for all of them: nobody 401, B 404 (B's API key may get 403
# session_required on login-only routes), a guessed id 404.
ROUTES: dict[tuple[str, str], Case] = {
    ("DELETE", "/v1/keys/{key_id}"): Case(),
    ("GET", "/v1/jobs/{job_id}"): Case(owner=(200, None)),
    ("POST", "/v1/jobs/{job_id}/cancel"): Case(),
    ("POST", "/v1/clips/{clip_id}/feedback"): Case(body={"kept": False, "reaction": "dislike"}),
    ("PATCH", "/v1/clips/{clip_id}"): Case(body={"title": "taken over"}),
    ("GET", "/v1/clips/{clip_id}/subtitles"): Case(owner=(200, None)),
    ("GET", "/v1/uploads/{upload_id}/search"): Case(query="?q=god", owner=(200, None)),
    ("GET", "/v1/transcripts/{upload_id}"): Case(owner=(200, None)),
    ("GET", "/v1/transcripts/{upload_id}/download"): Case(owner=(200, None)),
    ("GET", "/v1/summaries/{upload_id}"): Case(owner=(404, "no_summary")),   # summaries are off in tests
    ("GET", "/v1/projects/{upload_id}"): Case(owner=(200, None)),
    ("PATCH", "/v1/templates/custom/{template_id}"): Case(body={"name": "taken over"}),
    ("DELETE", "/v1/templates/custom/{template_id}"): Case(),
    ("GET", "/v1/imports/{import_id}"): Case(owner=(200, None)),
    ("POST", "/v1/imports/{import_id}/cancel"): Case(),
    # (#140) a clip's thumbnails. The premium routes answer 404 premium_thumbnails_off while the flag is off, the
    # same for a real and a guessed id.
    ("GET", "/v1/clips/{clip_id}/thumbnails"): Case(owner=(200, None)),
    ("POST", "/v1/clips/{clip_id}/thumbnails/{thumb_id}/select"): Case(),
    ("PATCH", "/v1/clips/{clip_id}/thumbnails/{thumb_id}"): Case(body={"show_text": False}),
    ("POST", "/v1/clips/{clip_id}/thumbnails/premium/quote"): Case(body={"style": "cinematic"}),
    ("POST", "/v1/clips/{clip_id}/thumbnails/premium"): Case(body={"style": "cinematic", "confirm": True,
                                                                  "likeness_consent": True}),
}

# Routes with an id in the path that are public on purpose.
PUBLIC_ID_ROUTES = {
    ("GET", "/v1/files/{token}"): "the signed token is the credential; expiry and tampering are tested below",
    ("GET", "/v1/templates/{template_id}/poster"): "catalogue posters are public images, not anyone's content",
}

# Routes that take an id in the JSON body. B sending A's upload id must get 404 and start nothing.
BODY_ROUTES: dict[tuple[str, str], dict] = {
    ("POST", "/v1/clips"): {"options": {"max_clips": 1, "clip_length": 10}},
    ("POST", "/v1/reframe"): {},
    ("POST", "/v1/captions"): {},
    ("POST", "/v1/find"): {"query": "god"},
    ("POST", "/v1/transcripts"): {},
    ("POST", "/v1/summaries"): {},
    ("POST", "/v1/clips/quote"): {"options": {"max_clips": 1, "clip_length": 10}},     # (#136) reserves nothing
}
# Routes that take a job id in the JSON body (#136 exports): B sending A's job id gets 404 and starts nothing.
JOB_BODY_ROUTES: dict[tuple[str, str], dict] = {
    ("POST", "/v1/clips/export"): {},
    ("POST", "/v1/clips/export/quote"): {},
}
PUBLIC_BODY_IDS = {
    ("POST", "/v1/billing/checkout", "pack_id"): "a server-side pack id, the same for every account",
    ("POST", "/v1/billing/subscribe", "plan_id"): "a server-side plan id, the same for every account",
}

# Account routes that list things: as B they must hold none of A's ids.
LISTINGS = ("/v1/me", "/v1/keys", "/v1/uploads", "/v1/jobs", "/v1/clips", "/v1/projects", "/v1/imports",
            "/v1/credits", "/v1/templates/custom", "/v1/me/consents")        # consents: #158
PUBLIC_GETS = {
    "/health": "status only", "/v1/auth/verify": "takes an emailed token", "/v1/languages": "fixed list",
    "/v1/options": "fixed list", "/v1/templates": "catalogue", "/v1/templates/games": "catalogue",
    "/v1/billing/packs": "price list", "/v1/billing/plans": "price list", "/v1/imports/sources": "fixed list",
    "/v1/legal/policies": "the published policy texts (#158)",
}


# ---- helpers ----

def signup(client) -> tuple[dict, dict]:
    r = client.post("/v1/auth/signup", json={"email": f"pa{uuid.uuid4().hex[:10]}@example.org",
                                             "password": "correct-horse-9"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["account"]


def api_key(client, headers) -> tuple[dict, str]:
    r = client.post("/v1/keys", json={"name": "access-test"}, headers=headers)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['key']}"}, r.json()["id"]


def finish(job_id: str) -> str:
    """Run the worker until this job is done; jobs other tests left queued run first."""
    for _ in range(10):
        with new_session() as db:
            status = db.get(Job, job_id).status
        if status in DONE:
            return status
        worker.run_once(FakeTranscriber())
    raise AssertionError(f"{job_id} never finished")


def started(r) -> str:
    assert r.status_code == 202, r.text
    return r.json().get("job_id") or r.json()["import_id"]


def local(url: str) -> str:
    return url.replace(get_settings().public_api_url, "")


def links(text: str) -> list[str]:
    return re.findall(r"/v1/files/[A-Za-z0-9._-]+", text)


def import_link(client, headers, video, url: str) -> dict:
    with pytest.MonkeyPatch.context() as mp:
        FakeYDL.instances, FakeYDL.video, FakeYDL.info = [], video, {}
        FakeYDL.refuse_extract = FakeYDL.refuse_download = FakeYDL.report_bytes = None
        mp.setattr(platforms, "YoutubeDL", FakeYDL)
        imp = started(client.post("/v1/imports", json={"url": url, "consent": True}, headers=headers))
        assert finish(imp) == "SUCCEEDED"
    out = client.get(f"/v1/imports/{imp}", headers=headers).json()
    assert out["upload_id"], out
    return out


def twitch_url() -> str:
    return f"https://www.twitch.tv/videos/{secrets.randbelow(10**9) + 10**9}"


def guess(real_id: str) -> str:
    return f"{real_id.split('_', 1)[0]}_{secrets.token_hex(12)}"


def path_params(path: str) -> list[str]:
    return re.findall(r"{(\w+)}", path)


def operations():
    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            yield method.upper(), path, op


def body_id_fields(op: dict) -> list[str]:
    schemas = app.openapi()["components"]["schemas"]
    ref = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema", {})
    schema = schemas.get(ref.get("$ref", "").rsplit("/", 1)[-1], ref)
    return sorted(name for name in schema.get("properties", {}) if name.endswith("_id"))


# ---- A's account, made once ----

@dataclass
class World:
    a: dict
    a_key: dict
    b: dict
    b_key: dict
    b_account: dict
    ids: dict[str, str]                       # path parameter name -> A's id
    secrets_of_a: set[str] = field(default_factory=set)   # every id of A's that must never reach B

    def call(self, client, method: str, path: str, case: Case, headers: dict | None, ids: dict | None = None):
        url = path.format(**(ids or self.ids)) + case.query
        return client.request(method, url, json=case.body, headers=headers or {})


@pytest.fixture(scope="module")
def world(client, video) -> World:
    a, a_account = signup(client)
    a_key, a_key_id = api_key(client, a)
    up = upload(client, a, video)
    clip_job = started(client.post("/v1/clips", json={"upload_id": up["upload_id"],
                                                      "options": {"max_clips": 1, "clip_length": 10}}, headers=a))
    assert finish(clip_job) == "SUCCEEDED"
    cap_job = started(client.post("/v1/captions", json={"upload_id": up["upload_id"],
                                                        "segments": [{"start": 0, "end": 10}]}, headers=a))
    assert finish(cap_job) == "SUCCEEDED"
    tr_job = started(client.post("/v1/transcripts", json={"upload_id": up["upload_id"]}, headers=a))
    assert finish(tr_job) == "SUCCEEDED"
    clip = client.get(f"/v1/jobs/{cap_job}", headers=a).json()["clips"][0]
    assert clip["thumb_url"] and clip["captions_url"], clip      # a clip with every kind of file
    template = client.post("/v1/templates/custom", json={"name": "Mine", "options": {"captions": False}}, headers=a)
    assert template.status_code == 201, template.text
    imp = import_link(client, a, video, twitch_url())
    b, b_account = signup(client)
    b_key, _ = api_key(client, b)
    thumb_id = new_id("thb")                  # (#140) a premium thumbnail of A's clip, stored as the job would
    with new_session() as db:
        db.add(ClipThumbnail(id=thumb_id, clip_id=clip["id"], account_id=a_account["id"], kind="premium",
                             style="cinematic", clean_key=f"thumbs/{clip['id']}/{thumb_id}.clean.jpg",
                             image_key=f"thumbs/{clip['id']}/{thumb_id}.jpg", show_text=True))
        db.commit()
    ids = {"key_id": a_key_id, "job_id": clip_job, "clip_id": clip["id"], "upload_id": up["upload_id"],
           "template_id": template.json()["id"], "import_id": imp["import_id"], "thumb_id": thumb_id}
    w = World(a, a_key, b, b_key, b_account, ids)
    w.secrets_of_a = {*ids.values(), a_account["id"], cap_job, tr_job, imp["upload_id"],
                      *(c["id"] for c in client.get(f"/v1/jobs/{clip_job}", headers=a).json()["clips"])}
    return w


def assert_denied_and_silent(r, world: World, allowed: set[int], where: str):
    assert r.status_code in allowed, f"{where}: {r.status_code} {r.text[:300]}"
    assert FILE_LINK not in r.text, f"{where} handed out a file link"
    leaked = [s for s in world.secrets_of_a if s in r.text]
    assert not leaked, f"{where} leaked {leaked}"


# ---- the route list (AC3) ----

def test_every_id_route_has_an_access_case():
    in_path = {(m, p) for m, p, _ in operations() if path_params(p)}
    missing = in_path - set(ROUTES) - set(PUBLIC_ID_ROUTES)
    assert not missing, f"add an access case to ROUTES (or a reason to PUBLIC_ID_ROUTES) for: {sorted(missing)}"
    assert not (set(ROUTES) | set(PUBLIC_ID_ROUTES)) - in_path, "a case names a route that no longer exists"
    in_body = {(m, p, f) for m, p, op in operations() for f in body_id_fields(op)}
    missing = {x for x in in_body if (x[0], x[1]) not in BODY_ROUTES and (x[0], x[1]) not in JOB_BODY_ROUTES
               and x not in PUBLIC_BODY_IDS}
    assert not missing, f"add an access case to BODY_ROUTES (or PUBLIC_BODY_IDS) for: {sorted(missing)}"
    assert {(m, p) for m, p, f in in_body if f == "upload_id"} == set(BODY_ROUTES)
    gets = {p for m, p, _ in operations() if m == "GET" and not path_params(p)}
    assert gets == set(LISTINGS) | set(PUBLIC_GETS), "a GET route needs a place in LISTINGS or PUBLIC_GETS"


def test_route_cases_name_only_ids_the_world_has(world):
    for _, path in ROUTES:
        assert set(path_params(path)) <= set(world.ids), path


# ---- AC1: id routes ----

@pytest.mark.parametrize("route", sorted(ROUTES), ids=lambda r: f"{r[0]} {r[1]}")
def test_others_cannot_reach_a_s_ids(client, world, route):
    method, path = route
    case = ROUTES[route]
    nobody = world.call(client, method, path, case, None)
    assert_denied_and_silent(nobody, world, {401}, f"anonymous {method} {path}")
    with_b = world.call(client, method, path, case, world.b)
    assert_denied_and_silent(with_b, world, {404}, f"B {method} {path}")
    with_key = world.call(client, method, path, case, world.b_key)
    assert_denied_and_silent(with_key, world, {403, 404}, f"B's key {method} {path}")
    if with_key.status_code == 403:
        assert with_key.json()["error"]["code"] == "session_required"
    # A guessed id gets exactly what B got for A's real one: no way to tell an id exists.
    guessed = {k: guess(v) for k, v in world.ids.items()}
    as_b = world.call(client, method, path, case, world.b, guessed)
    assert (as_b.status_code, as_b.json()) == (with_b.status_code, with_b.json())
    as_a = world.call(client, method, path, case, world.a, guessed)
    assert as_a.status_code == 404, f"A with a guessed id on {method} {path}: {as_a.text[:300]}"


@pytest.mark.parametrize("route", sorted(r for r, c in ROUTES.items() if c.owner), ids=lambda r: f"{r[0]} {r[1]}")
def test_the_owner_still_gets_in(client, world, route):
    method, path = route
    status, code = ROUTES[route].owner
    for headers in (world.a, world.a_key):
        r = world.call(client, method, path, ROUTES[route], headers)
        assert r.status_code == status, f"{method} {path}: {r.text[:300]}"
        if code:
            assert r.json()["error"]["code"] == code


@pytest.mark.parametrize("route", sorted(BODY_ROUTES), ids=lambda r: f"{r[0]} {r[1]}")
def test_others_cannot_start_jobs_on_a_s_upload(client, world, route):
    method, path = route
    before = balance(client, world.b)
    for upload_id, expect in ((world.ids["upload_id"], 404), (guess(world.ids["upload_id"]), 404)):
        body = {"upload_id": upload_id, **BODY_ROUTES[route]}
        assert_denied_and_silent(client.request(method, path, json=body), world, {401}, f"anonymous {path}")
        for who, headers in (("B", world.b), ("B's key", world.b_key)):
            r = client.request(method, path, json=body, headers=headers)
            assert_denied_and_silent(r, world, {expect}, f"{who} {path}")
            assert r.json()["error"]["code"] == "upload_not_found"
    assert balance(client, world.b) == before
    assert client.get("/v1/jobs", headers=world.b).json()["jobs"] == []


@pytest.mark.parametrize("route", sorted(JOB_BODY_ROUTES), ids=lambda r: f"{r[0]} {r[1]}")
def test_others_cannot_export_a_s_jobs(client, world, route):
    method, path = route
    before = balance(client, world.b)
    with_b = None
    for job_id in (world.ids["job_id"], guess(world.ids["job_id"])):
        body = {"job_id": job_id, **JOB_BODY_ROUTES[route]}
        assert_denied_and_silent(client.request(method, path, json=body), world, {401}, f"anonymous {path}")
        for who, headers in (("B", world.b), ("B's key", world.b_key)):
            r = client.request(method, path, json=body, headers=headers)
            assert_denied_and_silent(r, world, {404}, f"{who} {path}")
        with_b = with_b or r.json()
        assert r.json() == with_b                   # a real and a guessed job id look the same
    assert balance(client, world.b) == before
    assert client.get("/v1/jobs", headers=world.b).json()["jobs"] == []


def test_others_changed_nothing(client, world):
    """Runs after the attempts above: every one of A's things is as it was."""
    a, ids = world.a, world.ids
    assert client.get("/v1/credits", headers=world.a_key).status_code == 200            # key not revoked
    saved = client.get("/v1/templates/custom", headers=a).json()["templates"]
    assert [(t["id"], t["name"]) for t in saved] == [(ids["template_id"], "Mine")]
    clip = client.get(f"/v1/projects/{ids['upload_id']}", headers=a).json()["clips"]
    mine = next(c for c in clip if c["id"] == ids["clip_id"])
    assert mine["kept"] is None and mine["reaction"] is None and mine["title"] != "taken over"
    assert client.get(f"/v1/jobs/{ids['job_id']}", headers=a).json()["status"] == "SUCCEEDED"
    assert client.get(f"/v1/imports/{ids['import_id']}", headers=a).json()["status"] == "SUCCEEDED"


# ---- listings ----

@pytest.mark.parametrize("path", LISTINGS)
def test_listings_hold_only_your_own(client, world, path):
    assert client.get(path).status_code == 401
    for who, headers in (("B", world.b), ("B's key", world.b_key)):
        r = client.get(path, headers=headers)
        if r.status_code == 403:                                   # login-only route, B's key
            assert who == "B's key" and r.json()["error"]["code"] == "session_required"
            continue
        assert r.status_code == 200, r.text
        assert_denied_and_silent(r, world, {200}, f"{who} {path}")


def test_listings_show_a_their_own(client, world):
    """The listing checks above mean something: the same lists, as A, do hold A's things."""
    a, ids = world.a, world.ids
    assert ids["upload_id"] in client.get("/v1/uploads", headers=a).text
    assert ids["job_id"] in client.get("/v1/jobs", headers=a).text
    assert ids["clip_id"] in client.get("/v1/clips", headers=a).text
    assert ids["upload_id"] in client.get("/v1/projects", headers=a).text
    assert ids["import_id"] in client.get("/v1/imports", headers=a).text
    assert ids["job_id"] in client.get("/v1/credits", headers=a).text
    assert ids["template_id"] in client.get("/v1/templates/custom", headers=a).text
    assert ids["key_id"] in client.get("/v1/keys", headers=a).text


# ---- AC2: signed file links ----

def a_clip(client, world) -> dict:
    return client.get(f"/v1/jobs/{world.ids['job_id']}", headers=world.a).json()["clips"][0]


def payload_of(token: str) -> dict:
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def test_a_signed_link_works_until_its_ttl(client, world, monkeypatch):
    clip = a_clip(client, world)
    for url in (clip["video_url"], clip["thumb_url"], clip["captions_url"]):
        r = client.get(local(url))
        assert r.status_code == 200 and len(r.content) > 0
    monkeypatch.setattr(get_settings(), "signed_url_ttl_sec", -1)    # every link issued now is past its TTL
    late = a_clip(client, world)
    for url in (late["video_url"], late["thumb_url"], late["captions_url"]):
        r = client.get(local(url))
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_a_link_with_a_changed_key_is_refused(client, world):
    clip = a_clip(client, world)
    token = local(clip["video_url"]).rsplit("/", 1)[1]
    head, body, sig = token.split(".")
    other_key = payload_of(local(clip["thumb_url"]).rsplit("/", 1)[1])["k"]     # a file that exists
    changed = {**payload_of(token), "k": other_key}
    edited = base64.urlsafe_b64encode(json.dumps(changed).encode()).decode().rstrip("=")
    forged = [
        f"{head}.{edited}.{sig}",                                                      # payload edited, old signature
        jwt.encode(changed, "not-the-server-secret-not-the-server-secret", algorithm="HS256"),   # wrong secret
        jwt.encode(changed, None, algorithm="none"),                                   # unsigned
        f"{head}.{body}.{sig[:-2]}{'AA' if not sig.endswith('AA') else 'BB'}",          # signature changed
        "not-a-token",
    ]
    for bad in forged:
        r = client.get(f"/v1/files/{bad}")
        assert r.status_code == 404, f"{bad[:40]}: {r.text}"
        assert r.content != client.get(local(clip["thumb_url"])).content


def test_a_token_made_for_something_else_is_not_a_file_link(client, world):
    key = payload_of(local(a_clip(client, world)["video_url"]).rsplit("/", 1)[1])["k"]
    session = world.a["Authorization"].split(" ", 1)[1]
    others = [session] + [make_token("file", p, timedelta(hours=1), k=key) for p in ("session", "verify", "reset")]
    for token in others:
        r = client.get(f"/v1/files/{token}")
        assert r.status_code == 404, r.text


@pytest.mark.parametrize("key", ["../outside.txt", "clips/../../outside.txt", "/etc/hosts", "", ".", None])
def test_a_signed_key_outside_storage_is_404_not_500(client, key):
    """Only the server can sign, but a key that leaves the storage folder (or is missing) must still be a plain
    404, never a 500 or a file from somewhere else."""
    (get_settings().storage_dir.parent / "outside.txt").write_text("not for download")
    claims = {} if key is None else {"k": key}
    r = client.get(f"/v1/files/{make_token('file', 'file', timedelta(hours=1), **claims)}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", r.text


# ---- links stop for uploads that expired or were taken down ----

def test_an_expired_upload_stops_issuing_links(client, video):
    c, _ = signup(client)
    up = upload(client, c, video)["upload_id"]
    job = started(client.post("/v1/clips", json={"upload_id": up, "options": {"max_clips": 1, "clip_length": 10}},
                              headers=c))
    assert finish(job) == "SUCCEEDED"
    source = local(client.get(f"/v1/projects/{up}", headers=c).json()["source_url"])
    assert client.get(source).status_code == 200
    with new_session() as db:
        db.execute(update(Upload).where(Upload.id == up).values(expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    for path in (f"/v1/projects/{up}", f"/v1/uploads/{up}/search?q=god", f"/v1/transcripts/{up}",
                 f"/v1/transcripts/{up}/download", f"/v1/summaries/{up}"):
        r = client.get(path, headers=c)
        assert r.status_code == 404 and r.json()["error"]["code"] == "upload_not_found", path
        assert FILE_LINK not in r.text
    for path in ("/v1/uploads", "/v1/projects"):
        assert up not in client.get(path, headers=c).text
    assert client.post("/v1/clips", json={"upload_id": up}, headers=c).status_code == 404
    worker.sweep_expired()
    assert client.get(source).status_code == 404                    # the file is gone with the upload


def test_a_taken_down_import_stops_issuing_links(client, video):
    d, account = signup(client)
    imp = import_link(client, d, video, twitch_url())
    up = imp["upload_id"]
    job = started(client.post("/v1/clips", json={"upload_id": up, "options": {"max_clips": 1, "clip_length": 10}},
                              headers=d))
    assert finish(job) == "SUCCEEDED"
    clip = client.get(f"/v1/jobs/{job}", headers=d).json()["clips"][0]
    old = [local(u) for u in (clip["video_url"], clip["thumb_url"],
                              client.get(f"/v1/projects/{up}", headers=d).json()["source_url"]) if u]
    assert all(client.get(u).status_code == 200 for u in old)
    report = takedown(account=account["id"])
    assert any(r.upload_removed and r.upload_id == up for r in report.removed)
    got = client.get(f"/v1/jobs/{job}", headers=d)
    assert got.status_code == 200 and got.json()["clips"] == [] and FILE_LINK not in got.text
    assert client.get(f"/v1/projects/{up}", headers=d).status_code == 404
    for path in ("/v1/clips", "/v1/projects", "/v1/uploads"):
        assert FILE_LINK not in client.get(path, headers=d).text, path
    assert client.get(f"/v1/imports/{imp['import_id']}", headers=d).json()["upload_id"] is None
    assert all(client.get(u).status_code == 404 for u in old)        # files removed, links dead
    with new_session() as db:
        assert db.execute(select(Upload.deleted_at).where(Upload.id == up)).scalar_one() is not None
