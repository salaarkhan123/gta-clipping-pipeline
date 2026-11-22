"""Creators League: the data shapes, the two state machines and the ranking. No web code here.

Entry status      pending -> approved | rejected | disqualified
                  approved -> rejected | disqualified          rejected -> approved
                  disqualified is final. Once a winner is approved no entry can be approved, and only entries
                  ranked below the approved places can still be rejected or disqualified.
Competition       draft -> open -> closed -> finalized         closed -> open (reopened)
Prize             pending -> sent | forfeited                  (recorded by an admin; nothing is paid by this code)

Every move is one row in league_events with the state before and after, who and why. View counts come only from
admin observations (league_view_observations, append-only): the newest row per entry is the count the ranking
uses, the older rows are its history.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import templates
from .models import (Account, Clip, CreatorProfile, Job, LeagueCompetition, LeagueEntry, LeagueEvent,
                     LeagueViewObservation, new_id, utcnow)

Platform = Literal["tiktok", "youtube", "instagram"]
EntryStatus = Literal["pending", "approved", "rejected", "disqualified"]
EntryAction = Literal["approve", "reject", "disqualify"]
CompetitionStatus = Literal["draft", "open", "closed", "finalized"]
CompetitionAction = Literal["open", "close", "reopen", "finalize"]
PrizeStatus = Literal["pending", "sent", "forfeited"]
ObservationSource = Literal["public_page"]          # read by an admin off the video's public page

# action: (statuses it is allowed from, status after, a reason is required)
ENTRY_RULES: dict[str, tuple[tuple[str, ...], str, bool]] = {
    "approve": (("pending", "rejected"), "approved", False),
    "reject": (("pending", "approved"), "rejected", True),
    "disqualify": (("pending", "approved"), "disqualified", True),
}
COMPETITION_RULES: dict[str, tuple[tuple[str, ...], str]] = {
    "open": (("draft",), "open"),
    "close": (("open",), "closed"),
    "reopen": (("closed",), "open"),
    "finalize": (("closed",), "finalized"),
}
PRIZE_RULES: dict[str, tuple[str, ...]] = {"sent": ("pending",), "forfeited": ("pending",)}
PRIZE_PLACES = (1, 2, 3)
AVATARS = ("lime", "violet", "sky", "amber", "rose", "slate")
USERNAME = re.compile(r"[A-Za-z0-9_]{3,20}")
GAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 :'&.+-]{1,29}")
RESERVED_USERNAMES = frozenset({"admin", "administrator", "clutchclips", "clutch_clips", "official", "support",
                                "staff", "moderator", "system", "league", "winner"})


class Refused(Exception):
    """A rule of the league said no. `status` is the HTTP status the API answers with."""
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---- submitted video links: matched against fixed patterns, never fetched ----

@dataclass(frozen=True)
class VideoLink:
    platform: str
    url: str       # the canonical link, rebuilt from the matched parts: the only form stored or shown
    key: str       # platform:video id, the same for every spelling of one video


_HOSTS = {
    "tiktok": ("www.tiktok.com", "tiktok.com", "m.tiktok.com"),
    "youtube": ("www.youtube.com", "youtube.com", "m.youtube.com"),
    "instagram": ("www.instagram.com", "instagram.com"),
}
_PATHS = {
    "tiktok": re.compile(r"/@(?P<user>[A-Za-z0-9._]{2,24})/video/(?P<id>[0-9]{8,24})/?"),
    "youtube": re.compile(r"/shorts/(?P<id>[A-Za-z0-9_-]{11})/?"),
    "instagram": re.compile(r"/reels?/(?P<id>[A-Za-z0-9_-]{5,24})/?"),
}
_NAMES = {"tiktok": "TikTok video", "youtube": "YouTube Short", "instagram": "Instagram Reel"}
_EXAMPLES = {"tiktok": "https://www.tiktok.com/@name/video/1234567890123456789",
             "youtube": "https://www.youtube.com/shorts/AbCdEfGhIjK",
             "instagram": "https://www.instagram.com/reel/AbCdEfGhIjK/"}


def parse_video_link(platform: str, raw: str) -> VideoLink:
    """The canonical link of a public TikTok video, YouTube Short or Instagram Reel, or Refused. Only the text is
    examined: https, one of the platform's own hosts exactly, no port and no user info, and a path of the
    platform's video shape. Short links (vm.tiktok.com, youtu.be) are refused because reading them means
    following a redirect, and this code requests nothing from a submitted link."""
    bad = Refused(422, "invalid_video_url",
                  f"That is not a public {_NAMES[platform]} link. Paste the full link, like {_EXAMPLES[platform]}")
    if len(raw) > 300 or not raw.isascii() or any(c.isspace() or ord(c) < 0x21 or c in "\\\x7f" for c in raw):
        raise bad
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise bad from None
    if parts.scheme != "https" or port is not None or parts.username is not None or parts.password is not None:
        raise bad
    if parts.netloc.lower() not in _HOSTS[platform]:         # netloc, not hostname: nothing but the bare host
        raise bad
    m = _PATHS[platform].fullmatch(parts.path)
    if not m:
        raise bad
    vid = m["id"]
    url = {"tiktok": lambda: f"https://www.tiktok.com/@{m['user']}/video/{vid}",
           "youtube": lambda: f"https://www.youtube.com/shorts/{vid}",
           "instagram": lambda: f"https://www.instagram.com/reel/{vid}/"}[platform]()
    return VideoLink(platform, url, f"{platform}:{vid}")


# ---- creator-supplied text ----

def clean_username(raw: str) -> str:
    if not USERNAME.fullmatch(raw):
        raise Refused(422, "invalid_username", "A username is 3 to 20 letters, numbers or underscores.")
    if raw.lower() in RESERVED_USERNAMES:
        raise Refused(422, "username_reserved", "That username is reserved. Choose another.")
    return raw


def clean_game(raw: str) -> str:
    text = " ".join(raw.split())
    if not GAME.fullmatch(text):
        raise Refused(422, "invalid_game", "A game name is 2 to 30 letters, numbers, spaces or : ' & . + -")
    return text


# ---- time ----

def naive_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)


def phase(c: LeagueCompetition, now: datetime | None = None) -> str:
    """What the public sees: upcoming | live | ended (counting, winners provisional) | final."""
    now = now or utcnow()
    if c.status == "finalized":
        return "final"
    if c.status == "closed" or now >= c.ends_at:
        return "ended"
    return "live" if now >= c.starts_at else "upcoming"


def accepting(c: LeagueCompetition, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return c.status == "open" and c.starts_at <= now < c.ends_at


# ---- audit ----

def record(db: Session, actor_id: str, action: str, entity_kind: str, entity_id: str,
           competition_id: str | None, before: dict | None = None, after: dict | None = None,
           reason: str | None = None) -> None:
    db.add(LeagueEvent(competition_id=competition_id, actor_id=actor_id, action=action, entity_kind=entity_kind,
                       entity_id=entity_id, before=before, after=after, reason=reason))


# ---- submissions ----

def snapshot_of(clip: Clip, job: Job, link: VideoLink, now: datetime) -> dict:
    """The clip's facts at submission, kept for later analysis of what performs. No customer content: no title,
    no transcript, no file."""
    options = job.options or {}
    template = options.get("template")
    game = templates.TEMPLATES.get(template, {}).get("game") if template else None
    return {"game": game, "duration_sec": round(clip.end_sec - clip.start_sec, 2), "template": template,
            "caption_style": options.get("caption_style"), "captions": options.get("captions"),
            "aspect": options.get("aspect"), "kind": clip.kind, "platform": link.platform,
            "submitted_on": now.date().isoformat()}


def submit(db: Session, account: Account, competition: LeagueCompetition, clip_id: str, platform: str, raw_url: str,
           game: str | None, attribution_confirmed: bool, rules_version: str) -> LeagueEntry:
    """Enter the account's clip into the competition, or Refused. Entry is free: no plan and no credits are
    looked at. The caller commits; the two unique constraints catch a race the checks here missed."""
    now = utcnow()
    if not account.email_verified:
        raise Refused(403, "email_not_verified", "Verify your email address before you enter.")
    if not accepting(competition, now):
        raise Refused(409, "competition_closed", "This competition is not accepting entries.")
    profile = profile_of(db, account.id)
    if profile is None:
        raise Refused(409, "profile_required", "Choose a creator username before you enter.")
    if not attribution_confirmed:
        raise Refused(422, "attribution_required", "Confirm that the ClutchClips link is in your video's description.")
    if rules_version != competition.rules_version:
        raise Refused(422, "rules_not_accepted", "Read and accept the current competition rules.")
    link = parse_video_link(platform, raw_url)
    clip = db.get(Clip, clip_id)
    job = db.get(Job, clip.job_id) if clip else None
    if clip is None or clip.deleted_at or job is None or job.account_id != account.id:
        raise Refused(404, "not_found", "No such clip.")
    if entry_of(db, competition.id, account.id) is not None:
        raise Refused(409, "already_entered", "You have already entered this competition. One clip per creator.")
    if db.execute(select(LeagueEntry.id).where(LeagueEntry.competition_id == competition.id,
                                               LeagueEntry.url_key == link.key)).first():
        raise Refused(409, "duplicate_video", "That video has already been entered in this competition.")
    snap = snapshot_of(clip, job, link, now)
    entry = LeagueEntry(id=new_id("lent"), competition_id=competition.id, account_id=account.id, clip_id=clip.id,
                        platform=link.platform, url=link.url, url_key=link.key,
                        game=clean_game(game) if game else templates.GAME_NAMES.get(snap["game"] or ""),
                        status="pending", attribution_confirmed_at=now, rules_version=rules_version, snapshot=snap,
                        submitted_at=now, updated_at=now)
    db.add(entry)
    record(db, account.id, "submit", "entry", entry.id, competition.id, after={"status": "pending", "url": link.url})
    return entry


def profile_of(db: Session, account_id: str) -> CreatorProfile | None:
    return db.execute(select(CreatorProfile).where(CreatorProfile.account_id == account_id)).scalar_one_or_none()


def entry_of(db: Session, competition_id: str, account_id: str) -> LeagueEntry | None:
    return db.execute(select(LeagueEntry).where(LeagueEntry.competition_id == competition_id,
                                                LeagueEntry.account_id == account_id)).scalar_one_or_none()


# ---- admin moves ----

def review(db: Session, admin_id: str, entry: LeagueEntry, action: str, reason: str | None) -> None:
    allowed, after, needs_reason = ENTRY_RULES[action]
    if entry.status not in allowed:
        raise Refused(409, "review_not_allowed", f"An entry that is {entry.status} cannot be moved by '{action}'.")
    if needs_reason and not reason:
        raise Refused(422, "reason_required", f"Give the reason for '{action}': the creator sees it.")
    settled = settled_places(db, entry.competition_id)
    if settled:
        if action == "approve":         # a late approval would enter the ranking, perhaps above an approved winner
            raise Refused(409, "winners_approved", "A winner is already approved: no entry can join the ranking now.")
        c = db.get(LeagueCompetition, entry.competition_id)
        row = next((r for r in ranking(db, c) if r.entry.id == entry.id), None)
        if row is not None and row.rank <= settled:
            raise Refused(409, "winner_already_approved",
                          "A winner is approved at or below this entry's place: its status is settled.")
    before = entry.status
    entry.status, entry.status_reason, entry.updated_at = after, reason, utcnow()
    record(db, admin_id, action, "entry", entry.id, entry.competition_id, {"status": before}, {"status": after}, reason)


def flag(db: Session, admin_id: str, entry: LeagueEntry, flagged: bool, reason: str | None) -> None:
    if flagged and not reason:
        raise Refused(422, "reason_required", "Say what looks suspicious.")
    before = {"flagged": entry.flagged}
    entry.flagged, entry.flag_reason, entry.updated_at = flagged, reason if flagged else None, utcnow()
    record(db, admin_id, "flag" if flagged else "unflag", "entry", entry.id, entry.competition_id, before,
           {"flagged": flagged}, reason)


def observe(db: Session, admin_id: str, entry: LeagueEntry, views: int, source: str,
            observed_at: datetime | None) -> LeagueViewObservation:
    """Record what an admin read off the video's public page. Unverified: nobody but a person looked."""
    if entry.status != "approved":
        raise Refused(409, "entry_not_approved", "Views are recorded for approved entries only.")
    competition = db.get(LeagueCompetition, entry.competition_id)
    if competition.status == "finalized":
        raise Refused(409, "competition_final", "This competition's results are final.")
    if settled_places(db, competition.id):
        raise Refused(409, "winners_approved", "A winner is already approved: the counts are settled.")
    now = utcnow()
    if observed_at and observed_at > now:
        raise Refused(422, "observed_in_future", "The observation time is in the future.")
    before = latest_views(db, [entry.id]).get(entry.id)
    obs = LeagueViewObservation(entry_id=entry.id, views=views, source=source, verified=False, observed_by=admin_id,
                                observed_at=observed_at or now)
    db.add(obs)
    record(db, admin_id, "observe_views", "entry", entry.id, entry.competition_id,
           {"views": before.views if before else None}, {"views": views, "source": source})
    return obs


