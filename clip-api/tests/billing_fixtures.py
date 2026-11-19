"""Stripe's catalog and Checkout line-item responses for offline billing tests."""
import sys

import pytest
import stripe

from app.config import get_settings

CATALOG = {
    "starter_v2": {"month": ("price_st_m", 1599), "year": ("price_st_y", 6699)},
    "pro_v2": {"month": ("price_pro_m", 2699), "year": ("price_pro_y", 11499)},
    "scale_v2": {"month": ("price_sc_m", 13999), "year": ("price_sc_y", 83999)},
}
PRICES = {f"stripe_price_{plan.removesuffix('_v2')}_{interval}": price_id
          for plan, offers in CATALOG.items() for interval, (price_id, _) in offers.items()}


def pack_line():
    return {"quantity": 1, "amount_total": 499,
            "price": {"id": "price_pack_300", "type": "one_time", "unit_amount": 499, "currency": "usd",
                      "product": {"id": "prod_pack_300", "name": "300 credits"}}}


def subscription_line(plan, interval):
    price_id, cents = CATALOG[plan][interval]
    return {"quantity": 1, "amount_total": cents,
            "price": {"id": price_id, "type": "recurring", "unit_amount": cents, "currency": "usd",
                      "recurring": {"interval": interval, "interval_count": 1},
                      "product": {"id": "prod_" + plan, "active": True, "name": "Clutch Clips " + plan.removesuffix("_v2").title()}}}


@pytest.fixture
def stripe_catalog(monkeypatch):
    for field, price_id in PRICES.items():
        monkeypatch.setattr(get_settings(), field, price_id)
    sessions = {}
    def lines(session_id, **kwargs):
        line = sessions.get(session_id, pack_line())
        return stripe.StripeObject.construct_from({"data": [line], "has_more": False}, None)
    def price(price_id, **kwargs):
        for plan, offers in CATALOG.items():
            for interval, (sku, _) in offers.items():
                if sku == price_id:
                    return stripe.StripeObject.construct_from(subscription_line(plan, interval)["price"], None)
        raise AssertionError(f"unexpected provider lookup {price_id}")

    monkeypatch.setattr(stripe.Price, "retrieve", price)
    monkeypatch.setattr(stripe.checkout.Session, "list_line_items", lines)
    monkeypatch.setattr(sys.modules[__name__], "CHECKOUT_LINES", sessions)


CHECKOUT_LINES = {}


def checkout_receipt(account, sub, meta):
    line = subscription_line(meta["plan_id"], meta["interval"])
    session = "cs_" + sub
    CHECKOUT_LINES[session] = line
    return {"id": session, "mode": "subscription", "status": "complete", "payment_status": "paid",
            "subscription": sub, "customer": "cus_" + account["id"], "metadata": meta,
            "client_reference_id": account["id"], "currency": "usd", "amount_total": line["amount_total"]}


@pytest.fixture
def legacy_subscription(monkeypatch):
    def install(account, sub, name, interval, cents):
        price = {"id": "price_1OldInlinePrice", "type": "recurring", "currency": "usd", "unit_amount": cents,
                 "recurring": {"interval": interval, "interval_count": 1},
                 "product": {"id": "prod_legacy", "name": "ClutchClips " + name}}
        def retrieve(subscription_id, **kwargs):
            assert subscription_id == sub
            return stripe.StripeObject.construct_from({"id": sub, "customer": "cus_" + account["id"],
                                                       "items": {"data": [{"quantity": 1, "price": price}]}}, None)
        monkeypatch.setattr(stripe.Subscription, "retrieve", retrieve)
    return install
