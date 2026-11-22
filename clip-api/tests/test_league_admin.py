"""Creators League for admins: only admins reach the admin routes, entries move only by the review rules,
view counts are appended by admins and drive the ranking, ties break by submission time, winners are provisional
until approved in order, prizes are recorded and never paid, a final competition is frozen, a removed clip leaves
the public lists, no admin acts on their own entry, and every move is in the audit log."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import deps, routes_trust, worker
from app.config import get_settings
from app.db import new_session
from app.models import Clip, Job, LeagueEntry, LeagueViewObservation, utcnow
from tests.league_support import (approved_entry, competition, creator, enter, make_admin, make_clip, signup,
                                  unique_slug)

PRIZES = [{"place": 1, "amount_cents": 10000}, {"place": 2, "amount_cents": 5000}, {"place": 3, "amount_cents": 2500}]


@pytest.fixture(autouse=True)
def fresh_limits():
    deps._buckets.clear()
    yield
    deps._buckets.clear()


@pytest.fixture
def admin(client):
    return make_admin(client)[0]


@pytest.fixture
def cup(client, admin):
    return competition(client, admin, prizes=PRIZES)


def code(r):
    return r.status_code, r.json().get("error", {}).get("code")


def review(client, admin, entry_id, action, reason=None):
    return client.post(f"/v1/admin/league/entries/{entry_id}/review", json={"action": action, "reason": reason},
                       headers=admin)


def views(client, admin, entry_id, n, **more):
    return client.post(f"/v1/admin/league/entries/{entry_id}/observations", json={"views": n, **more}, headers=admin)


def board(client, cup):
    return client.get(f"/v1/league/{cup}/leaderboard").json()["entries"]


def move(client, admin, cup, action):
    return client.post(f"/v1/admin/league/competitions/{cup}/status", json={"action": action}, headers=admin)


def winner(client, admin, entry_id, place):
    return client.post(f"/v1/admin/league/entries/{entry_id}/winner", json={"place": place}, headers=admin)


# ---- admin authorisation ----

ADMIN_ROUTES = [
    ("get", "/v1/admin/league/competitions", None),
    ("post", "/v1/admin/league/competitions", {"name": "x", "slug": "x"}),
    ("patch", "/v1/admin/league/competitions/{cup}", {"name": "Renamed"}),
    ("delete", "/v1/admin/league/competitions/{cup}", None),
    ("post", "/v1/admin/league/competitions/{cup}/status", {"action": "close"}),
    ("get", "/v1/admin/league/competitions/{cup}/entries", None),
    ("get", "/v1/admin/league/competitions/{cup}/winners", None),
    ("post", "/v1/admin/league/entries/{entry}/review", {"action": "approve"}),
    ("post", "/v1/admin/league/entries/{entry}/observations", {"views": 999999}),
    ("post", "/v1/admin/league/entries/{entry}/winner", {"place": 1}),
    ("post", "/v1/admin/league/entries/{entry}/prize", {"status": "sent", "note": "paid"}),
    ("get", "/v1/admin/league/events", None),
    ("post", "/v1/admin/league/creators/{account}/visibility", {"hidden": True, "reason": "x"}),
]


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
def test_admin_routes_refuse_everyone_but_a_logged_in_admin(client, admin, cup, method, path, body):
    who = creator(client)
    entry = enter(client, cup, who).json()["id"]
    url = path.format(cup=cup, entry=entry, account=who["account"]["id"])
    kw = {"json": body} if body is not None else {}
    assert getattr(client, method)(url, **kw).status_code == 401                                   # no login
    assert code(getattr(client, method)(url, headers=who["h"], **kw)) == (403, "admin_required")   # a creator
    key = client.post("/v1/keys", json={"name": "k"}, headers=admin).json()["key"]
    r = getattr(client, method)(url, headers={"Authorization": f"Bearer {key}"}, **kw)
    assert code(r) == (403, "session_required")                                                    # an admin's API key
    with new_session() as db:
        assert db.get(LeagueEntry, entry).status == "pending"                                      # nothing moved
    assert board(client, cup) == []


def test_every_admin_league_route_is_in_the_list_above(client):
    paths = {(m.lower(), p) for p, ops in client.get("/openapi.json").json()["paths"].items()
             if p.startswith("/v1/admin/league") for m in ops}
    listed = {(m, p.replace("{cup}", "{slug}").replace("{entry}", "{entry_id}").replace("{account}", "{account_id}"))
              for m, p, _ in ADMIN_ROUTES}
    assert paths == listed


def test_a_creator_cannot_record_their_own_views(client, admin, cup):
    who = creator(client)
    entry = approved_entry(client, admin, cup, who)
    assert code(views(client, who["h"], entry, 5_000_000)) == (403, "admin_required")
    assert board(client, cup)[0]["views"] is None


# ---- competitions ----

def test_a_competition_starts_as_a_draft_nobody_else_can_see(client, admin):
    slug = competition(client, admin, opened=False)
    assert code(client.get(f"/v1/league/{slug}/leaderboard")) == (404, "not_found")
    assert move(client, admin, slug, "open").json()["status"] == "open"
    assert client.get(f"/v1/league/{slug}/leaderboard").status_code == 200


def test_dates_and_prizes_are_validated(client, admin):
    now = utcnow()
    base = {"name": "Cup", "slug": unique_slug(), "starts_at": now.isoformat() + "Z",
            "ends_at": (now - timedelta(hours=1)).isoformat() + "Z"}
    assert client.post("/v1/admin/league/competitions", json=base, headers=admin).status_code == 422
    ok = {**base, "ends_at": (now + timedelta(days=30)).isoformat() + "Z"}
    for bad in ({"slug": "Has Space"}, {"slug": "creators"}, {"prizes": [PRIZES[0], PRIZES[0]]},
                {"prizes": [{"place": 4, "amount_cents": 1}]}, {"prizes": [{"place": 1, "amount_cents": -5}]}):
        assert client.post("/v1/admin/league/competitions", json={**ok, **bad}, headers=admin).status_code == 422, bad
    assert client.post("/v1/admin/league/competitions", json=ok, headers=admin).status_code == 201
    assert code(client.post("/v1/admin/league/competitions", json=ok, headers=admin)) == (409, "slug_taken")


def test_prizes_can_be_configured_but_cash_stays_locked_without_the_server_setting(client, admin, cup):
    r = client.patch(f"/v1/admin/league/competitions/{cup}", json={"prizes": [{"place": 1, "amount_cents": 20000}]},
                     headers=admin)
    assert r.status_code == 200 and r.json()["prizes"] == [{"place": 1, "amount_cents": 20000, "currency": "USD", "label": None}]
    locked = client.patch(f"/v1/admin/league/competitions/{cup}", json={"cash_prizes_enabled": True}, headers=admin)
    assert code(locked) == (409, "cash_prizes_not_approved")
    assert client.get(f"/v1/league/{cup}/leaderboard").json()["competition"]["prizes"] is None


def test_with_the_server_setting_an_admin_can_show_cash_prizes(client, admin, cup, monkeypatch):
    monkeypatch.setattr(get_settings(), "league_cash_prizes_approved", True)
    assert client.patch(f"/v1/admin/league/competitions/{cup}", json={"cash_prizes_enabled": True},
                        headers=admin).json()["cash_prizes_enabled"] is True
    c = client.get(f"/v1/league/{cup}/leaderboard").json()["competition"]
    assert c["cash_prizes"] is True and c["prize_pool_cents"] == 17500 and [p["amount_cents"] for p in c["prizes"]] == [10000, 5000, 2500]
    monkeypatch.setattr(get_settings(), "league_cash_prizes_approved", False)       # the lock wins over the flag
    assert client.get(f"/v1/league/{cup}/leaderboard").json()["competition"]["prizes"] is None


def test_only_a_draft_can_be_deleted(client, admin, cup):
    draft = competition(client, admin, opened=False)
    assert client.delete(f"/v1/admin/league/competitions/{draft}", headers=admin).json() == {"deleted": True}
    assert code(client.delete(f"/v1/admin/league/competitions/{cup}", headers=admin)) == (409, "status_not_allowed")


@pytest.mark.parametrize("action", ["reopen", "finalize", "open"])
def test_a_competition_moves_only_by_its_rules(client, admin, cup, action):
    assert code(move(client, admin, cup, action)) == (409, "status_not_allowed")       # an open one


# ---- review ----

def test_review_moves_an_entry_and_tells_the_creator_why(client, admin, cup):
    who = creator(client)
    entry = enter(client, cup, who).json()["id"]
    assert code(review(client, admin, entry, "reject")) == (422, "reason_required")
    r = review(client, admin, entry, "reject", "The ClutchClips link is not in the description.")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    mine = client.get(f"/v1/league/me?competition={cup}", headers=who["h"]).json()["entry"]
    assert mine["status"] == "rejected" and mine["status_reason"] == "The ClutchClips link is not in the description."
    assert board(client, cup) == []
    assert review(client, admin, entry, "approve").json()["status"] == "approved"      # fixed, then approved
    assert [e["username"] for e in board(client, cup)] == [who["username"]]


def test_a_disqualified_entry_leaves_the_board_for_good(client, admin, cup):
    who = creator(client)
    entry = approved_entry(client, admin, cup, who, views=900)
    assert code(review(client, admin, entry, "disqualify")) == (422, "reason_required")
    assert review(client, admin, entry, "disqualify", "Purchased views.").json()["status"] == "disqualified"
    assert board(client, cup) == []
    for action in ("approve", "reject", "disqualify"):
        assert code(review(client, admin, entry, action, "again")) == (409, "review_not_allowed")
    assert code(views(client, admin, entry, 1000)) == (409, "entry_not_approved")


def test_a_flag_is_for_admins_only_and_needs_a_reason(client, admin, cup):
    who = creator(client)
    entry = approved_entry(client, admin, cup, who, views=10)
    assert code(review(client, admin, entry, "flag")) == (422, "reason_required")
    r = review(client, admin, entry, "flag", "Views jumped 50x overnight.")
    assert r.json()["flagged"] is True and r.json()["status"] == "approved"
    assert "jumped" not in client.get(f"/v1/league/{cup}/leaderboard").text
    assert "jumped" not in client.get(f"/v1/league/me?competition={cup}", headers=who["h"]).text
    assert review(client, admin, entry, "unflag").json()["flagged"] is False


def test_the_admin_list_shows_who_entered(client, admin, cup):
    who = creator(client)
    enter(client, cup, who)
    rows = client.get(f"/v1/admin/league/competitions/{cup}/entries?status=pending", headers=admin).json()
    assert rows["competition"]["entries"]["pending"] == 1
    assert rows["entries"][0]["email"] == who["account"]["email"] and rows["entries"][0]["username"] == who["username"]
    assert client.get(f"/v1/admin/league/competitions/{cup}/entries?status=approved", headers=admin).json()["entries"] == []


# ---- ranking ----

def test_the_board_ranks_approved_entries_by_their_newest_count(client, admin, cup):
    a, b, c = creator(client), creator(client), creator(client)
    ea = approved_entry(client, admin, cup, a, views=100)
    approved_entry(client, admin, cup, b, views=300)
    approved_entry(client, admin, cup, c)                       # no count yet: last
    assert [(e["rank"], e["username"], e["views"]) for e in board(client, cup)] == [
        (1, b["username"], 300), (2, a["username"], 100), (3, c["username"], None)]
    assert views(client, admin, ea, 5000).status_code == 201    # a newer reading overtakes
    assert [e["username"] for e in board(client, cup)][:2] == [a["username"], b["username"]]
    assert views(client, admin, ea, 50).status_code == 201      # the newest count is used, not the highest
    assert [e["username"] for e in board(client, cup)][:2] == [b["username"], a["username"]]


def test_the_newest_reading_by_its_time_is_the_count_and_a_backdated_one_is_refused(client, admin, cup):
    a, b = creator(client), creator(client)
    ea = approved_entry(client, admin, cup, a)
    approved_entry(client, admin, cup, b, views=500)
    hour_ago = (utcnow() - timedelta(hours=1)).isoformat() + "Z"
    assert views(client, admin, ea, 1000, observed_at=hour_ago).status_code == 201
    two_days_ago = (utcnow() - timedelta(days=2)).isoformat() + "Z"
    assert code(views(client, admin, ea, 10, observed_at=two_days_ago)) == (422, "observed_before_latest")
    assert [(e["username"], e["views"]) for e in board(client, cup)] == [(a["username"], 1000), (b["username"], 500)]
    assert views(client, admin, ea, 400).status_code == 201          # read now: newer than an hour ago, so it counts
    assert [(e["username"], e["views"]) for e in board(client, cup)] == [(b["username"], 500), (a["username"], 400)]


def test_counts_are_labelled_unverified_with_their_source_and_time(client, admin, cup):
    who = creator(client)
    entry = approved_entry(client, admin, cup, who)
    when = (utcnow() - timedelta(hours=2)).replace(microsecond=0)
    assert views(client, admin, entry, 4321, observed_at=when.isoformat() + "Z").status_code == 201
    page = client.get(f"/v1/league/{cup}/leaderboard").json()
    row = page["entries"][0]
    assert (row["views"], row["views_verified"], row["views_source"]) == (4321, False, "public_page")
    assert row["observed_at"] == when.isoformat() + "Z" == page["updated_at"]
    future = (utcnow() + timedelta(hours=1)).isoformat() + "Z"
    assert code(views(client, admin, entry, 9, observed_at=future)) == (422, "observed_in_future")
    assert views(client, admin, entry, -1).status_code == 422


def test_every_reading_is_kept_as_ranking_history(client, admin, cup):
    who = creator(client)
    entry = approved_entry(client, admin, cup, who)
    for n in (10, 250, 240):
        views(client, admin, entry, n)
    seen = client.get(f"/v1/admin/league/competitions/{cup}/entries", headers=admin).json()["entries"][0]["observations"]
    assert [o["views"] for o in seen] == [240, 250, 10] and all(o["verified"] is False for o in seen)
    with new_session() as db:
        obs = db.execute(select(LeagueViewObservation).where(LeagueViewObservation.entry_id == entry)).scalars().first()
        obs.views = 999_999
        with pytest.raises(RuntimeError, match="append-only"):
            db.commit()


def test_a_tie_goes_to_the_earlier_submission_then_the_entry_id(client, admin, cup):
    first, second, third = creator(client), creator(client), creator(client)
    e1 = approved_entry(client, admin, cup, first, views=700)
    e2 = approved_entry(client, admin, cup, second, views=700)
    e3 = approved_entry(client, admin, cup, third, views=700)
    assert [e["username"] for e in board(client, cup)] == [first["username"], second["username"], third["username"]]
    with new_session() as db:                                   # the same instant: the entry id decides
        when = db.get(LeagueEntry, e1).submitted_at
        for e in (e2, e3):
            db.get(LeagueEntry, e).submitted_at = when
        db.commit()
    by_id = {e1: first, e2: second, e3: third}
    assert [e["username"] for e in board(client, cup)] == [by_id[i]["username"] for i in sorted(by_id)]
    assert [e["rank"] for e in board(client, cup)] == [1, 2, 3]            # no shared places


def test_the_page_summary_counts_approved_entries_and_shows_the_top_three(client, admin):
    cup = competition(client, admin, starts_in_h=-0.00001)        # the newest live one: the current competition
    who = [creator(client) for _ in range(4)]
    for i, w in enumerate(who):
        approved_entry(client, admin, cup, w, views=(i + 1) * 10)
    enter(client, cup, creator(client))                          # pending: not a participant yet
    now = client.get("/v1/league/current").json()
    assert now["competition"]["slug"] == cup and now["competition"]["participants"] == 4
    assert [e["username"] for e in now["top"]] == [w["username"] for w in reversed(who[1:])]


# ---- removed clips ----

def admin_row(client, admin, cup, entry_id):
    rows = client.get(f"/v1/admin/league/competitions/{cup}/entries", headers=admin).json()["entries"]
    return next(e for e in rows if e["id"] == entry_id)


def public_lists(client, cup, who):
    """Where a creator's entry can be seen without a login: board, featured, their profile page, the count."""
    return {"board": [e["username"] for e in board(client, cup)],
            "featured": [e["username"] for e in client.get(f"/v1/league/{cup}/featured").json()["clips"]],
            "profile": [x["competition"]["slug"] for x in client.get(f"/v1/league/creators/{who['username']}").json()["entries"]],
            "participants": client.get(f"/v1/league/{cup}/leaderboard").json()["competition"]["participants"]}


