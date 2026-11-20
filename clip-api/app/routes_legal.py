"""Legal policies and the account's consent record (app/legal.py)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import legal
from .db import get_db
from .deps import ApiError, Principal, current_principal

router = APIRouter()


class ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # {policy id: version}: the versions you read and accept. Each must be the current one.
    policies: dict[str, str] = Field(max_length=len(legal.POLICIES))


def consents_json(db: Session, account_id: str) -> dict:
    missing = legal.missing(db, account_id)
    return {"consent_required": bool(missing), "missing": missing,
            "current": legal.current_versions(),
            "acceptances": [legal.acceptance_json(a) for a in legal.accepted(db, account_id)]}


@router.get("/v1/legal/policies")
def policies():
    """Every legal policy with its version, effective date and page on the website. Public, no key needed.
    `required`: the policies an account accepts at sign-up and again whenever their version changes."""
    return {"policies": legal.public_list(), "required": list(legal.REQUIRED)}


@router.get("/v1/me/consents")
def my_consents(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Which policy versions this account accepted and when, and which current versions it has not accepted."""
    return consents_json(db, p.account.id)


@router.post("/v1/me/consents")
def accept(body: ConsentRequest, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Accept the current version of one or more policies. Accepting a version twice adds nothing.
    409 when a version is not the current one (the page you read is out of date: reload it)."""
    for pid, version in body.policies.items():
        policy = legal.POLICIES.get(pid)
        if policy is None:
            raise ApiError(422, "unknown_policy", f"No policy {pid!r}. See GET /v1/legal/policies.")
        if version != policy.version:
            raise ApiError(409, "policy_version_stale",
                           f"{policy.title} is at version {policy.version}, not {version}. Reload the page.")
    legal.record(db, p.account.id, body.policies, "reaccept")
    db.commit()
    return consents_json(db, p.account.id)
