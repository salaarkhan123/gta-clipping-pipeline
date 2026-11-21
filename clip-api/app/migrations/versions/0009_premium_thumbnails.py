"""Premium AI thumbnails (#140): a clip's thumbnails besides its first one, the one it uses, and likeness consent.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17

Additive: two nullable columns on clips and two new tables. The frame without text is already kept in
features.thumbnail.frame_key (#138), so no column for it.
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"      # 0008_policy_acceptances (#158)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("thumb_id", sa.String(length=40), nullable=True))
    op.add_column("clips", sa.Column("thumb_chosen_key", sa.String(length=400), nullable=True))
    op.create_table(
        "clip_thumbnails",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("clip_id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=True),
        sa.Column("style", sa.String(length=40), nullable=True),
        sa.Column("instruction", sa.String(length=300), nullable=True),
        sa.Column("clean_key", sa.String(length=400), nullable=False),
        sa.Column("image_key", sa.String(length=400), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=True),
        sa.Column("show_text", sa.Boolean(), nullable=False),
        sa.Column("info", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clip_thumbnails_clip_id", "clip_thumbnails", ["clip_id"], unique=False)
    op.create_index("ix_clip_thumbnails_account_id", "clip_thumbnails", ["account_id"], unique=False)
    op.create_table(
        "likeness_consents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("clip_id", sa.String(length=40), nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column("wording", sa.String(length=400), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_likeness_consents_account_id", "likeness_consents", ["account_id"], unique=False)
    op.create_index("ix_likeness_consents_clip_id", "likeness_consents", ["clip_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_likeness_consents_clip_id", table_name="likeness_consents")
    op.drop_index("ix_likeness_consents_account_id", table_name="likeness_consents")
    op.drop_table("likeness_consents")
    op.drop_index("ix_clip_thumbnails_account_id", table_name="clip_thumbnails")
    op.drop_index("ix_clip_thumbnails_clip_id", table_name="clip_thumbnails")
    op.drop_table("clip_thumbnails")
    op.drop_column("clips", "thumb_chosen_key")
    op.drop_column("clips", "thumb_id")
