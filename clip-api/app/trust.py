"""Copyright and likeness reports: intake, finding the reported content, and what each reader may see.

A report never changes content. It opens a case (`trust_cases`), records the ClutchClips content its URLs point
at (`case_targets`) and its first event (`case_events`, append-only). Only an admin decision acts on the content.

The claimant's contact details are personal data: they are returned only by the admin routes, and are never sent
to the account whose content was reported (that user sees the claimant's name or organisation and the work).
"""
import hashlib
import hmac
import re
import secrets
from urllib.parse import unquote, urlparse

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Account, CaseEvent, CaseTarget, Clip, Job, TrustCase, Upload, new_id, utcnow

REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"    # no 0/O, 1/I: read aloud or typed from an email
ID_RE = re.compile(r"\b(upl|job|imp|clip|exp)_[0-9a-f]{24}\b")
KEY_RES = (                                             # storage keys, as they appear in a signed URL's path
    re.compile(r"uploads/(acct_[0-9a-f]{24})/(upl_[0-9a-f]{24})"),
    re.compile(r"clips/((?:job|imp)_[0-9a-f]{24})/(clip_[0-9a-f]{24})"),
    re.compile(r"exports/(job_[0-9a-f]{24})/(exp_[0-9a-f]{24})"),
)


def new_reference(db: Session) -> str:
    while True:
        raw = "".join(secrets.choice(REF_ALPHABET) for _ in range(8))
        ref = f"CC-{raw[:4]}-{raw[4:]}"
        if db.execute(select(TrustCase.id).where(TrustCase.reference == ref)).first() is None:
            return ref


def ip_hash(ip: str) -> str:
    """Keyed hash of the sender's IP: lets an admin see that reports came from one place without storing it."""
    return hmac.new(get_settings().secret_key.encode(), ip.encode(), hashlib.sha256).hexdigest()


def _file_token_key(url: str) -> str | None:
    """The storage key inside a `/v1/files/<token>` link, read without checking expiry: an expired link still
    names the content it pointed at. The signature is checked, so a made-up token names nothing."""
    path = urlparse(url).path
    if "/v1/files/" not in path:
        return None
    token = path.rsplit("/v1/files/", 1)[1].strip("/")
    try:
        data = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"], options={"verify_exp": False})
    except jwt.PyJWTError:
        return None
    return data.get("k") if data.get("p") == "file" else None


def ids_in(url: str) -> set[tuple[str, str]]:
    """(kind, id) pairs a reported URL points at: ids written in it, and storage keys in signed links."""
    text = unquote(url)
    key = _file_token_key(url)
    if key:
        text += " " + key
    found: set[tuple[str, str]] = set()
    for rx in KEY_RES:
        for parent, child in rx.findall(text):
            found.add(("upload" if child.startswith("upl_") else "clip" if child.startswith("clip_") else "export",
                       child))
            if not parent.startswith("acct_"):
                found.add(("job", parent))
    for m in ID_RE.finditer(text):
        prefix = m.group(1)
        kind = {"upl": "upload", "job": "job", "imp": "job", "clip": "clip", "exp": "export"}[prefix]
        found.add((kind, m.group(0)))
    return found


def _owner(db: Session, kind: str, target_id: str) -> str | None:
    if kind == "upload":
        row = db.get(Upload, target_id)
        return row.account_id if row else None
    if kind == "job":
        row = db.get(Job, target_id)
        return row.account_id if row else None
    if kind == "clip":
        row = db.get(Clip, target_id)
        job = db.get(Job, row.job_id) if row else None
        return job.account_id if job else None
    if kind == "export":
        from .models import Export
        row = db.get(Export, target_id)
        return row.account_id if row else None
    return None


def resolve(db: Session, urls: list[str]) -> list[tuple[str, str, str]]:
    """(kind, id, owner account id) for every reported item that exists. Unknown ids are ignored."""
    out = []
    for kind, target_id in sorted({pair for u in urls for pair in ids_in(u)}):
        owner = _owner(db, kind, target_id)
        if owner:
            out.append((kind, target_id, owner))
    return out


