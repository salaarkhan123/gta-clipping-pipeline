"""Yearly plans grant credits monthly: what each yearly invoice is for and the period it pays.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17

Additive: four nullable columns on payments.
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("subscription_id", sa.String(length=80), nullable=True))
    op.add_column("payments", sa.Column("plan_id", sa.String(length=40), nullable=True))
    op.add_column("payments", sa.Column("period_start", sa.DateTime(), nullable=True))
    op.add_column("payments", sa.Column("period_end", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for name in ("period_end", "period_start", "plan_id", "subscription_id"):
        op.drop_column("payments", name)
