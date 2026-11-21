"""Social publishing: connected accounts and scheduled posts.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-21

Additive only: two new tables. No DROP/RENAME. Tokens encrypted at rest in the app layer.
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("access_token_enc", sa.Text(), nullable=True),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "platform", "external_id", name="uq_social_account"),
    )
    op.create_index("ix_social_accounts_account_id", "social_accounts", ["account_id"], unique=False)

    op.create_table(
        "scheduled_posts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("clip_id", sa.String(length=40), nullable=False),
        sa.Column("social_account_id", sa.String(length=40), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("request_key", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.JSON(), nullable=True),
        sa.Column("privacy", sa.String(length=40), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("publish_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("step", sa.String(length=40), nullable=True),
        sa.Column("external_ref", sa.String(length=400), nullable=True),
        sa.Column("external_id", sa.String(length=120), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"]),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clip_id", "social_account_id", "request_key", name="uq_scheduled_post_idem"),
    )
    op.create_index("ix_scheduled_posts_account_id", "scheduled_posts", ["account_id"], unique=False)
    op.create_index("ix_scheduled_posts_clip_id", "scheduled_posts", ["clip_id"], unique=False)
    op.create_index("ix_scheduled_posts_social_account_id", "scheduled_posts", ["social_account_id"], unique=False)
    op.create_index("ix_scheduled_posts_due", "scheduled_posts", ["status", "publish_at", "next_attempt_at"], unique=False)
    op.create_index("ix_scheduled_posts_account_created", "scheduled_posts", ["account_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scheduled_posts_account_created", table_name="scheduled_posts")
    op.drop_index("ix_scheduled_posts_due", table_name="scheduled_posts")
    op.drop_index("ix_scheduled_posts_social_account_id", table_name="scheduled_posts")
    op.drop_index("ix_scheduled_posts_clip_id", table_name="scheduled_posts")
    op.drop_index("ix_scheduled_posts_account_id", table_name="scheduled_posts")
    op.drop_table("scheduled_posts")
    op.drop_index("ix_social_accounts_account_id", table_name="social_accounts")
    op.drop_table("social_accounts")
