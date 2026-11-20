"""Legal policy acceptances: which version of the Terms, Privacy Policy and Acceptable Use Policy each account
accepted, and when.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18

Additive: one new table.
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_acceptances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("policy", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "policy", "version", name="uq_policy_acceptance"),
    )
    op.create_index("ix_policy_acceptances_account_id", "policy_acceptances", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_policy_acceptances_account_id", table_name="policy_acceptances")
    op.drop_table("policy_acceptances")
