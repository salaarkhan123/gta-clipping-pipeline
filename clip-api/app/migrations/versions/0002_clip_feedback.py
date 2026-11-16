"""Clip reactions: clips.reaction, clips.bookmarked and the append-only clip_feedback log (1.2).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15

Additive: two columns (one nullable, one with a server default) and a new table.
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("reaction", sa.String(length=8), nullable=True))
    op.add_column("clips", sa.Column("bookmarked", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "clip_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("clip_id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("value", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clip_feedback_account_id", "clip_feedback", ["account_id"], unique=False)
    op.create_index("ix_clip_feedback_clip_id", "clip_feedback", ["clip_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_clip_feedback_clip_id", table_name="clip_feedback")
    op.drop_index("ix_clip_feedback_account_id", table_name="clip_feedback")
    op.drop_table("clip_feedback")
    op.drop_column("clips", "bookmarked")
    op.drop_column("clips", "reaction")
