"""Creators League routes (app/league.py holds the rules; app/league_rules.py the rules text).

Public reads need no login and show only what a creator agreed to show: username, avatar, game, the clip's
thumbnail, the published link and the recorded view count. Admin routes need a website login of an account with
`is_admin`. Nothing here requests a submitted link: links are matched against fixed patterns and stored.
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import league, league_rules
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, admin_principal, client_ip, rate_limit, session_principal
from .models import (Account, Clip, CreatorProfile, Job, LeagueCompetition, LeagueEntry, LeagueEvent,
                     LeagueViewObservation, new_id, utcnow)
from .storage import get_storage

router = APIRouter()
SLUG = r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$"
NO_CASH_NOTE = "Prizes are announced when the official rules are published."


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def refuse(e: league.Refused) -> ApiError:
    return ApiError(e.status, e.code, e.message)


def public_reads(request: Request) -> None:
    rate_limit(f"league:r:{client_ip(request)}", get_settings().league_reads_per_minute, 60)


def by_slug(db: Session, slug: str, drafts: bool = False) -> LeagueCompetition:
    c = db.execute(select(LeagueCompetition).where(LeagueCompetition.slug == slug)).scalar_one_or_none()
    if c is None or (c.status == "draft" and not drafts):
        raise ApiError(404, "not_found", "No such competition.")
    return c


def thumb_url(clip: Clip | None) -> str | None:
    """The creator's own ClutchClips thumbnail, from our storage. Nothing comes from the submitted link."""
    key = (clip.thumb_chosen_key or clip.thumb_key) if clip and not clip.deleted_at else None
    return get_storage().url(key) if key else None


# ---- shapes ----

def competition_json(db: Session, c: LeagueCompetition) -> dict:
    cash = bool(c.cash_prizes_enabled and get_settings().league_cash_prizes_approved)
    participants = db.execute(select(func.count(LeagueEntry.id)).where(
        LeagueEntry.competition_id == c.id, LeagueEntry.status == "approved")).scalar_one()
    return {"slug": c.slug, "name": c.name, "starts_at": iso(c.starts_at), "ends_at": iso(c.ends_at),
            "phase": league.phase(c), "accepting_entries": league.accepting(c), "participants": participants,
            "rules_version": c.rules_version, "cash_prizes": cash,
            "prizes": c.prizes if cash else None,
            "prize_pool_cents": sum(p["amount_cents"] for p in c.prizes) if cash else None,
            "prize_note": None if cash else NO_CASH_NOTE}


def profiles_of(db: Session, account_ids: set[str]) -> dict[str, CreatorProfile]:
    if not account_ids:
        return {}
    rows = db.execute(select(CreatorProfile).where(CreatorProfile.account_id.in_(account_ids))).scalars()
    return {p.account_id: p for p in rows}


def board_json(db: Session, c: LeagueCompetition, limit: int | None = None) -> list[dict]:
    board = league.ranking(db, c)[:limit]
    who = profiles_of(db, {r.entry.account_id for r in board})
    out = []
    for r in board:
        e, p = r.entry, who.get(r.entry.account_id)
        out.append({"rank": r.rank, "username": p.username if p else None, "avatar": p.avatar if p else "slate",
                    "has_profile": bool(p and p.is_public), "game": e.game, "platform": e.platform,
                    "video_url": e.url, "thumb_url": thumb_url(db.get(Clip, e.clip_id)), "views": r.views,
                    "views_verified": r.verified, "views_source": r.source, "observed_at": iso(r.observed_at),
                    "status": "winner" if e.final_place is not None else "provisional",
                    "final_place": e.final_place})
    return out


def profile_json(p: CreatorProfile | None) -> dict | None:
    return p and {"username": p.username, "avatar": p.avatar, "games": p.games, "is_public": p.is_public}


def my_entry_json(db: Session, c: LeagueCompetition, e: LeagueEntry | None) -> dict | None:
    if e is None:
        return None
    row = next((r for r in league.ranking(db, c) if r.entry.id == e.id), None) if e.status == "approved" else None
    return {"id": e.id, "status": e.status, "status_reason": e.status_reason, "platform": e.platform,
            "video_url": e.url, "game": e.game, "clip_id": e.clip_id, "submitted_at": iso(e.submitted_at),
            "rules_version": e.rules_version, "rank": row.rank if row else None, "views": row.views if row else None,
            "observed_at": iso(row.observed_at) if row else None, "final_place": e.final_place,
            "prize_status": e.prize_status}


