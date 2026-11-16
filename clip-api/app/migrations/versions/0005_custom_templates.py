"""Custom templates: the looks an account saves for reuse.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-16

Additive: one new table. See docs/CONTRACTS.md.
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_templates",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_custom_templates_account_id", "custom_templates", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_custom_templates_account_id", table_name="custom_templates")
    op.drop_table("custom_templates")
