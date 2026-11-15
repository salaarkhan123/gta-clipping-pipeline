# PROJECT.md — ClutchClips

Drafted by `super-board onboard` from `clip-api/README.md`, `SPEC.md` and the tree. `SPEC.md` is the source of truth; this is the map lane agents read first.

## What it is

Public clip-generation API and website for GTA 6 clippers (clutchclips.io). Users upload a long gameplay recording and get short captioned clips back. Credit pricing: 1 credit = 1 minute of source video.

## Where things live

| Path | What |
|---|---|
| `clip-api/app/pipeline/` | detection and rendering, `run_pipeline`. No web, DB or hardcoded-path code |
| `clip-api/app/ledger.py` | append-only credit ledger: reserve, then commit or release exactly once |
| `clip-api/app/worker.py` | job worker, stale-job refunds, retention cleanup |
| `clip-api/app/routes_*.py` | HTTP endpoints (auth, billing, media, tools) |
| `clip-api/app/storage.py` | ALL file access (local or S3/R2) |
| `clip-api/tests/` | pytest suite (SQLite default; Postgres via `TEST_DATABASE_URL`) |
| `clip-api/web-src/` | Next.js website source, exported static |
| `clip-api/web/` | built static site Caddy serves. Tracked on purpose |
| `clip-api/skill/clip-api/` | agent skill that drives the public API |
| `clip-api/scripts/admin.py` | admin CLI (accounts, keys, credits, stuck jobs) |

Not part of the product: `code/`, `design-docs/`, the old files in `docs/` (earlier design) and `test-tools/` (personal CLI). They are gitignored. NEVER wire them in.

## Commands (inside `clip-api/`)

| Task | Command |
|---|---|
| Tests | `pytest -q` |
| API | `uvicorn app.main:app --reload` |
| Worker | `python -m app.worker` |
| Full stack | `docker compose up -d --build` |

Needs Python 3.10+ and ffmpeg with libass.

## Stage (SPEC.md §10)

- A. Backend core: done.
- B. Verify on a real server: open (Docker build, faster-whisper end to end, S3/R2, Stripe Checkout, SMTP, long-VOD speed and cost).
- C. Website: static site built, legal pages missing.
- D. Deploy and go live: open.

## Hard rules (from CLAUDE.md)

- Uploads only. NEVER add server-side link downloading, proxy rotation or block evasion.
- Ledger rows are NEVER updated or deleted. Every job reserved once, settled once (`settle:<job_id>`). Every new failure path ends in a refund, with a test.
- Purchase credit amounts come from server-side pack config only.
- ffmpeg inputs use `-protocol_whitelist file,pipe` and a timeout.
- No migrations yet: a column change needs Alembic first.
- NEVER build SPEC.md §11 deferred items.