def take_down(client, admin, clip_id, action="disable"):
    """A copyright report against the clip and an admin's trust decision on it. Returns the case reference."""
    b = {"kind": "copyright", "name": "Rights Holder", "email": "claim@studio-example.com", "relationship": "owner",
         "address": "1 Main St", "phone": "+1 555 0100", "work": "My recording", "good_faith": True,
         "accurate": True, "signature": "Rights Holder", "reported_urls": [f"https://api.clutchclips.io/v1/clips/{clip_id}"]}
    r = client.post("/v1/trust/reports", json=b)
    assert r.status_code == 201, r.text
    ref = r.json()["reference"]
    r = client.post(f"/v1/admin/trust/cases/{ref}/decisions", json={"action": action}, headers=admin)
    assert r.status_code == 200, r.text
    return ref


@pytest.fixture
def quiet_mail(monkeypatch):
    monkeypatch.setattr(routes_trust, "send_email", lambda *a, **kw: None)


def test_a_clip_taken_down_by_a_trust_decision_is_disqualified_and_leaves_every_public_list(client, admin, cup, quiet_mail):
    gone, stays = creator(client), creator(client)
    e_gone = approved_entry(client, admin, cup, gone, views=900)
    approved_entry(client, admin, cup, stays, views=100)
    assert public_lists(client, cup, gone)["board"] == [gone["username"], stays["username"]]
    ref = take_down(client, admin, gone["clip"])
    seen = public_lists(client, cup, gone)
    assert (seen["board"], seen["featured"], seen["profile"], seen["participants"]) == (
        [stays["username"]], [stays["username"]], [], 1)
    row = admin_row(client, admin, cup, e_gone)
    assert (row["status"], row["clip_removed"]) == ("disqualified", True) and ref in row["status_reason"]
    log = client.get(f"/v1/admin/league/events?competition={cup}", headers=admin).json()["events"]
    dq = next(e for e in log if e["action"] == "disqualify" and e["entity_id"] == e_gone)
    assert (dq["actor_id"], dq["before"], dq["after"]) == ("system", {"status": "approved"}, {"status": "disqualified"})
    assert ref in dq["reason"]
    mine = client.get(f"/v1/league/me?competition={cup}", headers=gone["h"]).json()["entry"]
    assert mine["status"] == "disqualified" and ref in mine["status_reason"]


