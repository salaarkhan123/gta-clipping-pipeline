# SPEC.md — ClutchClips API (clutchclips.io)

Source of truth for the public product. `CLAUDE.md` points here. Updated 2026-11-14 after reading the project folder and building the backend.

## 0. What was in this folder, and what changed

- The only working clipper was `test-tools/auto_clip.py`, a single CLI script that takes **YouTube links** via yt-dlp. `code/` holds a mock adapter that refuses real footage and a fragment importing a missing `backend.realty.engine`. `design-docs/` describes a different product (a multi-agent clipping business with owner approvals). None of that is touched or used by the API.
- The public service lives in **`clip-api/`** (new). Its pipeline is a port of `auto_clip.py` that works on **uploaded files**.
- Carried over from `auto_clip.py`: audio loudness, on-screen chat motion, window picking, the vertical layout with the chat panel, word-highlight captions.
- Not carried over (they only exist for YouTube links): the "Most replayed" heatmap, YouTube chat replay, any yt-dlp download.

## 1. Product

API + website that turns long gameplay/stream recordings into short, captioned, vertical-ready clips for GTA 6 clippers. API-first; the website dashboard and the agent skill call the same public API.

- 1 credit = 1 minute of source video, rounded up. Credits are reserved at submit and refunded automatically if the job fails, times out or is canceled.
- Every clip returns a `signals` breakdown (why it was picked).

## 2. Decisions (owner, 2026-11-14)

| Topic | Decision |
|---|---|
| Ingestion | **Uploads, Google Drive / Dropbox, and public-link import** (decision changed 2026-11-15; was uploads only). Twitch and Kick first, YouTube best effort. Public, non-DRM content only; never logins, cookies, proxies, IP rotation, client spoofing or other block evasion; owner-or-permission consent and an import log per link; takedown flow per source URL or account. |
| Launch scope | **Full public launch:** open signups and live payments. |
| Hosting | **One VM + Docker Compose** (Postgres, api, worker, Caddy). |
| Website login | **Built-in email + password** (backend-issued JWT). |

## 3. Stack (as built)

- Python 3.12 in Docker (code runs on 3.10+), FastAPI, Pydantic v2, SQLAlchemy 2 (sync), Postgres 16; SQLite for local dev and tests.
- **Job queue is the `jobs` table**: workers claim with `SELECT ... FOR UPDATE SKIP LOCKED`. No Redis, no Arq.
- Schema: Alembic migrations (`app/migrations/`), run by `scripts/deploy.sh` before the restart and at every start (`init_db`). Revision `0001` is the baseline; the pre-migration production database is stamped at it.
- ffmpeg (needs libass), faster-whisper (`small.en`, CPU int8, baked into the image), numpy.
- Storage interface with local-disk and S3/R2 implementations. Stripe Checkout (one-time packs). argon2 password hashes, HS256 JWTs. Caddy for HTTPS.
- Website (to build): Next.js App Router + Tailwind.

## 4. Architecture

```
Website / API clients / agent skill
        |  HTTPS  (session JWT or API key "gck_...")
      Caddy -> FastAPI (app/main.py) ---- Postgres: accounts, api_keys, uploads, jobs, clips, credit_ledger
                                              ^
      Worker(s) (app/worker.py) -- claim job, run_pipeline, store clips, settle credits, send webhook
        |
   Storage (local disk or R2): uploads/, clips/   -> signed, expiring URLs
   Stripe webhook -> credit top-up
```

The pipeline is one importable function with no web or database code:

```python
run_pipeline(input_path, options: PipelineOptions, out_dir, progress_cb=None, transcriber=None, deadline=None) -> list[ClipResult]
```

## 5. Detection pipeline (as built, `clip-api/app/pipeline/`)

