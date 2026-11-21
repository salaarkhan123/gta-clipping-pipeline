"""The site's legal policies and their versions: the one list the API serves and the website shows.

A material change to a policy gets a new `version` and `effective` date here. Every account then reports
`consent_required: true` (GET /v1/me) until it accepts the new version of each `required` policy
(POST /v1/me/consents). Editorial fixes that change no right or duty keep the version.

Every policy is a DRAFT pending review by a lawyer: the website shows that notice until the owner removes it.
"""
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PolicyAcceptance, utcnow


@dataclass(frozen=True)
class Policy:
    id: str
    title: str
    version: str
    effective: str      # ISO date the version takes effect
    path: str           # the page on the website
    required: bool      # accepted at sign-up; a new version must be accepted again


DRAFT = "2026-11-18"
POLICIES: dict[str, Policy] = {p.id: p for p in (
    Policy("terms", "Terms of Service", "1.0-draft", DRAFT, "/terms/", True),
    Policy("privacy", "Privacy Policy", "1.0-draft", DRAFT, "/privacy/", True),
    Policy("acceptable-use", "Acceptable Use Policy", "1.0-draft", DRAFT, "/acceptable-use/", True),
    Policy("copyright", "Copyright and DMCA Policy", "1.0-draft", DRAFT, "/copyright/", False),
    Policy("refunds", "Refund Policy", "1.0-draft", DRAFT, "/refunds/", False),
    Policy("cookies", "Cookie Notice", "1.0-draft", DRAFT, "/cookies/", False),
)}
REQUIRED = tuple(p.id for p in POLICIES.values() if p.required)


def public_list() -> list[dict]:
    return [asdict(p) for p in POLICIES.values()]


def current_versions() -> dict[str, str]:
    """{policy id: current version} for the policies an account must accept."""
    return {pid: POLICIES[pid].version for pid in REQUIRED}


def accepted(db: Session, account_id: str) -> list[PolicyAcceptance]:
    return list(db.execute(select(PolicyAcceptance).where(PolicyAcceptance.account_id == account_id)
                           .order_by(PolicyAcceptance.accepted_at, PolicyAcceptance.id)).scalars())


def missing(db: Session, account_id: str) -> list[str]:
    """Required policies whose current version this account has not accepted."""
    have = {(a.policy, a.version) for a in accepted(db, account_id)}
    return [pid for pid, version in current_versions().items() if (pid, version) not in have]


def record(db: Session, account_id: str, versions: dict[str, str], source: str) -> list[PolicyAcceptance]:
    """Add one row per (policy, version) not already accepted. Rows are never changed or removed. The caller
    has checked that `versions` are current. Returns the rows added (none when everything was accepted)."""
    have = {(a.policy, a.version) for a in accepted(db, account_id)}
    now = utcnow()
    rows = [PolicyAcceptance(account_id=account_id, policy=pid, version=v, source=source, accepted_at=now)
            for pid, v in versions.items() if (pid, v) not in have]
    db.add_all(rows)
    db.flush()
    return rows


def acceptance_json(a: PolicyAcceptance) -> dict:
    return {"policy": a.policy, "version": a.version, "source": a.source,
            "accepted_at": a.accepted_at.isoformat() + "Z"}
