"""Baseline: the schema as create_all built it (plus the columns _add_missing_columns used to add).

Revision ID: 0001
Revises:
Create Date: 2026-11-15

A database that predates migrations is stamped at this revision by app.migrate instead of running it.
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('accounts',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('email_verified', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('plan', sa.String(length=20), nullable=True),
    sa.Column('stripe_customer_id', sa.String(length=64), nullable=True),
    sa.Column('stripe_subscription_id', sa.String(length=64), nullable=True),
    sa.Column('webhook_secret', sa.String(length=80), nullable=False),
    sa.Column('signup_ip', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_accounts_email', 'accounts', ['email'], unique=True)
    op.create_index('ix_accounts_stripe_customer_id', 'accounts', ['stripe_customer_id'], unique=False)

    op.create_table('api_keys',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('account_id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('prefix', sa.String(length=16), nullable=False),
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_api_keys_account_id', 'api_keys', ['account_id'], unique=False)
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'], unique=True)

    op.create_table('uploads',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('account_id', sa.String(length=40), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=400), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('duration_sec', sa.Float(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('has_audio', sa.Boolean(), nullable=False),
    sa.Column('analyzed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_uploads_account_id', 'uploads', ['account_id'], unique=False)

    op.create_table('jobs',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('account_id', sa.String(length=40), nullable=False),
    sa.Column('upload_id', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('options', sa.JSON(), nullable=False),
    sa.Column('duration_sec', sa.Float(), nullable=False),
    sa.Column('credits_reserved', sa.Integer(), nullable=False),
    sa.Column('credits_charged', sa.Integer(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('progress', sa.Integer(), nullable=False),
    sa.Column('stage', sa.String(length=40), nullable=True),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('webhook_url', sa.String(length=500), nullable=True),
    sa.Column('idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('cancel_requested', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['upload_id'], ['uploads.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'idempotency_key', name='uq_job_idem')
    )
    op.create_index('ix_jobs_account_created', 'jobs', ['account_id', 'created_at'], unique=False)
    op.create_index('ix_jobs_status_created', 'jobs', ['status', 'created_at'], unique=False)

    op.create_table('clips',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('job_id', sa.String(length=40), nullable=False),
    sa.Column('idx', sa.Integer(), nullable=False),
    sa.Column('start_sec', sa.Float(), nullable=False),
    sa.Column('end_sec', sa.Float(), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('signals', sa.JSON(), nullable=False),
    sa.Column('features', sa.JSON(), nullable=False),
    sa.Column('video_key', sa.String(length=400), nullable=False),
    sa.Column('thumb_key', sa.String(length=400), nullable=True),
    sa.Column('captions_key', sa.String(length=400), nullable=True),
    sa.Column('meta', sa.JSON(), nullable=True),
    sa.Column('kept', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_clips_job_id', 'clips', ['job_id'], unique=False)

    op.create_table('credit_ledger',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.String(length=40), nullable=False),
    sa.Column('delta', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('job_id', sa.String(length=40), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_credit_ledger_account_id', 'credit_ledger', ['account_id'], unique=False)

    op.create_table('webhook_deliveries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('job_id', sa.String(length=40), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=True),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_webhook_deliveries_job_id', 'webhook_deliveries', ['job_id'], unique=False)


def downgrade() -> None:
    raise RuntimeError("the baseline is not reversible: it would drop every table, the credit ledger included")
