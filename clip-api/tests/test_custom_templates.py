"""Custom templates: an account's saved looks (docs/CONTRACTS.md). Scoped to the account, validated as clip
options, capped at 20, and never part of what a job costs."""
import uuid
from typing import Literal

import pytest
from pydantic import Field
from sqlalchemy import func, select

from app import routes_templates
from app.db import new_session
from app.models import Account, CreditLedger, CustomTemplate
from app.render_options import LayoutOptions
from app.routes_media import ClipOptions
from app.routes_templates import EDIT_FIELDS, MAX_CUSTOM_TEMPLATES, PRICED_FIELDS, look_fields
from tests.test_api import balance, upload

URL = "/v1/templates/custom"
LOOK = {"layout": "split2", "aspect": "9:16", "captions": True, "caption_style": "bold", "punch_zoom": False}


def save(client, headers, name="My look", options=None):
    r = client.post(URL, json={"name": name, "options": LOOK if options is None else options}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def other_user(client):
    r = client.post("/v1/auth/signup", json={"email": f"o{uuid.uuid4().hex[:10]}@example.org", "password": "correct-horse-9"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def ledger_rows(account_id=None) -> int:
    with new_session() as db:
        q = select(func.count()).select_from(CreditLedger)
        return db.execute(q.where(CreditLedger.account_id == account_id) if account_id else q).scalar_one()


# --- create, list, edit, delete ---------------------------------------------------------------------------------

def test_save_list_rename_edit_and_delete(client, user):
    headers, _ = user
    assert client.get(URL, headers=headers).json() == {"templates": [], "limit": 20}
    first = save(client, headers, "  Split with captions  ")
    assert first["name"] == "Split with captions" and first["options"] == LOOK      # trimmed; options as sent
    assert first["id"].startswith("ctpl_") and first["created_at"].endswith("Z") and set(first) == {
        "id", "name", "options", "created_at", "updated_at"}
    assert first["updated_at"] == first["created_at"]
    second = save(client, headers, "Full screen", {"layout": "full", "captions": False})
    assert [t["id"] for t in client.get(URL, headers=headers).json()["templates"]] == [second["id"], first["id"]]   # newest first

    renamed = client.patch(f"{URL}/{first['id']}", json={"name": "Camera on top"}, headers=headers)
    assert renamed.status_code == 200 and renamed.json()["name"] == "Camera on top" and renamed.json()["options"] == LOOK
    edited = client.patch(f"{URL}/{first['id']}", json={"options": {"layout": "pip", "zoom": 1.2}}, headers=headers).json()
    assert edited["options"] == {"layout": "pip", "zoom": 1.2} and edited["name"] == "Camera on top"   # options replace the set
    assert edited["updated_at"] >= edited["created_at"] == first["created_at"]
    both = client.patch(f"{URL}/{second['id']}", json={"name": "Full", "options": {"layout": "full"}}, headers=headers).json()
    assert (both["name"], both["options"]) == ("Full", {"layout": "full"})

    gone = client.delete(f"{URL}/{first['id']}", headers=headers)
    assert gone.status_code == 200 and gone.json() == {"deleted": True}
    assert [t["id"] for t in client.get(URL, headers=headers).json()["templates"]] == [second["id"]]
    for again in (client.delete(f"{URL}/{first['id']}", headers=headers),
                  client.patch(f"{URL}/{first['id']}", json={"name": "x"}, headers=headers)):
        assert again.status_code == 404 and again.json()["error"]["code"] == "not_found"
    with new_session() as db:                                                  # a soft delete: the row stays, marked
        row = db.get(CustomTemplate, first["id"])
        assert row.deleted_at is not None and row.options == {"layout": "pip", "zoom": 1.2}


def test_every_route_needs_a_key_and_an_api_key_works(client, user):
    headers, _ = user
    for call in (lambda: client.get(URL), lambda: client.post(URL, json={"name": "x", "options": LOOK}),
                 lambda: client.patch(f"{URL}/ctpl_x", json={"name": "x"}), lambda: client.delete(f"{URL}/ctpl_x")):
        r = call()
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    key = client.post("/v1/keys", json={"name": "ci"}, headers=headers).json()["key"]
    by_key = {"Authorization": f"Bearer {key}"}
    made = save(client, by_key, "From a key")                                  # the same routes customers' code calls
    assert [t["id"] for t in client.get(URL, headers=headers).json()["templates"]] == [made["id"]]


def test_another_accounts_templates_are_invisible_and_untouchable(client, user):
    headers, _ = user
    mine = save(client, headers, "Mine")
    stranger = other_user(client)
    assert client.get(URL, headers=stranger).json()["templates"] == []
    for r in (client.patch(f"{URL}/{mine['id']}", json={"name": "Stolen", "options": {"layout": "full"}}, headers=stranger),
              client.delete(f"{URL}/{mine['id']}", headers=stranger)):
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.patch(f"{URL}/ctpl_nope", json={"name": "x"}, headers=headers).status_code == 404   # the same answer as a missing id
    assert client.get(URL, headers=headers).json()["templates"] == [mine]      # unchanged, not deleted


# --- what a look may hold ---------------------------------------------------------------------------------------

def test_the_allowed_options_are_read_from_the_models():
    allowed = look_fields()
    assert allowed == (set(LayoutOptions.model_fields) | {"tighten", "punch_zoom", "flash_forward", "hook_overlay"}) - PRICED_FIELDS
    assert set(EDIT_FIELDS) <= set(ClipOptions.model_fields) and allowed <= set(ClipOptions.model_fields)
    assert PRICED_FIELDS == {"max_clips", "clip_length", "duration", "limit", "range", "resolution", "render", "template"}
    assert not allowed & PRICED_FIELDS and {"layout", "aspect", "captions", "caption_style", "censor", "zoom"} <= allowed
    for name in allowed:                                                       # each one alone, at its default, is a valid look
        assert routes_templates.check_look({name: ClipOptions.model_fields[name].default}) == {name: ClipOptions.model_fields[name].default}


def test_the_split_options_can_be_saved_in_a_look(client, user):
    headers, _ = user
    assert {"camera", "split_ratio", "caption_position", "caption_accent"} <= look_fields()      # the renderer has them now
    assert save(client, headers, "Sized", {"camera": "top", "split_ratio": 0.4})["options"] == {"camera": "top", "split_ratio": 0.4}
    wide = client.post(URL, json={"name": "Too big", "options": {"split_ratio": 0.9}}, headers=headers)
    assert wide.status_code == 422 and "split_ratio" in wide.json()["error"]["message"]


def test_an_option_the_renderer_adds_later_is_accepted_without_a_change_here(client, user, monkeypatch):
    headers, _ = user
    refused = client.post(URL, json={"name": "Glowing", "options": {"glow": 0.4}}, headers=headers)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "unknown_option"    # not a clip option today

    class FutureLayout(LayoutOptions):                                         # what a render agent might add next
        glow: float | None = Field(default=None, ge=0.0, le=1.0)

    class FutureClip(ClipOptions, FutureLayout):
        pass
    monkeypatch.setattr(routes_templates, "LayoutOptions", FutureLayout)
    monkeypatch.setattr(routes_templates, "ClipOptions", FutureClip)
    assert "glow" in look_fields()
    assert save(client, headers, "Glowing", {"glow": 0.4})["options"] == {"glow": 0.4}
    bright = client.post(URL, json={"name": "Too bright", "options": {"glow": 9}}, headers=headers)
    assert bright.status_code == 422 and "glow" in bright.json()["error"]["message"]


@pytest.mark.parametrize("key, value", [("max_clips", 3), ("clip_length", 30), ("duration", "0-30"), ("limit", 5),
                                        ("range", {"start": 0, "end": 60}), ("resolution", "4k"), ("render", "full"),
                                        ("template", "car-chase")])
def test_an_option_that_sets_a_price_or_a_quality_is_refused_by_name(client, user, key, value):
    headers, _ = user
    r = client.post(URL, json={"name": "Priced", "options": {"layout": "full", key: value}}, headers=headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "forbidden_option", r.text
    assert f"'{key}'" in r.json()["error"]["message"]
    made = save(client, headers)
    patched = client.patch(f"{URL}/{made['id']}", json={"options": {key: value}}, headers=headers)
    assert patched.status_code == 422 and f"'{key}'" in patched.json()["error"]["message"]
    assert client.get(URL, headers=headers).json()["templates"] == [made]      # nothing saved, nothing changed


def test_unknown_options_and_bad_values_are_refused_by_name(client, user):
    headers, _ = user
    for key in ("weights", "judge_focus", "transcript_bonus", "upload_id", "webhook_url", "brightness", "Layout"):
        r = client.post(URL, json={"name": "x", "options": {key: 1}}, headers=headers)
        assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_option", key
        assert f"'{key}'" in r.json()["error"]["message"] and "caption_style" in r.json()["error"]["message"]
    for options, word in [({"caption_style": "comic"}, "caption_style"), ({"zoom": 9}, "zoom"), ({"aspect": "3:2"}, "aspect"),
                          ({"layout": "trio"}, "trio"), ({"layout": "split2", "aspect": "1:1"}, "split2"),
                          ({"facecam_box": [0.5, 0.5, 0.9, 0.9]}, "facecam_box"), ({"captions": "sometimes"}, "captions")]:
        r = client.post(URL, json={"name": "x", "options": options}, headers=headers)
        assert r.status_code == 422 and r.json()["error"]["code"] == "bad_options", options
        assert word in r.json()["error"]["message"], (options, r.json())
    empty = client.post(URL, json={"name": "x", "options": {}}, headers=headers)
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "bad_options"
    assert client.get(URL, headers=headers).json()["templates"] == []


def test_the_name_and_the_body_are_checked(client, user):
    headers, _ = user
    for body in ({"options": LOOK}, {"name": "", "options": LOOK}, {"name": "   ", "options": LOOK}, {"name": "x" * 81, "options": LOOK},
                 {"name": "x"}, {"name": "x", "options": "full"}, {"name": "x", "options": LOOK, "account_id": "acc_1"},
                 {"name": "x", "options": LOOK, "price": 0}):
        r = client.post(URL, json=body, headers=headers)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error", body
    assert save(client, headers, "x" * 80)["name"] == "x" * 80                 # 80 is the longest
    made = client.get(URL, headers=headers).json()["templates"][0]
    for body in ({}, {"name": None}, {"name": None, "options": None}, {"name": " "}, {"id": "ctpl_other"}, {"deleted_at": None, "name": "x"}):
        r = client.patch(f"{URL}/{made['id']}", json=body, headers=headers)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error", body
    assert client.get(URL, headers=headers).json()["templates"] == [made]


def test_values_are_stored_the_way_the_clip_options_read_them(client, user):
    headers, _ = user
    made = save(client, headers, "Loose", {"captions": "true", "zoom": "1.25", "facecam_region": None})
    assert made["options"] == {"captions": True, "zoom": 1.25, "facecam_region": None}
    ClipOptions(**made["options"])


# --- limits and money -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("plan", ["free", "scale"])                           # one technical cap: no plan changes it
def test_at_most_twenty_per_account_and_a_deleted_one_frees_a_place(client, user, plan):
    headers, account = user
    with new_session() as db:
        db.get(Account, account["id"]).plan = plan
        db.commit()
    assert MAX_CUSTOM_TEMPLATES == 20 and client.get(URL, headers=headers).json()["limit"] == 20
    ids = [save(client, headers, f"Look {i}")["id"] for i in range(20)]
    full = client.post(URL, json={"name": "One too many", "options": LOOK}, headers=headers)
    assert full.status_code == 409 and full.json()["error"]["code"] == "too_many_templates" and "20" in full.json()["error"]["message"]
    assert len(client.get(URL, headers=headers).json()["templates"]) == 20
    assert client.patch(f"{URL}/{ids[0]}", json={"name": "Still editable"}, headers=headers).status_code == 200
    assert save(client, other_user(client))["name"] == "My look"               # the cap is per account
    assert client.delete(f"{URL}/{ids[0]}", headers=headers).status_code == 200
    assert save(client, headers, "Fits again")["name"] == "Fits again"


def test_saving_editing_and_deleting_never_touch_the_ledger(client, user):
    headers, account = user
    start, rows, mine = balance(client, headers), ledger_rows(), ledger_rows(account["id"])
    made = save(client, headers)
    client.patch(f"{URL}/{made['id']}", json={"name": "Renamed", "options": {"layout": "full"}}, headers=headers)
    client.get(URL, headers=headers)
    client.post(URL, json={"name": "Refused", "options": {"max_clips": 9}}, headers=headers)
    assert client.delete(f"{URL}/{made['id']}", headers=headers).status_code == 200
    assert (balance(client, headers), ledger_rows(), ledger_rows(account["id"])) == (start, rows, mine)


def test_a_saved_look_is_used_by_sending_its_options_and_costs_what_the_job_costs(client, user, video):
    headers, account = user
    up = upload(client, headers, video)
    made = save(client, headers, "Camera on top", {"layout": "split2", "caption_style": "neon", "tighten": False})

    def reserve(options):
        r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": options}, headers=headers)
        assert r.status_code == 202, r.text
        client.post(f"/v1/jobs/{r.json()['job_id']}/cancel", headers=headers)
        return r.json()
    start, rows = balance(client, headers), ledger_rows(account["id"])
    plain = reserve({"max_clips": 2})
    looked = reserve({"max_clips": 2, **made["options"]})                      # the client applies the look itself
    assert looked["credits_reserved"] == plain["credits_reserved"]
    assert (looked["options"]["layout"], looked["options"]["caption_style"], looked["options"]["tighten"]) == ("split2", "neon", False)
    by_id = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"template": made["id"]}}, headers=headers)
    assert by_id.status_code == 422                                            # the server never applies a saved look by id
    assert balance(client, headers) == start
    assert ledger_rows(account["id"]) == rows + 4                              # two reserves and two refunds, from the jobs alone