# ---- public ----

@router.get("/v1/league/current", dependencies=[Depends(public_reads)])
def current(db: Session = Depends(get_db)):
    """The competition the Creators League page is about, with the top of its leaderboard, or `competition: null`
    when none has been opened. Cash amounts appear only for a competition with cash prizes switched on."""
    c = league.current(db)
    return {"competition": competition_json(db, c) if c else None, "top": board_json(db, c, 3) if c else []}


@router.get("/v1/league/rules", dependencies=[Depends(public_reads)])
def rules():
    """The competition rules with their version, and the attribution line every entry's video must carry. The
    rules are a draft: sections marked `needs_legal_review` hold placeholders."""
    return {**league_rules.document(), "attribution": league_rules.attribution(get_settings().public_web_url)}


@router.get("/v1/league/creators/{username}", dependencies=[Depends(public_reads)])
def creator(username: str, db: Session = Depends(get_db)):
    """A creator's public profile: username, avatar, games, and their approved entries with rank and awards.
    404 unless the creator made the profile public."""
    p = db.execute(select(CreatorProfile).where(CreatorProfile.username_key == username.lower())).scalar_one_or_none()
    if p is None or not p.is_public:
        raise ApiError(404, "not_found", "No such creator.")
    entries = []
    rows = db.execute(select(LeagueEntry, LeagueCompetition).join(
        LeagueCompetition, LeagueCompetition.id == LeagueEntry.competition_id).where(
        LeagueEntry.account_id == p.account_id, LeagueEntry.status == "approved",
        LeagueCompetition.status != "draft").order_by(LeagueCompetition.starts_at.desc())).all()
    for e, c in rows:
        row = next(r for r in league.ranking(db, c) if r.entry.id == e.id)
        entries.append({"competition": {"slug": c.slug, "name": c.name, "phase": league.phase(c)},
                        "platform": e.platform, "video_url": e.url, "game": e.game,
                        "thumb_url": thumb_url(db.get(Clip, e.clip_id)), "rank": row.rank, "views": row.views,
                        "observed_at": iso(row.observed_at), "final_place": e.final_place})
    return {"username": p.username, "avatar": p.avatar, "games": p.games, "entries": entries,
            "awards": [{"competition": x["competition"], "place": x["final_place"]} for x in entries
                       if x["final_place"] is not None]}