def move_competition(db: Session, admin_id: str, c: LeagueCompetition, action: str) -> None:
    allowed, after = COMPETITION_RULES[action]
    if c.status not in allowed:
        raise Refused(409, "status_not_allowed", f"A competition that is {c.status} cannot be moved by '{action}'.")
    if action == "reopen" and settled_places(db, c.id):
        raise Refused(409, "winners_approved", "A winner is already approved: entries cannot be reopened.")
    if action == "finalize":
        board = ranking(db, c)
        owed = [r.rank for r in board[:len(PRIZE_PLACES)] if r.views is not None and r.entry.final_place is None]
        if owed:
            raise Refused(409, "winners_not_approved",
                          "Approve each provisional winner before the results are made final.")
    before = c.status
    c.status, c.updated_at = after, utcnow()
    record(db, admin_id, f"competition_{action}", "competition", c.id, c.id, {"status": before}, {"status": after})


def approve_winner(db: Session, admin_id: str, entry: LeagueEntry, place: int) -> None:
    """Make a provisional winner final. Only for a closed competition, and only at the place the ranking gives
    the entry: to change who wins, disqualify an entry (with its reason) or record a newer view count."""
    c = db.get(LeagueCompetition, entry.competition_id)
    if c.status != "closed":
        raise Refused(409, "competition_not_closed", "Close the competition before approving winners.")
    if entry.final_place is not None:
        raise Refused(409, "winner_already_approved", "This winner is already approved.")
    row = next((r for r in ranking(db, c) if r.entry.id == entry.id), None)
    if row is None or row.views is None or place not in PRIZE_PLACES or row.rank != place:
        raise Refused(409, "not_provisional_winner", "This entry does not hold that place in the current ranking.")
    if place != settled_places(db, c.id) + 1:
        raise Refused(409, "approve_in_order", "Approve the winners in order: first place first.")
    entry.final_place, entry.winner_approved_at, entry.prize_status = place, utcnow(), "pending"
    entry.updated_at = entry.winner_approved_at
    record(db, admin_id, "approve_winner", "entry", entry.id, c.id, {"final_place": None},
           {"final_place": place, "views": row.views, "prize_status": "pending"})


