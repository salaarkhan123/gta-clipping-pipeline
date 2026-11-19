"""Match a paid Stripe receipt to the server's catalog before posting a credit grant."""
from .config import get_settings
from .deps import ApiError
from .plans import LEGACY_PLANS, find_plan, plan_for_price


def _stripe_read(method, *args, **kwargs):
    import stripe
    try:
        return method(*args, **kwargs, api_key=get_settings().stripe_secret_key).to_dict()
    except stripe.StripeError:
        # A failed provider read cannot authorize a grant. Stripe retries non-2xx deliveries.
        raise ApiError(503, "try_again", "Could not verify the payment with Stripe.") from None


def checkout_lines(session_id: str) -> dict:
    import stripe
    return _stripe_read(stripe.checkout.Session.list_line_items, session_id, limit=2, expand=["data.price.product"])


def _single_line(lines: dict) -> dict:
    rows = lines.get("data") or []
    return rows[0] if len(rows) == 1 and not lines.get("has_more") else {}


def pack_paid(session: dict, pack: dict) -> bool:
    cents = pack["price_cents"]
    currency = get_settings().currency.lower()
    meta = session.get("metadata") or {}
    if not (session.get("mode") == "payment" and session.get("status") == "complete"
            and session.get("payment_status") == "paid" and session.get("currency") == currency
            and session.get("amount_total") == cents and session.get("payment_intent")
            and session.get("client_reference_id") == meta.get("account_id") and session.get("id")):
        return False
    line = _single_line(checkout_lines(session["id"]))
    price = line.get("price") or {}
    product = price.get("product") or {}
    if not isinstance(product, dict):
        return False
    # Before this release Checkout generated inline Prices too. The session's authoritative
    # single line identifies its Price, and its expanded Product carries the server's pack name.
    if any(k in meta for k in ("receipt_version", "pack_price_id", "pack_product_id")):
        if meta.get("pack_price_id") != price.get("id") or meta.get("pack_product_id") != product.get("id"):
            return False
    return bool(price.get("id") and product.get("id") and product.get("name") == pack["name"]
                and line.get("quantity") == 1 and line.get("amount_total") == cents
                and price.get("type") == "one_time" and price.get("currency") == currency
                and price.get("unit_amount") == cents)


def matches_plan_price(price: dict, plan: dict, interval: str, currency: str) -> bool:
    product = price.get("product") or {}
    recurring = price.get("recurring") or {}
    return (isinstance(product, dict) and bool(product.get("id"))
            and product.get("name") == f"Clutch Clips {plan['name']}"
            and price.get("type") == "recurring" and price.get("currency") == currency
            and price.get("unit_amount") == plan[f"price_{interval}_cents"]
            and recurring.get("interval") == interval and recurring.get("interval_count") == 1)


def checkout_plan(session: dict):
    """Only establish entitlements for a completed Checkout at one of the configured recurring Prices."""
    meta = session.get("metadata") or {}
    currency = get_settings().currency.lower()
    if (not session.get("id") or not session.get("subscription") or not session.get("customer")
            or session.get("client_reference_id") != meta.get("account_id") or session.get("status") != "complete"
            or session.get("payment_status") != "paid" or session.get("currency") != currency):
        return None
    line = _single_line(checkout_lines(session["id"]))
    price = line.get("price") or {}
    offer = plan_for_price(price.get("id"))
    if not offer:
        return None
    plan, interval = offer
    cents = plan[f"price_{interval}_cents"]
    if (line.get("quantity") != 1 or not matches_plan_price(price, plan, interval, currency)
            or line.get("amount_total") != cents or session.get("amount_total") != cents):
        return None
    return plan


def _legacy_offer(account, subscription_id, price_id, line_product):
    import stripe
    plan = find_plan(account.plan)
    if plan not in LEGACY_PLANS or account.stripe_subscription_id != subscription_id:
        return None
    sub = _stripe_read(stripe.Subscription.retrieve, subscription_id, expand=["items.data.price.product"])
    entry = _single_line(sub.get("items") or {})
    price = entry.get("price") or {}
    product = price.get("product") or {}
    if not isinstance(product, dict):
        return None
    recurring = price.get("recurring") or {}
    interval = recurring.get("interval")
    expected_name = "ClutchClips " + plan["name"].removesuffix(" (legacy)")
    if (sub.get("customer") != account.stripe_customer_id or entry.get("quantity") != 1 or price.get("id") != price_id
            or not product.get("id") or (line_product and product["id"] != line_product)
            or product.get("name") != expected_name or price.get("type") != "recurring"
            or interval not in ("month", "year") or recurring.get("interval_count") != 1
            or price.get("currency") != get_settings().currency.lower()
            or price.get("unit_amount") != plan[f"price_{interval}_cents"]):
        return None
    return plan, interval


def paid_invoice_offer(invoice: dict, account, subscription_id):
    currency = get_settings().currency.lower()
    if (not account or not subscription_id or not invoice.get("id") or not invoice.get("customer")
            or invoice.get("status") != "paid" or invoice.get("currency") != currency
            or invoice.get("billing_reason") not in ("subscription_create", "subscription_cycle")
            or (account.stripe_customer_id and account.stripe_customer_id != invoice["customer"])):
        return None
    line = _single_line(invoice.get("lines") or {})
    details = (line.get("pricing") or {}).get("price_details") or {}
    price = line.get("price") or details
    price_id = (price.get("id") or price.get("price")) if isinstance(price, dict) else price
    parent = (line.get("parent") or {}).get("subscription_item_details") or {}
    if line.get("proration") or parent.get("proration") or parent.get("subscription") not in (None, subscription_id):
        return None
    if not price_id or line.get("quantity") != 1 or line.get("currency") != currency:
        return None
    offer = plan_for_price(price_id)
    line_product = price.get("product") if isinstance(price, dict) else None
    if isinstance(line_product, dict):
        line_product = line_product.get("id")
    if offer:
        import stripe
        catalog_price = _stripe_read(stripe.Price.retrieve, price_id, expand=["product"])
        if not matches_plan_price(catalog_price, *offer, currency):
            return None
        if line_product and line_product != catalog_price["product"]["id"]:
            return None
    else:
        offer = _legacy_offer(account, subscription_id, price_id, line_product)
    if not offer:
        return None
    plan, interval = offer
    expected = plan[f"price_{interval}_cents"]
    if expected <= 0 or any(value != expected for value in (invoice.get("amount_paid"), invoice.get("total"), line.get("amount"))):
        return None
    return offer
