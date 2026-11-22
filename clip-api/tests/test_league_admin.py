"""Creators League for admins: only admins reach the admin routes, entries move only by the review rules,
view counts are appended by admins and drive the ranking, ties break by submission time, winners are provisional
until approved in order, prizes are recorded and never paid, and every move is in the audit log."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import deps
from app.config import get_settings
from app.db import new_session
from app.models import LeagueEntry, LeagueViewObservation, utcnow
from tests.league_support import approved_entry, competition, creator, enter, make_admin, signup, unique_slug

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
]


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
def test_admin_routes_refuse_everyone_but_a_logged_in_admin(client, admin, cup, method, path, body):
    who = creator(client)
    entry = enter(client, cup, who).json()["id"]
    url = path.format(cup=cup, entry=entry)
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
    listed = {(m, p.replace("{cup}", "{slug}").replace("{entry}", "{entry_id}")) for m, p, _ in ADMIN_ROUTES}
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
