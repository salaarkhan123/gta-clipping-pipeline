"""Stripe webhook: failed payments, subscription changes, refunds and disputes.

Refund policy (owner, 2026-11-16): a refund or dispute removes the credits that payment granted, and the balance
never goes below zero.
"""
import hashlib
import hmac
import json
import time
import uuid

import pytest
from sqlalchemy import select

from app import routes_billing
from app.db import new_session
from app.models import Account, CreditLedger, Payment
from tests.test_api import balance

T0 = 1_800_000_000
RUN = {"n": ""}


@pytest.fixture(autouse=True)
def fresh_ids():
    """Stripe ids are unique per test: ledger keys are global and the test database outlives one test."""
    RUN["n"] = uuid.uuid4().hex[:8]


def i(name: str) -> str:
    return f"{name}_{RUN['n']}"


def send(client, kind, obj, created=T0, event_id="evt_x", secret=b"whsec_test"):
    payload = json.dumps({"id": event_id, "type": kind, "created": created, "data": {"object": obj}})
    ts = int(time.time())
    sig = hmac.new(secret, f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return client.post("/webhooks/stripe", content=payload, headers={"stripe-signature": f"t={ts},v1={sig}",
                                                                      "content-type": "application/json"})


def me(client, headers):
    return client.get("/v1/me", headers=headers).json()


def rows(account_id):
    with new_session() as db:
        return [(r.kind, r.delta, r.idempotency_key) for r in db.execute(
            select(CreditLedger).where(CreditLedger.account_id == account_id).order_by(CreditLedger.id)).scalars()]


def payment(ref):
    with new_session() as db:
        return db.execute(select(Payment).where(Payment.stripe_ref == ref)).scalars().first()


def buy_pack(client, account, session=None, intent=None, pack="pack_300", amount=499):
    session, intent = session or i("cs_1"), intent or i("pi_1")
    r = send(client, "checkout.session.completed", {
        "id": session, "mode": "payment", "payment_status": "paid", "payment_intent": intent, "amount_total": amount,
        "customer": f"cus_{account['id']}", "metadata": {"account_id": account["id"], "pack_id": pack}})
    assert r.status_code == 200


def subscribe(client, account, sub=None, plan="starter", created=T0):
    sub = sub or i("sub_1")
    meta = {"account_id": account["id"], "plan_id": plan, "interval": "month"}
    assert send(client, "checkout.session.completed", {
        "id": f"cs_{sub}", "mode": "subscription", "subscription": sub, "customer": f"cus_{account['id']}",
        "metadata": meta}, created).status_code == 200
    return meta


def invoice(account, meta, inv=None, sub=None, **extra):
    inv, sub = inv or i("in_1"), sub or i("sub_1")
    return {"id": inv, "customer": f"cus_{account['id']}", "amount_paid": 900, "subscription": sub,
            "subscription_details": {"metadata": meta}, **extra}


def charge(intent="", amount=499, refunded=499, full=True, charge_id=None, **extra):
    intent, charge_id = (i("pi_1") if intent == "" else intent), charge_id or i("ch_1")
    return {"id": charge_id, "payment_intent": intent, "amount": amount, "amount_refunded": refunded, "refunded": full, **extra}


# ---- refunds ----

def test_a_full_refund_takes_back_the_pack_once(client, user):
    headers, account = user
    buy_pack(client, account)
    assert balance(client, headers) == 330 and payment(i("cs_1")).credits == 300
    assert send(client, "charge.refunded", charge()).status_code == 200
    assert send(client, "charge.refunded", charge(), event_id="evt_again").status_code == 200       # redelivered
    assert balance(client, headers) == 30
    assert [r for r in rows(account["id"]) if r[0] == "adjust"] == [("adjust", -300, f"stripe-refund:{i('ch_1')}:499")]
    p = payment(i("cs_1"))
    assert (p.credits_removed, p.status) == (300, "refunded")


def test_partial_refunds_take_back_in_proportion_and_never_more_than_was_granted(client, user):
    headers, account = user
    buy_pack(client, account, amount=500)
    send(client, "charge.refunded", charge(amount=500, refunded=100, full=False))                     # a fifth
    assert balance(client, headers) == 270 and payment(i("cs_1")).status == "partial"
    send(client, "charge.refunded", charge(amount=500, refunded=250, full=False))                     # now half in total
    assert balance(client, headers) == 180
    send(client, "charge.refunded", charge(amount=500, refunded=100, full=False))                     # the first one, late
    assert balance(client, headers) == 180
    send(client, "charge.refunded", charge(amount=500, refunded=500, full=True))
    send(client, "charge.dispute.created", {"id": i("dp_1"), "payment_intent": i("pi_1")})                  # and then a dispute
    assert balance(client, headers) == 30 and payment(i("cs_1")).credits_removed == 300


def test_a_refund_after_the_credits_were_spent_stops_at_zero_and_is_not_owed_later(client, user):
    headers, account = user
    buy_pack(client, account)
    with new_session() as db:                                             # 320 of the 330 credits get used
        db.add(CreditLedger(account_id=account["id"], delta=-320, kind="reserve", idempotency_key="reserve:job_spent"))
        db.commit()
    assert balance(client, headers) == 10
    send(client, "charge.refunded", charge())
    assert balance(client, headers) == 0                                  # 10 taken, never negative
    assert ("adjust", -10, f"stripe-refund:{i('ch_1')}:499") in rows(account["id"])
    buy_pack(client, account, session=i("cs_2"), intent=i("pi_2"))
    send(client, "charge.refunded", charge(), event_id="evt_late")        # the old refund again
    assert balance(client, headers) == 300                                # the new purchase is untouched


def test_a_refund_of_a_plan_invoice_is_matched_through_stripe_when_the_charge_has_no_invoice(client, user, monkeypatch):
    headers, account = user
    meta = subscribe(client, account)
    assert send(client, "invoice.paid", invoice(account, meta)).status_code == 200                   # no payment_intent on it
    assert balance(client, headers) == 530 and payment(i("in_1")).payment_intent is None
    asked = []
    monkeypatch.setattr(routes_billing.get_settings(), "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(routes_billing, "_invoice_of", lambda intent, key: asked.append(intent) or i("in_1"))
    assert send(client, "charge.refunded", charge(intent=i("pi_sub"), amount=900, refunded=900)).status_code == 200
    assert asked == [i("pi_sub")] and balance(client, headers) == 30 and payment(i("in_1")).payment_intent == i("pi_sub")
    assert me(client, headers)["plan"] == "starter"                       # a refund does not end the subscription
    send(client, "charge.refunded", charge(intent=i("pi_sub"), amount=900, refunded=900), event_id="evt_2")
    assert asked == [i("pi_sub")] and balance(client, headers) == 30         # found by its payment now; nothing more taken


def test_an_older_charge_shape_names_its_invoice(client, user):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "invoice.paid", invoice(account, meta, payment_intent=i("pi_old")))
    send(client, "charge.refunded", charge(intent=None, amount=900, refunded=450, full=False, invoice=i("in_1")))
    assert balance(client, headers) == 30 + 250


def test_stripe_being_unreachable_asks_for_a_redelivery_and_changes_nothing(client, user, monkeypatch):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "invoice.paid", invoice(account, meta))

    def down(intent, key):
        raise RuntimeError("network")
    monkeypatch.setattr(routes_billing.get_settings(), "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(routes_billing, "_invoice_of", down)
    r = send(client, "charge.refunded", charge(intent=i("pi_sub"), amount=900, refunded=900))
    assert r.status_code == 503 and balance(client, headers) == 530


def test_a_refund_or_dispute_for_an_unknown_payment_changes_nothing(client, user):
    headers, account = user
    before = rows(account["id"])
    assert send(client, "charge.refunded", charge(intent="pi_nobody")).status_code == 200
    assert send(client, "charge.dispute.created", {"id": i("dp_9"), "payment_intent": "pi_nobody"}).status_code == 200
    assert rows(account["id"]) == before and balance(client, headers) == 30


def test_a_dispute_takes_back_the_whole_payment_once(client, user):
    headers, account = user
    buy_pack(client, account)
    for event_id in ("evt_a", "evt_b"):
        assert send(client, "charge.dispute.created", {"id": i("dp_1"), "payment_intent": i("pi_1")}, event_id=event_id).status_code == 200
    assert balance(client, headers) == 30 and payment(i("cs_1")).status == "disputed"
    send(client, "charge.refunded", charge())                             # the refund that follows takes nothing more
    assert balance(client, headers) == 30
    assert [r[1] for r in rows(account["id"]) if r[0] == "adjust"] == [-300]


def test_forged_refund_and_dispute_events_are_rejected(client, user):
    headers, account = user
    buy_pack(client, account)
    assert send(client, "charge.refunded", charge(), secret=b"whsec_wrong").status_code == 400
    assert send(client, "charge.dispute.created", {"id": i("dp_1"), "payment_intent": i("pi_1")}, secret=b"whsec_wrong").status_code == 400
    assert balance(client, headers) == 330


# ---- failed payments and subscription changes ----

def test_a_failed_payment_marks_the_account_past_due_and_a_paid_invoice_clears_it(client, user):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "invoice.paid", invoice(account, meta), T0 + 10)
    assert me(client, headers)["subscription_status"] == "active" and balance(client, headers) == 530
    before = rows(account["id"])
    assert send(client, "invoice.payment_failed", invoice(account, meta, inv=i("in_2")), T0 + 100).status_code == 200
    got = me(client, headers)
    assert got["subscription_status"] == "past_due" and got["plan"] == "starter"       # the plan stays while Stripe retries
    assert rows(account["id"]) == before                                                # no credits moved
    send(client, "invoice.paid", invoice(account, meta, inv=i("in_2")), T0 + 200)
    assert me(client, headers)["subscription_status"] == "active" and balance(client, headers) == 1030
    send(client, "invoice.payment_failed", invoice(account, meta, inv=i("in_2")), T0 + 100, event_id="evt_stale")
    assert me(client, headers)["subscription_status"] == "active"                       # the old failure arrives late