def settled_places(db: Session, competition_id: str) -> int:
    """How many places have an approved winner (they are approved in order, so also the lowest settled place)."""
    return db.execute(select(func.count(LeagueEntry.id)).where(LeagueEntry.competition_id == competition_id,
                                                               LeagueEntry.final_place.is_not(None))).scalar_one()


def set_prize(db: Session, admin_id: str, entry: LeagueEntry, status: str, note: str | None) -> None:
    if entry.final_place is None or entry.prize_status not in PRIZE_RULES[status]:
        raise Refused(409, "prize_not_allowed", "Only an approved winner's pending prize can be marked.")
    if not note:
        raise Refused(422, "reason_required", "Add a note: how the prize was sent, or why it was forfeited.")
    before = entry.prize_status
    entry.prize_status, entry.updated_at = status, utcnow()
    record(db, admin_id, "prize_status", "entry", entry.id, entry.competition_id, {"prize_status": before},
           {"prize_status": status}, note)


# ---- ranking ----

@dataclass(frozen=True)
class Ranked:
    rank: int
    entry: LeagueEntry
    views: int | None                 # None: no count recorded yet
    observed_at: datetime | None
    source: str | None
    verified: bool


def latest_views(db: Session, entry_ids: list[str]) -> dict[str, LeagueViewObservation]:
    """The newest observation of each entry: the last one recorded."""
    if not entry_ids:
        return {}
    newest = (select(func.max(LeagueViewObservation.id)).where(LeagueViewObservation.entry_id.in_(entry_ids))
              .group_by(LeagueViewObservation.entry_id))
    rows = db.execute(select(LeagueViewObservation).where(LeagueViewObservation.id.in_(newest))).scalars()
    return {o.entry_id: o for o in rows}


