"""Plans copied from WayinVideo (owner, 2026-11-17): the config, Stripe Price IDs, the credits a paid invoice grants,
the per-plan limits, and what happens to subscribers who bought a plan before the change (grandfathered)."""
import pytest
import stripe

from app.config import get_settings
from app.db import new_session
from app.models import Account
from app.pipeline.render import output_size
from app.plans import LEGACY_PLANS, PLANS, all_plans, get_plan, plan_for_price, plan_of, stripe_price_id
from tests.billing_fixtures import PRICES, legacy_subscription
from tests.ingest_support import no_stray_imports, web  # noqa: F401
from tests.test_api import balance
from tests.test_stripe_events import T0, fresh_ids, i, invoice, me, rows, send, sub_obj  # noqa: F401

# The plans on sale: name, monthly cents, yearly cents, credits a month, then our enforced limits: export short side,
# links per bulk import, saved templates. Monthly prices, credits and limits are WayinVideo's (docs/PARITY.md, w11);
# the yearly prices are the owner's of 2026-11-19: $66.99, $114.99, $839.99 a year.
WAYIN = {"starter_v2": ("Starter", 1599, 6699, 500, 1080, 10, 1),
         "pro_v2": ("Pro", 2699, 11499, 1000, 2160, 30, 3),
         "scale_v2": ("Scale", 13999, 83999, 6000, 2160, 50, 10)}


@pytest.fixture
def prices(monkeypatch):
    for name, value in PRICES.items():
        monkeypatch.setattr(get_settings(), name, value)


def set_account(account_id: str, **fields) -> None:
    with new_session() as db:
        acct = db.get(Account, account_id)
        for k, v in fields.items():
            setattr(acct, k, v)
        db.commit()


def line(price_id: str, new_shape: bool = False) -> dict:
    """An invoice line carrying a Stripe Price, in the older (`price`) or newer (`pricing.price_details`) shape."""
    if new_shape:
        return {"pricing": {"price_details": {"price": price_id}}}
    return {"price": {"id": price_id}}


# ---- the config ----

def test_plans_on_sale_are_wayins_and_legacy_plans_are_not_listed(client):
    body = client.get("/v1/billing/plans").json()
    listed = [p["id"] for p in body["plans"]]
    assert listed == ["free", "starter_v2", "pro_v2", "scale_v2"] and all_plans() == PLANS
    for plan_id, (name, month, year, credits, side, bulk, templates) in WAYIN.items():
        p = next(x for x in body["plans"] if x["id"] == plan_id)
        assert (p["name"], p["price_month_cents"], p["price_year_cents"], p["monthly_credits"]) == (
            name, month, year, credits)
        assert (p["max_side"], p["bulk_import_max"], p["custom_templates_max"]) == (side, bulk, templates)
    assert not {p["id"] for p in LEGACY_PLANS} & set(listed)
    for p in PLANS + LEGACY_PLANS:            # every plan, sold or grandfathered, has every limit the API reads
        assert {"max_side", "max_render_min", "bulk_import_max", "custom_templates_max", "monthly_credits"} <= set(p)
    assert get_plan("nope")["id"] == "free" and get_plan("agency")["monthly_credits"] == 8000


def test_each_plan_and_interval_maps_to_its_own_stripe_price(prices):
    seen = set()
    for plan in PLANS[1:]:
        for interval in ("month", "year"):
            price_id = stripe_price_id(plan, interval)
            assert price_id and price_id not in seen and plan_for_price(price_id) == (plan, interval)
            seen.add(price_id)
    assert seen == set(PRICES.values())
    assert stripe_price_id(PLANS[0], "month") == "" and stripe_price_id(get_plan("starter"), "month") == ""
    assert plan_for_price("price_someone_else") is None and plan_for_price(None) is None


def test_no_price_id_configured_means_no_price(monkeypatch):
    for name in PRICES:
        monkeypatch.setattr(get_settings(), name, "")
    assert all(stripe_price_id(p, iv) == "" for p in PLANS for iv in ("month", "year"))
    assert plan_for_price("") is None


# ---- buying a plan ----

