"""Stripe production validation (docs/ops/stripe-e2e-test.md): webhook signatures, duplicate and out-of-order
deliveries, checkout, subscription changes (plan change, pause, cancel at period end, immediate cancel), renewals
and the credits each one grants, exactly once."""
import hashlib
import hmac
import json
import time

import pytest

from app.config import get_settings
from app.db import new_session
from app.models import Account
from app.plan_grants import sweep_yearly_grants
from app import routes_billing
from tests.test_api import balance
from tests.test_plans import line, prices, set_account  # noqa: F401
from tests.test_stripe_events import (T0, buy_pack, charge, fresh_ids, i, invoice, me, payment, rows, send,  # noqa: F401
                                      sub_obj, subscribe)
from tests.test_yearly_grants import END, START, add_months, yearly_invoice

# The 8 events the live endpoint https://api.clutchclips.io/webhooks/stripe is subscribed to. Each one is handled.
SUBSCRIBED = ("checkout.session.completed", "checkout.session.async_payment_succeeded", "invoice.paid",
              "invoice.payment_failed", "customer.subscription.updated", "customer.subscription.deleted",
              "charge.refunded", "charge.dispute.created")


def sign(payload: str, ts: int, secret: bytes = b"whsec_test") -> str:
    return hmac.new(secret, f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()


def pack_event(account, session=None, event_id="evt_sig") -> str:
    return json.dumps({"id": event_id, "type": "checkout.session.completed", "created": T0, "data": {"object": {
        "id": session or i("cs_sig"), "mode": "payment", "payment_status": "paid", "payment_intent": i("pi_sig"),
        "amount_total": 499, "metadata": {"account_id": account["id"], "pack_id": "pack_300"}}}})


def post(client, payload: str, header: str | None):
    headers = {"content-type": "application/json"}
    if header is not None:
        headers["stripe-signature"] = header
    return client.post("/webhooks/stripe", content=payload, headers=headers)


def nothing_happened(client, headers, account) -> bool:
    return balance(client, headers) == 30 and payment(i("cs_sig")) is None and all(
        r[0] == "grant" and r[2].startswith("signup:") for r in rows(account["id"]))


# ---- signature verification ----

def test_the_handler_covers_exactly_the_subscribed_events():
    import inspect
    source = inspect.getsource(routes_billing.stripe_webhook)
    handled = {k for k in SUBSCRIBED if f'"{k}"' in source}
    assert handled == set(SUBSCRIBED)


@pytest.mark.parametrize("header", [None, "", "garbage", "t=notanumber,v1=abc", "v1=deadbeef", "t=1700000000"])
def test_a_missing_or_malformed_signature_is_refused_and_never_processed(client, user, header):
    headers, account = user
    r = post(client, pack_event(account), header)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_signature"
    assert nothing_happened(client, headers, account)


def test_an_old_timestamp_is_refused_even_with_a_valid_signature(client, user):
    headers, account = user
    payload = pack_event(account)
    old = int(time.time()) - 301                                   # Stripe's default tolerance is 300 s
    assert post(client, payload, f"t={old},v1={sign(payload, old)}").status_code == 400
    assert nothing_happened(client, headers, account)
    recent = int(time.time()) - 200
    assert post(client, payload, f"t={recent},v1={sign(payload, recent)}").status_code == 200
    assert balance(client, headers) == 330


def test_a_body_changed_after_signing_is_refused(client, user):
    headers, account = user
    payload, ts = pack_event(account), int(time.time())
    tampered = payload.replace("pack_300", "pack_5000")
    assert post(client, tampered, f"t={ts},v1={sign(payload, ts)}").status_code == 400
    assert nothing_happened(client, headers, account)


def test_both_secrets_work_while_stripe_rolls_the_webhook_secret(client, user, monkeypatch):
    """Rolling the secret in Stripe with an overlap signs each event with the old and the new secret, so the server
    can switch STRIPE_WEBHOOK_SECRET at any time inside the overlap (docs/ops/credential-rotation.md)."""
    headers, account = user
    payload, ts = pack_event(account), int(time.time())
    both = f"t={ts},v1={sign(payload, ts, b'whsec_old')},v1={sign(payload, ts, b'whsec_new')}"
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_old")
    assert post(client, payload, both).status_code == 200
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_new")
    assert post(client, payload, both).status_code == 200            # same event again: nothing more
    assert balance(client, headers) == 330
    assert post(client, payload, f"t={ts},v1={sign(payload, ts, b'whsec_old')}").status_code == 400   # old only


def test_without_a_webhook_secret_nothing_is_processed(client, user, monkeypatch):
    headers, account = user
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "")
    payload, ts = pack_event(account), int(time.time())
    assert post(client, payload, f"t={ts},v1={sign(payload, ts)}").status_code == 503    # Stripe retries later
    assert nothing_happened(client, headers, account)


