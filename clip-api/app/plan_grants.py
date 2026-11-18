"""Yearly plans grant their credits one month at a time (owner, 2026-11-17).

A paid yearly invoice is recorded as a `plan_year` Payment with its subscription, plan and period. Month 0 is
granted when the invoice is paid; month k (1 to 11) once `period_start + k months` has passed, on the same day of
the month (clamped: a subscription started on the 31st grants on the 28th or 30th in shorter months). The worker's
sweep calls `sweep_yearly_grants` every minute, so months missed while it was down are granted on the next run,
once each.

Every grant is one append-only ledger row keyed `grant:<subscription>:<period start>:<month>`, so a redelivered
webhook or a second sweep never grants twice. Grants stop for good when the payment is refunded or disputed, when
the account leaves the plan (cancellation, unpaid, a plan change) or moves to another subscription, and at the
period end. Credits already granted are kept, as with every plan (a refund still takes back what it covers).
Legacy yearly plans keep the whole year up front, as before.
"""
import calendar
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger
from .db import new_session
from .models import Account, Payment, utcnow
from .plans import PLANS, find_plan

log = logging.getLogger("clipapi.billing")

YEARLY = "plan_year"
MONTHS = 12
CATCH_UP = timedelta(days=366)      # a sweep still finishes a year whose period ended up to this long ago


def is_monthly_drip(plan: dict, interval: str) -> bool:
    """Plans on sale, billed yearly, grant monthly. Legacy plans keep what they had: the year up front."""
    return interval == "year" and plan in PLANS


def add_months(start: datetime, k: int) -> datetime:
    y, m = divmod(start.month - 1 + k, 12)
    year, month = start.year + y, m + 1
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))


def grant_key(pay: Payment, k: int) -> str:
    return f"grant:{pay.subscription_id}:{calendar.timegm(pay.period_start.timetuple())}:{k}"


def months_due(start: datetime, end: datetime, now: datetime) -> int:
    """How many of the 12 monthly grants are due by `now`: anniversaries that have passed and fall in the period."""
    return sum(1 for k in range(MONTHS) if add_months(start, k) <= now and add_months(start, k) < end)


def grant_due(db: Session, pay: Payment, now: datetime | None = None, first: bool = False) -> int:
    """Grant the months of this yearly payment that are due and not granted yet. `first`: the invoice was just
    paid, so month 0 is due whatever the clocks say. Returns the months granted now. The caller commits."""
    db.flush()
    acct = ledger.lock_account(db, pay.account_id)       # one granter at a time per account
    db.refresh(pay)
    plan = find_plan(pay.plan_id)
    if (pay.status != "paid" or not plan or acct.plan != pay.plan_id
            or (acct.stripe_subscription_id and acct.stripe_subscription_id != pay.subscription_id)):
        return 0
    now = now or utcnow()
    due = max(months_due(pay.period_start, pay.period_end, now), 1 if first else 0)
    granted = 0
    for k in range(due):
        if ledger.grant(db, acct.id, int(plan["monthly_credits"]), "grant", grant_key(pay, k),
                        f"{plan['name']} plan credits, month {k + 1} of {MONTHS}"):
            pay.credits += int(plan["monthly_credits"])
            granted += 1
    return granted


def sweep_yearly_grants(now: datetime | None = None) -> int:
    """Grant every yearly plan month that has come due. Safe to run any number of times. Returns months granted."""
    now = now or utcnow()
    total = 0
    with new_session() as db:
        ids = db.execute(select(Payment.id).where(Payment.kind == YEARLY, Payment.status == "paid",
                                                  Payment.period_end > now - CATCH_UP)).scalars().all()
        for pay_id in ids:
            try:
                total += grant_due(db, db.get(Payment, pay_id), now)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("monthly grant failed for payment %s", pay_id)
    return total