class FakeStripe:
    def __init__(self, monkeypatch, price: dict | None = None):
        self.price, self.sessions, self.looked_up = price, [], []
        monkeypatch.setattr(get_settings(), "stripe_secret_key", "sk_test_x")
        monkeypatch.setattr(stripe.Price, "retrieve", self.retrieve)
        monkeypatch.setattr(stripe.checkout.Session, "create", self.create)

    def retrieve(self, price_id, api_key=None, expand=None):
        self.looked_up.append(price_id)
        return stripe.StripeObject.construct_from({"id": price_id, **(self.price or {})}, api_key)

    def create(self, **kw):
        self.sessions.append(kw)
        return stripe.StripeObject.construct_from({"url": "https://checkout.stripe.com/c/test"}, "k")


def a_price(cents: int, interval: str, **over) -> dict:
    return {"active": True, "product": {"id": "prod_starter", "active": True, "name": "Clutch Clips Starter"}, "unit_amount": cents, "currency": "usd", "type": "recurring",
            "recurring": {"interval": interval, "interval_count": 1}, **over}


@pytest.mark.parametrize("plan_id,interval,price_id,cents", [
    ("starter_v2", "month", "price_st_m", 1599), ("pro_v2", "year", "price_pro_y", 11499),
    ("scale_v2", "year", "price_sc_y", 83999)])
def test_subscribe_checks_out_at_the_configured_stripe_price(client, user, prices, monkeypatch, plan_id, interval,
                                                              price_id, cents):
    headers, account = user
    fake = FakeStripe(monkeypatch, a_price(cents, interval, product={"id": "prod_test", "active": True,
                                                                     "name": "Clutch Clips " + WAYIN[plan_id][0]}))
    before = rows(account["id"])
    r = client.post("/v1/billing/subscribe", json={"plan_id": plan_id, "interval": interval}, headers=headers)
    assert r.status_code == 200 and r.json()["checkout_url"].startswith("https://checkout.stripe.com/")
    (sent,) = fake.sessions
    assert fake.looked_up == [price_id] and sent["line_items"] == [{"quantity": 1, "price": price_id}]
    assert sent["metadata"] == sent["subscription_data"]["metadata"] == {
        "account_id": account["id"], "plan_id": plan_id, "interval": interval}
    assert rows(account["id"]) == before                    # checkout grants nothing; invoice.paid does


@pytest.mark.parametrize("wrong", [{"unit_amount": 1999}, {"currency": "eur"}, {"active": False},
                                   {"recurring": {"interval": "year", "interval_count": 1}},
                                   {"recurring": {"interval": "month", "interval_count": 3}}, {"type": "one_time"}])
