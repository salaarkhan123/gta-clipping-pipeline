# Credential rotation

How to replace each production secret without downtime or data loss. Each secret has its own steps, a
verification and a rollback:

- [Stripe secret key](#1-stripe-secret-key)
- [Stripe webhook secret](#2-stripe-webhook-secret)
- [Anthropic API key](#3-anthropic-api-key)
- [SECRET_KEY](#4-secret_key)
- [Postgres password](#5-postgres-password)

Rotate on a schedule, when someone with access leaves, and at once after a suspected leak. After a leak, use the
no-overlap path where one is given.

## Rules for secrets

- Secrets live in the server's `clip-api/.env` and in the owner's password manager, nowhere else. `.env` is in
  `.gitignore`. Never `git add -f` it, and run `git status` before every commit.
- Edit `.env` with an editor (`nano .env`). Do not run `echo KEY=... >> .env` and do not pass a secret as a
  command-line argument: both land in the shell history, and arguments show in `ps`. The steps below use
  prompts instead (`\password`, `psql -W`).
- Never paste these into a ticket, PR, chat or AI tool: `.env`, `env`, `docker compose config`, or
  `docker inspect`. The last two print every resolved secret. To show which settings are present:
  - `.claude/bin/super-board-env-check.sh` prints key names only.
  - `scripts/admin.py stripe-check` reports the Stripe settings without printing them.
- Logs and error reports:
  - Request logs replace tokens and keys in URLs with `[redacted]` (`app/log_redact.py`). Download and
    email-verification links carry signed tokens.
  - Sentry gets no local variables. A handler's locals hold the settings object, whose repr includes
    `SECRET_KEY`, `STRIPE_SECRET_KEY` and the database password.
  - `stripe-check` prints Stripe errors by type only. Stripe itself masks keys in its error messages.
- Test fixtures use obviously fake values (`whsec_test`, `example_...`). `tests/test_stripe_live.py` refuses any
  key that is not a test-mode key.
- `tests/test_secrets_in_logs.py` runs last in every full test run. It scans every log line the suite wrote and
  fails on a secret-shaped string (Stripe, Anthropic and ClutchClips keys, webhook secrets, signed tokens,
  passwords in URLs, password hashes) or on any secret value the suite is configured with.

## Before every rotation

1. Check that no job is running: `docker compose exec -T api python scripts/admin.py stuck`. Wait if a line
   says `RUNNING`. Recreating the worker stops its job. The stale-job sweep then fails the job and refunds it,
   but the user loses the run.
2. Write down when the containers were created: `docker compose ps --format '{{.Name}} {{.CreatedAt}}'`.

After you edit `.env`, `docker compose up -d api worker` recreates the containers whose settings changed. Check
with `docker compose ps` that the creation times are new. If they are not, run
`docker compose up -d --force-recreate api worker`.

The API is down for a few seconds while it restarts. Stripe retries webhooks that fail, for up to 3 days, and
the handler is idempotent, so no payment event is lost.

## 1. Stripe secret key

**Used by:** the API only. It creates Checkout Sessions and billing portal sessions, checks each plan's Price,
and matches refunds and disputes to plan invoices through the Invoice Payments API.

1. In Stripe (live mode), open **Developers, API keys**. On the secret key, or on the restricted key if the
   server uses one, choose **Roll key**.
   a. Set the old key to expire **in 24 hours**. That is the overlap.
   b. Copy the new key. Stripe shows it once.
   c. A restricted key needs these permissions: Checkout Sessions write, Prices read, Customer portal write,
      Invoices read (Invoice Payments), and Accounts read (used only by `stripe-check`).
2. On the server, set `STRIPE_SECRET_KEY=<new key>` in `.env`.
3. Run `docker compose up -d api worker`.
4. Verify:
   a. `docker compose exec -T api python scripts/admin.py stripe-check`. Expected: `key mode: live`,
      `OK key accepted`, six `OK` Price lines, and `ALL OK`.
   b. On the website, open **Pricing** and click a plan. Stripe Checkout opens. Close it without paying.
   c. `docker compose logs --since 10m api | grep -iE 'stripe|billing'` shows no `AuthenticationError`.
5. In **Developers, API keys**, expire the old key now, or let the 24 hours run out.

**Rollback:** during the overlap, put the old key back in `.env` and run `docker compose up -d api worker`. After
the old key expires, roll again.

**After a leak:** roll with **Expire now**. Then read **Developers, Logs** for requests the API did not make.

## 2. Stripe webhook secret

**Used by:** the API only, to verify each `POST /webhooks/stripe`. An event is refused with 400 unless its
signature matches `STRIPE_WEBHOOK_SECRET` and its timestamp is less than 5 minutes old. Keep the server clock in
sync (`timedatectl` shows "System clock synchronized: yes").

1. In **Workbench, Webhooks**, open the endpoint `https://api.clutchclips.io/webhooks/stripe` and choose
   **Roll secret**. Set the old secret to expire in 24 hours.
   During the overlap, Stripe signs every event with both secrets: the `Stripe-Signature` header has two `v1=`
   values. The API accepts an event when one of them matches, so both the old and the new value work while you
   switch. `tests/test_stripe_validation.py::test_both_secrets_work_while_stripe_rolls_the_webhook_secret`
   proves this.
2. Reveal the new signing secret. Set `STRIPE_WEBHOOK_SECRET=<new secret>` in `.env`.
3. Run `docker compose up -d api worker`. The worker does not read this secret; restarting it is harmless.
4. Verify:
   a. In **Workbench, Events**, open a recent event of one of the 8 handled types, such as the last
      `customer.subscription.updated` or `invoice.paid`, and **Resend** it to the endpoint. Delivery: HTTP 200.
      A resend changes nothing, because every handler is idempotent.
   b. `docker compose logs --since 10m api | grep '/webhooks/stripe'` shows `200` and no `400`.
5. Expire the old secret now, or let it run out. Resend one more event: it must still return 200. That shows the
   server uses the new secret. The endpoint's list of failed deliveries stays empty.

**Rollback:** during the overlap, put the old secret back and restart. Events that failed meanwhile are retried
by Stripe. You can also resend them from the endpoint's failed deliveries.

**After a leak:** a leaked webhook secret lets someone send forged events. The ledger keys stop them from
granting a pack or invoice twice, but they could invent new ones. Roll with immediate expiry.

## 3. Anthropic API key

**Used by:** the worker (clip titles, hooks and scores), and the API when `TRANSLATION_PROVIDER` or
`SUMMARY_PROVIDER` is `ai`. Each process reads the key once at startup (`app/ai.py`, `default_ai`), so a restart
is needed.

1. In the Claude Console, open **Settings, API keys**. Create a key in the same workspace, named for example
   `clutchclips-prod-YYYYMMDD`, and copy it.
2. Set `ANTHROPIC_API_KEY=<new key>` in `.env`.
3. Run `docker compose up -d api worker`.
4. Verify the key without spending tokens. Listing models is free:

   ```bash
   docker compose exec -T worker python -c "import httpx; from app.config import get_settings; \
   r = httpx.get('https://api.anthropic.com/v1/models?limit=1000', timeout=10, \
       headers={'x-api-key': get_settings().anthropic_api_key, 'anthropic-version': '2023-06-01'}); \
   print(r.status_code, get_settings().ai_model in [m['id'] for m in r.json().get('data', [])])"
   ```

   Expected: `200 True`. `401` means the key is wrong. `200 False` means `AI_MODEL` is not available to this
   key's workspace.
5. Run one small job and check that its clips have AI titles. `docker compose logs --since 10m worker` shows no
   `401`.
6. In the Console, disable the old key, then delete it.

**Rollback:** the old key works until you disable it. Put it back and restart.

## 4. SECRET_KEY

### What it signs

`SECRET_KEY` signs the HS256 tokens made by `app/security.py` (`make_token`). There are four:

| Token | Where it is used | Lifetime | If SECRET_KEY changes with no overlap |
|---|---|---|---|
| Session | Website sign-in (`/v1/auth/signup`, `/v1/auth/login`). The browser sends it as `Bearer` on every call. | `JWT_TTL_HOURS` (168 h) | Every website user is signed out and must sign in again. |
| Email verification | Link `/v1/auth/verify?token=...` in the sign-up email | 48 h | The link says "invalid or expired". The user asks for a new one (resend button). |
| Password reset | Link `/reset-password?token=...` in the reset email | 1 h, single use | The link fails. The user asks for a new one. |
| Download link | `/v1/files/<token>`, only with `STORAGE_BACKEND=local` | `SIGNED_URL_TTL_SEC` (3600 s) | Links already handed out (API answers, job webhooks) return 404. Fetching the clip again gives a new link. |

`SECRET_KEY` does **not** affect:

- API keys. They are stored as a SHA-256 hash of the key, with no secret involved, so API customers notice
  nothing.
- Passwords (argon2).
- Each account's webhook signing secret, which is random and stored.
- With `STORAGE_BACKEND=s3`, download links, which the bucket's access key signs.
- Stripe.

### Overlap

`SECRET_KEY_PREVIOUS` holds the old key during a rotation. Tokens signed with it are still accepted until they
expire. New tokens are always signed with `SECRET_KEY`. In production the API refuses to start when
`SECRET_KEY_PREVIOUS` is set but shorter than 32 characters. Releases older than the Stripe validation PR do not
have `SECRET_KEY_PREVIOUS`; on those, only the no-overlap rotation is possible.

### Planned rotation

1. Make a new key with `openssl rand -hex 32` and keep it in the password manager.
2. In `.env`:
   - Set `SECRET_KEY_PREVIOUS` to the current `SECRET_KEY` value.
   - Set `SECRET_KEY` to the new key.
3. Run `docker compose up -d api worker`. Restart both: the worker signs download links in job webhooks.
4. Verify:
   a. `docker compose logs --since 5m api | grep -i unsafe` prints nothing.
   b. A browser that was signed in before the restart still loads the dashboard. That shows the old key is
      still accepted.
   c. Sign out and sign in again. That shows the new key signs. `/v1/me` answers 200.
5. After `JWT_TTL_HOURS` (7 days), delete the `SECRET_KEY_PREVIOUS` line and run
   `docker compose up -d api worker` again. From then on the old key is worth nothing.

### After a leak

Do not use the overlap. Anyone holding the old key can make a session token for any account. Set only the new
`SECRET_KEY`, leave `SECRET_KEY_PREVIOUS` empty, and restart. Everyone is signed out, and pending verification
and reset links stop working.

To void only the emailed reset and verification links, without changing `SECRET_KEY` (for example after mail
logs leaked), run `docker compose exec -T api python scripts/admin.py bump-token-epoch`. Sessions stay valid.

**Rollback:** put the old value back as `SECRET_KEY`. If you want tokens issued in the meantime to keep working,
set the new value as `SECRET_KEY_PREVIOUS`. Then restart.

## 5. Postgres password

### How it is wired

`.env` has `POSTGRES_PASSWORD`. `docker-compose.yml` uses it in two places:

- It builds `DATABASE_URL` (`postgresql+psycopg://clip:<password>@db:5432/clip`) for `api` and `worker`.
- It passes the value to the `db` container. The `db` container reads it only when it first creates the
  `pgdata` volume.

So changing `.env` alone does not change the database's password. You change the password in Postgres, then
give the new value to `api` and `worker`.

### Steps

Do steps 4 to 6 within a minute. Between them, new database connections from `api` and `worker` fail.

1. Back up, outside the repository:

   ```bash
   mkdir -p ~/backups && docker compose exec -T db pg_dump -U clip -d clip -Fc > ~/backups/clip-$(date +%F-%H%M).dump
   ls -lh ~/backups/        # the new file is not empty
   ```

2. Run the checks in [Before every rotation](#before-every-rotation). Also keep the old password in the password
   manager until this rotation is finished; the rollback needs it.
3. Make the new password with `openssl rand -hex 24`. Use hex only: it goes into `DATABASE_URL` and needs no
   escaping there.
4. Change it in Postgres. Inside the container, psql connects over the local socket, which needs no password:

   ```bash
   docker compose exec db psql -U clip -d clip
   clip=# \password clip          -- type the new password twice; psql sends only its hash
   clip=# \q
   ```

   Existing connections stay open. New ones need the new password from now on.
5. Set `POSTGRES_PASSWORD=<new password>` in `.env`.
6. Run `docker compose up -d api worker`.
   - Compose recreates `api` and `worker` with the new `DATABASE_URL`.
   - Compose may also recreate `db`, because its environment changed. That is safe: the data stays on the
     `pgdata` volume, Postgres shuts down cleanly, and a new container does not initialise a data directory that
     already exists.
   - `depends_on` keeps the order: `db`, then `api` once `db` is healthy, then `worker` once `api` is healthy.
   - No committed data is lost. Requests in flight during the restart fail and are retried by the website,
     customers and Stripe.
7. Verify:
   - `docker compose ps` shows `db` and `api` as healthy.
   - `curl -fsS https://api.clutchclips.io/health` returns `{"ok":true,...}`. The health check runs `SELECT 1`.
   - `docker compose exec -T api python scripts/admin.py db-status` prints the schema revision.
   - `docker compose logs --since 5m api worker | grep -i 'password authentication failed'` prints nothing.
   - The old password is refused over TCP. `-h 127.0.0.1` forces a password check; the socket does not check:

     ```bash
     docker compose exec db psql -h 127.0.0.1 -U clip -d clip -W -c 'select 1'
     ```

     The old password gives "password authentication failed"; the new one prints `1`.
   - Give the new password to anything else that connects, such as a backup job or a reporting tool.

**Rollback:**

1. Run `docker compose exec db psql -U clip -d clip`, then `\password clip`, and enter the old password.
2. Put the old `POSTGRES_PASSWORD` back in `.env`.
3. Run `docker compose up -d api worker`.

The rollback does not touch the data. Use the dump from step 1 only if the data itself is damaged, which a
password change does not do. Restoring it (`pg_restore --clean`) overwrites the database, so it needs the
owner's decision.
