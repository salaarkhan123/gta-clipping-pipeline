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

# Premium AI thumbnails (#140): the named looks a user picks from. Each prompt describes a look only; the fixed
# rules (keep the face, add nothing, no text, brand-safe) are in app/imagegen/prompts.py and always come first.
# Override with PREMIUM_THUMB_STYLES (the same JSON shape).
DEFAULT_THUMB_STYLES = json.dumps([
    {"id": "cinematic", "name": "Cinematic",
     "prompt": "a cinematic film still: teal and orange color grade, soft volumetric light, gentle haze and depth in "
               "the background, rich contrast, a subtle vignette"},
    {"id": "high_energy", "name": "High-energy gaming",
     "prompt": "a high-energy gaming thumbnail: punchy saturated colors, strong colored rim light on the person, a "
               "soft glow outline around them, vivid contrast and motion energy in the existing background"},
    {"id": "clean", "name": "Clean professional",
     "prompt": "a clean professional look: balanced natural colors, crisp detail, soft even lighting, a slightly "
               "calmer, less cluttered background"},
    {"id": "dramatic", "name": "Dramatic",
     "prompt": "a dramatic look: deep shadows, moody low-key lighting with one strong key light on the person, a "
               "dark vignette and an intense atmosphere"},
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
    # Copyright and likeness reports (app/trust.py). TRUST_ADMIN_EMAIL: where new-report notices go (comma
    # separated); empty = every active admin account. Limits are per sender IP and per claimant email.
    trust_admin_email: str = ""
    trust_reports_per_ip_per_hour: int = 5
    trust_reports_per_ip_per_day: int = 20
    trust_reports_per_email_per_day: int = 3
    # Repeat infringers (owner, 2026-11-18: three strikes). Strikes expire after this many days; 0 = never.
    # Both are owner decisions (app/trust_decisions.py).
    repeat_infringer_strikes: int = 3
    repeat_infringer_strike_days: int = 0

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

    # AI titles, hashtags and the AI rating of each clip (optional; off when the key is empty). The rating is the
    # model's opinion of the clip, 0-100, never a probability or prediction of views or virality.
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"
    # (U3) With the AI key and a whole transcript of the upload, an LLM reads the transcript in 5-minute chunks and
    # proposes moments for the judge (app/pipeline/llm_pass.py). Costs tokens per job (measured in the U3 PR);
    # false: candidates are nominated from the signals only, as before.
    llm_pass: bool = True
    # (U4) Automatic discovery (a clip-length bucket and no clip count): the AI rating (0-100) a moment needs to become
    # a clip. No quota: a video gets as many clips as it has moments this good, never filler. Tune on tuning videos.
    clip_quality_floor: int = Field(40, ge=0, le=100)
    # Per-game weights of the five sub-scores, for ranking only: JSON {"<game or genre or default>": {"hook": n,
    # "payoff": n, "clarity": n, "emotion": n, "pacing": n}}. Empty: every game ranks by the plain mean. Fill it from
    # scripts/fit_score_weights.py, which fits on the owner's labels (tuning videos only).
    score_weights: str = ""

    # Premium AI thumbnails (#140, paid; owner OK 2026-11-17). Off until real provider testing and a quality check
    # are done: off, the premium routes answer 404 `premium_thumbnails_off` and /v1/options does not list them. The
    # free frame-based thumbnail is always made and stays free.
    premium_thumbnails: bool = False
    premium_thumb_credits: int = Field(25, ge=1)      # what one premium thumbnail costs: the only price used
    gemini_api_key: str = ""                          # Gemini Nano Banana 2.1 (image edit); a billing-enabled key only
    gemini_image_model: str = "gemini-nano-banana-2.1"
    gemini_image_size: str = "2K"                     # 1K | 2K | 4K (upper-case K)
    premium_thumb_timeout_sec: float = Field(60.0, ge=5, le=300)   # one provider attempt, end to end
    premium_thumb_styles: str = DEFAULT_THUMB_STYLES

    # Pipeline
    whisper_model: str = "small.en"   # captions. "none" disables transcription and captions
    whisper_index_model: str = "base.en"   # full-video search index: smaller and several times faster
    # Whole-recording transcription. "local" runs the Whisper models above; hosted providers are added with
    # their adapters. TRANSCRIBE_PARALLEL chunks run at once: leave it at 1 on a 4 vCPU server (one model already
    # uses every core) and raise it on a machine with 8 or more (see DEPLOY.md, "Measuring speed").
    transcription_provider: str = "local"
    transcribe_parallel: int = Field(1, ge=1, le=8)
    transcribe_chunk_sec: int = Field(300, ge=60, le=1800)
    # Clip Maker transcribes the whole recording first (with word timings) and keeps it for every later job on the
    # upload, instead of transcribing candidate windows only. Off by default: on the 4 vCPU droplet the local model
    # makes a 2-hour job slower (see DEPLOY.md, "Transcription settings"); turn it on with a hosted provider or a
    # bigger machine.
    transcribe_whole: bool = False
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
    def thumb_styles(self) -> list[dict]:
        return json.loads(self.premium_thumb_styles)

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