@router.get("/v1/league/{slug}/leaderboard", dependencies=[Depends(public_reads)])
def leaderboard(slug: str, limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    """Approved entries by recorded public views, most first; ties go to the earlier submission. Counts are read
    by hand from each video's public page (`views_verified` false) and `updated_at` is the newest reading."""
    c = by_slug(db, slug)
    rows = board_json(db, c, limit)
    newest = max((r["observed_at"] for r in rows if r["observed_at"]), default=None)
    return {"competition": competition_json(db, c), "updated_at": newest, "entries": rows}


@router.get("/v1/league/{slug}/featured", dependencies=[Depends(public_reads)])
def featured(slug: str, db: Session = Depends(get_db)):
    """Up to six approved entries that have a thumbnail, best ranked first. Real entries only."""
    rows = [r for r in board_json(db, by_slug(db, slug)) if r["thumb_url"]][:6]
    return {"clips": rows}


# ---- signed in ----

def my_clips(db: Session, account_id: str) -> list[dict]:
    rows = db.execute(select(Clip).join(Job, Job.id == Clip.job_id).where(
        Job.account_id == account_id, Clip.deleted_at.is_(None)).order_by(Clip.created_at.desc(), Clip.id)
        .limit(60)).scalars()
    return [{"id": c.id, "title": (c.meta or {}).get("title"), "thumb_url": thumb_url(c),
             "duration_sec": round(c.end_sec - c.start_sec, 1), "created_at": iso(c.created_at)} for c in rows]


@router.get("/v1/league/me")
def me(competition: str | None = Query(None, max_length=40), p: Principal = Depends(session_principal),
       db: Session = Depends(get_db)):
    """Everything the entry form needs: your creator profile, the clips you can enter, the competition (the
    current one, or the one whose slug is `competition`), your entry in it with its review status, and the
    attribution line to paste."""
    c = by_slug(db, competition) if competition else league.current(db)
    entry = league.entry_of(db, c.id, p.account.id) if c else None
    return {"email_verified": p.account.email_verified, "profile": profile_json(league.profile_of(db, p.account.id)),
            "avatars": list(league.AVATARS), "clips": my_clips(db, p.account.id),
            "competition": competition_json(db, c) if c else None, "entry": my_entry_json(db, c, entry),
            "attribution": league_rules.attribution(get_settings().public_web_url),
            "rules_version": league_rules.VERSION}


class ProfileBody(BaseModel):
    """Your public creator profile. `is_public` true gives you a profile page; your username, avatar and game
    appear on the leaderboard whenever you have an approved entry."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    username: str = Field(min_length=3, max_length=20)
    avatar: Literal[league.AVATARS] = "lime"
    games: list[str] = Field(default_factory=list, max_length=5)
    is_public: bool = False


@router.put("/v1/league/me/profile")
def put_profile(body: ProfileBody, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Create or change your creator profile. Usernames are unique whatever their case. 409 `username_taken`."""
    rate_limit(f"league:p:{p.account.id}", get_settings().league_profile_edits_per_hour, 3600)
    try:
        username = league.clean_username(body.username)
        games = list(dict.fromkeys(league.clean_game(g) for g in body.games))
    except league.Refused as e:
        raise refuse(e) from None
    taken = db.execute(select(CreatorProfile).where(CreatorProfile.username_key == username.lower())).scalar_one_or_none()
    if taken is not None and taken.account_id != p.account.id:
        raise ApiError(409, "username_taken", "That username is taken. Choose another.")
    profile = league.profile_of(db, p.account.id)
    if profile is None:
        profile = CreatorProfile(id=new_id("cpro"), account_id=p.account.id)
        db.add(profile)
    profile.username, profile.username_key, profile.avatar = username, username.lower(), body.avatar
    profile.games, profile.is_public, profile.updated_at = games, body.is_public, utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "username_taken", "That username is taken. Choose another.") from None
    return profile_json(profile)


class EntryBody(BaseModel):
    """One entry. `attribution_confirmed`: the ClutchClips link is in the video's description. `rules_version`:
    the version of the rules you read and accept (GET /v1/league/rules)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    clip_id: str = Field(min_length=1, max_length=40)
    platform: league.Platform
    url: str = Field(min_length=10, max_length=300)
    game: str | None = Field(default=None, max_length=30)
    attribution_confirmed: bool
    rules_version: str = Field(min_length=1, max_length=32)


@router.post("/v1/league/{slug}/entries", status_code=201)
def submit(slug: str, body: EntryBody, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Enter one of your clips. Free: no plan is needed. Needs a verified email and a creator profile, a clip
    that is yours, a public TikTok video, YouTube Short or Instagram Reel link, the attribution confirmed and
    the current rules accepted. One entry per creator and per video. The entry waits for a person to review it."""
    rate_limit(f"league:s:{p.account.id}", get_settings().league_submits_per_hour, 3600)
    c = by_slug(db, slug)
    try:
        entry = league.submit(db, p.account, c, body.clip_id, body.platform, body.url, body.game,
                              body.attribution_confirmed, body.rules_version)
        db.commit()
    except league.Refused as e:
        db.rollback()
        raise refuse(e) from None
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "already_entered", "You or this video are already entered in this competition.") from None
    return my_entry_json(db, c, entry)


# ---- admins ----

class Prize(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    place: Literal[league.PRIZE_PLACES]
    amount_cents: int = Field(ge=0, le=1_000_000)
    currency: Literal["USD"] = "USD"
    label: str | None = Field(default=None, max_length=60)


class CompetitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=3, max_length=80)
    slug: str = Field(pattern=SLUG)
    starts_at: datetime
    ends_at: datetime
    prizes: list[Prize] = Field(default_factory=list, max_length=3)


class CompetitionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=3, max_length=80)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    prizes: list[Prize] | None = Field(default=None, max_length=3)
    cash_prizes_enabled: bool | None = None


def prizes_json(prizes: list[Prize]) -> list[dict]:
    if len({p.place for p in prizes}) != len(prizes):
        raise ApiError(422, "validation_error", "prizes: one prize per place.")
    return [p.model_dump() for p in sorted(prizes, key=lambda p: p.place)]


