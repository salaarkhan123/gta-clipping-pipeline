"""uploads.content_hash: sha256 of the uploaded bytes, to reuse a re-upload of the same file (0.3).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15

Additive: a nullable column and an index. Uploads from before this revision keep NULL and are never matched.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("uploads", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_uploads_account_hash", "uploads", ["account_id", "content_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_uploads_account_hash", table_name="uploads")
    op.drop_column("uploads", "content_hash")
