"""Download my data and delete my account (#149), for the account holder and for admins answering an emailed
request. What is deleted and what is kept: app/account_data.py."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import account_data
from .db import get_db
from .deps import ApiError, Principal, admin_principal, rate_limit, session_principal
from .emailer import send_email
from .models import Account
from .security import verify_password
from .trust_decisions import Refused

router = APIRouter()


class DeleteRequest(BaseModel):
    """Your password, and the word DELETE typed out."""
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=200)
    confirm: Literal["DELETE"]


class AdminDeleteRequest(BaseModel):
    """Where the request came from (for example the email's date and sender), kept in the server log."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(min_length=1, max_length=2000)


def _delete(db: Session, account: Account, actor: str) -> dict:
    try:
        report = account_data.delete(db, account, actor)
    except Refused as e:
        db.rollback()
        raise ApiError(409, e.code, e.message) from None
    db.commit()
    if not report.already_deleted:
        send_email(report.old_email, "Your ClutchClips account was deleted",
                   "Your ClutchClips account and everything made in it (videos, transcripts, clips, thumbnails, "
                   "exports, saved looks and API keys) were deleted. This cannot be undone.\n\n"
                   "We keep records of credits and payments, with no name or email attached, and the records the "
                   "law requires us to keep.\n\n"
                   f"If you did not ask for this, reply to this email or write to {account_data.CONTACT}.")
    return {"deleted": True, **report.counts()}


@router.get("/v1/me/export")
def export_me(p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Download my data: everything ClutchClips holds about your account, as JSON (profile, API keys without the
    keys themselves, accepted policies, uploads, jobs, clips, saved looks, credit history, payments, import log,
    reports about your content). Website login only."""
    return account_data.export(db, p.account)


@router.post("/v1/me/delete")
def delete_me(body: DeleteRequest, p: Principal = Depends(session_principal), db: Session = Depends(get_db)):
    """Delete your account. Cannot be undone. Deletes every upload, transcript, clip, thumbnail and export, your
    saved looks and API keys, and removes your email and personal details. Credit and payment records stay,
    without your identity, and so do the records the law requires. Website login only; 5 tries an hour.
    403 wrong_password. 409 subscription_active (cancel your plan first), case_open (a report about your content
    is open: contact us), job_running (wait for it or cancel it)."""
    rate_limit(f"delete:{p.account.id}", 5, 3600)
    if not verify_password(p.account.password_hash, body.password):
        raise ApiError(403, "wrong_password", "That password is not right.")
    return _delete(db, p.account, "self")


def _account(db: Session, account_id: str) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise ApiError(404, "not_found", "No such account.")
    return account


@router.get("/v1/admin/accounts/{account_id}/export")
def admin_export(account_id: str, admin: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    """Admins only: an account's data export, for an access request that arrived by email."""
    account = _account(db, account_id)
    account_data.log.info("account %s exported by admin %s", account.id, admin.account.id)
    return account_data.export(db, account)


@router.post("/v1/admin/accounts/{account_id}/delete")
def admin_delete(account_id: str, body: AdminDeleteRequest, admin: Principal = Depends(admin_principal),
                 db: Session = Depends(get_db)):
    """Admins only: delete an account for a deletion request that arrived by email. Same rules and refusals (409)
    as POST /v1/me/delete, without the password. Safe to repeat."""
    account = _account(db, account_id)
    account_data.log.warning("admin %s deletes account %s: %s", admin.account.id, account.id, body.note)
    return _delete(db, account, f"admin:{admin.account.id}")