def admin_competition_json(db: Session, c: LeagueCompetition) -> dict:
    counts = dict(db.execute(select(LeagueEntry.status, func.count(LeagueEntry.id)).where(
        LeagueEntry.competition_id == c.id).group_by(LeagueEntry.status)).all())
    return {"id": c.id, "slug": c.slug, "name": c.name, "starts_at": iso(c.starts_at), "ends_at": iso(c.ends_at),
            "status": c.status, "phase": league.phase(c), "prizes": c.prizes, "rules_version": c.rules_version,
            "cash_prizes_enabled": c.cash_prizes_enabled,
            "cash_prizes_approved": get_settings().league_cash_prizes_approved,
            "entries": {s: counts.get(s, 0) for s in ("pending", "approved", "rejected", "disqualified")}}


def tracked(c: LeagueCompetition) -> dict:
    return {"name": c.name, "starts_at": iso(c.starts_at), "ends_at": iso(c.ends_at), "prizes": c.prizes,
            "cash_prizes_enabled": c.cash_prizes_enabled}


@router.get("/v1/admin/league/competitions")
def admin_competitions(_admin: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    """Admins only: every competition, drafts included, newest first, with its entry counts."""
    rows = db.execute(select(LeagueCompetition).order_by(LeagueCompetition.starts_at.desc())).scalars()
    return {"competitions": [admin_competition_json(db, c) for c in rows]}


@router.post("/v1/admin/league/competitions", status_code=201)
def create_competition(body: CompetitionBody, admin: Principal = Depends(admin_principal),
                       db: Session = Depends(get_db)):
    """Admins only: create a competition as a draft. It is public once opened. Cash prizes start switched off."""
    starts, ends = league.naive_utc(body.starts_at), league.naive_utc(body.ends_at)
    if ends <= starts:
        raise ApiError(422, "validation_error", "ends_at must be after starts_at.")
    if body.slug in ("creators", "me", "current", "rules"):
        raise ApiError(422, "validation_error", "slug: that word is reserved.")
    if db.execute(select(LeagueCompetition.id).where(LeagueCompetition.slug == body.slug)).first():
        raise ApiError(409, "slug_taken", "A competition already has that slug.")
    c = LeagueCompetition(id=new_id("lcmp"), slug=body.slug, name=body.name, starts_at=starts, ends_at=ends,
                          status="draft", prizes=prizes_json(body.prizes), rules_version=league_rules.VERSION,
                          cash_prizes_enabled=False, created_by=admin.account.id)
    db.add(c)
    league.record(db, admin.account.id, "competition_create", "competition", c.id, c.id, after=tracked(c))
    db.commit()
    return admin_competition_json(db, c)


@router.patch("/v1/admin/league/competitions/{slug}")
def edit_competition(slug: str, body: CompetitionPatch, admin: Principal = Depends(admin_principal),
                     db: Session = Depends(get_db)):
    """Admins only: change the name, dates or prizes, or switch cash prizes on or off. Switching them on is
    refused (409 `cash_prizes_not_approved`) unless the server has LEAGUE_CASH_PRIZES_APPROVED set. A final
    competition cannot be changed."""
    c = by_slug(db, slug, drafts=True)
    if c.status == "finalized":
        raise ApiError(409, "competition_final", "This competition's results are final.")
    before = tracked(c)
    if body.cash_prizes_enabled and not get_settings().league_cash_prizes_approved:
        raise ApiError(409, "cash_prizes_not_approved",
                       "Cash prizes are locked until the official rules are approved (LEAGUE_CASH_PRIZES_APPROVED).")
    if body.name is not None:
        c.name = body.name
    if body.starts_at is not None:
        c.starts_at = league.naive_utc(body.starts_at)
    if body.ends_at is not None:
        c.ends_at = league.naive_utc(body.ends_at)
    if c.ends_at <= c.starts_at:
        raise ApiError(422, "validation_error", "ends_at must be after starts_at.")
    if body.prizes is not None:
        c.prizes = prizes_json(body.prizes)
    if body.cash_prizes_enabled is not None:
        c.cash_prizes_enabled = body.cash_prizes_enabled
    c.updated_at = utcnow()
    league.record(db, admin.account.id, "competition_edit", "competition", c.id, c.id, before, tracked(c))
    db.commit()
    return admin_competition_json(db, c)


@router.delete("/v1/admin/league/competitions/{slug}")
def delete_competition(slug: str, admin: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    """Admins only: delete a draft. A competition that was ever opened is kept."""
    c = by_slug(db, slug, drafts=True)
    if c.status != "draft":
        raise ApiError(409, "status_not_allowed", "Only a draft can be deleted.")
    league.record(db, admin.account.id, "competition_delete", "competition", c.id, c.id, before=tracked(c))
    db.delete(c)
    db.commit()
    return {"deleted": True}


class StatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: league.CompetitionAction


@router.post("/v1/admin/league/competitions/{slug}/status")
def competition_status(slug: str, body: StatusBody, admin: Principal = Depends(admin_principal),
                       db: Session = Depends(get_db)):
    """Admins only: open (draft to public), close (stop entries, start winner review), reopen, or finalize
    (needs every provisional winner approved). 409 when the status does not allow the action."""
    c = by_slug(db, slug, drafts=True)
    try:
        league.move_competition(db, admin.account.id, c, body.action)
    except league.Refused as e:
        db.rollback()
        raise refuse(e) from None
    db.commit()
    return admin_competition_json(db, c)


def admin_entry_json(db: Session, e: LeagueEntry, rank: league.Ranked | None) -> dict:
    account, profile = db.get(Account, e.account_id), league.profile_of(db, e.account_id)
    seen = db.execute(select(LeagueViewObservation).where(LeagueViewObservation.entry_id == e.id)
                      .order_by(LeagueViewObservation.id.desc()).limit(20)).scalars()
    return {"id": e.id, "status": e.status, "status_reason": e.status_reason, "flagged": e.flagged,
            "flag_reason": e.flag_reason, "platform": e.platform, "video_url": e.url, "game": e.game,
            "clip_id": e.clip_id, "thumb_url": thumb_url(db.get(Clip, e.clip_id)), "snapshot": e.snapshot,
            "username": profile.username if profile else None, "email": account.email if account else None,
            "account_id": e.account_id, "submitted_at": iso(e.submitted_at),
            "attribution_confirmed_at": iso(e.attribution_confirmed_at), "rules_version": e.rules_version,
            "rank": rank.rank if rank else None, "views": rank.views if rank else None,
            "final_place": e.final_place, "winner_approved_at": iso(e.winner_approved_at),
            "prize_status": e.prize_status,
            "observations": [{"views": o.views, "source": o.source, "verified": o.verified,
                              "observed_at": iso(o.observed_at), "observed_by": o.observed_by} for o in seen]}


def entry_or_404(db: Session, entry_id: str) -> LeagueEntry:
    e = db.execute(select(LeagueEntry).where(LeagueEntry.id == entry_id).with_for_update()).scalar_one_or_none()
    if e is None:
        raise ApiError(404, "not_found", "No such entry.")
    return e


def one_entry(db: Session, e: LeagueEntry) -> dict:
    c = db.get(LeagueCompetition, e.competition_id)
    return admin_entry_json(db, e, next((r for r in league.ranking(db, c) if r.entry.id == e.id), None))


@router.get("/v1/admin/league/competitions/{slug}/entries")
def admin_entries(slug: str, status: league.EntryStatus | None = None, _admin: Principal = Depends(admin_principal),
                  db: Session = Depends(get_db)):
    """Admins only: a competition's entries with the creator's email, flags, the clip's snapshot and every
    recorded view count. Approved entries first in ranking order, then the rest, oldest first."""
    c = by_slug(db, slug, drafts=True)
    ranks = {r.entry.id: r for r in league.ranking(db, c)}
    where = [LeagueEntry.competition_id == c.id] + ([LeagueEntry.status == status] if status else [])
    rows = list(db.execute(select(LeagueEntry).where(*where).order_by(LeagueEntry.submitted_at, LeagueEntry.id)).scalars())
    rows.sort(key=lambda e: (e.id not in ranks, ranks[e.id].rank if e.id in ranks else 0))
    return {"competition": admin_competition_json(db, c), "entries": [admin_entry_json(db, e, ranks.get(e.id)) for e in rows]}


class ReviewBody(BaseModel):
    """approve, reject or disqualify (the last two need `reason`, which the creator sees); flag or unflag marks
    an entry as suspicious for other admins (`reason` stays private)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject", "disqualify", "flag", "unflag"]
    reason: str | None = Field(default=None, max_length=500)


def admin_move(db: Session, entry_id: str, move) -> dict:
    e = entry_or_404(db, entry_id)
    try:
        move(e)
    except league.Refused as err:
        db.rollback()
        raise refuse(err) from None
    db.commit()
    return one_entry(db, e)


@router.post("/v1/admin/league/entries/{entry_id}/review")
def review_entry(entry_id: str, body: ReviewBody, admin: Principal = Depends(admin_principal),
                 db: Session = Depends(get_db)):
    """Admins only: approve, reject, disqualify, flag or unflag an entry. Each move is one audit event."""
    def move(e: LeagueEntry) -> None:
        if body.action in ("flag", "unflag"):
            league.flag(db, admin.account.id, e, body.action == "flag", body.reason)
        else:
            league.review(db, admin.account.id, e, body.action, body.reason)
    return admin_move(db, entry_id, move)


class ObservationBody(BaseModel):
    """A view count read from the video's public page. Stored as unverified with who read it and when."""
    model_config = ConfigDict(extra="forbid")
    views: int = Field(ge=0, le=100_000_000_000)
    source: league.ObservationSource = "public_page"
    observed_at: datetime | None = None


@router.post("/v1/admin/league/entries/{entry_id}/observations", status_code=201)
def record_views(entry_id: str, body: ObservationBody, admin: Principal = Depends(admin_principal),
                 db: Session = Depends(get_db)):
    """Admins only: record the view count of an approved entry. Counts are appended, never changed: the newest
    is the one the ranking uses."""
    when = league.naive_utc(body.observed_at) if body.observed_at else None
    return admin_move(db, entry_id, lambda e: league.observe(db, admin.account.id, e, body.views, body.source, when))


@router.get("/v1/admin/league/competitions/{slug}/winners")
def winners(slug: str, _admin: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    """Admins only: the top three of the ranking. `state` is provisional until an admin approves the place."""
    c = by_slug(db, slug, drafts=True)
    top = league.ranking(db, c)[:len(league.PRIZE_PLACES)]
    return {"competition": admin_competition_json(db, c),
            "winners": [{**admin_entry_json(db, r.entry, r), "place": r.rank,
                         "state": "final" if r.entry.final_place is not None else "provisional",
                         "prize": next((p for p in c.prizes if p["place"] == r.rank), None)} for r in top]}


class WinnerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place: Literal[league.PRIZE_PLACES]


@router.post("/v1/admin/league/entries/{entry_id}/winner")
def approve_winner(entry_id: str, body: WinnerBody, admin: Principal = Depends(admin_principal),
                   db: Session = Depends(get_db)):
    """Admins only: approve a provisional winner at the place the ranking gives it, first place first. The
    competition must be closed. Sets the prize to pending; nothing is paid."""
    return admin_move(db, entry_id, lambda e: league.approve_winner(db, admin.account.id, e, body.place))


class PrizeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["sent", "forfeited"]
    note: str = Field(min_length=3, max_length=500)


@router.post("/v1/admin/league/entries/{entry_id}/prize")
def prize_status(entry_id: str, body: PrizeBody, admin: Principal = Depends(admin_principal),
                 db: Session = Depends(get_db)):
    """Admins only: record that an approved winner's prize was sent by hand, or forfeited. A record only: this
    API moves no money."""
    return admin_move(db, entry_id, lambda e: league.set_prize(db, admin.account.id, e, body.status, body.note))


@router.get("/v1/admin/league/events")
def events(competition: str | None = Query(None, max_length=40), limit: int = Query(100, ge=1, le=500),
           offset: int = Query(0, ge=0), _admin: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    """Admins only: the league's audit log, newest first: who did what to which entry or competition, the state
    before and after, and the reason. `competition` is a slug."""
    where = [LeagueEvent.competition_id == by_slug(db, competition, drafts=True).id] if competition else []
    rows = db.execute(select(LeagueEvent).where(*where).order_by(LeagueEvent.id.desc()).limit(limit).offset(offset)).scalars()
    return {"events": [{"id": ev.id, "action": ev.action, "entity_kind": ev.entity_kind, "entity_id": ev.entity_id,
                        "actor_id": ev.actor_id, "before": ev.before, "after": ev.after, "reason": ev.reason,
                        "created_at": iso(ev.created_at)} for ev in rows]}
