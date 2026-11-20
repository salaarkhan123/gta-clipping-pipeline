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
from . import trust_decisions as decisions
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, admin_principal, client_ip, current_principal, rate_limit, session_principal
from .emailer import send_email
from .models import Account, CaseEvent, CaseTarget, TrustCase, utcnow

router = APIRouter()
MAX_BODY = 32 * 1024
Url = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=2000)]
STATUSES = ("received", "in_review", "info_requested", "disabled", "removed", "rejected", "withdrawn", "restored",
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


# ---- decisions (admins) ----

class Decision(BaseModel):
    """One admin decision. `message` goes to the claimant (request_info, reject); `note` stays in the case
    history. `account_id`: the account to suspend at once (terminate)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: decisions.Action
    note: str | None = Field(default=None, max_length=5000)
    message: str | None = Field(default=None, max_length=5000)
    account_id: str | None = Field(default=None, max_length=40)


def _owner_mail(db: Session, case: TrustCase, subject: str, text: str) -> list[str]:
    """Email every account whose content the case points at. Never includes the claimant's contact details."""
    s, sent = get_settings(), []
    who = case.claimant_organization or case.claimant_name
    for account_id in decisions.owners(db, case):
        acct = db.get(Account, account_id)
        if acct is None:
            continue
        mine = [f"{t.kind} {t.target_id}" for t in decisions.targets(db, case) if t.account_id == account_id]
        send_email(acct.email, f"{subject} ({case.reference})",
                   f"{text}\n\nCase: {case.reference} ({case.kind})\nReported by: {who}\nThe work or person: "
                   f"{case.work[:1000]}\nYour content in this case: {', '.join(mine) or 'none found'}\n\n"
                   f"See the case, and send a counter-notice if you believe this is a mistake: "
                   f"{s.public_web_url}/dashboard/cases/?ref={case.reference}")
        sent.append(account_id)
    return sent


def _after(db: Session, case: TrustCase, action: str, body: Decision) -> None:
    """The emails a decision sends."""
    if action == "request_info":
        send_email(case.claimant_email, f"More information needed ({case.reference})",
                   f"{body.message}\n\nReply to this email and quote {case.reference}.")
    elif action == "forward_notice":
        sent = _owner_mail(db, case, "A notice about your content",
                           "We received a notice of claimed infringement about content on your ClutchClips account "
                           "and are forwarding it to you. This message removes nothing.")
        send_email(case.claimant_email, f"Your notice was forwarded ({case.reference})",
                   f"We forwarded your notice to {len(sent)} account holder(s)." if sent else
                   "We could not forward your notice: no account holder could be identified for the content.")
    elif action in ("disable", "remove"):
        _owner_mail(db, case, "Your content was disabled" if action == "disable" else "Your content was removed",
                    "Content on your account was made unavailable after a copyright or likeness report."
                    + (" It is disabled while we review the report." if action == "disable" else
                       " We found the report valid: this counts as a strike under our repeat-infringer policy."))
    elif action in ("reject", "withdraw", "restore"):
        _owner_mail(db, case, "A report about your content was closed",
                    "A report about your content was closed without action, or your content was restored.")
        if action == "restore":
            send_email(case.claimant_email, f"Content restored ({case.reference})",
                       "The reported content has been restored.")
        if action == "reject":
            send_email(case.claimant_email, f"Decision on your report ({case.reference})",
                       "We reviewed your report and decided not to act on it."
                       + (f"\n\n{body.message}" if body.message else ""))
    elif action == "terminate":
        acct = db.get(Account, body.account_id)
        if acct is not None:
            send_email(acct.email, f"Your account was suspended ({case.reference})",
                       "Your ClutchClips account was suspended for a serious violation of our policies. Reply to "
                       "this email if you believe this is a mistake.")


def _locked(db: Session, reference: str) -> TrustCase:
    case = find_case(db, reference)
    return db.execute(select(TrustCase).where(TrustCase.id == case.id).with_for_update()).scalar_one()


@router.post("/v1/admin/trust/cases/{reference}/decisions")
def decide(reference: str, body: Decision, admin: Principal = Depends(admin_principal),
           db: Session = Depends(get_db)):
    """Admins only: act on a case. Each decision is recorded with who and when. Content is never deleted except by
    `delete_content` on a case already decided `remove`. Actions: review, request_info (needs `message`),
    forward_notice (sends the notice to the account holder), disable (hides the content, keeps its files), remove
    (verified: one strike per account), reject, withdraw (the claimant withdrew), restore, delete_content,
    terminate (suspends `account_id` at once for a serious violation; needs `note`), note, close.
    409 when the case's status does not allow the action."""
    case = _locked(db, reference)
    try:
        decisions.decide(db, case, admin.account.id, body.action, body.note, body.message, body.account_id)
    except decisions.Refused as e:
        db.rollback()
        raise ApiError(409 if e.code == "decision_not_allowed" else 422, e.code, e.message) from None
    db.commit()
    _after(db, case, body.action, body)
    return trust.case_admin_json(db, case)


# ---- the reported account holder ----

class CounterNotice(BaseModel):
    """17 U.S.C. 512(g)(3): your name, address and phone; the material and where it was (the case says); a
    statement under penalty of perjury that it was removed or disabled by mistake or misidentification; consent to
    the jurisdiction of the court for your address (outside the US: any district where ClutchClips may be found)
    and to accept service from the claimant; your signature."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=200)
    address: str = Field(min_length=5, max_length=500)
    phone: str = Field(min_length=5, max_length=40)
    explanation: str = Field(min_length=10, max_length=5000)
    mistake: bool
    consent: bool
    signature: str = Field(min_length=2, max_length=200)

    @model_validator(mode="after")
    def _sworn(self):
        if not (self.mistake and self.consent):
            raise ValueError("mistake and consent must both be true")
        return self


def _my_case(db: Session, p: Principal, reference: str) -> tuple[TrustCase, list]:
    case = db.execute(select(TrustCase).where(TrustCase.reference == reference.strip().upper())).scalar_one_or_none()
    mine = [t for t in decisions.targets(db, case) if t.account_id == p.account.id] if case else []
    if not mine:
        raise ApiError(404, "not_found", "No such case on your account.")
    return case, mine


def _my_case_json(case: TrustCase, mine: list) -> dict:
    """What the reported account holder sees: never the claimant's email, address or phone."""
    return {"reference": case.reference, "kind": case.kind, "status": case.status,
            "reported_by": case.claimant_organization or case.claimant_name, "work": case.work,
            "your_content": [{"kind": t.kind, "id": t.target_id, "state": t.state} for t in mine],
            "can_counter_notice": case.status in ("disabled", "removed"), "created_at": trust.iso(case.created_at)}


@router.get("/v1/trust/my-cases")
def my_cases(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Reports about your content: who reported it (name or organisation), the work, your items and the status."""
    ids = select(CaseTarget.case_id).where(CaseTarget.account_id == p.account.id)
    cases = db.execute(select(TrustCase).where(TrustCase.id.in_(ids)).order_by(TrustCase.created_at.desc())).scalars()
    return {"cases": [_my_case_json(c, [t for t in decisions.targets(db, c) if t.account_id == p.account.id])
                      for c in cases]}


@router.post("/v1/trust/my-cases/{reference}/counter-notice")
def counter_notice(reference: str, body: CounterNotice, p: Principal = Depends(session_principal),
                   db: Session = Depends(get_db)):
    """Send a counter-notice for your content that was disabled or removed. A copy with your name, address and
    phone goes to the claimant, as 17 U.S.C. 512(g)(2)(B) requires. Unless the claimant tells us within 10
    business days that they filed a court action, an admin may restore the content (when its files still exist)."""
    case, mine = _my_case(db, p, reference)
    case = db.execute(select(TrustCase).where(TrustCase.id == case.id).with_for_update()).scalar_one()
    if case.status not in ("disabled", "removed"):
        raise ApiError(409, "counter_notice_not_allowed", "A counter-notice applies to disabled or removed content.")
    restore_after = decisions.business_days_after(utcnow(), 10)
    db.add(CaseEvent(case_id=case.id, actor_kind="reported_user", actor_id=p.account.id, action="counter_notice",
                     note=body.explanation, created_at=utcnow(),
                     data={"name": body.name, "address": body.address, "phone": body.phone,
                           "signature": body.signature, "restore_after": trust.iso(restore_after)}))
    case.status, case.updated_at = "counter_noticed", utcnow()
    db.commit()
    send_email(case.claimant_email, f"Counter-notice received ({case.reference})",
               f"The account holder sent a counter-notice for case {case.reference}.\n\n"
               f"Name: {body.name}\nAddress: {body.address}\nPhone: {body.phone}\n"
               f"Statement: {body.explanation}\nSigned: {body.signature}\n\n"
               "They state under penalty of perjury that the material was removed or disabled by mistake or "
               "misidentification, and consent to the court's jurisdiction and to accept service from you. Unless "
               f"you tell us by {restore_after:%Y-%m-%d} that you have filed a court action, the content may be "
               "restored.")
    for admin in trust.admin_emails(db):
        send_email(admin, f"Counter-notice on {case.reference}",
                   f"Restore after {restore_after:%Y-%m-%d} unless a court action is reported: "
                   f"{get_settings().public_web_url}/dashboard/admin/cases/?ref={case.reference}")
    return _my_case_json(case, mine)
