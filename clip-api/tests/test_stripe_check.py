"""scripts/admin.py stripe-check: the read-only check run after a deploy or a Stripe key rotation."""
import stripe

from app.config import get_settings
from tests.test_plans import prices  # noqa: F401
from tests.test_send_test_email import load_admin

KEY = "sk_" + "test_" + "example0do0not0print"


class Obj(dict):
    def __getattr__(self, name):
        return self[name]


def fake_stripe(monkeypatch, wrong: str | None = None, refused: bool = False):
    from app.plans import PLANS, stripe_price_id
    by_id = {}
    for plan in PLANS:
        for interval in ("month", "year"):
            if (plan.get(f"price_{interval}_cents") or 0) > 0:
                pid = stripe_price_id(plan, interval)
                by_id[pid] = {"id": pid, "active": True, "type": "recurring", "currency": "usd",
                              "product": {"id": "prod_" + plan["id"], "name": "Clutch Clips " + plan["name"], "active": True},
                              "unit_amount": plan[f"price_{interval}_cents"] + (1 if pid == wrong else 0),
                              "recurring": {"interval": interval, "interval_count": 1}}

    def account(api_key):
        if refused:
            raise stripe.AuthenticationError(f"Invalid API Key provided: {api_key}")
        return Obj(id="acct_example")
    monkeypatch.setattr(stripe.Account, "retrieve", staticmethod(account))
    monkeypatch.setattr(stripe.Price, "retrieve", staticmethod(lambda pid, api_key, expand: by_id[pid]))


def run(monkeypatch, capsys, key=KEY, secret="whsec_test"):
    monkeypatch.setattr(get_settings(), "stripe_secret_key", key)
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", secret)
    code = load_admin().stripe_check()
    out = capsys.readouterr()
    assert KEY not in out.out + out.err and "whsec_test" not in out.out + out.err      # never prints a secret
    return code, out.out


def test_all_ok_with_matching_prices(monkeypatch, capsys, prices):
    fake_stripe(monkeypatch)
    code, out = run(monkeypatch, capsys)
    assert code == 0 and "key mode: test" in out and "OK    starter_v2/month: price_st_m" in out and "ALL OK" in out


def test_a_price_that_differs_from_the_config_fails(monkeypatch, capsys, prices):
    fake_stripe(monkeypatch, wrong="price_pro_y")
    code, out = run(monkeypatch, capsys)
    assert code == 1 and "FAIL  pro_v2/year: price_pro_y does not match" in out and "1 CHECK(S) FAILED" in out


def test_a_refused_key_or_missing_settings_fail_without_printing_them(monkeypatch, capsys, prices):
    fake_stripe(monkeypatch, refused=True)
    code, out = run(monkeypatch, capsys, secret="")
    assert code == 1 and "FAIL  key refused: AuthenticationError" in out and "STRIPE_WEBHOOK_SECRET is not set" in out
    code, out = run(monkeypatch, capsys, key="")
    assert code == 2 and "STRIPE_SECRET_KEY is not set" in out