# ---- duplicate deliveries ----

def test_a_pack_paid_in_both_checkout_events_grants_once(client, user):
    headers, account = user
    obj = {"id": i("cs_1"), "mode": "payment", "payment_status": "unpaid", "payment_intent": i("pi_1"),
           "amount_total": 499, "metadata": {"account_id": account["id"], "pack_id": "pack_300"}}
    send(client, "checkout.session.completed", obj, event_id="evt_a")                       # bank debit: not paid yet
    assert balance(client, headers) == 30
    send(client, "checkout.session.async_payment_succeeded", {**obj, "payment_status": "paid"}, event_id="evt_b")
    send(client, "checkout.session.completed", {**obj, "payment_status": "paid"}, event_id="evt_c")
    send(client, "checkout.session.async_payment_succeeded", {**obj, "payment_status": "paid"}, event_id="evt_b")
    assert balance(client, headers) == 330 and payment(i("cs_1")).credits == 300


def test_the_same_invoice_in_several_events_grants_once(client, user, prices):
    headers, account = user
    meta = subscribe(client, account)
    inv = invoice(account, meta, lines={"data": [line("price_st_m")]})
    for event_id in ("evt_a", "evt_a", "evt_b"):              # a redelivery, then a Dashboard resend of a copy
        assert send(client, "invoice.paid", inv, T0 + 5, event_id=event_id).status_code == 200
    send(client, "checkout.session.completed", {"id": f"cs_{i('sub_1')}", "mode": "subscription",
         "subscription": i("sub_1"), "invoice": i("in_1"), "payment_status": "paid",
         "customer": f"cus_{account['id']}", "metadata": meta}, T0 + 6, event_id="evt_c")
    assert balance(client, headers) == 530
    assert [r for r in rows(account["id"]) if r[0] == "grant"][-1] == ("grant", 500, f"stripe-inv:{i('in_1')}")


def test_the_same_yearly_invoice_in_several_events_grants_its_first_month_once(client, user, prices):
    headers, account = user
    subscribe(client, account, plan="pro_v2")
    for event_id in ("evt_a", "evt_b"):
        send(client, "invoice.paid", yearly_invoice(account), T0 + 5, event_id=event_id)
    sweep_yearly_grants(START)
    assert balance(client, headers) == 30 + 1000 and payment(i("in_1")).credits == 1000


# ---- checkout and subscription lifecycle ----

def test_a_subscription_checkout_starts_the_plan_and_the_paid_invoice_brings_the_credits(client, user, prices):
    headers, account = user
    meta = subscribe(client, account)
    got = me(client, headers)
    assert (got["plan"], got["subscription_status"], got["credits"]) == ("starter_v2", "active", 30)
    send(client, "invoice.paid", invoice(account, meta, lines={"data": [line("price_st_m")]}), T0 + 5)
    assert balance(client, headers) == 530


def test_each_monthly_renewal_grants_once(client, user, prices):
    headers, account = user
    meta = subscribe(client, account)
    for n, inv in enumerate((i("in_1"), i("in_2"), i("in_3")), start=1):
        for event_id in ("evt_a", "evt_b"):
            send(client, "invoice.paid", invoice(account, meta, inv=inv, lines={"data": [line("price_st_m")]}),
                 T0 + n, event_id=f"{event_id}_{n}")
        assert balance(client, headers) == 30 + 500 * n


def test_a_late_checkout_event_cannot_bring_back_a_cancelled_subscription(client, user):
    """A checkout.session.completed that is redelivered (or resent from the Dashboard) after the subscription was
    cancelled must not put the account back on the plan."""
    headers, account = user
    meta = subscribe(client, account)
    send(client, "customer.subscription.deleted", sub_obj(account, meta, status="canceled"), T0 + 50)
    send(client, "checkout.session.completed", {"id": f"cs_{i('sub_1')}", "mode": "subscription",
         "subscription": i("sub_1"), "customer": f"cus_{account['id']}", "metadata": meta}, T0, event_id="evt_late")
    got = me(client, headers)
    assert (got["plan"], got["subscription_status"]) == ("free", "canceled")
    with new_session() as db:
        assert db.get(Account, account["id"]).stripe_subscription_id is None


