"""Subscription plans. Prices and credit amounts come from the PLANS env var (JSON); the defaults are placeholders."""
import json

from .config import get_settings

DEFAULT_PLANS = [
    # PLACEHOLDER PRICES AND CREDITS. Set real ones after measuring cost per source minute.
    # max_side = export resolution cap (short side, px). max_render_min = Reframe/Captions minutes per job (null = no cap).
    {"id": "free", "name": "Free", "price_month_cents": 0, "price_year_cents": 0, "monthly_credits": 0,
     "max_side": 720, "max_render_min": 10},
    {"id": "starter", "name": "Starter", "price_month_cents": 900, "price_year_cents": 8400, "monthly_credits": 500,
     "max_side": 1080, "max_render_min": 60},
    {"id": "pro", "name": "Pro", "price_month_cents": 1900, "price_year_cents": 18000, "monthly_credits": 1200,
     "max_side": 1080, "max_render_min": 180},
    {"id": "scale", "name": "Scale", "price_month_cents": 7900, "price_year_cents": 75600, "monthly_credits": 8000,
     "max_side": 1080, "max_render_min": None},
]


def all_plans() -> list[dict]:
    raw = get_settings().plans
    return json.loads(raw) if raw else DEFAULT_PLANS


def get_plan(plan_id: str | None) -> dict:
    plans = all_plans()
    return next((p for p in plans if p["id"] == plan_id), plans[0])


def plan_of(account) -> dict:
    return get_plan(getattr(account, "plan", None) or "free")
