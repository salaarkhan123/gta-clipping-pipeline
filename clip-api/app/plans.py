"""Subscription plans: prices, monthly credits and the per-plan limits the API enforces.

This file is the only source of plan prices and credit amounts: a change here is a pricing change and needs the
owner's OK in its PR. Stripe Price IDs are the one part that comes from the environment (STRIPE_PRICE_<PLAN>_<INTERVAL>,
see DEPLOY.md), because they differ between test and live mode.

Owner's decision (2026-11-17): copy WayinVideo's plans (docs/PARITY.md, "Their pricing (w11)").

Limits, per plan:
- `max_side`: export resolution cap, the short side in pixels (720p, 1080p, 2160 = 4K).
- `max_render_min`: Reframe and Captions minutes per job (None = no plan cap, only the server's).
- `bulk_import_max`: links per bulk import request (`POST /v1/imports/bulk`).
- `custom_templates_max`: saved looks per account (`POST /v1/templates/custom`). Looks saved before a downgrade are
  kept and stay editable; only new saves past the cap are refused.

Credits: monthly plans grant `monthly_credits` per paid invoice. Yearly plans on sale grant the same amount each month of the paid year (app/plan_grants.py), not the year up front.

Grandfathering: plans sold before 2026-11-17 are in LEGACY_PLANS under the ids their subscribers already have.
They are never offered again, and a legacy subscriber keeps exactly that plan's credits and limits for as long as
the subscription runs. Stripe keeps charging the price the subscription was created with. New plans use new ids,
so an account's `plan` alone says which catalog it is on.
"""
from .config import get_settings

INTERVALS = ("month", "year")

PLANS: list[dict] = [
    {"id": "free", "name": "Free", "price_month_cents": 0, "price_year_cents": 0, "monthly_credits": 0,
     "max_side": 720, "max_render_min": 10, "bulk_import_max": 10, "custom_templates_max": 1},
    # price_year_cents is the yearly charge: $5.58 / $9.58 / $69.99 a month, billed yearly.
    {"id": "starter_v2", "name": "Starter", "price_month_cents": 1599, "price_year_cents": 6696, "monthly_credits": 500,
     "max_side": 1080, "max_render_min": 60, "bulk_import_max": 10, "custom_templates_max": 1},
    {"id": "pro_v2", "name": "Pro", "price_month_cents": 2699, "price_year_cents": 11496, "monthly_credits": 1000,
     "max_side": 2160, "max_render_min": 180, "bulk_import_max": 30, "custom_templates_max": 3},
    {"id": "scale_v2", "name": "Scale", "price_month_cents": 13999, "price_year_cents": 83988, "monthly_credits": 6000,
     "max_side": 2160, "max_render_min": None, "bulk_import_max": 50, "custom_templates_max": 10},
]

# Sold before 2026-11-17 (production PLANS from clip-api/plans.env, plus the code default "scale"). Limits are the
# ones those subscribers had: 1080p, the old render caps, 10 links per bulk import, 20 saved looks.
LEGACY_PLANS: list[dict] = [
    {"id": "starter", "name": "Starter (legacy)", "price_month_cents": 1900, "price_year_cents": 11400,
     "monthly_credits": 600, "max_side": 1080, "max_render_min": 60, "bulk_import_max": 10, "custom_templates_max": 20},
    {"id": "pro", "name": "Pro (legacy)", "price_month_cents": 3900, "price_year_cents": 23400,
     "monthly_credits": 1500, "max_side": 1080, "max_render_min": 180, "bulk_import_max": 10, "custom_templates_max": 20},
    {"id": "agency", "name": "Agency (legacy)", "price_month_cents": 14900, "price_year_cents": 89400,
     "monthly_credits": 8000, "max_side": 1080, "max_render_min": None, "bulk_import_max": 10, "custom_templates_max": 20},
    {"id": "scale", "name": "Scale (legacy)", "price_month_cents": 7900, "price_year_cents": 75600,
     "monthly_credits": 8000, "max_side": 1080, "max_render_min": None, "bulk_import_max": 10, "custom_templates_max": 20},
]


def all_plans() -> list[dict]:
    """The plans on sale, in display order. Legacy plans are not listed."""
    return PLANS


def find_plan(plan_id: str | None) -> dict | None:
    """A current or legacy plan by id, or None."""
    return next((p for p in PLANS + LEGACY_PLANS if p["id"] == plan_id), None)


def get_plan(plan_id: str | None) -> dict:
    """A current or legacy plan by id; anything unknown is the free plan."""
    return find_plan(plan_id) or PLANS[0]


def plan_of(account) -> dict:
    return get_plan(getattr(account, "plan", None) or "free")


def stripe_price_id(plan: dict, interval: str) -> str:
    """The Stripe Price ID for a plan on sale, from STRIPE_PRICE_<PLAN>_<INTERVAL>; empty when not configured."""
    if plan not in PLANS or interval not in INTERVALS:
        return ""
    return getattr(get_settings(), f"stripe_price_{plan['id'].removesuffix('_v2')}_{interval}", "") or ""


def plan_for_price(price_id: str | None) -> tuple[dict, str] | None:
    """(plan, interval) for one of our configured Stripe Price IDs, else None."""
    if not price_id:
        return None
    for plan in PLANS:
        for interval in INTERVALS:
            if stripe_price_id(plan, interval) == price_id:
                return plan, interval
    return None