def test_a_takedown_in_a_final_competition_flags_the_winner_for_an_admin(client, admin, podium, quiet_mail):
    cup, ids, who = podium["cup"], podium["ids"], podium["who"]
    move(client, admin, cup, "close")
    for place, entry in enumerate(ids[:3], start=1):
        winner(client, admin, entry, place)
    move(client, admin, cup, "finalize")
    ref = take_down(client, admin, who[0]["clip"])
    row = admin_row(client, admin, cup, ids[0])
    assert (row["status"], row["final_place"], row["flagged"], row["clip_removed"]) == ("approved", 1, True, True)
    assert ref in row["flag_reason"]
    assert [(e["rank"], e["username"]) for e in board(client, cup)] == [
        (2, who[1]["username"]), (3, who[2]["username"]), (4, who[3]["username"])]       # places do not move
    flag = next(e for e in client.get(f"/v1/admin/league/events?competition={cup}", headers=admin).json()["events"]
                if e["action"] == "flag" and e["entity_id"] == ids[0])
    assert flag["actor_id"] == "system" and ref in flag["reason"]


def test_a_creator_who_removes_their_own_clip_leaves_the_public_lists(client, admin, cup):
    who = creator(client)
    who = {**who, "clip": make_clip(who["account"]["id"],          # a link import: the creator can take it down
                                    source_url=f"https://www.twitch.tv/videos/{uuid.uuid4().int % 10**9}")}
    entry = approved_entry(client, admin, cup, who, views=50)
    other = creator(client)
    approved_entry(client, admin, cup, other, views=10)
    r = client.post("/v1/imports/takedown", json={"all_imports": True, "consent": True}, headers=who["h"])
    assert r.status_code == 200, r.text
    seen = public_lists(client, cup, who)
    assert (seen["board"], seen["featured"], seen["profile"], seen["participants"]) == (
        [other["username"]], [other["username"]], [], 1)
    row = admin_row(client, admin, cup, entry)
    assert (row["status"], row["clip_removed"], row["rank"]) == ("approved", True, None)


