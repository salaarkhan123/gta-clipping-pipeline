"""What an admin can decide on a copyright or likeness case, and what each decision does to the content.

Every decision appends exactly one CaseEvent (plus a `strike` or `account_suspended` event when the repeat-infringer
rule acts). Content is never deleted on a report alone:

- `disable` hides the reported content (the same `deleted_at` mark every listing and signed-link route already
  skips) and keeps its files, so `restore` can bring it back. Links handed out before stay valid until they expire
  (SIGNED_URL_TTL_SEC).
- `remove` is the verified decision: the content stays hidden and each owner gets a strike.
- `delete_content` removes the files of removed content. It is its own decision, logged like the others.

Strikes (owner, 2026-11-18): a strike comes only from a `remove` that was not later withdrawn (`withdraw`) or
successfully countered (`restore` after a counter-notice). REPEAT_INFRINGER_STRIKES strikes suspend the account.
`terminate` suspends an account at once for a serious violation.
"""
from collections import defaultdict
from datetime import timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger
from .config import get_settings
from .models import Account, CaseEvent, CaseTarget, Clip, Export, Job, TrustCase, Upload, utcnow
from .storage import get_storage, transcript_key, transcript_parts_key, vindex_key
from .thumbnail_jobs import thumbnail_keys
from .thumbnails import frame_key_of

Action = Literal["review", "request_info", "forward_notice", "disable", "remove", "reject", "withdraw", "restore",
                 "delete_content", "terminate", "note", "close"]
OPEN = ("received", "in_review", "info_requested")
# action: (statuses it may be taken from, status after; None = unchanged)
RULES: dict[str, tuple[tuple[str, ...], str | None]] = {
    "review": (("received", "info_requested"), "in_review"),
    "request_info": (OPEN, "info_requested"),
    "forward_notice": ((*OPEN, "disabled", "removed"), None),
    "disable": (OPEN, "disabled"),
    "remove": ((*OPEN, "disabled"), "removed"),
    "reject": ((*OPEN, "disabled"), "rejected"),
    "withdraw": ((*OPEN, "disabled", "removed", "counter_noticed"), "withdrawn"),
    "restore": (("disabled", "removed", "counter_noticed"), "restored"),
    "delete_content": (("removed",), None),
    "terminate": ((*OPEN, "disabled", "removed", "counter_noticed"), None),
    "note": (("received", "in_review", "info_requested", "disabled", "removed", "rejected", "withdrawn",
              "restored", "counter_noticed", "closed"), None),
    "close": (("removed", "rejected", "withdrawn", "restored"), "closed"),
}
TAKEN_DOWN = ("taken_down", "This video was disabled after a copyright or likeness report. Any credits held for "
                            "this job were returned.")


class Refused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def targets(db: Session, case: TrustCase) -> list[CaseTarget]:
    return list(db.execute(select(CaseTarget).where(CaseTarget.case_id == case.id).order_by(CaseTarget.id)).scalars())


def _event(db: Session, case: TrustCase, actor_kind: str, actor_id: str | None, action: str,
           note: str | None = None, data: dict | None = None) -> CaseEvent:
    ev = CaseEvent(case_id=case.id, actor_kind=actor_kind, actor_id=actor_id, action=action, note=note, data=data,
                   created_at=utcnow())
    db.add(ev)
    return ev


def _clip_target(db: Session, case: TrustCase, clip: Clip, owner: str) -> CaseTarget:
    t = db.execute(select(CaseTarget).where(CaseTarget.case_id == case.id, CaseTarget.kind == "clip",
                                            CaseTarget.target_id == clip.id)).scalar_one_or_none()
    if t is None:
        t = CaseTarget(case_id=case.id, kind="clip", target_id=clip.id, account_id=owner, created_at=utcnow())
        db.add(t)
        db.flush()
    return t


def _stop_jobs(db: Session, upload_id: str) -> None:
    """Jobs on a hidden upload: waiting ones are cancelled and refunded, running ones are told to stop."""
    for job in db.execute(select(Job).where(Job.upload_id == upload_id, Job.status.in_(("QUEUED", "RUNNING")))
                          .with_for_update()).scalars():
        if job.status == "QUEUED":
            job.status, job.finished_at = "CANCELED", utcnow()
            job.error_code, job.error_message = TAKEN_DOWN
            if job.credits_reserved:
                ledger.settle(db, job, success=False)
        else:
            job.cancel_requested = True