def test_a_returning_subscriber_is_active_again_whatever_the_event_order(client, user, prices):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "customer.subscription.deleted", sub_obj(account, meta, status="canceled"), T0 + 50)
    assert me(client, headers)["subscription_status"] == "canceled"
    # A new subscription: its invoice.paid arrives before its checkout.session.completed.
    send(client, "invoice.paid", invoice(account, meta, inv=i("in_2"), sub=i("sub_2"),
                                         lines={"data": [line("price_st_m")]}), T0 + 100)
    subscribe(client, account, sub=i("sub_2"), created=T0 + 101)
    got = me(client, headers)
    assert (got["plan"], got["subscription_status"], got["credits"]) == ("starter_v2", "active", 530)


def test_cancel_at_period_end_is_shown_in_the_newer_api_shape(client, user):
    """Since 2025-03-31.basil the period end is on the subscription items, not on the subscription."""
    headers, account = user
    meta = subscribe(client, account)
    items = {"data": [{"price": {"id": "price_x"}, "current_period_start": T0, "current_period_end": T0 + 86400}]}
    send(client, "customer.subscription.updated", sub_obj(account, meta, cancel_at_period_end=True, cancel_at=None,
                                                          items=items), T0 + 5)
    got = me(client, headers)
    assert got["subscription_cancel_at"].startswith("2027-01-16") and got["plan"] == "starter_v2"


def test_pausing_payment_collection_keeps_the_plan_and_grants_nothing(client, user, prices):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "invoice.paid", invoice(account, meta, lines={"data": [line("price_st_m")]}), T0 + 5)
    before = rows(account["id"])
    send(client, "customer.subscription.updated", sub_obj(account, meta, pause_collection={"behavior": "void"}), T0 + 9)
    assert me(client, headers)["plan"] == "starter_v2" and rows(account["id"]) == before


def test_a_paused_yearly_subscription_grants_no_months_until_it_resumes_and_never_more_than_twelve(client, user, prices):
    headers, account = user
    subscribe(client, account, plan="pro_v2")
    send(client, "invoice.paid", yearly_invoice(account), T0 + 5)
    send(client, "customer.subscription.updated", sub_obj(account, {**{"account_id": account["id"]}},
         status="paused", items={"data": [line("price_pro_y")]}), T0 + 10)
    assert me(client, headers)["plan"] == "free"
    sweep_yearly_grants(add_months(START, 3))
    assert balance(client, headers) == 30 + 1000                         # paused: no months
    send(client, "customer.subscription.updated", sub_obj(account, {"account_id": account["id"]},
         items={"data": [line("price_pro_y")]}), T0 + 20)
    assert me(client, headers)["plan"] == "pro_v2"
    sweep_yearly_grants(add_months(START, 3))
    assert balance(client, headers) == 30 + 4 * 1000                     # months 1 to 4, each once
    sweep_yearly_grants(END)
    sweep_yearly_grants(add_months(END, 2))
    assert balance(client, headers) == 30 + 12 * 1000


def test_an_invoice_outside_a_subscription_grants_no_plan_credits(client, user):
    """A one-off invoice (made in the Dashboard) for a subscriber is not a plan renewal."""
    headers, account = user
    set_account(account["id"], plan="starter_v2", stripe_subscription_id=i("sub_1"),
                stripe_customer_id=f"cus_{account['id']}", subscription_status="active")
    send(client, "invoice.paid", {"id": i("in_manual"), "customer": f"cus_{account['id']}", "amount_paid": 2500,
                                  "billing_reason": "manual"})
    assert balance(client, headers) == 30 and me(client, headers)["plan"] == "starter_v2"


def test_a_dispute_on_a_plan_invoice_is_matched_through_stripe(client, user, monkeypatch, prices):
    headers, account = user
    meta = subscribe(client, account)
    send(client, "invoice.paid", invoice(account, meta, lines={"data": [line("price_st_m")]}), T0 + 5)
    monkeypatch.setattr(get_settings(), "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(routes_billing, "_invoice_of", lambda intent, key: i("in_1"))
    send(client, "charge.dispute.created", {"id": i("dp_1"), "charge": i("ch_1"), "payment_intent": i("pi_sub")})
    assert balance(client, headers) == 30 and payment(i("in_1")).status == "disputed"
    send(client, "charge.refunded", charge(intent=i("pi_sub"), amount=1599, refunded=1599))     # nothing more to take
    assert balance(client, headers) == 30