def test_a_failed_payment_without_a_subscription_does_nothing(client, user):
    headers, account = user
    send(client, "invoice.payment_failed", {"id": "in_x", "customer": "cus_nobody", "subscription": "sub_x"})
    assert me(client, headers)["subscription_status"] is None


def sub_obj(account, meta, sub=None, **fields):
    sub = sub or i("sub_1")
    return {"id": sub, "customer": f"cus_{account['id']}", "status": "active", "metadata": meta, **fields}


def test_cancel_at_period_end_is_shown_and_can_be_undone(client, user):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "customer.subscription.updated", sub_obj(account, meta, cancel_at_period_end=True, cancel_at=T0 + 86400), T0 + 5)
    got = me(client, headers)
    assert got["subscription_cancel_at"].startswith("2027-01-16") and got["plan"] == "starter" and got["subscription_status"] == "active"
    send(client, "customer.subscription.updated", sub_obj(account, meta, cancel_at_period_end=False, cancel_at=None), T0 + 9)
    assert me(client, headers)["subscription_cancel_at"] is None


@pytest.mark.parametrize("status,plan,keeps_subscription", [
    ("past_due", "starter", True), ("trialing", "starter", True), ("unpaid", "free", True), ("paused", "free", True),
    ("canceled", "free", False), ("incomplete_expired", "free", False)])