def test_a_clip_past_its_retention_keeps_its_entry_on_the_board(client, admin, cup):
    who = creator(client)
    entry = approved_entry(client, admin, cup, who, views=50)
    with new_session() as db:
        db.get(Job, db.get(Clip, who["clip"]).job_id).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert worker.sweep_expired() >= 1
    with new_session() as db:
        assert db.get(Clip, who["clip"]).deleted_at is not None
    assert [(e["username"], e["thumb_url"]) for e in board(client, cup)] == [(who["username"], None)]
    assert admin_row(client, admin, cup, entry)["clip_removed"] is False


# ---- admins and their own entries ----

def test_an_admin_cannot_review_count_or_crown_their_own_entry(client, cup):
    me, acct = make_admin(client)
    assert client.put("/v1/league/me/profile", json={"username": f"a{uuid.uuid4().hex[:10]}"}, headers=me).status_code == 200
    mine = enter(client, cup, {"h": me, "clip": make_clip(acct["id"])})
    assert mine.status_code == 201, mine.text
    entry = mine.json()["id"]
    assert code(review(client, me, entry, "approve")) == (403, "own_entry")
    assert code(review(client, me, entry, "flag", "x")) == (403, "own_entry")
    other = make_admin(client)[0]
    assert review(client, other, entry, "approve").json()["status"] == "approved"
    assert code(views(client, me, entry, 10**9)) == (403, "own_entry")
    assert views(client, other, entry, 10).status_code == 201
    move(client, other, cup, "close")
    assert code(winner(client, me, entry, 1)) == (403, "own_entry")
    assert winner(client, other, entry, 1).json()["final_place"] == 1
    assert [(e["views"], e["final_place"]) for e in board(client, cup)] == [(10, 1)]


