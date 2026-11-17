"""Stripe: subscription status on accounts, and a record of each payment that granted credits.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16

Additive: three nullable columns and one new table.
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

COLUMNS = ("subscription_status", "subscription_cancel_at", "subscription_event_at")


def upgrade() -> None:
    op.add_column("accounts", sa.Column("subscription_status", sa.String(length=20), nullable=True))
    op.add_column("accounts", sa.Column("subscription_cancel_at", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("subscription_event_at", sa.DateTime(), nullable=True))
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("stripe_ref", sa.String(length=80), nullable=False),
        sa.Column("payment_intent", sa.String(length=80), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("credits_removed", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_ref"),
    )
    op.create_index("ix_payments_account_id", "payments", ["account_id"], unique=False)
    op.create_index("ix_payments_payment_intent", "payments", ["payment_intent"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payments_payment_intent", table_name="payments")
    op.drop_index("ix_payments_account_id", table_name="payments")
    op.drop_table("payments")
    for name in reversed(COLUMNS):
        op.drop_column("accounts", name)