1. **Probe** with ffprobe. All ffmpeg inputs use `-protocol_whitelist file,pipe` (uploads are untrusted).
2. **Audio signal** (always, if there is an audio track): RMS dB per second, z-score against a rolling 5-minute median/MAD baseline, smoothed and scaled. Weight 0.7.
3. **On-screen chat motion** (only if `chat_region` is set): edge-change rate in the top or bottom band of the frame, same baseline treatment, shifted 4 s earlier for chat lag. Weight 1.0. Slow on long videos because it decodes every frame.
4. **Fusion and windows:** weighted sum; highest-scoring non-overlapping fixed-length windows; intro/outro skipped; windows under 20% of the best score are dropped (fewer clips rather than filler).
5. **Whisper on candidates only:** twice as many candidates as requested (max 10) are transcribed with 4 s padding. Exclamation phrases add up to +0.15 to the score, then the top `max_clips` are kept. Clip edges snap to the nearest sentence boundary within 4 s.
6. **Render:** libx264 veryfast CRF 20; vertical 1080x1920 with blurred background and optional chat panel, or source aspect; burned-in word-highlight captions; thumbnail; captions JSON.
7. **Feature logging:** raw per-candidate features are stored in `clips.features`, and `POST /v1/clips/{id}/feedback` stores kept/discarded. This is the training data for the deferred learned ranker.

### Tools (added 2026-11-14, `app/pipeline/tools.py`, `app/routes_tools.py`)

| Tool | Endpoint | What it does | Cost |
|---|---|---|---|
| AI Clip Maker | `POST /v1/clips` | Detects highlights and renders them | 1 credit per source minute |
| AI Reframe | `POST /v1/reframe` | Renders the whole video or up to 10 `segments` as 9:16. Layouts: `split` (facecam top third, gameplay below), `fill`, `classic`; `auto` picks split when a facecam is given | 1 credit per rendered minute |
| AI Caption Generator | `POST /v1/captions` | Burns word-highlight captions into the whole video or segments. Styles: `pop`, `bold`, `neon`, `boxed`, `clean` | 1 credit per rendered minute |
| AI Video Finder | `POST /v1/find`, `GET /v1/uploads/{id}/search` | Finds moments by what was SAID (keyword/phrase search over the transcript), optionally cuts a clip per match. First search transcribes the upload and caches the transcript | First search: 1 credit per source minute. Later: clips rendered (min 1). GET search: free |

- Reframe and Captions render at most `MAX_RENDER_SEC` (30 min) per job.
- Video Finder searches speech only. It does not understand visuals (no "find the car chase").
- The facecam position is supplied by the user (`facecam_region` corner preset or `facecam_box`); there is no automatic facecam detection yet.
- Captions skip low-confidence segments (music lyrics, background chatter). Captioning only the main speaker needs diarization (deferred).
- Job results that are not clips (search matches) are returned in `job.result`. The `jobs.result` column is part of the baseline migration.

### Launch-tier additions (2026-11-14, second pass)

- **Subscriptions** (`app/plans.py`, `app/routes_billing.py`): Free, Starter, Pro, Scale. `POST /v1/billing/subscribe {plan_id, interval}` opens Stripe Checkout; `invoice.paid` grants the plan's monthly credits (12 months up front on yearly); `customer.subscription.deleted` returns the account to Free; `POST /v1/billing/portal` opens Stripe's portal. Credit packs still exist as top-ups. Credits do not expire. **Plan prices and credit amounts are placeholders.**
- **Plan limits:** export resolution (`max_side`: Free 720p, paid 1080p) and Reframe/Captions minutes per job (`max_render_min`). 2K/4K export is not built.
- **Aspect ratios:** `aspect` = 9:16, 4:5, 1:1, 16:9 on every tool.
- **Auto facecam:** `facecam_region: "auto"` (the default) finds a face that stays in one place and uses the split layout; falls back to full-frame when none is found.
- **Visual search:** Video Finder embeds one frame every 2 s with CLIP (local, free) and matches text to frames; `mode` = auto | speech | visual. Weaker than a multimodal model that watches the video.
- **Faster search index:** the full-video transcript uses `WHISPER_INDEX_MODEL` (base.en).
- **Charge once per upload:** after a full-price job succeeds on an upload, later jobs on it pay only for minutes rendered.
- **AI titles, hashtags, virality** (`app/ai.py`): one Anthropic Messages API call per clip when `ANTHROPIC_API_KEY` is set; without it clips have no title or score. The virality number is a model's opinion, not a forecast.
- **Subtitles:** `GET /v1/clips/{id}/subtitles?format=srt|vtt|txt`.
- **Self-check:** `python scripts/admin.py selftest` loads every model on the server.