# ---- creator profiles ----

def test_an_admin_can_hide_a_profile_and_the_creator_cannot_make_it_public_again(client, admin, cup):
    who = creator(client)
    approved_entry(client, admin, cup, who, views=5)
    hide = lambda body: client.post(f"/v1/admin/league/creators/{who['account']['id']}/visibility",  # noqa: E731
                                    json=body, headers=admin)
    assert code(hide({"hidden": True})) == (422, "reason_required")
    r = hide({"hidden": True, "reason": "Offensive username."})
    assert r.status_code == 200 and (r.json()["is_public"], r.json()["hidden"]) == (False, True)
    assert code(client.get(f"/v1/league/creators/{who['username']}")) == (404, "not_found")
    assert board(client, cup)[0]["has_profile"] is False
    again = {"username": who["username"], "is_public": True}
    assert code(client.put("/v1/league/me/profile", json=again, headers=who["h"])) == (403, "profile_hidden")
    row = client.get(f"/v1/admin/league/competitions/{cup}/entries", headers=admin).json()["entries"][0]
    assert row["profile_hidden"] is True
    assert hide({"hidden": False}).json() == {**r.json(), "hidden": False}             # still private
    assert client.put("/v1/league/me/profile", json=again, headers=who["h"]).json()["is_public"] is True
    assert client.get(f"/v1/league/creators/{who['username']}").status_code == 200
    log = client.get("/v1/admin/league/events", headers=admin).json()["events"]
    assert [e["action"] for e in log if e["entity_kind"] == "profile"][:2] == ["profile_unhide", "profile_hide"]
    assert next(e for e in log if e["action"] == "profile_hide")["reason"] == "Offensive username."


