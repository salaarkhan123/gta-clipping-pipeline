"""Creators League: creator profiles, competitions, entries, view observations and the audit log.

Revision ID: 0012_league
Revises: 0011
Create Date: 2026-11-22

Additive only: five new tables. No DROP/RENAME, no change to an existing table.

The id carries a name because another open change (#273, 0012_admin_mfa) also revises 0011. Whichever of the
two merges second must point its down_revision at the other, or the chain has two heads.
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_league"
down_revision = "0011"      # 0011_social_publishing (#266)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creator_profiles",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("username", sa.String(length=20), nullable=False),
        sa.Column("username_key", sa.String(length=20), nullable=False),
        sa.Column("avatar", sa.String(length=16), nullable=False),
        sa.Column("games", sa.JSON(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id"),
        sa.UniqueConstraint("username_key"),
    )
    op.create_table(
        "league_competitions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("prizes", sa.JSON(), nullable=False),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("cash_prizes_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "league_entries",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("competition_id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("clip_id", sa.String(length=40), nullable=False),
        sa.Column("platform", sa.String(length=12), nullable=False),
        sa.Column("url", sa.String(length=300), nullable=False),
        sa.Column("url_key", sa.String(length=80), nullable=False),
        sa.Column("game", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("status_reason", sa.String(length=500), nullable=True),
        sa.Column("flagged", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("flag_reason", sa.String(length=500), nullable=True),
        sa.Column("attribution_confirmed_at", sa.DateTime(), nullable=False),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("final_place", sa.Integer(), nullable=True),
        sa.Column("winner_approved_at", sa.DateTime(), nullable=True),
        sa.Column("prize_status", sa.String(length=12), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"]),
        sa.ForeignKeyConstraint(["competition_id"], ["league_competitions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("competition_id", "account_id", name="uq_league_entry_account"),
        sa.UniqueConstraint("competition_id", "url_key", name="uq_league_entry_url"),
    )
    op.create_index("ix_league_entries_account_id", "league_entries", ["account_id"], unique=False)
    op.create_index("ix_league_entries_competition_id", "league_entries", ["competition_id"], unique=False)
    op.create_table(
        "league_view_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entry_id", sa.String(length=40), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("observed_by", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["league_entries.id"]),
        sa.ForeignKeyConstraint(["observed_by"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_league_view_observations_entry_id", "league_view_observations", ["entry_id"], unique=False)
    op.create_table(
        "league_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("competition_id", sa.String(length=40), nullable=True),
        sa.Column("actor_id", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("entity_kind", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.String(length=40), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_league_events_competition_id", "league_events", ["competition_id"], unique=False)
    op.create_index("ix_league_events_entity_id", "league_events", ["entity_id"], unique=False)


def downgrade() -> None:
    for name in ("ix_league_events_entity_id", "ix_league_events_competition_id"):
        op.drop_index(name, table_name="league_events")
    op.drop_table("league_events")
    op.drop_index("ix_league_view_observations_entry_id", table_name="league_view_observations")
    op.drop_table("league_view_observations")
    for name in ("ix_league_entries_competition_id", "ix_league_entries_account_id"):
        op.drop_index(name, table_name="league_entries")
    op.drop_table("league_entries")
    op.drop_table("league_competitions")
    op.drop_table("creator_profiles")