Never run against the real services: Stripe subscription checkout and portal, the Anthropic API, the real CLIP and Whisper index models (tests use stand-ins). Run `selftest` and one real job of each kind after deploying.

Not built yet: AI Montage Maker, AI Video Enhancer, AI Video Editor, automatic facecam detection, speaker diarization, viewer-made Twitch clips prior, user-supplied chat logs, deep scan (full-source transcription), GTA HUD/event detectors. See section 11.

## 6. Data model (`app/models.py`)

`accounts`, `api_keys` (sha256 hash only), `uploads`, `jobs` (status QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELED, heartbeat, idempotency key unique per account), `clips`, `credit_ledger` (append-only, unique idempotency key), `webhook_deliveries`.

## 7. Credits (`app/ledger.py`)

- Balance = SUM(delta). Rows are never updated or deleted. Credits do not expire at launch.
- Submit, in one transaction: lock the account row, check limits, insert the job, insert `reserve` (-cost); 402 `insufficient_credits` if short.
- Each job is settled exactly once under the key `settle:<job_id>`: `commit` on success, `release` (+cost) on failure, timeout, cancel or worker loss. A second settle is a no-op.
- Grants: one-time free signup grant after email verification (`signup:<account_id>`); Stripe top-ups keyed on the Checkout Session id, with the credit amount taken from server-side pack config.
- **Pack prices in `config.py` are placeholders.** Measure cost per source minute on the real server, then set `CREDIT_PACKS`. Reference: WayinVideo's yearly plans come to about $0.010-0.012 per credit.

## 8. API (all built; interactive docs at `/docs`)

```
POST /v1/auth/signup | login | forgot | reset | resend-verification     GET /v1/auth/verify
GET  /v1/me
POST /v1/keys   GET /v1/keys   DELETE /v1/keys/{id}          (website session only)
POST /v1/uploads?filename=NAME      raw file body, streamed with a size cap
POST /v1/clips                      {upload_id, options, webhook_url?}, Idempotency-Key header -> 202
GET  /v1/jobs/{id}   GET /v1/jobs   POST /v1/jobs/{id}/cancel
POST /v1/clips/{id}/feedback        {kept}
POST /v1/reframe   POST /v1/captions   POST /v1/find   GET /v1/uploads/{id}/search   GET /v1/uploads
GET  /v1/credits
GET  /v1/billing/packs   POST /v1/billing/checkout {pack_id}   POST /webhooks/stripe
GET  /health
```

Options: `max_clips` 1-10 (3), `clip_length` 10-60 s (30), `vertical` (true), `chat_region` none/top-right/top-center/top-left/bottom-right/bottom-left (none), `zoom` 1.0-1.6, `captions` (true).
Errors: `{"error": {"code", "message"}}` with 401, 402, 403, 404, 413, 415, 422, 429, 503.
Job webhooks: POST to a public https URL only (private and local addresses are rejected), signed with `X-ClipAPI-Signature: sha256=<hmac of body with the account's webhook_secret>`.

## 9. Limits, safety, ops (as built)

- Env-configurable: max upload 8 GB, max duration 6 h, 2 concurrent jobs per account, per-account rate limit, signup and login throttles per IP, global daily source-minutes cap, `ACCEPT_JOBS` kill switch, job timeout = max(15 min, 3x duration).
- Workers heartbeat every 30 s; a RUNNING job with no heartbeat for 5 minutes is failed and refunded, and a worker that comes back late cannot flip it to SUCCEEDED.
- Files are deleted after `RETENTION_DAYS` (7). Signed URLs expire after 1 hour.
- Production startup refuses default secrets, SQLite, or auto-verified email.
- Rate limiting is in-memory (one API process). Move it to Redis if the API is scaled out.
- Admin: `scripts/admin.py` (create account, mint key, grant credits, suspend, list stuck jobs).

## 10. Checklists

