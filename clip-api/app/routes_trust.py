"""Copyright and likeness reports (public) and the admin case routes (app/trust.py).

Admin routes are ordinary public API routes, listed in the OpenAPI document like every other: they need a website
login of an account with `is_admin` (scripts/admin.py make-admin), and answer 401/403 to everyone else.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, ValidationError, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import trust
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, admin_principal, client_ip, rate_limit
from .emailer import send_email
from .models import TrustCase

router = APIRouter()
MAX_BODY = 32 * 1024
Url = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=2000)]
STATUSES = ("received", "in_review", "info_requested", "disabled", "removed", "rejected", "restored",
            "counter_noticed", "closed")


class Report(BaseModel):
    """A copyright notice or a likeness complaint. For copyright, the fields are the elements 17 U.S.C.
    512(c)(3) asks for: your contact details, the work, the material and where it is, a good-faith statement,
    a statement under penalty of perjury that the notice is accurate and you may act, and your signature."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["copyright", "likeness"]
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    organization: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=40)
    # copyright: owner | agent (acting for the owner). likeness: self | representative (acting for the person).
    relationship: Literal["owner", "agent", "self", "representative"]
    work: str = Field(min_length=10, max_length=5000)       # the copyrighted work, or the person shown and how
    reported_urls: list[Url] = Field(min_length=1, max_length=20)   # links or ids of the material on ClutchClips
    details: str | None = Field(default=None, max_length=5000)
    good_faith: bool       # you believe in good faith the use is not authorised by the owner, its agent or the law
    accurate: bool         # under penalty of perjury: the report is accurate and you may act for the owner/person
    signature: str = Field(min_length=2, max_length=200)    # your full name, typed
    website: str = Field(default="", max_length=200)        # leave empty (spam trap)

    @model_validator(mode="after")
    def _complete(self):
        if not (self.good_faith and self.accurate):
            raise ValueError("good_faith and accurate must both be true")
        if self.kind == "copyright":
            if self.relationship not in ("owner", "agent"):
                raise ValueError("relationship must be owner or agent for a copyright notice")
            if not self.address:
                raise ValueError("address is required for a copyright notice")
        elif self.relationship not in ("self", "representative"):
            raise ValueError("relationship must be self or representative for a likeness report")
        return self


async def read_report(request: Request) -> Report:
    """The body, at most 32 KB, read in pieces so a huge body is refused before it is held in memory."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY:
        raise ApiError(413, "too_large", "The report is too large (32 KB at most).")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BODY:
            raise ApiError(413, "too_large", "The report is too large (32 KB at most).")
    try:
        return Report.model_validate_json(bytes(raw) or b"{}")
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first.get("loc", []))
        msg = str(first.get("msg", "invalid report")).removeprefix("Value error, ")
        raise ApiError(422, "validation_error", f"{where}: {msg}".strip(": ")) from None


def _notify(db: Session, case: TrustCase) -> None:
    s = get_settings()
    label = "copyright notice" if case.kind == "copyright" else "likeness report"
    send_email(case.claimant_email, f"We received your {label} ({case.reference})",
               f"Thank you. Your {label} is case {case.reference}.\n\n"
               "A person at ClutchClips reviews every report. Nothing is removed automatically: we check the "
               "report, may contact you for more information, and tell you what we decided. Quote the case "
               "reference in any reply.\n\nIf you did not send this report, reply to tell us.")
    for admin in trust.admin_emails(db):
        send_email(admin, f"New {label}: {case.reference}",
                   f"A new {label} arrived: {case.reference}, {len(case.reported_urls)} reported link(s).\n\n"
                   f"Review it: {s.public_web_url}/dashboard/admin/cases/?ref={case.reference}")


@router.post("/v1/trust/reports", status_code=201, openapi_extra={"requestBody": {
    "required": True, "content": {"application/json": {"schema": Report.model_json_schema()}}}})
async def report(request: Request, db: Session = Depends(get_db)):
    """Report content on ClutchClips that infringes your copyright or uses your likeness without permission.
    No login needed. Returns a case reference, also sent to your email. Nothing is removed automatically: an
    admin reviews every report. Limits: 32 KB per report, 5 reports an hour and 20 a day from one address,
    3 a day per claimant email."""
    s = get_settings()
    ip = client_ip(request)
    rate_limit(f"trust:h:{ip}", s.trust_reports_per_ip_per_hour, 3600)
    rate_limit(f"trust:d:{ip}", s.trust_reports_per_ip_per_day, 86400)
    body = await read_report(request)
    if body.website:                    # the spam trap was filled: answer like a success, keep nothing
        return {"reference": trust.new_reference(db), "kind": body.kind, "status": "received"}
    rate_limit(f"trust:e:{str(body.email).lower()}", s.trust_reports_per_email_per_day, 86400)
    case = trust.open_case(db, body, ip)
    db.commit()
    _notify(db, case)
    return {"reference": case.reference, "kind": case.kind, "status": case.status}


def find_case(db: Session, reference: str) -> TrustCase:
    case = db.execute(select(TrustCase).where(TrustCase.reference == reference.strip().upper())).scalar_one_or_none()
    if case is None:
        raise ApiError(404, "not_found", "No such case.")
    return case


@router.get("/v1/admin/trust/cases")
def list_cases(status: Literal[STATUSES] | None = None, kind: Literal["copyright", "likeness"] | None = None,
               limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               _admin: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    """Admins only: copyright and likeness cases, newest first, without the claimant's contact details."""
    where = [c for c in (TrustCase.status == status if status else None,
                         TrustCase.kind == kind if kind else None) if c is not None]
    total = db.execute(select(func.count(TrustCase.id)).where(*where)).scalar_one()
    rows = db.execute(select(TrustCase).where(*where).order_by(TrustCase.created_at.desc(), TrustCase.id)
                      .limit(limit).offset(offset)).scalars()
    return {"total": total, "cases": [trust.case_summary(db, c) for c in rows]}


@router.get("/v1/admin/trust/cases/{reference}")
def get_case(reference: str, _admin: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    """Admins only: one case with the claimant's details, the content it points at and its owners, and the full
    history."""
    return trust.case_admin_json(db, find_case(db, reference))
