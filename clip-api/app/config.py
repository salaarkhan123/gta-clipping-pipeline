"""All configuration comes from environment variables (see .env.example)."""
import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PACKS = json.dumps([
    # PLACEHOLDER PRICES. Set real ones after measuring cost per source minute.
    {"id": "pack_300", "name": "300 credits", "credits": 300, "price_cents": 499},
    {"id": "pack_1000", "name": "1,000 credits", "credits": 1000, "price_cents": 1299},
    {"id": "pack_5000", "name": "5,000 credits", "credits": 5000, "price_cents": 4999},
])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # "prod" enables startup safety checks
    database_url: str = "sqlite:///./data/dev.db"
    data_dir: str = "./data"
    secret_key: str = "dev-insecure-change-me"
    public_api_url: str = "http://localhost:8000"
    public_web_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Storage: "local" (dev/tests) or "s3" (Cloudflare R2 or any S3-compatible store)
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"
    signed_url_ttl_sec: int = 3600
    retention_days: int = 7

    # Limits and cost guards
    max_upload_bytes: int = 8 * 1024 ** 3
    max_duration_sec: int = 6 * 3600
    min_duration_sec: int = 20
    max_concurrent_jobs_per_account: int = 2
    rate_limit_per_minute: int = 120
    signup_limit_per_ip_per_hour: int = 5
    login_limit_per_ip_per_minute: int = 10
    accept_jobs: bool = True          # kill switch: false rejects new jobs
    daily_minutes_cap: int = 6000     # global source minutes accepted per UTC day
    job_timeout_factor: float = 3.0   # job timeout = max(900 s, duration * factor)
    max_render_sec: int = 6 * 3600    # reframe/captions: max video rendered per job
    charge_once_per_upload: bool = True   # after a video is analysed once, tools only charge for minutes rendered
    visual_search: bool = True        # Video Finder also searches what is on screen (CLIP)
    stale_job_minutes: int = 5        # RUNNING job with no heartbeat for this long is failed + refunded

    # Credits
    free_signup_credits: int = 30
    credit_packs: str = DEFAULT_PACKS
    currency: str = "usd"

    # Auth and email
    jwt_ttl_hours: int = 168
    auto_verify_email: bool = True    # dev default; set false in prod once SMTP is configured
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "no-reply@example.com"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    plans: str = ""                   # JSON list overriding app/plans.py DEFAULT_PLANS

    # AI titles, hashtags and virality scores (optional; off when the key is empty)
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"

    # Pipeline
    whisper_model: str = "small.en"   # captions. "none" disables transcription and captions
    whisper_index_model: str = "base.en"   # full-video search index: smaller and several times faster
    caption_font: str = "DejaVu Sans"
    worker_poll_sec: float = 2.0
    sentry_dsn: str = ""

    @property
    def packs(self) -> list[dict]:
        return json.loads(self.credit_packs)

    @property
    def work_dir(self) -> Path:
        p = Path(self.data_dir) / "work"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def storage_dir(self) -> Path:
        p = Path(self.data_dir) / "storage"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def check_production(self) -> None:
        """Refuse to start in prod with unsafe defaults."""
        if self.env != "prod":
            return
        problems = []
        if self.secret_key == "dev-insecure-change-me" or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a random string of 32+ characters")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point at Postgres")
        if self.auto_verify_email:
            problems.append("AUTO_VERIFY_EMAIL must be false (configure SMTP)")
        if problems:
            raise RuntimeError("Unsafe production config: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
