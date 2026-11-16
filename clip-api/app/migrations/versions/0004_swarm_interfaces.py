"""Shared schema for the parity work: project names, link sources, clip rank/kind/preview/export/edit, exports, import log.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16

Additive: nullable columns and two new tables. See docs/CONTRACTS.md.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def columns():
    """(table, column) pairs added by this revision; built fresh each time, since a Column belongs to one table."""
    return (
        ("jobs", sa.Column("name", sa.String(length=120), nullable=True)),
        ("uploads", sa.Column("source_url", sa.String(length=1000), nullable=True)),
        ("uploads", sa.Column("source_platform", sa.String(length=40), nullable=True)),
        ("uploads", sa.Column("language", sa.String(length=8), nullable=True)),
        ("clips", sa.Column("rank", sa.Integer(), nullable=True)),
        ("clips", sa.Column("kind", sa.String(length=16), nullable=True)),
        ("clips", sa.Column("preview_key", sa.String(length=400), nullable=True)),
        ("clips", sa.Column("export_key", sa.String(length=400), nullable=True)),
        ("clips", sa.Column("export_res", sa.String(length=8), nullable=True)),
        ("clips", sa.Column("edit", sa.JSON(), nullable=True)),
    )


def upgrade() -> None:
    for table, column in columns():
        op.add_column(table, column)
    op.create_table(
        "exports",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("clip_id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("resolution", sa.String(length=8), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exports_account_id", "exports", ["account_id"], unique=False)
    op.create_index("ix_exports_clip_id", "exports", ["clip_id"], unique=False)
    op.create_table(
        "import_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=True),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_log_account_id", "import_log", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_import_log_account_id", table_name="import_log")
    op.drop_table("import_log")
    op.drop_index("ix_exports_clip_id", table_name="exports")
    op.drop_index("ix_exports_account_id", table_name="exports")
    op.drop_table("exports")
    for table, column in reversed(columns()):
        op.drop_column(table, column.name)
