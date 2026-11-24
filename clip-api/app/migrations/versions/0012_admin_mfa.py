"""Admin TOTP secret on accounts (SEC-004).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-22

Additive only: one nullable column. No DROP/RENAME.
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("mfa_secret", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "mfa_secret")
