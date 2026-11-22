"""Creators League for creators and the public: entry is free, the clip must be the caller's, one entry per
creator and per video, only inside the window, only links of the three platforms' video shapes, attribution and
rules accepted, nothing private on the public pages, and the limits."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import deps, league, league_rules
from app.config import get_settings
from app.db import new_session
from app.models import Account, LeagueCompetition, LeagueEntry, utcnow
from tests.league_support import (approved_entry, competition, creator, enter, entry_body, make_admin, make_clip,
                                  short_url, signup)


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
    return competition(client, admin)


def code(r):
    return r.status_code, r.json().get("error", {}).get("code")


# ---- free entry ----

def test_a_free_account_with_no_credits_can_enter(client, cup):
    who = creator(client)
    with new_session() as db:
        assert db.get(Account, who["account"]["id"]).plan in (None, "free")
    before = client.get("/v1/credits", headers=who["h"]).json()["balance"]
    r = enter(client, cup, who)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert client.get("/v1/credits", headers=who["h"]).json()["balance"] == before      # entering costs nothing


def test_an_unverified_email_cannot_enter(client, cup):
    who = creator(client)
    with new_session() as db:
        db.get(Account, who["account"]["id"]).email_verified = False
        db.commit()
    assert code(enter(client, cup, who)) == (403, "email_not_verified")


def test_entering_needs_a_login_and_a_website_session(client, cup):
    who = creator(client)
    assert client.post(f"/v1/league/{cup}/entries", json=entry_body(who["clip"])).status_code == 401
    key = client.post("/v1/keys", json={"name": "k"}, headers=who["h"]).json()["key"]
    r = client.post(f"/v1/league/{cup}/entries", json=entry_body(who["clip"]), headers={"Authorization": f"Bearer {key}"})
    assert code(r) == (403, "session_required")


def test_entering_needs_a_creator_profile(client, cup):
    h, acct = signup(client)
    r = client.post(f"/v1/league/{cup}/entries", json=entry_body(make_clip(acct["id"])), headers=h)
    assert code(r) == (409, "profile_required")


# ---- clip ownership ----

def test_someone_elses_clip_cannot_be_entered_and_looks_like_a_missing_one(client, cup):
    who, other = creator(client), creator(client)
    theirs = enter(client, cup, {**who, "clip": other["clip"]})
    missing = enter(client, cup, {**who, "clip": "clip_doesnotexist"})
    assert code(theirs) == code(missing) == (404, "not_found")
    assert theirs.json() == missing.json()


def test_a_deleted_clip_cannot_be_entered(client, cup):
    who = creator(client)
    gone = make_clip(who["account"]["id"], deleted=True)
    assert code(enter(client, cup, {**who, "clip": gone})) == (404, "not_found")


# ---- duplicates ----

def test_one_entry_per_creator_per_competition(client, cup):
    who = creator(client)
    assert enter(client, cup, who).status_code == 201
    second = make_clip(who["account"]["id"])
    assert code(enter(client, cup, {**who, "clip": second})) == (409, "already_entered")


def test_the_same_video_cannot_be_entered_twice_whatever_its_spelling(client, cup):
    a, b = creator(client), creator(client)
    vid = uuid.uuid4().hex[:11]
    assert enter(client, cup, a, url=f"https://www.youtube.com/shorts/{vid}").status_code == 201
    r = enter(client, cup, b, url=f"https://m.youtube.com/shorts/{vid}/?feature=share")
    assert code(r) == (409, "duplicate_video")


def test_the_same_creator_can_enter_the_next_competition(client, admin, cup):
    who = creator(client)
    assert enter(client, cup, who).status_code == 201
    assert enter(client, competition(client, admin), who).status_code == 201


def test_the_database_itself_refuses_a_second_entry(client, cup):
    """The two unique constraints are the last line when two requests race past the checks."""
    who = creator(client)
    assert enter(client, cup, who).status_code == 201
    with new_session() as db:
        first = db.execute(select(LeagueEntry).where(LeagueEntry.account_id == who["account"]["id"])).scalar_one()
        clone = {c.name: getattr(first, c.name) for c in LeagueEntry.__table__.columns}
        db.add(LeagueEntry(**{**clone, "id": "lent_race", "url_key": "youtube:other000000"}))
        with pytest.raises(Exception, match="(?i)unique"):
            db.commit()


# ---- deadlines ----

def test_no_entry_before_the_competition_starts(client, admin):
    cup = competition(client, admin, starts_in_h=1, ends_in_h=48)
    assert code(enter(client, cup, creator(client))) == (409, "competition_closed")


def test_no_entry_after_the_deadline_by_the_servers_clock(client, admin, cup):
    who = creator(client)
    with new_session() as db:
        c = db.execute(select(LeagueCompetition).where(LeagueCompetition.slug == cup)).scalar_one()
        c.ends_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert code(enter(client, cup, who)) == (409, "competition_closed")
    c = client.get(f"/v1/league/{cup}/leaderboard").json()["competition"]
    assert c["accepting_entries"] is False and c["phase"] == "ended"


def test_no_entry_into_a_draft_or_a_closed_competition(client, admin):
    draft = competition(client, admin, opened=False)
    assert code(enter(client, draft, creator(client))) == (404, "not_found")       # a draft is not public
    cup = competition(client, admin)
    client.post(f"/v1/admin/league/competitions/{cup}/status", json={"action": "close"}, headers=admin)
    assert code(enter(client, cup, creator(client))) == (409, "competition_closed")


def test_the_entry_keeps_its_submission_time_and_the_rules_version(client, cup):
    who = creator(client)
    r = enter(client, cup, who)
    assert r.json()["rules_version"] == league_rules.VERSION and r.json()["submitted_at"].endswith("Z")
    with new_session() as db:
        e = db.get(LeagueEntry, r.json()["id"])
        assert e.attribution_confirmed_at is not None and abs((utcnow() - e.submitted_at).total_seconds()) < 60
        assert e.snapshot["duration_sec"] == 22.5 and e.snapshot["platform"] == "youtube"


# ---- video links ----

GOOD = [
    ("tiktok", "https://www.tiktok.com/@clutch.kid/video/7301234567890123456", "tiktok:7301234567890123456"),
    ("tiktok", "https://m.tiktok.com/@clutch_kid/video/7301234567890123456?lang=en", "tiktok:7301234567890123456"),
    ("youtube", "https://www.youtube.com/shorts/AbCdEfGh_-1", "youtube:AbCdEfGh_-1"),
    ("youtube", "https://youtube.com/shorts/AbCdEfGh_-1?feature=share", "youtube:AbCdEfGh_-1"),
    ("instagram", "https://www.instagram.com/reel/Cx1_abcDEF-/", "instagram:Cx1_abcDEF-"),
    ("instagram", "https://instagram.com/reels/Cx1_abcDEF-", "instagram:Cx1_abcDEF-"),
]
BAD = [
    ("youtube", "http://www.youtube.com/shorts/AbCdEfGh_-1"),                       # not https
    ("youtube", "https://www.youtube.com/watch?v=AbCdEfGh_-1"),                     # not a Short
    ("youtube", "https://youtu.be/AbCdEfGh_-1"),                                    # short link: a redirect
    ("tiktok", "https://vm.tiktok.com/ZMabcdef/"),                                  # short link: a redirect
    ("tiktok", "https://www.youtube.com/shorts/AbCdEfGh_-1"),                       # the wrong platform
    ("youtube", "https://www.youtube.com.evil.example/shorts/AbCdEfGh_-1"),         # a look-alike host
    ("youtube", "https://evil.example/www.youtube.com/shorts/AbCdEfGh_-1"),
    ("youtube", "https://www.youtube.com@evil.example/shorts/AbCdEfGh_-1"),         # user info
    ("youtube", "https://evil.example\\@www.youtube.com/shorts/AbCdEfGh_-1"),
    ("youtube", "https://www.youtube.com:8443/shorts/AbCdEfGh_-1"),                 # a port
    ("youtube", "https://127.0.0.1/shorts/AbCdEfGh_-1"),                            # an address
    ("youtube", "https://169.254.169.254/latest/meta-data/"),
    ("youtube", "https://localhost/shorts/AbCdEfGh_-1"),
    ("youtube", "https://[::1]/shorts/AbCdEfGh_-1"),
    ("youtube", "//www.youtube.com/shorts/AbCdEfGh_-1"),                            # no scheme
    ("youtube", "javascript:alert(1)//www.youtube.com/shorts/AbCdEfGh_-1"),
    ("youtube", "data:text/html,<script>alert(1)</script>"),
    ("youtube", "file:///etc/passwd#youtube.com/shorts/AbCdEfGh_-1"),
    ("youtube", "https://www.youtube.com/shorts/AbCdEfGh_-1/../../watch"),          # a path that walks away
    ("youtube", "https://www.youtube.com/shorts/<script>alert(1)</script>"),
    ("youtube", "https://www.youtube.com/shorts/AbCdEfGh_-1\nhttps://evil.example"),
    ("youtube", "https://www.youtube.com/shorts/AbCdEfGh_-1 "),                     # (stripped by the API; refused here)
    ("youtube", "https://www.youtube.com\t/shorts/AbCdEfGh_-1"),
    ("youtube", "https://www.youtubе.com/shorts/AbCdEfGh_-1"),                      # a Cyrillic letter in the host
    ("youtube", "https://WWW.YOUTUBE.COM./shorts/AbCdEfGh_-1"),                     # a trailing dot
    ("instagram", "https://www.instagram.com/p/Cx1_abcDEF-/"),                      # a post, not a Reel
    ("instagram", "https://www.instagram.com/someone/"),
    ("tiktok", "https://www.tiktok.com/@someone"),                                  # a profile
    ("tiktok", "https://www.tiktok.com/@a/video/12"),                               # an id too short to be one
    ("youtube", "https://www.youtube.com/shorts/" + "A" * 400),
]


@pytest.mark.parametrize("platform,url,key", GOOD)
def test_a_real_video_link_is_stored_in_one_canonical_form(platform, url, key):
    link = league.parse_video_link(platform, url)
    assert link.key == key and link.url.startswith("https://www.") and "?" not in link.url
    assert league.parse_video_link(platform, link.url) == link          # canonical stays canonical


@pytest.mark.parametrize("platform,url", BAD)
def test_anything_else_is_refused(platform, url):
    with pytest.raises(league.Refused) as e:
        league.parse_video_link(platform, url)
    assert e.value.code == "invalid_video_url"


@pytest.mark.parametrize("platform,url", BAD[:12])
def test_the_api_answers_422_to_a_bad_link_and_stores_nothing(client, cup, platform, url):
    who = creator(client)
    assert code(enter(client, cup, who, platform=platform, url=url)) == (422, "invalid_video_url")
    assert client.get(f"/v1/league/me?competition={cup}", headers=who["h"]).json()["entry"] is None


def test_submitting_a_link_makes_no_outbound_request(client, cup, monkeypatch):
    """No SSRF surface: the server opens no connection while handling an entry."""
    import socket

    def refuse(*a, **k):
        raise AssertionError("the league opened a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    who = creator(client)
    assert enter(client, cup, who).status_code == 201
    assert client.get(f"/v1/league/{cup}/leaderboard").status_code == 200


def test_the_stored_link_is_rebuilt_not_the_text_that_was_sent(client, cup):
    who = creator(client)
    vid = uuid.uuid4().hex[:11]
    r = enter(client, cup, who, url=f"https://youtube.com/shorts/{vid}?x=<script>alert(1)</script>#frag")
    assert r.status_code == 201 and r.json()["video_url"] == f"https://www.youtube.com/shorts/{vid}"


# ---- attribution and rules ----

def test_the_attribution_line_uses_the_configured_website(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_web_url", "https://clips.example.test/")
    a = client.get("/v1/league/rules").json()["attribution"]
    assert a == {"url": "https://clips.example.test", "text": "Edited with ClutchClips 🎮\nhttps://clips.example.test"}


def test_an_entry_without_the_attribution_confirmed_is_refused(client, cup):
    who = creator(client)
    assert code(enter(client, cup, who, attribution_confirmed=False)) == (422, "attribution_required")
    body = entry_body(who["clip"])
    del body["attribution_confirmed"]
    assert code(client.post(f"/v1/league/{cup}/entries", json=body, headers=who["h"])) == (422, "validation_error")


def test_an_entry_must_accept_the_current_rules_version(client, cup):
    who = creator(client)
    assert code(enter(client, cup, who, rules_version="2020-old")) == (422, "rules_not_accepted")


def test_the_rules_are_a_draft_and_claim_no_legal_review(client):
    doc = client.get("/v1/league/rules").json()
    assert doc["version"] == league_rules.VERSION and doc["status"] == "draft" and doc["legally_reviewed"] is False
    todo = {s["id"] for s in doc["sections"] if s["needs_legal_review"]}
    assert {"eligibility", "geography", "dates", "prizes", "winners", "disqualification", "platforms", "privacy",
            "law"} <= todo
    for s in doc["sections"]:
        if s["needs_legal_review"]:
            assert any("PLACEHOLDER FOR LEGAL REVIEW" in line for line in s["body"]), s["id"]
    text = " ".join(line for s in doc["sections"] for line in s["body"]).lower()
    assert not any(w in text for w in ("fully compliant", "complies with", "legally compliant", "guarantee"))


def test_unknown_fields_are_refused(client, cup):
    who = creator(client)
    r = client.post(f"/v1/league/{cup}/entries", json={**entry_body(who["clip"]), "views": 9_000_000}, headers=who["h"])
    assert code(r) == (422, "validation_error")          # a creator cannot send a view count


# ---- profiles and creator text ----

@pytest.mark.parametrize("name", ["ab", "a" * 21, "has space", "<script>", "naïve", "semi;colon", "a/b", ""])
def test_a_username_outside_the_charset_is_refused(client, name):
    h, _ = signup(client)
    assert client.put("/v1/league/me/profile", json={"username": name}, headers=h).status_code == 422


IMPERSONATING = ["ClutchClips", "Admin", "clutchclips_", "ClutchClipsHQ", "clutch_clips_team", "c1utchclips",
                 "ClutchClipsOfficial", "admin_", "moderat0r", "CLUTCH_CLIPS_STAFF", "0ff1c1a1", "the_4dm1n",
                 "Supp0rt_Desk", "st4ff_pick", "5upport", "Winner", "System"]


@pytest.mark.parametrize("name", IMPERSONATING)
def test_names_that_pass_for_clutchclips_or_its_staff_are_refused(client, name):
    h, _ = signup(client)
    assert code(client.put("/v1/league/me/profile", json={"username": name}, headers=h)) == (422, "username_reserved")


@pytest.mark.parametrize("name", ["clipper_", "AdamClips_", "offside_ace_", "modern_ace_"])
def test_ordinary_names_are_not_caught_by_the_reserved_words(client, name):
    h, _ = signup(client)
    name += uuid.uuid4().hex[:4]
    assert client.put("/v1/league/me/profile", json={"username": name}, headers=h).status_code == 200


def test_a_name_given_up_is_held_for_its_old_owner_for_30_days(client, monkeypatch):
    old = f"champ{uuid.uuid4().hex[:8]}"
    a = creator(client, username=old)
    renamed = client.put("/v1/league/me/profile", json={"username": old + "x", "is_public": True}, headers=a["h"])
    assert renamed.status_code == 200
    b, _ = signup(client)
    assert code(client.put("/v1/league/me/profile", json={"username": old.upper()}, headers=b)) == (409, "username_held")
    assert code(client.get(f"/v1/league/creators/{old}")) == (404, "not_found")
    back = client.put("/v1/league/me/profile", json={"username": old, "is_public": True}, headers=a["h"])
    assert back.status_code == 200                                     # its old owner can take it back
    assert client.put("/v1/league/me/profile", json={"username": old + "y"}, headers=a["h"]).status_code == 200
    later = utcnow() + timedelta(days=31)
    monkeypatch.setattr(league, "utcnow", lambda: later)
    assert client.put("/v1/league/me/profile", json={"username": old}, headers=b).status_code == 200


def test_usernames_are_unique_whatever_their_case(client):
    who = creator(client)
    h, _ = signup(client)
    r = client.put("/v1/league/me/profile", json={"username": who["username"].upper()}, headers=h)
    assert code(r) == (409, "username_taken")
    again = client.put("/v1/league/me/profile", json={"username": who["username"], "avatar": "rose"}, headers=who["h"])
    assert again.status_code == 200 and again.json()["avatar"] == "rose"       # keeping your own name is fine


@pytest.mark.parametrize("games", [["<img src=x onerror=alert(1)>"], ["a"], ["x" * 31], ["ok"] * 6, ["GTA‮5"]])
def test_game_names_outside_the_charset_are_refused(client, games):
    h, _ = signup(client)
    name = f"u{uuid.uuid4().hex[:8]}"
    assert client.put("/v1/league/me/profile", json={"username": name, "games": games}, headers=h).status_code == 422


def test_an_avatar_is_one_of_the_presets_never_a_link(client):
    h, _ = signup(client)
    r = client.put("/v1/league/me/profile", json={"username": f"u{uuid.uuid4().hex[:8]}",
                                                  "avatar": "https://evil.example/a.png"}, headers=h)
    assert r.status_code == 422


# ---- public pages and data isolation ----

def test_with_no_competition_the_page_has_nothing_to_show(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db import Base
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert league.current(db) is None


def test_the_current_competition_is_the_one_running_now(client, admin):
    competition(client, admin, starts_in_h=24, ends_in_h=48)
    live = competition(client, admin, starts_in_h=-0.001, ends_in_h=12)
    competition(client, admin, opened=False, starts_in_h=-0.0001, ends_in_h=12)        # a draft is never current
    now = client.get("/v1/league/current").json()
    assert now["competition"]["slug"] == live and now["competition"]["phase"] == "live" and now["top"] == []


def test_a_pending_entry_is_not_on_the_public_leaderboard(client, cup):
    who = creator(client)
    assert enter(client, cup, who).status_code == 201
    board = client.get(f"/v1/league/{cup}/leaderboard").json()
    assert board["entries"] == [] and board["competition"]["participants"] == 0 and board["updated_at"] is None
    assert client.get(f"/v1/league/{cup}/featured").json() == {"clips": []}


def test_the_public_leaderboard_shows_no_private_account_data(client, admin, cup):
    who = creator(client)
    approved_entry(client, admin, cup, who, views=1200)
    for path in (f"/v1/league/{cup}/leaderboard", f"/v1/league/{cup}/featured", "/v1/league/current",
                 f"/v1/league/creators/{who['username']}"):
        text = client.get(path).text
        assert who["account"]["email"] not in text and who["account"]["id"] not in text and who["clip"] not in text, path
    row = client.get(f"/v1/league/{cup}/leaderboard").json()["entries"][0]
    assert set(row) == {"rank", "username", "avatar", "has_profile", "game", "platform", "video_url", "thumb_url",
                        "views", "views_verified", "views_source", "observed_at", "status", "final_place"}
    assert row["username"] == who["username"] and row["views"] == 1200 and row["views_verified"] is False


def test_a_private_profile_has_no_profile_page(client, admin, cup):
    who = creator(client, public=False)
    approved_entry(client, admin, cup, who)
    assert code(client.get(f"/v1/league/creators/{who['username']}")) == (404, "not_found")
    assert client.get(f"/v1/league/{cup}/leaderboard").json()["entries"][0]["has_profile"] is False


def test_a_public_profile_shows_only_approved_entries(client, admin, cup):
    who = creator(client)
    assert enter(client, cup, who).status_code == 201
    page = client.get(f"/v1/league/creators/{who['username'].upper()}").json()        # any case finds it
    assert page["username"] == who["username"] and page["games"] == ["GTA 5"] and page["entries"] == []


def test_one_creator_never_sees_anothers_entry_or_clips(client, cup):
    a, b = creator(client), creator(client)
    assert enter(client, cup, a).status_code == 201
    mine = client.get(f"/v1/league/me?competition={cup}", headers=a["h"]).json()
    theirs = client.get(f"/v1/league/me?competition={cup}", headers=b["h"]).json()
    assert mine["entry"]["status"] == "pending" and theirs["entry"] is None
    assert [c["id"] for c in mine["clips"]] == [a["clip"]] and [c["id"] for c in theirs["clips"]] == [b["clip"]]
    assert mine["profile"]["username"] == a["username"] and theirs["profile"]["username"] == b["username"]


def test_cash_amounts_stay_hidden_until_cash_prizes_are_switched_on(client, admin):
    cup = competition(client, admin, prizes=[{"place": 1, "amount_cents": 10000}, {"place": 2, "amount_cents": 5000},
                                             {"place": 3, "amount_cents": 2500}])
    c = client.get(f"/v1/league/{cup}/leaderboard").json()["competition"]
    assert c["cash_prizes"] is False and c["prizes"] is None and c["prize_pool_cents"] is None
    assert c["prize_note"] == "Prizes are announced when the official rules are published."
    assert "10000" not in client.get(f"/v1/league/{cup}/leaderboard").text


# ---- limits ----

def test_entries_are_rate_limited_per_account(client, cup, monkeypatch):
    monkeypatch.setattr(get_settings(), "league_submits_per_hour", 2)
    who = creator(client)
    for _ in range(2):
        assert enter(client, cup, who, url="https://example.org/nope").status_code == 422
    assert code(enter(client, cup, who)) == (429, "rate_limited")
    assert enter(client, cup, creator(client)).status_code == 201           # another account is not held back


def test_profile_edits_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "league_profile_edits_per_hour", 1)
    h, _ = signup(client)
    name = f"u{uuid.uuid4().hex[:8]}"
    assert client.put("/v1/league/me/profile", json={"username": name}, headers=h).status_code == 200
    assert code(client.put("/v1/league/me/profile", json={"username": name}, headers=h)) == (429, "rate_limited")


@pytest.mark.parametrize("path", ["/v1/league/nope/leaderboard", "/v1/league/nope/featured", "/v1/league/creators/nobody"])
def test_public_reads_are_rate_limited_per_address(client, monkeypatch, path):
    monkeypatch.setattr(get_settings(), "league_reads_per_minute", 3)
    for _ in range(3):
        assert client.get(path).status_code in (200, 404)
    assert code(client.get(path)) == (429, "rate_limited")


def test_the_homepage_reads_hold_no_limiter_key_and_may_be_cached(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "league_reads_per_minute", 3)
    for _ in range(10):                                   # a burst of homepage visits, well past the per-address limit
        for path in ("/v1/league/current", "/v1/league/rules"):
            r = client.get(path)
            assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=30"
    assert not [k for k in deps._buckets if k.startswith("league:")]


def test_the_other_public_reads_may_be_cached_too(client, admin, cup):
    who = creator(client)
    approved_entry(client, admin, cup, who)
    for path in (f"/v1/league/{cup}/leaderboard", f"/v1/league/{cup}/featured", f"/v1/league/creators/{who['username']}"):
        assert client.get(path).headers["cache-control"] == "public, max-age=30", path
    assert "public" not in client.get("/v1/league/me", headers=who["h"]).headers.get("cache-control", "")


# ---- rules versions ----

def test_an_open_competition_keeps_the_rules_version_it_was_opened_with(client, admin, cup, monkeypatch):
    first = league_rules.VERSION
    monkeypatch.setattr(league_rules, "VERSION", "draft-2027-01-01")
    monkeypatch.setitem(league_rules.TEXTS, "draft-2027-01-01", ("draft", [{"id": "entry", "title": "How to enter",
                                                                           "needs_legal_review": False, "body": ["New."]}]))
    assert client.get("/v1/league/rules").json()["version"] == "draft-2027-01-01"
    served = client.get(f"/v1/league/rules?version={first}").json()
    assert served["version"] == first and served["sections"] == league_rules.TEXTS[first][1]
    assert code(client.get("/v1/league/rules?version=nope")) == (404, "not_found")
    who = creator(client)
    me = client.get(f"/v1/league/me?competition={cup}", headers=who["h"]).json()
    assert me["rules_version"] == me["competition"]["rules_version"] == first
    assert code(enter(client, cup, who, rules_version="draft-2027-01-01")) == (422, "rules_not_accepted")
    r = enter(client, cup, who, rules_version=first)
    assert r.status_code == 201 and r.json()["rules_version"] == first
    listed = {c["slug"]: c for c in client.get("/v1/admin/league/competitions", headers=admin).json()["competitions"]}
    assert (listed[cup]["rules_version"], listed[cup]["rules_latest"]) == (first, "draft-2027-01-01")
    newer = competition(client, admin)
    listed = {c["slug"]: c for c in client.get("/v1/admin/league/competitions", headers=admin).json()["competitions"]}
    assert listed[newer]["rules_version"] == "draft-2027-01-01"
