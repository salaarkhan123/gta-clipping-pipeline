"""Stripe: subscriptions (monthly credits), one-time credit packs, the billing portal and the webhook.

Webhook events handled: checkout.session.completed, checkout.session.async_payment_succeeded, invoice.paid,
invoice.payment_failed, customer.subscription.updated, customer.subscription.deleted, charge.refunded,
charge.dispute.created. Anything else is acknowledged and ignored.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger
from .config import get_settings
from .db import get_db
from .deps import ApiError, Principal, session_principal
from .models import Account, Payment
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


def _invoice_subscription(inv: dict) -> str | None:
    """The subscription an invoice belongs to, wherever this Stripe API version puts it."""
    sub = inv.get("subscription") or ((inv.get("parent") or {}).get("subscription_details") or {}).get("subscription")
    return sub.get("id") if isinstance(sub, dict) else sub


def _when(ts) -> datetime | None:
    """A Stripe timestamp (unix seconds) as the naive UTC time the database stores."""
    return datetime.fromtimestamp(int(ts), timezone.utc).replace(tzinfo=None) if ts else None


def _fresh(acct: Account, event: dict, mark: bool = True) -> bool:
    """False when a newer subscription snapshot was already applied: Stripe does not deliver in order, and an old
    "past due" must not overwrite a newer "active". Subscription events `mark` themselves as the newest; invoice
    events only compare, because the subscription events that follow them carry the authoritative status."""
    at = _when(event.get("created"))
    if at and acct.subscription_event_at and at < acct.subscription_event_at:
        return False
    if mark:
        acct.subscription_event_at = at or acct.subscription_event_at
    return True


def _record_payment(db: Session, account_id: str, kind: str, ref: str, credits: int, amount, payment_intent) -> None:
    """Remember what a paid Checkout Session or invoice granted, once, so a refund can take exactly that back."""
    if db.execute(select(Payment.id).where(Payment.stripe_ref == ref)).first():
        return
    intent = payment_intent.get("id") if isinstance(payment_intent, dict) else payment_intent
    db.add(Payment(account_id=account_id, kind=kind, stripe_ref=ref, payment_intent=intent,
                   amount_cents=int(amount) if amount is not None else None, credits=credits))


def _invoice_of(payment_intent: str, key: str) -> str | None:
    """The invoice a payment paid. Newer Stripe API versions no longer put it on the charge."""
    import stripe
    found = stripe.InvoicePayment.list(api_key=key, limit=1,
                                       payment={"type": "payment_intent", "payment_intent": payment_intent})
    rows = found["data"] if isinstance(found, dict) else found.data
    if not rows:
        return None
    inv = rows[0]["invoice"]
    return inv.get("id") if isinstance(inv, dict) else inv


def _payment_for(db: Session, payment_intent, invoice_id) -> Payment | None:
    """The recorded payment behind a charge or dispute: by its payment, else by its invoice."""
    intent = payment_intent.get("id") if isinstance(payment_intent, dict) else payment_intent
    invoice_id = invoice_id.get("id") if isinstance(invoice_id, dict) else invoice_id
    if intent:
        pay = db.execute(select(Payment).where(Payment.payment_intent == intent)).scalars().first()
        if pay:
            return pay
    key = get_settings().stripe_secret_key
    if not invoice_id and intent and key:
        try:
            invoice_id = _invoice_of(intent, key)
        except Exception:
            log.exception("could not look up the invoice for payment %s", intent)
            raise ApiError(503, "try_again", "Could not reach Stripe to match this payment.") from None   # Stripe redelivers
    if not invoice_id:
        return None
    pay = db.execute(select(Payment).where(Payment.stripe_ref == invoice_id)).scalars().first()
    if pay and intent and not pay.payment_intent:
        pay.payment_intent = intent
    return pay


def _take_back(db: Session, pay: Payment, target: int, key: str, note: str, status: str) -> int:
    """Bring the credits removed for this payment up to `target` (never more than it granted), stopping at a
    zero balance: what was already spent is written off, not owed. Safe to repeat."""
    db.flush()
    ledger.lock_account(db, pay.account_id)
    db.refresh(pay)                                   # another delivery may have got here first
    target = min(int(target), pay.credits)
    owed = target - pay.credits_removed
    if owed <= 0:
        return 0
    taken = ledger.claw_back(db, pay.account_id, owed, key, note)
    if taken is None:
        return 0
    pay.credits_removed, pay.status = target, status
    log.warning("took back %s of %s credits from account=%s for %s (%s)", taken, owed, pay.account_id, pay.stripe_ref, status)
    return taken


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
                    acct.subscription_status = acct.subscription_status or "active"
            elif obj.get("payment_status") == "paid":
                pack = find_pack(meta.get("pack_id", ""))
                if pack:   # keyed on the Checkout Session id, so redelivered events never grant twice
                    ledger.grant(db, acct.id, int(pack["credits"]), "topup", f"stripe:{obj['id']}",
                                 f"Purchased {pack['name']}")
                    _record_payment(db, acct.id, "pack", obj["id"], int(pack["credits"]), obj.get("amount_total"),
                                    obj.get("payment_intent"))
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
            _record_payment(db, acct.id, "plan", obj["id"], int(plan["monthly_credits"]) * months, obj.get("amount_paid"),
                            obj.get("payment_intent"))
            if _invoice_subscription(obj) in (None, acct.stripe_subscription_id) and _fresh(acct, event, mark=False):
                acct.subscription_status = "active"      # a payment went through: clears "past_due"
            db.commit()
            log.info("invoice paid account=%s plan=%s granted=%s", acct.id, plan["id"], granted)
        elif not acct:
            log.error("invoice %s could not be matched to an account", obj.get("id"))
    elif kind == "invoice.payment_failed":
        # No credits move: nothing was granted for an unpaid invoice. Stripe retries the card; if it gives up, the
        # subscription ends and arrives as customer.subscription.deleted (or "unpaid" in an update).
        acct = _account(db, _invoice_meta(obj).get("account_id"), obj.get("customer"))
        if (acct and acct.stripe_subscription_id and _invoice_subscription(obj) in (None, acct.stripe_subscription_id)
                and _fresh(acct, event, mark=False)):
            acct.subscription_status = "past_due"
            db.commit()
            log.warning("invoice payment failed account=%s invoice=%s", acct.id, obj.get("id"))
    elif kind == "customer.subscription.updated":
        meta = obj.get("metadata") or {}
        acct = _account(db, meta.get("account_id"), obj.get("customer"))
        status, plan_id = obj.get("status"), meta.get("plan_id")
        known_plan = bool(plan_id) and get_plan(plan_id)["id"] == plan_id and bool(get_plan(plan_id).get("monthly_credits"))
        mine = bool(acct) and (acct.stripe_subscription_id == obj.get("id") or (
            # This event beat checkout.session.completed: a live subscription for a plan we sell, on an account without one.
            not acct.stripe_subscription_id and status in ("active", "trialing") and known_plan))
        if mine and _fresh(acct, event):                          # an event older than the newest applied changes nothing
            acct.stripe_subscription_id = obj.get("id")
            if status in ("canceled", "incomplete_expired"):      # over: same as customer.subscription.deleted
                acct.plan, acct.stripe_subscription_id = "free", None
                acct.subscription_status, acct.subscription_cancel_at = "canceled", None
            else:
                acct.subscription_status = status
                ends = obj.get("cancel_at") or (obj.get("current_period_end") if obj.get("cancel_at_period_end") else None)
                acct.subscription_cancel_at = _when(ends)
                if status in ("active", "trialing", "past_due"):  # past_due keeps the plan while Stripe retries
                    if known_plan:
                        acct.plan = plan_id
                else:                                             # unpaid, paused, incomplete: no service until paid
                    acct.plan = "free"
            db.commit()
    elif kind == "customer.subscription.deleted":
        acct = _account(db, (obj.get("metadata") or {}).get("account_id"), obj.get("customer"))
        if acct and (not acct.stripe_subscription_id or acct.stripe_subscription_id == obj.get("id")):
            acct.plan, acct.stripe_subscription_id = "free", None
            if acct.subscription_status:
                acct.subscription_status = "canceled"
            acct.subscription_cancel_at = None
            _fresh(acct, event)
            db.commit()
    elif kind == "charge.refunded":
        # Take back the credits this payment granted, in proportion to how much of it has been refunded so far.
        pay = _payment_for(db, obj.get("payment_intent"), obj.get("invoice"))
        if not pay:
            log.error("refund on charge %s matches no recorded payment; no credits changed", obj.get("id"))
        else:
            amount, refunded = int(obj.get("amount") or 0), int(obj.get("amount_refunded") or 0)
            full = bool(obj.get("refunded")) or (amount > 0 and refunded >= amount)
            target = pay.credits if full else (pay.credits * refunded // amount if amount > 0 else 0)
            _take_back(db, pay, target, f"stripe-refund:{obj.get('id')}:{refunded}",
                       f"Refund of {pay.stripe_ref}", "refunded" if full else "partial")
        db.commit()
    elif kind == "charge.dispute.created":
        # The bank has pulled the money back: treat it as a full refund of that payment.
        pay = _payment_for(db, obj.get("payment_intent"), None)
        if not pay:
            log.error("dispute %s matches no recorded payment; no credits changed", obj.get("id"))
        else:
            _take_back(db, pay, pay.credits, f"stripe-dispute:{obj.get('id')}", f"Dispute on {pay.stripe_ref}", "disputed")
            pay.status = "disputed"
        db.commit()
    return {"received": True}
