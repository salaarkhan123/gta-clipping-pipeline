"""All configuration comes from environment variables (see .env.example)."""
import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    # trio, grid4, ots and the auto layout chosen per moment are our own reading of WayinVideo's names, not yet
    # checked on real gaming footage. Off: they are not offered and auto draws one layout per video, as before.
    provisional_layouts: bool = False
    stale_job_minutes: int = 5        # RUNNING job with no heartbeat for this long is failed + refunded

    # Link import (app/ingest, agent E). An import is free; the imported file then follows the upload limits
    # above, so the lower of the two applies. The downloaders' own options are fixed in code, not settings.
    imports_enabled: bool = True              # kill switch: false refuses new imports and stops queued ones
    import_max_bytes: int = 8 * 1024 ** 3     # largest file an import may download
    import_max_duration_sec: int = 6 * 3600   # longest video an import may bring in
    import_timeout_sec: int = 1800            # the whole download; a slower one is stopped

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
    # Signup without accept_policies=true is refused (422 terms_required). Off by default so API clients written
    # before consent records keep working; the website always sends it. Owner decision (app/legal.py).
    require_terms_acceptance: bool = False

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # Stripe Price IDs for the plans in app/plans.py (created by the owner in Stripe, see DEPLOY.md). Prices and
    # credits themselves live in app/plans.py only; a plan whose Price ID is empty cannot be bought.
    stripe_price_starter_month: str = ""
    stripe_price_starter_year: str = ""
    stripe_price_pro_month: str = ""
    stripe_price_pro_year: str = ""
    stripe_price_scale_month: str = ""
    stripe_price_scale_year: str = ""

    # AI titles, hashtags and virality scores (optional; off when the key is empty)
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"

    # Pipeline
    whisper_model: str = "small.en"   # captions. "none" disables transcription and captions
    whisper_index_model: str = "base.en"   # full-video search index: smaller and several times faster
    # Whole-recording transcription. "local" runs the Whisper models above; hosted providers are added with
    # their adapters. TRANSCRIBE_PARALLEL chunks run at once: leave it at 1 on a 4 vCPU server (one model already
    # uses every core) and raise it on a machine with 8 or more (see DEPLOY.md, "Measuring speed").
    transcription_provider: str = "local"
    transcribe_parallel: int = Field(1, ge=1, le=8)
    transcribe_chunk_sec: int = Field(300, ge=60, le=1800)
    # Languages (agent F; app/languages.py). English always uses the two models above, exactly as before. Speech in
    # any other language uses the multilingual model of the same size: empty = worked out from the model above
    # (small.en -> small, base.en -> base). They are public models and are downloaded on first use unless the
    # image already has them (see the PR's "Wiring needed").
    whisper_multilingual_model: str = ""
    whisper_index_multilingual_model: str = ""
    language_detect: bool = True      # no source_lang sent: detect the spoken language. false: assume English, as before
    # Translation (transcripts, subtitle downloads) and video summaries. "none" (default): the feature answers "not
    # configured". "ai": the AI client above (needs ANTHROPIC_API_KEY; costs tokens per use, and nothing is charged
    # for it yet: see the PR's money questions). "standin" marks text instead of translating: tests and demos only.
    translation_provider: str = "none"
    summary_provider: str = "none"
    speaker_provider: str = "none"    # who is speaking, in transcripts. "none": `speaker` is null. No other provider yet
    caption_font: str = "DejaVu Sans"
    worker_poll_sec: float = 2.0
    # Jobs one worker process runs at once. 2 is the most a 4 vCPU / 8 GB server holds (ffmpeg and Whisper
    # both use every core); raise the limit only with a bigger server and a new benchmark.
    worker_concurrency: int = Field(1, ge=1, le=2)
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
