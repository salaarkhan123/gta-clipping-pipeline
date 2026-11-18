"""Database tables. All timestamps are naive UTC."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended
    plan: Mapped[str | None] = mapped_column(String(20), default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # What Stripe last said about the subscription: active | trialing | past_due | unpaid | paused | canceled.
    subscription_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    subscription_cancel_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # set to end on this date
    subscription_event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)    # newest Stripe event applied
    webhook_secret: Mapped[str] = mapped_column(String(80))
    signup_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 of the full key
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (Index("ix_uploads_account_hash", "account_id", "content_hash"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(400))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    duration_sec: Mapped[float] = mapped_column(Float)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    has_audio: Mapped[bool] = mapped_column(Boolean)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)   # a full-price job has succeeded on it
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)   # sha256 of the file's bytes
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)   # where a link import came from
    source_platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)        # spoken language, once detected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_job_idem"),
        Index("ix_jobs_account_created", "account_id", "created_at"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"))
    status: Mapped[str] = mapped_column(String(12), default="QUEUED")  # QUEUED RUNNING SUCCEEDED FAILED CANCELED
    options: Mapped[dict] = mapped_column(JSON)
    duration_sec: Mapped[float] = mapped_column(Float)
    credits_reserved: Mapped[int] = mapped_column(Integer)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # tool output (e.g. search matches)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)          # the project name the user gave
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Clip(Base):
    __tablename__ = "clips"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    signals: Mapped[dict] = mapped_column(JSON)    # per-signal contribution, shown to users
    features: Mapped[dict] = mapped_column(JSON)   # raw features, training data for the future ranker
    video_key: Mapped[str] = mapped_column(String(400))
    thumb_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    captions_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # title, description, hashtags, virality
    kept: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reaction: Mapped[str | None] = mapped_column(String(8), nullable=True)   # like | dislike
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)              # 0 = best in its run
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)           # funny | argument | reaction | clutch | fail | story
    preview_key: Mapped[str | None] = mapped_column(String(400), nullable=True)   # fast low-resolution render
    export_key: Mapped[str | None] = mapped_column(String(400), nullable=True)    # latest full-quality render
    export_res: Mapped[str | None] = mapped_column(String(8), nullable=True)
    edit: Mapped[dict | None] = mapped_column(JSON, nullable=True)                # edit decisions saved by the editor
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ClipFeedback(Base):
    """Append-only log of what users did with clips: training data for the future ranker. Current state is on Clip."""
    __tablename__ = "clip_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[str] = mapped_column(ForeignKey("clips.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))    # kept | reaction | bookmarked
    value: Mapped[str | None] = mapped_column(String(8), nullable=True)   # true/false, like/dislike, or NULL = cleared
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Export(Base):
    """One request to render a clip at full quality with given options."""
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    clip_id: Mapped[str] = mapped_column(ForeignKey("clips.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    resolution: Mapped[str] = mapped_column(String(8))
    options: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="QUEUED")
    storage_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ImportLog(Base):
    """Append-only record of every link import: who asked for which URL and that they confirmed their rights."""
    __tablename__ = "import_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    consent: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CustomTemplate(Base):
    """A look an account saved for reuse: a name and the clip options it sets. Never changes what a job costs."""
    __tablename__ = "custom_templates"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    options: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Payment(Base):
    """One paid Stripe purchase that granted credits: a credit pack (Checkout Session) or a plan invoice.
    Kept so a refund or dispute can take back exactly what that payment granted, once."""
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))                       # pack | plan
    stripe_ref: Mapped[str] = mapped_column(String(80), unique=True)    # Checkout Session id or invoice id
    payment_intent: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits: Mapped[int] = mapped_column(Integer)                       # granted by this payment
    credits_removed: Mapped[int] = mapped_column(Integer, default=0)    # taken back (or written off) after refunds
    status: Mapped[str] = mapped_column(String(12), default="paid")     # paid | partial | refunded | disputed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CreditLedger(Base):
    """Append-only. Balance is SUM(delta). Rows are never updated or deleted."""
    __tablename__ = "credit_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))  # grant topup reserve commit release adjust
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
