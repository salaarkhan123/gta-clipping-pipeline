"""Stripe: subscriptions (monthly credits), one-time credit packs, the billing portal and the webhook."""
import json
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, session_principal
from .models import Account
from .plans import all_plans, get_plan
from typing import Literal

router = APIRouter()
log = logging.getLogger("clipapi.billing")


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pack_id: str


class SubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str
    interval: Literal["month", "year"] = "month"


def find_pack(pack_id: str) -> dict | None:
    return next((p for p in get_settings().packs if p["id"] == pack_id), None)


def _stripe_key() -> str:
    key = get_settings().stripe_secret_key
    if not key:
        raise ApiError(503, "billing_unavailable", "Payments are not configured yet.")
    return key


@router.get("/v1/billing/packs")
def packs():
    s = get_settings()
    return {"currency": s.currency, "packs": s.packs}


@router.get("/v1/billing/plans")
def plans():
    s = get_settings()
    return {"currency": s.currency, "billing_enabled": bool(s.stripe_secret_key), "plans": all_plans()}


@router.post("/v1/billing/checkout")
def checkout(body: CheckoutRequest, p: Principal = Depends(session_principal)):
    """One-time credit pack."""
    s, key = get_settings(), _stripe_key()
    pack = find_pack(body.pack_id)
    if not pack:
        raise ApiError(404, "pack_not_found", "No such credit pack.")
    import stripe
    who = {"customer": p.account.stripe_customer_id} if p.account.stripe_customer_id else {"customer_email": p.account.email}
    session = stripe.checkout.Session.create(
        api_key=key, mode="payment", **who,
        line_items=[{"quantity": 1, "price_data": {
            "currency": s.currency, "unit_amount": int(pack["price_cents"]),
            "product_data": {"name": pack["name"]}}}],
        client_reference_id=p.account.id,
        metadata={"account_id": p.account.id, "pack_id": pack["id"]},
        success_url=f"{s.public_web_url}/dashboard?purchase=success",
        cancel_url=f"{s.public_web_url}/pricing?purchase=cancelled",
    )
    return {"checkout_url": session.url}


@router.post("/v1/billing/subscribe")
def subscribe(body: SubscribeRequest, p: Principal = Depends(session_principal)):
    """Start a subscription. Credits are granted when Stripe reports each invoice as paid."""
    s, key = get_settings(), _stripe_key()
    plan = get_plan(body.plan_id)
    price = plan.get("price_year_cents" if body.interval == "year" else "price_month_cents") or 0
    if plan["id"] != body.plan_id or price <= 0:
        raise ApiError(404, "plan_not_found", "No such paid plan.")
    if p.account.stripe_subscription_id:
        raise ApiError(409, "already_subscribed", "You already have a subscription. Change or cancel it in the billing portal.")
    import stripe
    meta = {"account_id": p.account.id, "plan_id": plan["id"], "interval": body.interval}
    who = {"customer": p.account.stripe_customer_id} if p.account.stripe_customer_id else {"customer_email": p.account.email}
    session = stripe.checkout.Session.create(
        api_key=key, mode="subscription", **who,
        line_items=[{"quantity": 1, "price_data": {
            "currency": s.currency, "unit_amount": int(price), "recurring": {"interval": body.interval},
            "product_data": {"name": f"ClutchClips {plan['name']}"}}}],
        client_reference_id=p.account.id, metadata=meta, subscription_data={"metadata": meta},
        success_url=f"{s.public_web_url}/dashboard?purchase=success",
        cancel_url=f"{s.public_web_url}/pricing?purchase=cancelled",
    )
    return {"checkout_url": session.url}


@router.post("/v1/billing/portal")
def portal(p: Principal = Depends(session_principal)):
    """Stripe-hosted page to change plan, update the card or cancel."""
    s, key = get_settings(), _stripe_key()
    if not p.account.stripe_customer_id:
        raise ApiError(409, "no_billing_account", "You have not bought anything yet.")
    import stripe
    session = stripe.billing_portal.Session.create(api_key=key, customer=p.account.stripe_customer_id,
                                                   return_url=f"{s.public_web_url}/dashboard")
    return {"portal_url": session.url}


def _invoice_meta(inv: dict) -> dict:
    """Subscription metadata, wherever this Stripe API version puts it on an invoice."""
    places = [(inv.get("subscription_details") or {}).get("metadata"),
              ((inv.get("parent") or {}).get("subscription_details") or {}).get("metadata")]
    places += [ln.get("metadata") for ln in ((inv.get("lines") or {}).get("data") or [])]
    return next((m for m in places if m and m.get("account_id")), {})


def _account(db: Session, account_id: str | None, customer_id: str | None) -> Account | None:
    if account_id:
        acct = db.get(Account, account_id)
        if acct:
            return acct
    if customer_id:
        return db.execute(select(Account).where(Account.stripe_customer_id == customer_id)).scalars().first()
    return None


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.stripe_webhook_secret:
        raise ApiError(503, "billing_unavailable", "Payments are not configured yet.")
    payload = (await request.body()).decode("utf-8")
    import stripe
    try:
        stripe.WebhookSignature.verify_header(payload, request.headers.get("stripe-signature", ""),
                                              s.stripe_webhook_secret, tolerance=300)
        event = json.loads(payload)
    except Exception:
        raise ApiError(400, "bad_signature", "Invalid webhook signature.") from None

    kind, obj = event.get("type"), (event.get("data") or {}).get("object") or {}
    # All credit amounts come from server-side config, never from numbers in the event.
    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        meta = obj.get("metadata") or {}
        acct = _account(db, meta.get("account_id"), None)
        if not acct:
            log.error("stripe event %s references an unknown account: %s", event.get("id"), meta)
        else:
            if obj.get("customer"):
                acct.stripe_customer_id = obj["customer"]
            if obj.get("mode") == "subscription":
                if obj.get("subscription") and get_plan(meta.get("plan_id"))["id"] == meta.get("plan_id"):
                    acct.stripe_subscription_id, acct.plan = obj["subscription"], meta["plan_id"]
            elif obj.get("payment_status") == "paid":
                pack = find_pack(meta.get("pack_id", ""))
                if pack:   # keyed on the Checkout Session id, so redelivered events never grant twice
                    ledger.grant(db, acct.id, int(pack["credits"]), "topup", f"stripe:{obj['id']}",
                                 f"Purchased {pack['name']}")
            db.commit()
    elif kind == "invoice.paid":
        meta = _invoice_meta(obj)
        acct = _account(db, meta.get("account_id"), obj.get("customer"))
        plan = get_plan(meta.get("plan_id") or (acct.plan if acct else None))
        if acct and plan.get("monthly_credits"):
            months = 12 if meta.get("interval") == "year" else 1   # yearly plans get the year's credits up front
            acct.plan = plan["id"]
            if obj.get("customer"):
                acct.stripe_customer_id = obj["customer"]
            granted = ledger.grant(db, acct.id, int(plan["monthly_credits"]) * months, "grant",
                                   f"stripe-inv:{obj['id']}", f"{plan['name']} plan credits")
            db.commit()
            log.info("invoice paid account=%s plan=%s granted=%s", acct.id, plan["id"], granted)
        elif not acct:
            log.error("invoice %s could not be matched to an account", obj.get("id"))
    elif kind == "customer.subscription.deleted":
        acct = _account(db, (obj.get("metadata") or {}).get("account_id"), obj.get("customer"))
        if acct and (not acct.stripe_subscription_id or acct.stripe_subscription_id == obj.get("id")):
            acct.plan, acct.stripe_subscription_id = "free", None
            db.commit()
    return {"received": True}