def open_case(db: Session, report, ip: str) -> TrustCase:
    """Store one report as a case with its targets and a `received` event. Changes no content."""
    now = utcnow()
    case = TrustCase(id=new_id("case"), reference=new_reference(db), kind=report.kind, status="received",
                     claimant_name=report.name, claimant_email=str(report.email).lower(),
                     claimant_organization=report.organization, claimant_address=report.address,
                     claimant_phone=report.phone, relationship=report.relationship, work=report.work,
                     reported_urls=list(report.reported_urls), details=report.details, signature=report.signature,
                     ip_hash=ip_hash(ip), created_at=now, updated_at=now)
    db.add(case)
    db.flush()
    targets = resolve(db, report.reported_urls)
    for kind, target_id, owner in targets:
        db.add(CaseTarget(case_id=case.id, kind=kind, target_id=target_id, account_id=owner, created_at=now))
    db.add(CaseEvent(case_id=case.id, actor_kind="claimant", action="received", created_at=now,
                     data={"urls": len(report.reported_urls), "targets_found": len(targets)}))
    db.flush()
    return case


def admin_emails(db: Session) -> list[str]:
    s = get_settings()
    if s.trust_admin_email:
        return [e.strip() for e in s.trust_admin_email.split(",") if e.strip()]
    return list(db.execute(select(Account.email).where(Account.is_admin.is_(True),
                                                       Account.status == "active")).scalars())


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


def my_case_json(case: TrustCase, mine: list[CaseTarget]) -> dict:
    """What the reported account holder sees (their case list, their data export): never the claimant's email,
    address or phone."""
    return {"reference": case.reference, "kind": case.kind, "status": case.status,
            "reported_by": case.claimant_organization or case.claimant_name, "work": case.work,
            "your_content": [{"kind": t.kind, "id": t.target_id, "state": t.state} for t in mine],
            "can_counter_notice": case.status in ("disabled", "removed"), "created_at": iso(case.created_at)}


def target_json(db: Session, t: CaseTarget) -> dict:
    owner = db.get(Account, t.account_id)
    return {"kind": t.kind, "id": t.target_id, "state": t.state, "account_id": t.account_id,
            "account_email": owner.email if owner else None}


def event_json(e: CaseEvent) -> dict:
    return {"id": e.id, "actor_kind": e.actor_kind, "actor_id": e.actor_id, "action": e.action, "note": e.note,
            "data": e.data, "created_at": iso(e.created_at)}


def case_summary(db: Session, c: TrustCase) -> dict:
    n = len(db.execute(select(CaseTarget.id).where(CaseTarget.case_id == c.id)).all())
    return {"reference": c.reference, "kind": c.kind, "status": c.status, "claimant_name": c.claimant_name,
            "claimant_organization": c.claimant_organization, "targets": n, "urls": len(c.reported_urls or []),
            "created_at": iso(c.created_at), "updated_at": iso(c.updated_at)}


def case_admin_json(db: Session, c: TrustCase) -> dict:
    """Everything, for an admin: the claimant's contact details, the targets and their owners, the history."""
    targets = db.execute(select(CaseTarget).where(CaseTarget.case_id == c.id).order_by(CaseTarget.id)).scalars()
    events = db.execute(select(CaseEvent).where(CaseEvent.case_id == c.id).order_by(CaseEvent.id)).scalars()
    return {**case_summary(db, c),
            "claimant": {"name": c.claimant_name, "email": c.claimant_email, "organization": c.claimant_organization,
                         "address": c.claimant_address, "phone": c.claimant_phone, "relationship": c.relationship},
            "work": c.work, "reported_urls": c.reported_urls, "details": c.details, "signature": c.signature,
            "ip_hash": c.ip_hash, "targets": [target_json(db, t) for t in targets],
            "events": [event_json(e) for e in events]}