### A. Backend core — DONE (2026-11-14)
- [x] Pipeline ported from `auto_clip.py` to file-based `run_pipeline`
- [x] Accounts, login, email verification, password reset, API keys
- [x] Uploads, jobs, cancel, feedback, credits endpoints
- [x] Postgres-backed queue, worker, heartbeat, stale-job refund, retention sweeper
- [x] Credit ledger with reserve/commit/release
- [x] Stripe Checkout + webhook
- [x] Local and S3/R2 storage
- [x] Limits and cost guards
- [x] Dockerfile, docker-compose, Caddyfile, `.env.example`, README
- [x] Agent skill (`clip-api/skill/clip-api/`)
- [x] Deployed 2026-11-14 to https://api.clutchclips.io (DigitalOcean, bootstrap config: ENV=dev, auto-verify on, Stripe off)
- [x] Tools: Reframe, Captions, Video Finder; split/fill layouts; caption styles
- [x] 55 tests: all pass on Postgres 16, 54 on SQLite where the row-locking test is skipped (refund on failure/crash/cancel/worker loss, idempotent submit, parallel overspend, forged webhook)

### B. Not yet verified — do first on the server
- [x] `docker compose up --build`: production runs on it (DigitalOcean droplet); CI builds the image on every PR (#2 / PR #9)
- [x] faster-whisper end to end: opt-in test (#3 / PR #10); the server benchmark below ran `small.en` captions in the production image
- [x] S3/R2 storage against a real bucket: `scripts/check_storage.py` (#4 / PR #13), run by the owner
- [x] Stripe Checkout session creation: test-mode check (#5 / PR #14), run by the owner
- [x] Real SMTP delivery: `admin.py send-test-email` (#6 / PR #15), confirmed by the owner
- [x] Speed and cost on a multi-hour 1080p VOD, especially with `chat_region` set
  - **Server run (production), 2026-11-15**, through the live API (not `bench_pipeline.py`). DigitalOcean `s-4vcpu-8gb` (4 shared vCPU, 8 GB), Toronto, same Docker image as production; Whisper `small.en` (captions), `base.en` (index). Input `GTA_Benchmark_2Hours.mkv`, 2:00:18, 2,848 MB, 1080p; split layout, facecam auto, pop captions, 9:16, no chat region.

    | Run | Job | Clips | Total | Real time | Transcribing | Rendering | Credits |
    |---|---|---|---|---|---|---|---|
    | A | `job_f176e3fb591249be9d356114` | 3 | 675.4 s | 10.7× | 200.4 s | 397.6 s | 121 |
    | B | `job_c6d8edabf3fe44d18a33ebba` | 10 | 932.7 s | 7.7× | 257.0 s | 578.4 s | 121 |

  - Run A stages: downloading 11.7 s, probing 17.6 s, audio 47.9 s, transcribing 200.4 s, rendering 397.6 s, uploading 0.1 s.
  - Rendering is ~59% of processing (A: 58.9%, B: 62.0%); transcribing ~30% (A). 3 → 10 clips adds 257.3 s (+38%).
  - Upload is separate from processing: ~20 min at ~19 Mbps on a home connection for 2,848 MB.
  - Findings: clip picking was 95–100% audio-driven; AI titles missing on 8 of 10 clips in run B (reply parse failure); a re-upload of the same file is charged again (charge-once is per upload, not per file).
  - `chat_region` was not part of the server run; its cost on the server is still unmeasured.
  - **Local development benchmark, not production.** Measured 2026-11-15 on the owner's Apple Silicon MacBook Air with `scripts/bench_pipeline.py` (card #7), `GTA_Benchmark_2Hours.mkv`, 120.29 min, 1920x1080:

    | Run | wall_seconds | realtime_factor | peak_rss_mb | clips | credits | chat_region |
    |---|---|---|---|---|---|---|
    | No chat region | 42.68 | 169.09 | 1084.6 | 3 | 121 | none |
    | Chat region | 279.22 | 25.85 | 1072.4 | 3 | 121 | top-right |

  - Runtime: `chat_region` makes the job 6.5× slower (+236.5 s, 42.68 s → 279.22 s; realtime factor 169 → 26). Onscreen chat motion decodes the whole 1080p video; without it, only cheap audio signals scan the full source and Whisper runs on candidate windows only. Memory is flat (~1.1 GB peak) either way. Credits are `ceil(source minutes)`, so both runs charge 121.
  - Apple Silicon numbers do not transfer to the server's x86 vCPUs, and this run used `bench_pipeline.py` defaults rather than the server run's layout and caption options; size pricing and the server from the server run above.

### C. Website — BUILT 2026-11-14 as a static site in `clip-api/web/` (plain HTML/CSS/JS, no build step, served by Caddy; not Next.js). Covers: homepage upload flow, signup/login/reset, pricing with subscriptions, dashboard (all four tools, jobs, clips, credits, API keys). Legal pages are still missing.
### C (original checklist)
- [ ] Next.js app: landing page (upload box, 3-step explainer, sample clips), pricing, docs link, signup/login, verify and reset-password pages
- [ ] Dashboard: upload with progress, options form, job list with live status, clip previews with download and keep/discard, credits balance and history, API keys, buy credits
- [ ] Legal pages: Terms, Privacy, content-rights acceptance at signup, takedown contact (get them reviewed)

### D. Deploy + go live (Day 2-3)
- [ ] Server, domain, DNS, `.env`, `docker compose up -d --build`
- [ ] SMTP provider (e.g. Resend, Postmark) and `AUTO_VERIFY_EMAIL=false`
- [ ] R2 bucket (or stay on local disk with enough disk space) and off-server Postgres backups
- [ ] Stripe account verified, live keys, webhook endpoint, real pack prices
- [ ] Sentry DSN
- [ ] Run the section B checks, then open signups

## 11. Deferred (do NOT build unless the owner asks)
Learned ranker (`clip_feedback` collects its training data from 1.2), team seats, Chrome extension, mobile app, Enterprise features, viewer-made Twitch clips prior, user-supplied chat logs, deep scan, credit expiry, local download CLI, MCP server.

Moved out of this list on 2026-11-15 because they are built or now planned (section 13): VLM re-rank (the AI judge), subscriptions and yearly plans (live), Alembic (0.7), presigned / resumable uploads (4.4b), Google Drive import (4.4c), live chat via official chat APIs (4.5), per-game detection tuning (2.4; HUD detectors only once the 0.6 eval set can measure them).

## 12. Definition of done (launch)
- A new user can sign up, verify email, get free credits, upload, receive captioned clips, buy credits, and see the balance change correctly.
- A failed, timed-out, canceled or orphaned job always refunds exactly once (tested).
- Duplicate submits with the same Idempotency-Key never double-charge (tested).
- One oversized or malicious input cannot exceed the limits in section 9.
- Cost per source minute is measured and pack prices cover it.

## 13. Re-engineering plan (approved 2026-11-15)

Goal: match what the leading clipping tools offer gaming clippers, with a cleaner, faster product built only for gameplay plus a facecam. Own brand and copy (palette: dark, lime `#b8ff3c`, cyan `#3cf0ff`; Poppins and Inter). Never claim an unbuilt feature: hide it or mark it "Coming soon". Every feature that costs money per use has a credit price shown before the user confirms; money paths need the owner's OK in the PR. Every non-Claude price is verified in its ticket before approval.

Work phase by phase; a phase starts after the owner merges the one before. PRs into `staging` with tests. One ticket per item on the ClutchClips build board (`phase:N` labels); the board tracks, it does not run.

| Phase | Items |
|---|---|
| 0 Foundations | 0.0 rules and spec · 0.1 deploy from git · 0.2 clip quality (variety, facecam crop, caption lines, censor, coverage check, AI truncation) · 0.3 re-upload dedupe (money) · 0.4 `WORKER_CONCURRENCY` (default 1, max 2 on s-4vcpu-8gb) · 0.5 Spaces storage · 0.6 quality eval set · 0.7 Alembic |
| 1 Library and editor | 1.1 projects and sidebar · 1.2 sort, filter, feedback · 1.3 score as rank + tier, raw score and breakdown in a tooltip · 1.4a–d editor (edit-decision list, captions, layout and boxes, filler and pause removal) · 1.5 bulk actions and ZIP |
| 2 Layouts, captions, templates | 2.1a–b layouts · 2.2 15+ caption presets · 2.3 multilingual + translated line · 2.4 game templates · 2.5 brand kit |
| 3 AI editing | 3.1 noise reduction and crossfades · 3.2 AI hook, later TTS · 3.3 natural-language find · 3.4 montage (one-off royalty-free music license) · 3.5 B-roll |
| 4 Publishing and ingestion | 4.0 platform approvals (owner) · 4.1 OAuth publishing · 4.2 calendar and scheduler · 4.3 bulk import · 4.4a–d link import, resumable uploads, Drive/Dropbox, failure alerts · 4.5a–d live clipping |
| 5 Website | home, tool pages, gaming page, pricing from plan config, quality floor, DRAFT legal pages |

## 14. North-star goal (approved 2026-11-16)

A streamer finishes a 2–4 hour stream and, when they open ClutchClips, 30–50 candidate clips are already found, ranked by a 0–100 score, and playable as vertical previews with captions, framing and thumbnails, ready to review, edit and export. Speed and understanding come before everything else in section 13.

**Targets**, end to end from "file or link available on the server" to "clips visible":

| What | Target |
|---|---|
| 2-hour VOD: 30–50 ranked clips with playable previews | 10 minutes or less (stretch: 5) |
| 4-hour VOD | 15 minutes or less |
| 1080p export of one clip | 30 seconds or less |
| Batch export of 40 clips | 3 minutes or less |

Starting point (server, 2026-11-15): a 2-hour VOD gave 10 clips in 932.7 s (transcribing 257 s, rendering 578 s). Every speed PR reports before and after with `scripts/job_timings.py`; every selection PR reports precision@20, precision@40 and recall on the eval set.

**Infrastructure: setup B.** The current droplet for the API, database and analysis; hosted transcription behind config; one 16-vCPU CPU-optimized render worker. The owner provisions and pays; nothing is signed up for or deployed by an agent. Hosted transcription sends users' audio to a third party, so the Terms and Privacy pages must say so.

**Design decisions**
- No full video proxy: decoding two hours costs more than rendering the preview windows from the source. Audio is extracted once (16 kHz mono); visual analysis runs on sparse frames.
- Previews first (540×960, fast preset, all clips in parallel), 1080p only on export or download, cached. Preview renders are included in the credit price; export limits per plan are a money change for the owner.
- Results are progressive: clips appear as they finish.
- The 0–100 score goes on the clip card only after calibration against the eval set (until then: rank and tier, section 13 item 1.3).
- Link import tries any URL and stays inside the ingestion rule (no logins, cookies, proxies or block evasion); the site lists only platforms verified to work.
- Thumbnails: best frame with the hook text is free; AI-generated thumbnails are a paid option, priced in their own ticket.

| Track | Tickets (build order: S0, S3, S1, S2, then S4; U6 alongside; U1 to U5; U7) |
|---|---|
| Speed | S0 stage timing and before/after script (#94) · S3 full audio once, transcription provider (#95) · S1 stage queue, progressive results (#96) · S2 previews first, export on demand (#97) · S4 worker roles for a render machine (#98) · S5 GPU / NVENC benchmark (#99) |
| Understanding | U1 whole transcript with speakers (#100) · U2 per-second signal timeline (#101) · U3 LLM pass over transcript chunks (#102) · U4 judge v2 with sub-scores, 15–60 s story cuts (#103) · U5 score calibration (#104) · U6 eval set v2, about 100 moments over 3 VODs (#105) · U7 thumbnails (#106) |

After these: the dashboard redesign and the editor (1.4), then link import and automation (4.x). Changes to section 13: per-quarter nomination (0.2e) is replaced by U3; 1.5 bulk export joins S2; 3.3 becomes Video Finder on the U1 transcript; 2.4 grows into a template gallery across games; 4.5 gains chat logging; auto-processing when a stream ends is new (4.6, with a credit cap: money).
