# Clip API

Upload a long gameplay recording, get short captioned clips back. 1 credit = 1 minute of source video. See `../SPEC.md` for the full product spec.

## Run locally (no Docker)

Needs Python 3.10+, ffmpeg with libass (on macOS: `brew install ffmpeg-full`).

```bash
cd clip-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # API on http://localhost:8000, docs at /docs
python -m app.worker                   # in a second terminal
pytest -q                              # tests (use WHISPER_MODEL=none to skip the model download when running the app)
```

Local defaults: SQLite database and file storage under `./data`, emails auto-verified, 30 free credits per signup.

## Try it

```bash
API=http://localhost:8000
TOKEN=$(curl -s $API/v1/auth/signup -H 'content-type: application/json' \
  -d '{"email":"you@yourdomain.com","password":"a-long-password"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
KEY=$(curl -s -X POST $API/v1/keys -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"test"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["key"])')

curl -s -X POST "$API/v1/uploads?filename=video.mp4" -H "authorization: Bearer $KEY" -T video.mp4
curl -s -X POST $API/v1/clips -H "authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"upload_id":"upl_...","options":{"max_clips":3,"clip_length":30,"chat_region":"top-right"}}'
curl -s $API/v1/jobs/job_... -H "authorization: Bearer $KEY"
```

Large files, when the server stores files in a bucket (`STORAGE_BACKEND=s3`): send them straight to the bucket in
resumable parts. `POST /v1/uploads/multipart {filename, size_bytes}` gives an `upload_token`;
`POST /v1/uploads/multipart/parts {upload_token}` gives signed PUT URLs for the parts not stored yet (call it again
to resume); `PUT` each part's exact bytes to its URL; `POST /v1/uploads/multipart/complete {upload_token}` returns
the upload, like `POST /v1/uploads`. `POST /v1/uploads/multipart/abort` discards the parts. Without a bucket the
first call answers 409 `direct_upload_unavailable`; use `POST /v1/uploads`.

## Deploy on one server

1. Create an Ubuntu 24.04 server (4 vCPU / 8 GB RAM or more; video work is CPU-heavy). Point a DNS A record for `api.yourdomain.com` at it.
2. Install Docker: `curl -fsSL https://get.docker.com | sh`
3. Copy this `clip-api/` folder to the server, then:
   ```bash
   cp .env.example .env && nano .env     # fill in every required value
   docker compose up -d --build          # first build downloads the speech model (a few minutes)
   docker compose ps                     # api should be "healthy"
   curl https://api.yourdomain.com/health
   ```
4. Stripe: add a webhook endpoint `https://api.yourdomain.com/webhooks/stripe` (payload style Snapshot) for these events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`, `charge.refunded`, `charge.dispute.created`, put its signing secret in `.env`, then `docker compose up -d`.
5. More throughput: `docker compose up -d --scale worker=2` (each worker runs one job at a time).

## Operate

```bash
docker compose exec api python scripts/admin.py --help   # accounts, keys, credits, stuck jobs
docker compose logs -f worker
docker compose exec db pg_dump -U clip clip > backup.sql # back this up off the server daily
```

Kill switch: set `ACCEPT_JOBS=false` in `.env` and run `docker compose up -d api`.

## Layout

- `app/pipeline/` detection and rendering (`run_pipeline`), no web or database code
- `app/ledger.py` append-only credit ledger (reserve, then commit or release exactly once)
- `app/worker.py` job worker, stale-job refunds, retention cleanup
- `app/routes_*.py` HTTP endpoints
- `skill/clip-api/` agent skill that drives the API