# ---- winners ----

@pytest.fixture
def podium(client, admin, cup):
    who = [creator(client) for _ in range(4)]
    ids = [approved_entry(client, admin, cup, w, views=n) for w, n in zip(who, (4000, 3000, 2000, 1000))]
    return {"cup": cup, "who": who, "ids": ids}


def test_winners_are_provisional_until_an_admin_approves_them(client, admin, podium):
    cup, ids = podium["cup"], podium["ids"]
    assert code(winner(client, admin, ids[0], 1)) == (409, "competition_not_closed")
    assert move(client, admin, cup, "close").json()["status"] == "closed"
    top = client.get(f"/v1/admin/league/competitions/{cup}/winners", headers=admin).json()["winners"]
    assert [(w["place"], w["state"], w["id"]) for w in top] == [(1, "provisional", ids[0]), (2, "provisional", ids[1]),
                                                                (3, "provisional", ids[2])]
    assert [w["prize"]["amount_cents"] for w in top] == [10000, 5000, 2500]
    assert all(e["status"] == "provisional" for e in board(client, cup))
    assert code(move(client, admin, cup, "finalize")) == (409, "winners_not_approved")
    assert code(winner(client, admin, ids[1], 1)) == (409, "not_provisional_winner")      # not the place it holds
    assert code(winner(client, admin, ids[3], 3)) == (409, "not_provisional_winner")      # fourth is no winner
    assert code(winner(client, admin, ids[1], 2)) == (409, "approve_in_order")
    for place, entry in enumerate(ids[:3], start=1):
        r = winner(client, admin, entry, place)
        assert r.status_code == 200 and r.json()["final_place"] == place and r.json()["prize_status"] == "pending"
    assert code(winner(client, admin, ids[0], 1)) == (409, "winner_already_approved")
    assert [(e["status"], e["final_place"]) for e in board(client, cup)] == [("winner", 1), ("winner", 2), ("winner", 3),
                                                                           ("provisional", None)]
    done = move(client, admin, cup, "finalize")
    assert done.json()["status"] == "finalized" and done.json()["phase"] == "final"
    profile = client.get(f"/v1/league/creators/{podium['who'][0]['username']}").json()
    assert profile["awards"][0]["place"] == 1 and profile["entries"][0]["rank"] == 1


