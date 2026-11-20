"""Yearly plans grant their credits monthly (owner, 2026-11-17): month 1 when the yearly invoice is paid, months 2
to 12 from the worker's sweep on the same day of the month, each exactly once, until a refund, a dispute, a
cancellation or the period end. Legacy yearly plans keep the whole year up front."""
import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app import worker
from app.db import new_session
from app.models import CreditLedger, Payment
from app.plan_grants import add_months, sweep_yearly_grants
from tests.billing_fixtures import legacy_subscription
from tests.test_api import balance
from tests.test_plans import prices, set_account  # noqa: F401
from tests.test_stripe_events import T0, charge, fresh_ids, i, invoice, me, payment, send, sub_obj, subscribe  # noqa: F401

START = datetime.fromtimestamp(T0, timezone.utc).replace(tzinfo=None)      # 2027-01-15 08:00 UTC
END = add_months(START, 12)


def ts(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def yearly_invoice(account, inv=None, start=START, price="price_pro_y", intent=None):
    meta = {"account_id": account["id"], "plan_id": "pro_v2", "interval": "year"}
    line = {"price": {"id": price}, "period": {"start": ts(start), "end": ts(add_months(start, 12))}}
    return invoice(account, meta, inv=inv, amount_paid=11499, payment_intent=intent or i("pi_y"),
                   lines={"data": [line]})


@pytest.fixture
def pro_yearly(client, user, prices):
    """A Pro yearly subscriber whose first yearly invoice has just been paid."""
    headers, account = user
    subscribe(client, account, plan="pro_v2")
    assert send(client, "invoice.paid", yearly_invoice(account), T0 + 5).status_code == 200
    return headers, account


def grant_keys(account_id: str) -> list[str]:
    with new_session() as db:
        return [k for k in db.execute(select(CreditLedger.idempotency_key).where(
            CreditLedger.account_id == account_id, CreditLedger.kind == "grant")).scalars() if k.startswith("grant:")]


def test_months_fall_on_the_same_day_of_the_month():
    jan31 = datetime(2027, 1, 31, 12)
    assert [add_months(jan31, k).date().isoformat() for k in (1, 2, 3, 12)] == [
        "2027-02-28", "2027-03-31", "2027-04-30", "2028-01-31"]
    assert add_months(datetime(2027, 11, 15), 2) == datetime(2028, 1, 15)


def test_paying_the_yearly_invoice_grants_the_first_month_only(client, pro_yearly):
    headers, account = pro_yearly
    assert balance(client, headers) == 30 + 1000 and me(client, headers)["plan"] == "pro_v2"
    assert grant_keys(account["id"]) == [f"grant:{i('sub_1')}:{T0}:0"]
    pay = payment(i("in_1"))
    assert (pay.kind, pay.credits, pay.plan_id, pay.period_start, pay.period_end) == ("plan_year", 1000, "pro_v2", START, END)


def test_months_two_to_twelve_come_from_the_sweep_on_their_day(client, pro_yearly):
    headers, account = pro_yearly
    for k in range(1, 12):
        day = add_months(START, k)
        sweep_yearly_grants(day.replace(hour=7))                   # an hour early: not due yet
        assert balance(client, headers) == 30 + 1000 * k
        sweep_yearly_grants(day)
        assert balance(client, headers) == 30 + 1000 * (k + 1)
    sweep_yearly_grants(END)                                       # the period is over: twelve and no more
    sweep_yearly_grants(add_months(END, 3))
    assert balance(client, headers) == 30 + 12000 and len(grant_keys(account["id"])) == 12
    assert payment(i("in_1")).credits == 12000


def test_a_redelivered_invoice_or_a_second_sweep_never_grants_twice(client, pro_yearly):
    headers, account = pro_yearly
    send(client, "invoice.paid", yearly_invoice(account), T0 + 6, event_id="evt_again")
    assert balance(client, headers) == 1030
    when = add_months(START, 2)
    sweep_yearly_grants(when)
    sweep_yearly_grants(when)
    send(client, "invoice.paid", yearly_invoice(account), T0 + 7, event_id="evt_late")
    assert balance(client, headers) == 30 + 3000 and len(grant_keys(account["id"])) == 3


def test_months_missed_while_the_worker_was_down_are_granted_once(client, pro_yearly):
    headers, account = pro_yearly
    sweep_yearly_grants(add_months(START, 5))                      # months 2 to 6 at once
    assert balance(client, headers) == 30 + 6000
    sweep_yearly_grants(add_months(START, 5))
    assert balance(client, headers) == 30 + 6000
    sweep_yearly_grants(add_months(END, 1))                        # down past the period end: the rest, once
    sweep_yearly_grants(add_months(END, 1))
    assert balance(client, headers) == 30 + 12000 and len(grant_keys(account["id"])) == 12


def test_cancelling_stops_the_grants_and_keeps_what_was_granted(client, pro_yearly):
    headers, account = pro_yearly
    sweep_yearly_grants(add_months(START, 3))
    send(client, "customer.subscription.deleted", sub_obj(account, {"account_id": account["id"]}, status="canceled"), T0 + 99)
    assert me(client, headers)["plan"] == "free"
    sweep_yearly_grants(add_months(START, 8))
    assert balance(client, headers) == 30 + 4000                   # the four months granted stay


def test_a_cancel_at_period_end_keeps_granting_the_paid_year(client, pro_yearly):
    headers, account = pro_yearly
    meta = {"account_id": account["id"], "plan_id": "pro_v2", "interval": "year"}
    send(client, "customer.subscription.updated", sub_obj(account, meta, cancel_at_period_end=True,
                                                          cancel_at=ts(END)), T0 + 50)
    sweep_yearly_grants(add_months(START, 11))
    assert balance(client, headers) == 30 + 12000


def test_a_refund_takes_back_what_was_granted_and_stops_the_grants(client, pro_yearly):
    headers, account = pro_yearly
    sweep_yearly_grants(add_months(START, 2))
    assert balance(client, headers) == 30 + 3000
    send(client, "charge.refunded", charge(intent=i("pi_y"), amount=11499, refunded=11499))
    assert balance(client, headers) == 30 and payment(i("in_1")).status == "refunded"
    sweep_yearly_grants(add_months(START, 6))
    assert balance(client, headers) == 30


def test_a_partial_refund_takes_its_share_and_stops_the_grants(client, pro_yearly):
    headers, account = pro_yearly
    sweep_yearly_grants(add_months(START, 1))
    send(client, "charge.refunded", charge(intent=i("pi_y"), amount=11499, refunded=5750, full=False))
    assert balance(client, headers) == 30 + 1000 and payment(i("in_1")).status == "partial"
    sweep_yearly_grants(add_months(START, 6))
    assert balance(client, headers) == 30 + 1000


def test_a_dispute_stops_the_grants(client, pro_yearly):
    headers, account = pro_yearly
    send(client, "charge.dispute.created", {"id": i("dp_1"), "payment_intent": i("pi_y")})
    assert balance(client, headers) == 30
    sweep_yearly_grants(add_months(START, 4))
    assert balance(client, headers) == 30


def test_a_yearly_renewal_starts_a_new_twelve(client, pro_yearly):
    headers, account = pro_yearly
    sweep_yearly_grants(add_months(START, 11))
    assert balance(client, headers) == 30 + 12000
    send(client, "invoice.paid", yearly_invoice(account, inv=i("in_2"), start=END, intent=i("pi_y2")), ts(END) + 5)
    assert balance(client, headers) == 30 + 13000
    sweep_yearly_grants(add_months(END, 11))
    assert balance(client, headers) == 30 + 24000
    assert f"grant:{i('sub_1')}:{ts(END)}:0" in grant_keys(account["id"])


def test_a_legacy_yearly_subscriber_still_gets_the_year_up_front(client, user, prices, legacy_subscription):
    headers, account = user
    set_account(account["id"], plan="pro", stripe_subscription_id=i("sub_1"), stripe_customer_id=f"cus_{account['id']}")
    meta = {"account_id": account["id"], "plan_id": "pro", "interval": "year"}
    legacy_subscription(account, i("sub_1"), "Pro", "year", 23400)
    line = {"price": {"id": "price_1OldInlinePrice"}, "period": {"start": T0, "end": ts(END)}}
    send(client, "invoice.paid", invoice(account, meta, total=23400, lines={"data": [line]}))
    assert balance(client, headers) == 30 + 1500 * 12 and payment(i("in_1")).kind == "plan"
    sweep_yearly_grants(add_months(START, 6))
    assert balance(client, headers) == 30 + 18000


def test_monthly_plans_are_unchanged(client, user, prices):
    headers, account = user
    meta = subscribe(client, account, plan="pro_v2")
    send(client, "invoice.paid", invoice(account, meta, lines={"data": [{"price": {"id": "price_pro_m"}}]}))
    assert balance(client, headers) == 30 + 1000 and payment(i("in_1")).kind == "plan"
    sweep_yearly_grants(add_months(START, 3))
    assert balance(client, headers) == 30 + 1000


def test_the_worker_sweep_runs_the_monthly_grants(monkeypatch):
    stop, ran = threading.Event(), []
    monkeypatch.setattr(worker, "sweep_yearly_grants", lambda: ran.append(1) or stop.set() or 0)
    monkeypatch.setattr(worker, "run_once", lambda *a, **k: None)
    worker._slot(0, stop, None, None, None, None, object())        # slot 0 runs the sweeps, then stops
    assert ran == [1]
    with new_session() as db:                                        # every yearly record can be scheduled
        assert db.execute(select(Payment).where(Payment.kind == "plan_year", Payment.period_start.is_(None))).first() is None
