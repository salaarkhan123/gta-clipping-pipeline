# Data map

What personal and customer data ClutchClips collects, where it is kept, for how long, who can read it, and which
outside companies receive it. Written from the code on `staging` at `0463321` (after #135 and #136) plus this branch (2026-11-18).
Every legal page (`/privacy`, `/terms`, `/cookies`, …) must agree with this file. When the code changes what it
collects or who it sends it to, change this file in the same PR.

> Draft for the owner and a lawyer to review. It describes what the code does; it is not legal advice.

Paths are relative to `clip-api/`. "Admin" means a person with shell access to the server (today only the owner;
`scripts/admin.py`). No in-app admin role exists yet (#145 adds one).

## 1. Account and login

| Data | Where | Kept | Who can read | Sent to |
|---|---|---|---|---|
| Email address | `accounts.email` (`app/models.py:22`) | Until the account is deleted. No self-serve deletion yet (#149) | The user (`GET /v1/me`), admin | Resend, the email provider (every email), Stripe (`customer_email` at first checkout, `app/routes_billing.py:71`, `:118`) |
| Password | `accounts.password_hash`, argon2 (`app/models.py:23`, `app/security.py:17`) | Until deleted | Nobody can read the password; admin sees the hash | Nobody |
| Sign-up IP address | `accounts.signup_ip` (`app/models.py:34`, set at `app/routes_auth.py` signup) | Until deleted | Admin | Nobody |
| Verified flag, plan, status, created time | `accounts` | Until deleted | The user, admin | Nobody |
| Webhook signing secret | `accounts.webhook_secret` (`app/models.py:33`) | Until deleted | The user (session only, `GET /v1/me`), admin | Nobody |
| Session token (JWT, 168 h) | Not stored on the server. The browser keeps it in `localStorage["cc_token"]` (`web-src/lib/api.ts:8`) | Until it expires or the user logs out | The user's browser | Nobody |
| API keys | `api_keys.key_hash` (sha256 only), `prefix`, `name`, `last_used_at` (`app/models.py:39-47`) | Until deleted; revoked keys stay as rows | The user (name, prefix, dates), admin (hash) | Nobody |
| Policy acceptances (new) | `policy_acceptances`: policy, version, source, time (`app/models.py:211`) | Append-only, kept for the life of the account (proposal in #150) | The user (`GET /v1/me/consents`), admin | Nobody |
| Rate-limit counters | Process memory, keyed by IP or account id (`app/deps.py:20`) | Up to 1 hour, lost on restart | Nobody | Nobody |

## 2. Videos and what is made from them

Storage is local disk or a private S3-compatible bucket (DigitalOcean Spaces in production). Every read goes
through `app/storage.py`. Downloads are signed links that expire after `SIGNED_URL_TTL_SEC` (1 hour,
`app/config.py:35`).

| Data | Where | Kept | Who can read | Sent to |
|---|---|---|---|---|
| Uploaded video (may show the streamer's face, voice, other people, chat usernames) | `uploads/<account>/<upload>.<ext>`; row in `uploads` with filename, size, length, hash (`app/models.py:50-70`) | `RETENTION_DAYS` (7) after upload, then the file is deleted and the row marked (`app/worker.py:501`) | The user (signed link), admin | Storage provider only |
| Imported link: source URL, platform | `uploads.source_url`, `uploads.source_platform` | Same as the upload | The user, admin | The platform (Twitch, Kick, YouTube) is contacted to download it (`app/ingest/platforms.py`) |
| Import log: account, URL, platform, consent, time | `import_log` (`app/models.py:154`) | No limit today (gap, #150) | Admin | Nobody |
| Transcript (words spoken, with times) and search index | `transcripts/<upload>.json`, `index/<upload>.npz` (`app/storage.py`) | Deleted with the upload (`app/worker.py:509-510`) | The user (`GET /v1/transcripts/<upload>`), admin | Anthropic, when translation or summaries are switched on (`TRANSLATION_PROVIDER=ai`, `SUMMARY_PROVIDER=ai`) |
| Clips: video, thumbnail, captions JSON, preview, export | `clips/<job>/<clip>.*`, `exports/<export job>/<export id>.mp4` (`app/worker.py:257`, `:315`); rows in `clips`, `exports` | `RETENTION_DAYS` after the job: video, thumbnail, captions, preview and the latest export (`clips.export_key`) are deleted (`app/worker.py:516`). Gap: earlier exports of the same clip (other `exports` rows) stay, and a worker-lost job leaves its export file (`app/worker.py:488`, #150) | The user (signed links), admin | Storage provider |
| AI copy per clip: titles, hook, description, hashtags, rating, reason | `clips.meta` (`app/models.py:116`) | Row kept after files are deleted (no limit, #150) | The user, admin | Made by Anthropic from the data below |
| Ranking features and feedback (kept, like, bookmark) | `clips.features`, `clip_feedback` (`app/models.py:112`, `:130`) | No limit (training data for a future ranker) | Admin | Nobody |
| Job options, including the user's free-text `prompt` and project name | `jobs.options`, `jobs.name` (`app/models.py:83`, `:94`) | No limit | The user, admin | The prompt goes to Anthropic with the clip (`app/ai.py:275`) |
| Saved looks (custom templates) | `custom_templates` | Until the user deletes one (soft delete) | The user, admin | Nobody |
| Clip edits from the editor | `clips.edit`; unsent drafts in the browser's `localStorage` (`web-src/lib/edit.ts:35`) | Row: no limit. Browser: until sent or cleared | The user | Nobody |

## 3. AI processing (what leaves the server)

| Step | Runs where | What is sent | Provider retention (their documents) |
|---|---|---|---|
| Speech to text | On our server: faster-whisper (`app/pipeline/transcribe.py`). `TRANSCRIPTION_PROVIDER=local` is the only provider built (`app/config.py`) | Nothing leaves the server | n/a |
| Visual search (CLIP) and face detection for the facecam | On our server (`app/pipeline/visual.py`, `app/pipeline/facecam.py`) | Nothing leaves the server. Face detection finds a box; no face template is stored | n/a |
| AI judge: titles, hook, rating, cut | Anthropic Messages API, only when `ANTHROPIC_API_KEY` is set (`app/ai.py:23`, `:357`) | One JPEG frame of the clip, up to about 2,500+ characters of its timed transcript, its signal scores, and the user's `prompt` (`app/ai.py:254-280`) | Inputs and outputs deleted within 30 days; flagged content up to 2 years; no training on API data. See [privacy-law-review.md](privacy-law-review.md#providers) |
| Translation and summaries | Anthropic, when `TRANSLATION_PROVIDER` / `SUMMARY_PROVIDER` is `ai` (both `none` by default) | Transcript text | As above |
| Premium AI thumbnail (#152, not merged, off by default) | Google Gemini, paid tier only, every request with `store: false`. No other image provider | One frame of the clip, a close-up of the face in it, and the prompt (the style and the user's custom styling). No video, no account details | 55 days for abuse monitoring only; no training on the paid tier. A free-tier key must never be used: Google trains on free-tier inputs and people may review them |

## 4. Payments

| Data | Where | Kept | Who can read | Sent to |
|---|---|---|---|---|
| Card details | Never reach us: Stripe Checkout collects them | n/a | n/a | Stripe |
| Stripe customer and subscription ids, subscription status | `accounts.stripe_customer_id`, `stripe_subscription_id`, `subscription_*` (`app/models.py:27-32`) | Until the account is deleted | Admin; status shown to the user | Stripe |
| Payments: Stripe reference, amount, credits granted, refunds | `payments` (`app/models.py:177`) | No limit (accounting) | Admin | Stripe |
| Credit ledger: every grant, purchase, reserve, charge, refund, with a note | `credit_ledger` (`app/models.py:198`), append-only | Never deleted (`CLAUDE.md`: append-only) | The user (last 50, `GET /v1/credits`), admin | Nobody |
| Account id sent to Stripe | `client_reference_id` and `metadata.account_id` (`app/routes_billing.py:77`, `:122`) | Stripe's own retention | Stripe | Stripe |

## 5. Email

| Email | When | Contains |
|---|---|---|
| Confirm your email | Sign-up (`app/routes_auth.py`, `send_verification`) | A 48-hour verification link |
| Reset your password | `POST /v1/auth/forgot` | A 1-hour reset link |
| Admin test email | `admin.py send-test-email` | Fixed text |

The email provider is **Resend** (owner, 2026-11-18). #159 sends through Resend's HTTPS API (`EMAIL_PROVIDER=resend`);
until it ships, mail goes through the SMTP server in `SMTP_HOST` (`app/emailer.py:19`). Resend receives the
recipient address, the subject and the text, which holds the verification or reset link. Resend keeps email data
for 30 days on every plan ([Resend docs](https://resend.com/docs/knowledge-base/account-quotas-and-limits)).
**Gap, fixed in #159:** when `SMTP_HOST` is empty the full message, including the reset link, is written to the log
(`app/emailer.py:34`). #159 logs only a masked address and the subject, and production refuses to start without
a working provider.

## 6. Logs and monitoring

| Data | Where | Kept | Sent to |
|---|---|---|---|
| Request logs (IP, path, status) | Caddy and uvicorn stdout, Docker's log driver on the droplet | Docker default (no rotation set in `docker-compose.yml`): until the container is removed. Gap, #150 | Nobody |
| Import preview log: account id, platform, first 200 characters of the URL | `app/routes_ingest.py:168` | As above | Nobody |
| Billing logs: account id, plan, invoice id | `app/routes_billing.py:275`, `:346`, `:357` | As above | Nobody |
| Errors | Sentry, only when `SENTRY_DSN` is set (`app/main.py:23-25`); `send_default_pii` is not set, so the SDK default (off) applies | Sentry: 30 days (Developer) or 90 days (Team) | Sentry |
| Webhook deliveries: job id, target URL, status | `webhook_deliveries` (`app/models.py:230`) | No limit (gap, #150) | The customer's own server (the job's status and id, signed) |

## 7. The website

- Static files served by Caddy (`Caddyfile`). Fonts are bundled (`@fontsource`), so no request goes to Google Fonts.
- No cookies are set by the site or the API. No analytics, no advertising, no tracking pixels (checked:
  no `posthog`, `gtag`, `analytics` or `sentry` in `web-src/`).
- `localStorage` holds the session token (`cc_token`) and unsent editor drafts. Both are needed for the service
  to work; neither is shared with anyone.
- Stripe Checkout and the Stripe billing portal are Stripe pages, with Stripe's own cookies.

## 8. Where data is

| Place | Provider | Region |
|---|---|---|
| Server: API, worker, Postgres, local storage | DigitalOcean droplet | Toronto (TOR1), per SPEC.md 10.B |
| Object storage | DigitalOcean Spaces (when `STORAGE_BACKEND=s3`) | Set by `S3_ENDPOINT_URL`; owner to confirm TOR1 |
| AI judge | Anthropic | United States (storage at rest is US-only) |
| Payments | Stripe | United States (Stripe, LLC) and Stripe's other regions |
| Errors | Sentry | US or EU, chosen when the Sentry organisation was created: owner to confirm |
| Email | Resend | Resend's sending region: owner to confirm (account setting) |

## 9. Gaps between this map and what the policies should promise

| Gap | Where it is fixed |
|---|---|
| No self-serve account deletion or data export | #149 |
| Earlier exports and worker-lost exports outlive `RETENTION_DAYS` | #150 |
| No retention limit on `import_log`, `clips.meta`, `clip_feedback`, `jobs.options`, `webhook_deliveries`, Docker logs | #150 (durations are the owner's decision) |
| Email bodies with reset links are logged when SMTP is not configured | #159 (no body, link or token in any log) |
| No form for copyright or likeness complaints; no case records | #145, #146, #148 |
| Policy acceptance was not recorded before this PR; accounts created earlier show `consent_required: true` | this PR; the site asks them on next login (#147) |
| No admin role in the app | #145 |
| Black Forest Labs trains on API inputs by default and offers no verifiable opt-out | Removed in #152 (owner rule, 2026-11-18: customer footage never goes to a provider that trains on API inputs without the user's explicit, informed authorization) |