def test_no_public_response_carries_a_prize_amount_while_the_server_lock_is_off(client, admin, podium, monkeypatch):
    cup, ids, first = podium["cup"], podium["ids"], podium["who"][0]
    amounts = [{"place": 1, "amount_cents": 13579}, {"place": 2, "amount_cents": 8642}, {"place": 3, "amount_cents": 7531}]
    monkeypatch.setattr(get_settings(), "league_cash_prizes_approved", True)
    saved = client.patch(f"/v1/admin/league/competitions/{cup}", json={"prizes": amounts, "cash_prizes_enabled": True},
                         headers=admin).json()
    assert saved["cash_prizes_enabled"] is True and [p["amount_cents"] for p in saved["prizes"]] == [13579, 8642, 7531]
    monkeypatch.setattr(get_settings(), "league_cash_prizes_approved", False)
    move(client, admin, cup, "close")
    for place, entry in enumerate(ids[:3], start=1):
        assert winner(client, admin, entry, place).status_code == 200
    seen = [client.get(path, headers=h) for path, h in (
        ("/v1/league/current", {}), ("/v1/league/rules", {}), (f"/v1/league/{cup}/leaderboard", {}),
        (f"/v1/league/{cup}/featured", {}), (f"/v1/league/creators/{first['username']}", {}),
        (f"/v1/league/me?competition={cup}", first["h"]), ("/v1/league/me", first["h"]))]
    move(client, admin, cup, "finalize")
    seen.append(client.get(f"/v1/league/{cup}/leaderboard"))
    for r in seen:
        assert r.status_code == 200, (r.request.url, r.text)
        assert "amount_cents" not in r.text and "13579" not in r.text and "8642" not in r.text, r.request.url
        assert '"prize_pool_cents":null' in r.text.replace(" ", "") or "prize_pool_cents" not in r.text, r.request.url


def test_a_disqualification_before_approval_moves_the_next_entry_up(client, admin, podium):
    cup, ids = podium["cup"], podium["ids"]
    move(client, admin, cup, "close")
    assert review(client, admin, ids[0], "disqualify", "Not made with ClutchClips.").status_code == 200
    top = client.get(f"/v1/admin/league/competitions/{cup}/winners", headers=admin).json()["winners"]
    assert [w["id"] for w in top] == ids[1:4]
    assert winner(client, admin, ids[1], 1).status_code == 200


def test_once_a_winner_is_approved_the_result_above_it_is_settled(client, admin, podium):
    cup, ids = podium["cup"], podium["ids"]
    move(client, admin, cup, "close")
    winner(client, admin, ids[0], 1)
    assert code(views(client, admin, ids[1], 9_999_999)) == (409, "winners_approved")
    assert code(review(client, admin, ids[0], "disqualify", "late")) == (409, "winner_already_approved")
    assert review(client, admin, ids[1], "disqualify", "Video was made private.").status_code == 200   # below: allowed
    assert winner(client, admin, ids[2], 2).status_code == 200


def test_a_rejected_entry_cannot_rejoin_the_ranking_above_an_approved_winner(client, admin, cup):
    low, high = creator(client), creator(client)
    e_low = approved_entry(client, admin, cup, low, views=500)
    e_high = approved_entry(client, admin, cup, high, views=1000)
    assert review(client, admin, e_high, "reject", "No attribution link.").status_code == 200
    move(client, admin, cup, "close")
    assert winner(client, admin, e_low, 1).status_code == 200
    assert code(review(client, admin, e_high, "approve")) == (409, "winners_approved")
    assert [(e["username"], e["final_place"]) for e in board(client, cup)] == [(low["username"], 1)]
    assert code(move(client, admin, cup, "reopen")) == (409, "winners_approved")
    assert move(client, admin, cup, "finalize").json()["status"] == "finalized"