def ranking(db: Session, c: LeagueCompetition) -> list[Ranked]:
    """Approved entries, most views first. Ties: the earlier submission, then the entry id. Entries with no
    count yet come last, in the same tie order. Every entry gets its own rank: no shared places."""
    entries = list(db.execute(select(LeagueEntry).where(LeagueEntry.competition_id == c.id,
                                                        LeagueEntry.status == "approved")).scalars())
    seen = latest_views(db, [e.id for e in entries])

    def order(e: LeagueEntry):
        o = seen.get(e.id)
        return (o is None, -(o.views if o else 0), e.submitted_at, e.id)
    out = []
    for i, e in enumerate(sorted(entries, key=order), start=1):
        o = seen.get(e.id)
        out.append(Ranked(i, e, o.views if o else None, o.observed_at if o else None, o.source if o else None,
                          bool(o.verified) if o else False))
    return out


def current(db: Session, now: datetime | None = None) -> LeagueCompetition | None:
    """The competition the public page is about: the one running now, else the next to start, else the last to
    end. Drafts are never public."""
    now = now or utcnow()
    rows = list(db.execute(select(LeagueCompetition).where(LeagueCompetition.status != "draft")).scalars())
    live = [c for c in rows if c.starts_at <= now < c.ends_at and c.status == "open"]
    if live:
        return max(live, key=lambda c: c.starts_at)
    upcoming = [c for c in rows if c.starts_at > now and c.status == "open"]
    if upcoming:
        return min(upcoming, key=lambda c: c.starts_at)
    return max(rows, key=lambda c: c.ends_at, default=None)