def test_subscription_status_decides_the_plan(client, user, status, plan, keeps_subscription):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "customer.subscription.updated", sub_obj(account, meta, status=status), T0 + 5)
    got = me(client, headers)
    assert got["plan"] == plan and got["subscription_status"] == ("canceled" if not keeps_subscription else status)
    with new_session() as db:                                # an unpaid subscription is kept, so it is fixed in the
        kept = db.get(Account, account["id"]).stripe_subscription_id      # portal and a second one cannot be started
    assert (kept == i("sub_1")) == keeps_subscription and (kept is None) != keeps_subscription
    if keeps_subscription and plan == "free":                # paying it brings the plan back
        send(client, "customer.subscription.updated", sub_obj(account, meta, status="active"), T0 + 9)
        assert me(client, headers)["plan"] == "starter"


def test_a_plan_change_and_events_out_of_order(client, user):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "customer.subscription.updated", sub_obj(account, {**meta, "plan_id": "pro"}), T0 + 50)
    assert me(client, headers)["plan"] == "pro"
    send(client, "customer.subscription.updated", sub_obj(account, meta, status="past_due"), T0 + 20)     # older: ignored
    got = me(client, headers)
    assert got["plan"] == "pro" and got["subscription_status"] == "active"
    send(client, "customer.subscription.updated", sub_obj(account, {**meta, "plan_id": "not-a-plan"}), T0 + 60)
    assert me(client, headers)["plan"] == "pro"                                                            # unknown plan ids change nothing


def test_another_subscription_cannot_change_this_account(client, user):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "customer.subscription.updated", sub_obj(account, meta, sub=i("sub_other"), status="canceled"), T0 + 5)
    assert me(client, headers)["plan"] == "starter"
    send(client, "customer.subscription.updated", sub_obj(account, {"account_id": "acc_nobody"}, sub=i("sub_1"), status="canceled")
         | {"customer": "cus_nobody"}, T0 + 6)
    assert me(client, headers)["plan"] == "starter"


def test_an_update_that_arrives_before_checkout_completes_starts_the_plan(client, user):
    headers, account = user
    meta = {"account_id": account["id"], "plan_id": "starter", "interval": "month"}
    send(client, "customer.subscription.updated", sub_obj(account, meta, status="incomplete"), T0)
    assert me(client, headers)["plan"] == "free"                          # not paid yet
    send(client, "customer.subscription.updated", sub_obj(account, meta), T0 + 1)
    assert me(client, headers)["plan"] == "starter" and me(client, headers)["subscription_status"] == "active"
    assert balance(client, headers) == 30                                 # credits come only with invoice.paid


def test_deleting_the_subscription_clears_its_status(client, user):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "customer.subscription.updated", sub_obj(account, meta, cancel_at=T0 + 86400), T0 + 5)
    send(client, "customer.subscription.deleted", sub_obj(account, meta, status="canceled"), T0 + 9)
    got = me(client, headers)
    assert (got["plan"], got["subscription_status"], got["subscription_cancel_at"]) == ("free", "canceled", None)