def test_a_final_competition_takes_no_more_changes(client, admin, podium):
    cup, ids = podium["cup"], podium["ids"]
    move(client, admin, cup, "close")
    for place, entry in enumerate(ids[:3], start=1):
        winner(client, admin, entry, place)
    move(client, admin, cup, "finalize")
    assert code(views(client, admin, ids[3], 5)) == (409, "competition_final")
    assert code(review(client, admin, ids[3], "disqualify", "Late.")) == (409, "competition_final")
    assert code(review(client, admin, ids[3], "reject", "Late.")) == (409, "competition_final")
    assert code(review(client, admin, ids[3], "flag", "Odd.")) == (409, "competition_final")
    assert code(review(client, admin, ids[0], "unflag")) == (409, "competition_final")
    assert [e["rank"] for e in board(client, cup)] == [1, 2, 3, 4]
    assert code(client.patch(f"/v1/admin/league/competitions/{cup}", json={"name": "Other"}, headers=admin)) == (409, "competition_final")
    assert code(move(client, admin, cup, "reopen")) == (409, "status_not_allowed")


def test_a_prize_is_recorded_by_hand_and_nothing_is_paid(client, admin, podium):
    cup, ids, first = podium["cup"], podium["ids"], podium["who"][0]
    before = client.get("/v1/credits", headers=first["h"]).json()["balance"]
    prize = lambda entry, status, note="Sent by bank transfer, ref 123": client.post(      # noqa: E731
        f"/v1/admin/league/entries/{entry}/prize", json={"status": status, "note": note}, headers=admin)
    assert code(prize(ids[0], "sent")) == (409, "prize_not_allowed")                   # not an approved winner yet
    move(client, admin, cup, "close")
    winner(client, admin, ids[0], 1)
    assert prize(ids[0], "sent").json()["prize_status"] == "sent"
    assert code(prize(ids[0], "forfeited")) == (409, "prize_not_allowed")              # settled once
    mine = client.get(f"/v1/league/me?competition={cup}", headers=first["h"]).json()["entry"]
    assert mine["final_place"] == 1 and mine["prize_status"] == "sent"
    assert client.get("/v1/credits", headers=first["h"]).json()["balance"] == before   # no credits, no payment


# ---- audit ----

def test_every_admin_move_is_in_the_audit_log_with_before_after_and_reason(client, admin, podium):
    cup, ids = podium["cup"], podium["ids"]
    review(client, admin, ids[3], "flag", "Odd traffic.")
    review(client, admin, ids[3], "disqualify", "Bought views.")
    views(client, admin, ids[1], 3500)
    move(client, admin, cup, "close")
    winner(client, admin, ids[0], 1)
    log = client.get(f"/v1/admin/league/events?competition={cup}&limit=500", headers=admin).json()["events"]
    actions = [e["action"] for e in reversed(log)]
    for wanted in ("competition_create", "competition_open", "submit", "approve", "observe_views", "flag",
                   "disqualify", "competition_close", "approve_winner"):
        assert wanted in actions, wanted
    dq = next(e for e in log if e["action"] == "disqualify")
    assert (dq["before"], dq["after"], dq["reason"], dq["entity_id"]) == ({"status": "approved"}, {"status": "disqualified"},
                                                                         "Bought views.", ids[3])
    seen = next(e for e in log if e["action"] == "observe_views" and e["entity_id"] == ids[1])
    assert seen["before"] == {"views": 3000} and seen["after"]["views"] == 3500
    won = next(e for e in log if e["action"] == "approve_winner")
    assert won["after"]["final_place"] == 1 and won["actor_id"]
    assert all(e["actor_id"] and e["created_at"] for e in log)


def test_a_refused_move_writes_nothing(client, admin, cup):
    who = creator(client)
    entry = approved_entry(client, admin, cup, who)
    n = len(client.get(f"/v1/admin/league/events?competition={cup}", headers=admin).json()["events"])
    assert review(client, admin, entry, "approve").status_code == 409
    assert winner(client, admin, entry, 1).status_code == 409
    assert len(client.get(f"/v1/admin/league/events?competition={cup}", headers=admin).json()["events"]) == n


def test_a_non_admin_signup_is_not_an_admin(client):
    h, _ = signup(client)
    assert code(client.get("/v1/admin/league/competitions", headers=h)) == (403, "admin_required")
