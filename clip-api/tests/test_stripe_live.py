"""Opt-in check that Stripe accepts the Checkout sessions the API creates (test mode only, no charges).

    STRIPE_SECRET_KEY=sk_test_... RUN_STRIPE_LIVE=1 pytest -q tests/test_stripe_live.py
"""
import os

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db import new_session
from app.models import CreditLedger
from app.plans import all_plans

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_STRIPE_LIVE"),
                                reason="opt-in: set RUN_STRIPE_LIVE=1 and STRIPE_SECRET_KEY=sk_test_... to run the Stripe test-mode check")

CHECKOUT_PREFIX = "https://checkout.stripe.com/"
TEST_KEY_PREFIXES = ("sk_test_", "rk_test_")
PACKS = [p["id"] for p in get_settings().packs]
PAID_PLANS = [(p["id"], interval) for p in all_plans() for interval in ("month", "year")
              if (p.get(f"price_{interval}_cents") or 0) > 0]


@pytest.fixture(autouse=True)
def stripe_test_key(monkeypatch):
    """Use STRIPE_SECRET_KEY from the environment, and refuse anything that is not a test-mode key."""
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key.startswith(TEST_KEY_PREFIXES):
        pytest.fail("STRIPE_SECRET_KEY must be a Stripe test-mode key (sk_test_... or rk_test_...); this check never runs against live mode",
                    pytrace=False)
    monkeypatch.setattr(get_settings(), "stripe_secret_key", key)


def _ledger_rows(account_id: str) -> int:
    with new_session() as db:
        return db.scalar(select(func.count()).select_from(CreditLedger).where(CreditLedger.account_id == account_id))


def _assert_creates_session(client, user, path: str, body: dict) -> None:
    headers, account = user
    rows, credits = _ledger_rows(account["id"]), client.get("/v1/credits", headers=headers).json()["balance"]
    r = client.post(path, json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"].startswith(CHECKOUT_PREFIX), r.json()
    assert _ledger_rows(account["id"]) == rows
    assert client.get("/v1/credits", headers=headers).json()["balance"] == credits


@pytest.mark.parametrize("pack_id", PACKS)
def test_pack_checkout_session(client, user, pack_id):
    _assert_creates_session(client, user, "/v1/billing/checkout", {"pack_id": pack_id})


@pytest.mark.parametrize("plan_id,interval", PAID_PLANS)
def test_plan_subscription_session(client, user, plan_id, interval):
    _assert_creates_session(client, user, "/v1/billing/subscribe", {"plan_id": plan_id, "interval": interval})
