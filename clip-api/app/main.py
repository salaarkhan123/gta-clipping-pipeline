import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import routes_auth, routes_billing, routes_ingest, routes_media, routes_meta, routes_projects, routes_templates, routes_text, routes_thumbnails, routes_tools
from .config import get_settings
from .db import get_engine, init_db
from .deps import ApiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    s.check_production()
    if s.sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=s.sentry_dsn, traces_sample_rate=0.0)
    init_db()
    yield


app = FastAPI(title="Clip API", version="1.0.0", lifespan=lifespan,
              description="Turn long gameplay recordings into short captioned clips. 1 credit = 1 minute of source video.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(routes_auth.router, tags=["auth"])
app.include_router(routes_media.router, tags=["clips"])
app.include_router(routes_tools.router, tags=["tools"])
app.include_router(routes_text.router, tags=["languages"])      # (languages, agent F)
app.include_router(routes_projects.router, tags=["projects"])
app.include_router(routes_templates.router, tags=["templates"])
app.include_router(routes_meta.router, tags=["clips"])
app.include_router(routes_billing.router, tags=["billing"])
app.include_router(routes_ingest.router, tags=["imports"])     # link import (agent E)
app.include_router(routes_thumbnails.router, tags=["thumbnails"])   # premium thumbnails (#140)


@app.exception_handler(ApiError)
async def api_error(_request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse(status_code=422, content={"error": {
        "code": "validation_error", "message": f"{where}: {first.get('msg', 'invalid request')}".strip(": ")}})


@app.get("/health", tags=["ops"])
def health():
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True, "accepting_jobs": get_settings().accept_jobs}
