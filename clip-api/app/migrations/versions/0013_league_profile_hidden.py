"""Creators League: an admin can hide a creator profile.

Revision ID: 0013_league_hide
Revises: 0012_league
Create Date: 2026-11-22

Additive only: one nullable column. No DROP/RENAME, no change to existing rows.
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_league_hide"
down_revision = "0012_league"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("creator_profiles", sa.Column("hidden_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("creator_profiles", "hidden_at")
