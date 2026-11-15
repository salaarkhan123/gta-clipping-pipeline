# CLAUDE.md

Project: a public clip-generation API + website for GTA 6 clippers, with credit-based pricing. Full spec, decisions and checklists are in `SPEC.md`; read it before making architectural decisions.

## Where things are
- `clip-api/` is the product backend (FastAPI, worker, pipeline, tests, Docker). All new work goes here or in a sibling `web/` folder for the website.
- `test-tools/auto_clip.py` is the original YouTube-link CLI the pipeline was ported from. Keep it as a personal tool; do not wire it into the service.
- `code/`, `design-docs/`, `docs/` belong to a different, earlier design (multi-agent business automation). Leave them alone.

## Current phase
Backend core is done (SPEC.md section 10 A). Next: section 10 B (verify on a real server), C (website), D (deploy and go live). Tick items off in SPEC.md as they are finished.

## Rules
- Ingestion is uploads only. Do not add server-side link downloading, proxy rotation, client spoofing or any block-evasion.
- The pipeline stays one importable function, `run_pipeline`, with no web, database or hardcoded-path code.
- Credits are an append-only ledger. Never update or delete ledger rows. Every job is reserved once and settled once (`settle:<job_id>`). Any new failure path must end in a refund, with a test.
- Credit amounts for purchases come from server-side pack config, never from client or webhook-supplied numbers.
- Do not build deferred items (SPEC.md section 11).
- Secrets only from environment variables. Never commit `.env`. API keys are stored hashed.
- All file access goes through `app/storage.py`. All ffmpeg inputs use `-protocol_whitelist file,pipe` and a timeout.
- The website calls the same public API as customers; no private endpoints.
- There are no migrations yet: adding or changing a column needs Alembic first (tables are created with `create_all`).

## Commands (run inside `clip-api/`)
- Tests: `pytest -q` (SQLite) or `TEST_DATABASE_URL=postgresql+psycopg://... pytest -q`
- Local API: `uvicorn app.main:app --reload`; worker: `python -m app.worker`
- Full stack: `docker compose up -d --build`
- Admin: `python scripts/admin.py --help`

## Style
Python type hints, Pydantic v2 models for request bodies, SQLAlchemy 2 style, small modules, errors as `ApiError(status, code, message)`. Frontend: Next.js App Router + Tailwind.