def test_a_stripe_price_that_differs_from_the_config_is_never_sold(client, user, prices, monkeypatch, wrong):
    headers, _ = user
    fake = FakeStripe(monkeypatch, {**a_price(1599, "month"), **wrong})
    r = client.post("/v1/billing/subscribe", json={"plan_id": "starter_v2", "interval": "month"}, headers=headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "plan_unavailable" and fake.sessions == []


def test_a_plan_without_a_price_id_cannot_be_bought(client, user, monkeypatch):
    headers, _ = user
    fake = FakeStripe(monkeypatch)
    for name in PRICES:
        monkeypatch.setattr(get_settings(), name, "")
    r = client.post("/v1/billing/subscribe", json={"plan_id": "pro_v2", "interval": "month"}, headers=headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "plan_unavailable"
    assert fake.looked_up == [] and fake.sessions == []


@pytest.mark.parametrize("plan_id", ["free", "starter", "pro", "agency", "scale", "nope"])
def test_only_plans_on_sale_can_be_bought(client, user, prices, monkeypatch, plan_id):
    headers, _ = user
    fake = FakeStripe(monkeypatch, a_price(1900, "month"))
    r = client.post("/v1/billing/subscribe", json={"plan_id": plan_id, "interval": "month"}, headers=headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "plan_not_found" and fake.sessions == []


# ---- what a paid invoice grants ----

def test_invoice_credits_come_from_the_config_of_its_price_never_from_the_event(client, user, prices):
    headers, account = user
    meta = {"account_id": account["id"], "plan_id": "starter_v2", "interval": "month"}     # stale: the price decides
    send(client, "invoice.paid", invoice(account, meta, amount_paid=1, credits=999999, monthly_credits=999999,
                                         lines={"data": [line("price_sc_m", new_shape=True)]}))
    assert balance(client, headers) == 30 and me(client, headers)["plan"] == "free"
    send(client, "invoice.paid", invoice(account, meta, lines={"data": [line("price_sc_m", new_shape=True)]}))
    assert balance(client, headers) == 6030 and me(client, headers)["plan"] == "scale_v2"
    send(client, "invoice.paid", invoice(account, meta, lines={"data": [line("price_sc_m", new_shape=True)]}))
    assert balance(client, headers) == 6030                                     # a redelivery grants nothing


@pytest.mark.parametrize("price_id,meta_interval,credits", [
    ("price_st_m", "year", 500), ("price_st_y", "month", 500), ("price_pro_m", "month", 1000),
    ("price_pro_y", "year", 1000), ("price_sc_y", "month", 6000)])
def test_a_yearly_price_grants_its_first_month_now_and_a_monthly_one_a_month(client, user, prices, price_id,
                                                                                 meta_interval, credits):
    headers, account = user
    meta = {"account_id": account["id"], "plan_id": "starter_v2", "interval": meta_interval}
    send(client, "invoice.paid", invoice(account, meta, lines={"data": [line(price_id)]}))
    assert balance(client, headers) == 30 + credits


def test_an_unknown_price_grants_neither_monthly_nor_yearly_credits(client, user):
    headers, account = user
    yearly = {"account_id": account["id"], "plan_id": "pro_v2", "interval": "year"}
    send(client, "invoice.paid", invoice(account, yearly, inv=i("in_y"), lines={"data": [line("price_unknown")]}))
    assert balance(client, headers) == 30
    send(client, "invoice.paid", invoice(account, {**yearly, "interval": "month"}, inv=i("in_m"), lines={"data": [line("price_unknown")]}))
    assert balance(client, headers) == 30


# ---- subscribers from before the change (grandfathered) ----

@pytest.mark.parametrize("plan_id,interval,credits", [
    ("starter", "month", 600), ("pro", "month", 1500), ("agency", "month", 8000), ("pro", "year", 18000)])
def test_an_existing_subscriber_keeps_the_credits_and_limits_they_bought(client, user, prices, legacy_subscription, plan_id, interval,
                                                                       credits):
    headers, account = user
    # A subscription from before 2026-11-17: an inline price Stripe made up, and our metadata with the old plan id.
    set_account(account["id"], plan=plan_id, stripe_subscription_id=i("sub_1"), stripe_customer_id=f"cus_{account['id']}",
                subscription_status="active")
    meta = {"account_id": account["id"], "plan_id": plan_id, "interval": interval}
    cents = get_plan(plan_id)[f"price_{interval}_cents"]
    legacy_subscription(account, i("sub_1"), plan_id.title(), interval, cents)
    send(client, "invoice.paid", invoice(account, meta, total=cents, lines={"data": [line("price_1OldInlinePrice")]}), T0 + 10)
    assert balance(client, headers) == 30 + credits and me(client, headers)["plan"] == plan_id
    send(client, "customer.subscription.updated", sub_obj(account, meta, items={"data": [line("price_1OldInlinePrice")]}),
         T0 + 20)
    send(client, "customer.subscription.updated", sub_obj(account, meta, status="past_due"), T0 + 30)
    assert me(client, headers)["plan"] == plan_id                          # still on the plan they bought
    with new_session() as db:
        plan = plan_of(db.get(Account, account["id"]))
    assert (plan["max_side"], plan["bulk_import_max"], plan["custom_templates_max"]) == (1080, 10, 20)
    assert client.get("/v1/templates/custom", headers=headers).json()["limit"] == 20


def test_a_renewal_without_metadata_follows_the_accounts_legacy_plan(client, user, legacy_subscription):
    headers, account = user
    set_account(account["id"], plan="agency", stripe_subscription_id=i("sub_1"), stripe_customer_id=f"cus_{account['id']}")
    legacy_subscription(account, i("sub_1"), "Agency", "month", 14900)
    send(client, "invoice.paid", invoice(account, {}, total=14900))
    assert balance(client, headers) == 30 + 8000 and me(client, headers)["plan"] == "agency"


def test_changing_plan_moves_a_legacy_subscriber_to_the_new_price(client, user, prices):
    headers, account = user
    set_account(account["id"], plan="starter", stripe_subscription_id=i("sub_1"), stripe_customer_id=f"cus_{account['id']}",
                subscription_status="active")
    legacy = {"account_id": account["id"], "plan_id": "starter", "interval": "month"}
    # A plan change in Stripe swaps the subscription's price; its metadata still names the old plan.
    send(client, "customer.subscription.updated", sub_obj(account, legacy, items={"data": [line("price_pro_m")]}), T0 + 5)
    assert me(client, headers)["plan"] == "pro_v2"
    send(client, "invoice.paid", invoice(account, legacy, lines={"data": [line("price_pro_m")]}), T0 + 6)
    assert balance(client, headers) == 30 + 1000
    send(client, "customer.subscription.deleted", sub_obj(account, legacy, status="canceled"), T0 + 9)
    assert me(client, headers)["plan"] == "free"
    assert get_plan("starter") not in all_plans()                          # once gone, the legacy plan cannot come back


# ---- limits ----

@pytest.mark.parametrize("plan_id,most", [("free", 10), ("starter_v2", 10), ("pro_v2", 30), ("scale_v2", 50)])
def test_bulk_import_takes_up_to_the_plans_batch(client, user, web, plan_id, most):
    headers, account = user
    set_account(account["id"], plan=plan_id)
    urls = [f"https://cdn.test/video.mp4?n={n}" for n in range(most + 1)]
    r = client.post("/v1/imports/bulk", json={"urls": urls, "consent": True}, headers=headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_urls" and f"at most {most} links" in r.text
    ok = client.post("/v1/imports/bulk", json={"urls": urls[:most], "consent": True}, headers=headers).json()
    assert ok["accepted"] == most and ok["refused"] == 0                   # a full batch fits the waiting-imports cap
    more = client.post("/v1/imports", json={"url": urls[most], "consent": True}, headers=headers)
    assert more.status_code == 429 and more.json()["error"]["code"] == "too_many_imports"


@pytest.mark.parametrize("plan_id,most", [("free", 10), ("starter_v2", 10), ("pro_v2", 30), ("scale_v2", 50),
                                          ("agency", 10)])
def test_import_sources_tells_a_signed_in_caller_their_plans_batch(client, user, plan_id, most):
    headers, account = user
    set_account(account["id"], plan=plan_id)
    assert client.get("/v1/imports/sources").json()["bulk_max"] == 10              # no login: the Free plan's, as before
    assert client.get("/v1/imports/sources", headers=headers).json()["bulk_max"] == most
    key = client.post("/v1/keys", json={"name": "ci"}, headers=headers).json()["key"]
    assert client.get("/v1/imports/sources", headers={"Authorization": f"Bearer {key}"}).json()["bulk_max"] == most


def test_import_sources_refuses_a_bad_token_instead_of_answering_for_free(client):
    r = client.get("/v1/imports/sources", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("plan_id,size", [("free", (720, 1280)), ("starter_v2", (1080, 1920)),
                                          ("pro_v2", (2160, 3840)), ("scale_v2", (2160, 3840)), ("agency", (1080, 1920))])
def test_a_4k_export_is_capped_at_the_plans_resolution(plan_id, size):
    assert output_size(3840, 2160, True, "9:16", "4k", max_side=get_plan(plan_id)["max_side"]) == size


def test_the_free_plan_says_how_many_credits_sign_up_gives(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "free_signup_credits", 100)
    plans = {p["id"]: p for p in client.get("/v1/billing/plans").json()["plans"]}
    assert plans["free"]["signup_credits"] == 100                               # the setting, never a number in the site
    assert all("signup_credits" not in p for pid, p in plans.items() if pid != "free")
    assert "signup_credits" not in get_plan("free")                            # the config itself is unchanged