HELD = ("disabled", "deleted")        # a target in one of these states keeps its content hidden


def held_elsewhere(db: Session, case: TrustCase, kind: str, target_id: str) -> bool:
    """Whether another case's decision is keeping this upload or clip hidden. Restoring one case must not bring
    back content that another case removed."""
    return db.execute(select(CaseTarget.id).where(CaseTarget.kind == kind, CaseTarget.target_id == target_id,
                                                  CaseTarget.case_id != case.id, CaseTarget.state.in_(HELD))
                      .limit(1)).first() is not None


def hide(db: Session, case: TrustCase) -> int:
    """Hide every live target (an upload's clips and a job's clips with it). Returns how many rows were hidden.
    A clip another case already hides is held by this case too (state disabled), so it stays hidden until every
    case holding it is restored; a clip its owner deleted is `gone`."""
    now, hidden = utcnow(), 0
    for t in [t for t in targets(db, case) if t.state == "live"]:
        found: list[Clip] = []
        if t.kind == "upload":
            up = db.get(Upload, t.target_id)
            if up is not None and up.deleted_at is None:
                up.deleted_at = now
                hidden += 1
                _stop_jobs(db, up.id)
            job_ids = select(Job.id).where(Job.upload_id == t.target_id)
            found = list(db.execute(select(Clip).where(Clip.job_id.in_(job_ids))).scalars())
        elif t.kind == "job":
            found = list(db.execute(select(Clip).where(Clip.job_id == t.target_id)).scalars())
        elif t.kind in ("clip", "export"):
            clip_id = t.target_id if t.kind == "clip" else getattr(db.get(Export, t.target_id), "clip_id", None)
            clip = db.get(Clip, clip_id) if clip_id else None
            found = [clip] if clip is not None else []
        clips = [c for c in found if c.deleted_at is None or held_elsewhere(db, case, "clip", c.id)]
        t.state = "disabled" if (clips or t.kind == "upload") else "gone"
        for clip in clips:
            if clip.deleted_at is None:
                clip.deleted_at = now
                hidden += 1
            if clip.id != t.target_id:
                _clip_target(db, case, clip, t.account_id).state = "disabled"
    db.flush()
    return hidden


def unhide(db: Session, case: TrustCase) -> int:
    """Bring back what this case hid, unless its retention ran out, its files are gone, or another case still
    holds it (held_elsewhere: this case lets go, the content stays hidden until that case does too)."""
    now, storage, shown = utcnow(), get_storage(), 0
    for t in [t for t in targets(db, case) if t.state == "disabled"]:
        if t.kind == "upload":
            up = db.get(Upload, t.target_id)
            ok = up is not None and up.expires_at > now and storage.exists(up.storage_key)
            if ok and not held_elsewhere(db, case, "upload", up.id):
                up.deleted_at = None
        elif t.kind == "clip":
            clip = db.get(Clip, t.target_id)
            job = db.get(Job, clip.job_id) if clip else None
            ok = clip is not None and job.expires_at > now and storage.exists(clip.video_key)
            if ok and not held_elsewhere(db, case, "clip", clip.id):
                clip.deleted_at = None
        else:
            ok = True                   # a job or export target: its clips are targets of their own
        t.state = "restored" if ok else "expired"
        shown += ok
    db.flush()
    return shown


def delete_files(db: Session, case: TrustCase) -> list[str]:
    """Remove the stored files of every disabled target. Returns the keys removed."""
    storage, keys = get_storage(), []
    for t in [t for t in targets(db, case) if t.state == "disabled"]:
        if t.kind == "upload":
            up = db.get(Upload, t.target_id)
            if up is not None:
                keys += [k for k in (up.storage_key, transcript_key(up.id), transcript_parts_key(up.id),
                                     vindex_key(up.id)) if k]
        elif t.kind == "clip":
            clip = db.get(Clip, t.target_id)
            if clip is not None:
                # Every image of the clip too: the thumbnail's clean frame (#138) and its gallery (#140), as the
                # import takedown (app/ingest/takedown.py) removes them. The expiry sweep skips taken-down clips.
                keys += [k for k in (clip.video_key, clip.thumb_key, clip.captions_key, clip.preview_key,
                                     clip.export_key, frame_key_of(clip.features)) if k]
                keys += thumbnail_keys(db, [clip.id])
                for ex in db.execute(select(Export).where(Export.clip_id == clip.id,
                                                          Export.storage_key.is_not(None))).scalars():
                    keys.append(ex.storage_key)
                    ex.storage_key = None
        t.state = "deleted"
    keys = list(dict.fromkeys(keys))
    for key in keys:
        storage.delete(key)
    db.flush()
    return keys


