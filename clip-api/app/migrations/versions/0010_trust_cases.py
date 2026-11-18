"""Trust and safety: an admin flag on accounts, and copyright/likeness cases with their targets and history.

Revision ID: 0010
Revises: 0008
Create Date: 2026-11-18

Additive: one column with a false default and three new tables.
Numbering: 0009 is taken by #152 (premium thumbnails). Whichever of the two merges second points its
down_revision at the other (tests/test_consents.py::test_migrations_have_one_head fails until it does).
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "trust_cases",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("reference", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("claimant_name", sa.String(length=200), nullable=False),
        sa.Column("claimant_email", sa.String(length=320), nullable=False),
        sa.Column("claimant_organization", sa.String(length=200), nullable=True),
        sa.Column("claimant_address", sa.String(length=500), nullable=True),
        sa.Column("claimant_phone", sa.String(length=40), nullable=True),
        sa.Column("relationship", sa.String(length=24), nullable=False),
        sa.Column("work", sa.Text(), nullable=False),
        sa.Column("reported_urls", sa.JSON(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("signature", sa.String(length=200), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index("ix_trust_cases_claimant_email", "trust_cases", ["claimant_email"], unique=False)
    op.create_table(
        "case_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("target_id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["trust_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "kind", "target_id", name="uq_case_target"),
    )
    op.create_index("ix_case_targets_account_id", "case_targets", ["account_id"], unique=False)
    op.create_index("ix_case_targets_case_id", "case_targets", ["case_id"], unique=False)
    op.create_index("ix_case_targets_target_id", "case_targets", ["target_id"], unique=False)
    op.create_table(
        "case_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=40), nullable=False),
        sa.Column("actor_kind", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=40), nullable=True),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["trust_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_events_case_id", "case_events", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_case_events_case_id", table_name="case_events")
    op.drop_table("case_events")
    for name in ("ix_case_targets_target_id", "ix_case_targets_case_id", "ix_case_targets_account_id"):
        op.drop_index(name, table_name="case_targets")
    op.drop_table("case_targets")
    op.drop_index("ix_trust_cases_claimant_email", table_name="trust_cases")
    op.drop_table("trust_cases")
    op.drop_column("accounts", "is_admin")
