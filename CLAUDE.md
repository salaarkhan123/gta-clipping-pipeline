@AGENTS.md

# CLAUDE.md

Project: a public clip-generation API + website for GTA 6 clippers, with credit-based pricing. Full spec, decisions and checklists are in `SPEC.md`; read it before making architectural decisions.

## Where things are
- `clip-api/` is the product backend (FastAPI, worker, pipeline, tests, Docker). All new work goes here or in a sibling `web/` folder for the website.
- `test-tools/auto_clip.py` is the original YouTube-link CLI the pipeline was ported from. Keep it as a personal tool; do not wire it into the service.
- `code/`, `design-docs/`, `docs/` belong to a different, earlier design (multi-agent business automation). Leave them alone.

## Current phase
North-star goal first (SPEC.md section 14): a 2-hour VOD gives 30–50 ranked clips with previews in 10 minutes. Build the speed track (S0, S3, S1, S2, S4) and the understanding track (U1–U7) before anything else; every speed PR reports before/after with `scripts/job_timings.py`, every selection PR reports the eval set. The rest of the re-engineering plan (SPEC.md section 13) follows. Tickets live on the ClutchClips build board (`track:speed`, `track:understanding`, `phase:N` labels). Build PRs directly into `staging`; the board is for tracking only.

## Rules
- Ingestion: uploads, Google Drive / Dropbox imports, and public-link import (Twitch and Kick first; YouTube best effort, "may fail, upload instead").
  - Public, non-DRM content only. Never use logins, cookies, accounts, proxies, IP rotation, client spoofing or impersonation, or any other way around a block, paywall, age gate or rate limit. If a site refuses, fail cleanly and tell the user to upload the file.
  - Every link import requires the user to confirm they own the content or have permission to clip it, and is logged (source URL, account, time).
  - Every imported source can be removed through the takedown flow (all clips and files for a source URL or account).
- The pipeline stays one importable function, `run_pipeline`, with no web, database or hardcoded-path code.
- Credits are an append-only ledger. Never update or delete ledger rows. Every job is reserved once and settled once (`settle:<job_id>`). Any new failure path must end in a refund, with a test.
- Credit amounts for purchases come from server-side pack config, never from client or webhook-supplied numbers.
- Do not build deferred items (SPEC.md section 11). Every feature that costs money per use (AI, TTS, video generation, render or live minutes) has a credit price shown before the user confirms; credits, billing and pricing changes need the owner's explicit OK in the PR.
- Secrets only from environment variables. Never commit `.env`. API keys are stored hashed.
- All file access goes through `app/storage.py`. All ffmpeg inputs use `-protocol_whitelist file,pipe` and a timeout.
- The website calls the same public API as customers; no private endpoints.
- Schema changes go through Alembic (`app/migrations/`, see `app/migrate.py`): one reviewed revision per change, additive only (anything that drops, renames or rewrites data needs the owner's OK). `deploy.sh` migrates before the restart.

## Commands (run inside `clip-api/`)
- Tests: `pytest -q` (SQLite) or `TEST_DATABASE_URL=postgresql+psycopg://... pytest -q`
- Local API: `uvicorn app.main:app --reload`; worker: `python -m app.worker`
- Full stack: `docker compose up -d --build`
- Admin: `python scripts/admin.py --help`

## Style
Python type hints, Pydantic v2 models for request bodies, SQLAlchemy 2 style, small modules, errors as `ApiError(status, code, message)`. Frontend: Next.js App Router + Tailwind.
