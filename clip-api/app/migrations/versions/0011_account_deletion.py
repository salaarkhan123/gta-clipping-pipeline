"""Account deletion (#149): when an account was deleted, and a keyed hash of its old email.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18

Additive: two nullable columns and one index.
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"      # 0010_trust_cases (#145)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("deleted_email_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_accounts_deleted_email_hash", "accounts", ["deleted_email_hash"])


def downgrade() -> None:
    op.drop_index("ix_accounts_deleted_email_hash", table_name="accounts")
    op.drop_column("accounts", "deleted_email_hash")
    op.drop_column("accounts", "deleted_at")