def strikes(db: Session, account_id: str) -> int:
    """Standing strikes: `strike` events against the account not cancelled by a `strike_cancelled` on the same
    case, within REPEAT_INFRINGER_STRIKE_DAYS (0 = strikes never expire)."""
    s = get_settings()
    q = select(CaseEvent).where(CaseEvent.action.in_(("strike", "strike_cancelled")))
    if s.repeat_infringer_strike_days > 0:
        q = q.where(CaseEvent.created_at >= utcnow() - timedelta(days=s.repeat_infringer_strike_days))
    standing: dict[str, int] = defaultdict(int)
    for ev in db.execute(q).scalars():
        if (ev.data or {}).get("account_id") == account_id:
            standing[ev.case_id] += 1 if ev.action == "strike" else -1
    return sum(1 for n in standing.values() if n > 0)


def _suspend(db: Session, case: TrustCase, account_id: str, actor_kind: str, actor_id: str | None, why: str) -> bool:
    acct = db.get(Account, account_id)
    if acct is None or acct.status != "active":
        return False
    acct.status = "suspended"
    _event(db, case, actor_kind, actor_id, "account_suspended", why, {"account_id": account_id})
    return True


def owners(db: Session, case: TrustCase) -> list[str]:
    return sorted({t.account_id for t in targets(db, case)})


def decide(db: Session, case: TrustCase, admin_id: str, action: str, note: str | None, message: str | None,
           account_id: str | None = None) -> CaseEvent:
    """Apply one admin decision. Raises Refused when the case's status does not allow it. Caller commits and
    sends the emails (routes_trust)."""
    allowed, after = RULES[action]
    if case.status not in allowed:
        raise Refused("decision_not_allowed", f"A case that is {case.status} cannot be given '{action}'.")
    data: dict = {}
    if action == "request_info" and not message:
        raise Refused("message_required", "request_info needs a message for the claimant.")
    if action in ("disable", "remove") and case.status != "disabled":
        if not any(t.state == "live" for t in targets(db, case)):
            if action == "disable":
                raise Refused("nothing_to_disable", "No reported content is live: add targets or reject the case.")
        data["hidden"] = hide(db, case)
    if action in ("reject", "withdraw", "restore"):
        data["restored"] = unhide(db, case)
    if action == "delete_content":
        data["deleted_files"] = len(delete_files(db, case))
    if action == "terminate":
        if account_id not in owners(db, case):
            raise Refused("not_a_reported_account", "account_id must own content reported in this case.")
        if not note:
            raise Refused("note_required", "Say why the violation is serious enough to terminate at once.")
        data["account_id"] = account_id
    ev = _event(db, case, "admin", admin_id, action, note, data or None)
    if message:
        ev.data = {**(ev.data or {}), "message": message}
    if after:
        case.status = after
    case.updated_at = utcnow()
    if action == "terminate":
        _suspend(db, case, account_id, "admin", admin_id, "terminated for a serious violation")
    if action == "remove":
        s = get_settings()
        for owner in owners(db, case):
            _event(db, case, "system", None, "strike", None, {"account_id": owner})
            db.flush()
            if strikes(db, owner) >= s.repeat_infringer_strikes:
                _suspend(db, case, owner, "system", None, f"repeat infringer: {s.repeat_infringer_strikes} strikes")
    if action in ("withdraw", "restore"):
        struck = {(e.data or {}).get("account_id") for e in db.execute(select(CaseEvent).where(
            CaseEvent.case_id == case.id, CaseEvent.action == "strike")).scalars()}
        for owner in sorted(a for a in struck if a):
            _event(db, case, "system", None, "strike_cancelled", f"case {after}", {"account_id": owner})
    db.flush()
    return ev


def business_days_after(start, days: int):
    d = start
    while days > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days -= 1
    return d
