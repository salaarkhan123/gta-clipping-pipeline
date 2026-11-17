"""Credit ledger: append-only, idempotent, refund-safe.

Rules:
- Balance = SUM(delta) for the account.
- A refund or dispute takes back what the payment granted with one `adjust` row (key `stripe-refund:...` or
  `stripe-dispute:...`), stopping at a zero balance.
- A job is reserved once (key `reserve:<job>`) and settled once (key `settle:<job>`),
  either as a commit (keep the charge) or a release (refund). The unique key makes a
  second settle a no-op, so a job can never be refunded twice or refunded after commit.
"""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Account, CreditLedger, Job


class InsufficientCredits(Exception):
    def __init__(self, balance: int, cost: int):
        super().__init__(f"balance {balance} < cost {cost}")
        self.balance, self.cost = balance, cost


def balance(db: Session, account_id: str) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(CreditLedger.delta), 0)).where(CreditLedger.account_id == account_id)
    ).scalar_one()
    return int(total)


def lock_account(db: Session, account_id: str) -> Account:
    """Row lock (Postgres) so concurrent submits for one account are serialised."""
    return db.execute(select(Account).where(Account.id == account_id).with_for_update()).scalar_one()


def _insert_once(db: Session, **row) -> bool:
    """Insert a ledger row unless its idempotency key already exists. Returns True if inserted."""
    key = row["idempotency_key"]
    if db.execute(select(CreditLedger.id).where(CreditLedger.idempotency_key == key)).first():
        return False
    try:
        with db.begin_nested():
            db.add(CreditLedger(**row))
        return True
    except IntegrityError:
        return False  # lost a race to an identical write


def grant(db: Session, account_id: str, credits: int, kind: str, key: str, note: str | None = None) -> bool:
    if credits <= 0 and kind != "adjust":
        raise ValueError("grant must be positive")
    return _insert_once(db, account_id=account_id, delta=credits, kind=kind, note=note, idempotency_key=key)


def claw_back(db: Session, account_id: str, credits: int, key: str, note: str | None = None) -> int | None:
    """Take back credits that a refunded or disputed payment granted, never below a zero balance. Appends one
    row, also when nothing is left to take, so the refund is on record. Returns the credits taken, or None when
    this key was handled before. The caller holds the account lock and commits."""
    if credits <= 0:
        raise ValueError("claw back must be positive")
    taken = min(credits, max(0, balance(db, account_id)))
    done = _insert_once(db, account_id=account_id, delta=-taken, kind="adjust", note=note, idempotency_key=key)
    return taken if done else None


def reserve(db: Session, account_id: str, job_id: str, cost: int) -> None:
    """Hold credits for a job. Caller must commit. Raises InsufficientCredits."""
    if cost <= 0:
        raise ValueError("cost must be positive")
    lock_account(db, account_id)
    have = balance(db, account_id)
    if have < cost:
        raise InsufficientCredits(have, cost)
    _insert_once(db, account_id=account_id, delta=-cost, kind="reserve", job_id=job_id,
                 idempotency_key=f"reserve:{job_id}")


def settle(db: Session, job: Job, success: bool) -> bool:
    """Commit (success) or release (refund) a job's reservation exactly once. Caller must commit."""
    if success:
        done = _insert_once(db, account_id=job.account_id, delta=0, kind="commit", job_id=job.id,
                            idempotency_key=f"settle:{job.id}")
        if done:
            job.credits_charged = job.credits_reserved
    else:
        done = _insert_once(db, account_id=job.account_id, delta=job.credits_reserved, kind="release",
                            job_id=job.id, idempotency_key=f"settle:{job.id}")
        if done:
            job.credits_charged = 0
    return done
