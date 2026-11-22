import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import log_redact, routes_auth, routes_billing, routes_captions, routes_direct_upload, routes_export, routes_fonts, routes_ingest, routes_legal, routes_media, routes_meta, routes_projects, routes_publish, routes_templates, routes_text, routes_thumbnails, routes_tools, routes_trust
from .live import routes_live
from .config import get_settings
from .db import get_engine, init_db
from .deps import ApiError
from .render_options import refused_layout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log_redact.install()          # no verification or file token, and no key, in the request logs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    s.check_production()
    if s.sentry_dsn:
        log_redact.init_sentry(s.sentry_dsn)
    init_db()
    yield


# Commercial OpenAPI: versioned public customer API under /v1. The website uses these same routes
# (no private website-only endpoints). Interactive docs: /docs · machine-readable: /openapi.json.
OPENAPI_TAGS = [
    {"name": "auth", "description": "Sign up, log in, account profile, and API keys (Bearer `gck_…`)."},
    {"name": "clips", "description": "Upload video, quote and start clip jobs, poll jobs, credits balance, and clip edits."},
    {"name": "projects", "description": "Project library and clip listings for an account."},
    {"name": "tools", "description": "Reframe, burn captions, and find moments by what was said."},
    {"name": "imports", "description": "Authorized public-link import (Twitch/Kick first; YouTube best effort)."},
    {"name": "templates", "description": "Game templates, caption fonts, and saved brand looks."},
    {"name": "thumbnails", "description": "Clip thumbnail variants and optional premium styles."},
    {"name": "languages", "description": "Transcripts, translations, and summaries."},
    {"name": "billing", "description": "Credit packs, plans, checkout, and Stripe webhooks."},
    {"name": "legal", "description": "Published policies and account consent records."},
    {"name": "trust", "description": "Copyright and likeness reports; admin case review (session + admin only)."},
    {"name": "publishing", "description": "Connect social accounts; publish or schedule clips; calendar status. Off until PUBLISHING=true."},
    {"name": "live", "description": "Live clipping scaffold (creator-push). Off until LIVE_CLIPPING=true; mock only — not measured real-time."},
    {"name": "ops", "description": "Service health for load balancers and monitors."},
]

app = FastAPI(
    title="ClutchClips API",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    description=(
        "Versioned commercial API (`/v1`) for turning long gameplay recordings into short captioned clips.\n\n"
        "**Credits:** 1 credit = 1 minute of source video. Failed jobs are refunded. Quote before you confirm.\n\n"
        "**Auth:** `Authorization: Bearer` with a session token or an API key (`gck_…`). "
        "Create keys from the dashboard or `POST /v1/keys`.\n\n"
        "**Same API for the website:** the ClutchClips site calls only these public `/v1` routes "
        "(plus `/openapi.json` for feature detection and `/docs` for humans). "
        "There are no private website-only endpoints.\n\n"
        "**Core customer flow:** `POST /v1/uploads` → `POST /v1/clips/quote` / `POST /v1/clips` → "
        "`GET /v1/jobs/{job_id}` → download clips. Also: `GET /v1/options`, `GET /v1/credits`, "
        "`GET|POST|DELETE /v1/keys`."
    ),
)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(routes_auth.router, tags=["auth"])
app.include_router(routes_export.router, tags=["clips"])      # re-export and clip edits
app.include_router(routes_media.router, tags=["clips"])
app.include_router(routes_direct_upload.router, tags=["clips"])   # resumable uploads straight to the bucket
app.include_router(routes_tools.router, tags=["tools"])
app.include_router(routes_text.router, tags=["languages"])
app.include_router(routes_projects.router, tags=["projects"])
app.include_router(routes_templates.router, tags=["templates"])
app.include_router(routes_fonts.router, tags=["templates"])      # caption fonts
app.include_router(routes_captions.router, tags=["clips"])       # caption words for text editing
app.include_router(routes_meta.router, tags=["clips"])
app.include_router(routes_billing.router, tags=["billing"])
app.include_router(routes_ingest.router, tags=["imports"])
app.include_router(routes_thumbnails.router, tags=["thumbnails"])
app.include_router(routes_legal.router, tags=["legal"])
app.include_router(routes_trust.router, tags=["trust"])
app.include_router(routes_publish.router, tags=["publishing"])
app.include_router(routes_live.router, tags=["live"])


@app.exception_handler(ApiError)
async def api_error(_request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    refused = refused_layout(exc.errors())          # a provisional layout while PROVISIONAL_LAYOUTS is off
    if refused:
        return JSONResponse(status_code=400, content={"error": {"code": refused[0], "message": refused[1]}})
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse(status_code=422, content={"error": {
        "code": "validation_error", "message": f"{where}: {first.get('msg', 'invalid request')}".strip(": ")}})


@app.get("/health", tags=["ops"], summary="Health check")
def health():
    """Liveness for load balancers. `accepting_jobs` is false when the API is draining."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True, "accepting_jobs": get_settings().accept_jobs}
