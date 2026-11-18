# Deploying from git

The droplet deploys from git only: `/root/clip-api` is the `clip-api/` folder of a checkout of the deploy
branch (`main`). Code reaches `main` only through reviewed PRs (`staging` → `main`).

## Every deploy

```bash
cd /root/clip-api && bash scripts/deploy.sh
```

`scripts/deploy.sh` refuses while a job is RUNNING (it checks `admin.py stuck` before the pull and again right
before the restart), refuses if the job list cannot be read, if tracked files were edited on the server, or if
the checkout is not on the deploy branch. It then fast-forwards, builds `api` and `worker`, runs the schema
migrations from the new image (`admin.py migrate`), restarts only `api` and `worker`, and runs
`admin.py selftest`. A failed migration stops before the restart, so the old code keeps serving on an unchanged
schema. On a selftest failure it prints the rollback command. Caddy and Postgres are
not restarted; `web/` is served straight from the checkout, so the site updates with the pull. A change to the
`Caddyfile` needs `docker compose up -d caddy` as well.

## Schema migrations

Alembic, in `app/migrations/`. Migrations are additive only (new tables, new nullable or defaulted columns, new
indexes), so the old code keeps working while it still serves and a code rollback needs no schema rollback.
Anything that drops, renames or rewrites data needs its own PR and the owner's OK, with a backup first.

- **See where the database is (read-only):** `docker compose exec -T api python scripts/admin.py db-status`.
  Exit 0 means it is at the latest revision. It lists anything that differs from the models.
- **First deploy with migrations:** the production database predates them. Before that deploy, run `db-status`
  and back up the database (`pg_dump`, as in step 1 below). It should report "from before migrations" plus, at
  most, a missing `ix_accounts_stripe_customer_id` index. `deploy.sh` then brings the database to the baseline
  (adding the missing columns and indexes, and making `uploads.analyzed` NOT NULL, which changes no values) and
  stamps it. After the deploy, `db-status` must report `revision 0001 · latest 0001`.

## Measuring speed

Every job records where its time went: `result.stages` (seconds per pipeline stage), `result.counts` (candidates,
clips, seconds transcribed and rendered), `result.queue_sec` and `result.total_sec` (queue + run: what a customer
waits). Failed and cancelled jobs record it too. The goal is a 2-hour video in 10 minutes and a 4-hour video in 15.

```bash
curl -s $API/v1/jobs/<job_id> -H "authorization: Bearer $KEY" > job.json
python scripts/job_timings.py job.json                           # stage table and the target for that length
python scripts/job_timings.py job.json --baseline before.json    # change against an earlier job
python scripts/job_timings.py job.json --baseline before.json --md   # the same, as a table for a PR
```

A job from before stage timing existed has only the coarse stages shown in the dashboard; comparing with one
uses those. Without a server: `python scripts/bench_pipeline.py <video> --max-clips 10` runs the pipeline locally
(no AI judge) and prints the same stages.

## Transcription settings

- `TRANSCRIPTION_PROVIDER=local` (the only provider so far): whole recordings are transcribed by the local Whisper
  models, in chunks cut at quiet points. Hosted providers are added with their adapters; an unknown name stops the
  worker at start with a clear message.
- `TRANSCRIBE_PARALLEL` (default 1, up to 8): chunks transcribed at once, for whole-recording transcription (Video
  Finder's index today). Leave it at 1 on the 4 vCPU droplet: one model already uses every core. On a machine
  with 8 or more cores try 2 to 4 and compare with `scripts/job_timings.py`. Each extra one adds memory.
- `TRANSCRIBE_CHUNK_SEC` (default 300): the chunk length.
- A transcript that Video Finder made for an upload is reused by Clip Maker for its first, rough pass, so that
  pass costs nothing on the second job. Captions are still made by the caption model.

## Provisional layouts

`PROVISIONAL_LAYOUTS` (default `false`) controls the layouts that are built but not yet checked on real gaming
footage: `trio`, `grid4`, `ots`, and the `auto` layout that picks a layout for each moment.

- Off (the default):
  - `GET /v1/options` does not list `trio`, `grid4` or `ots`.
  - A request that asks for one of them gets `400 layout_not_available`. This applies to clip jobs, quotes,
    Reframe, Captions, exports and saved templates.
  - `auto` picks one layout for the whole video, as it did before PR #136.
- On: the three layouts are offered, and `auto` looks at each moment. When the camera is hidden, the moment
  fills the frame with gameplay. When the face fills the frame, the moment is framed on the person.

To turn it on:

1. Render a few real VODs with each of the three layouts and with `auto`.
2. Check the frames.
3. Set `PROVISIONAL_LAYOUTS=true` in the server's env file.
4. Run `docker compose up -d api worker`. The API and the worker both read the setting.

Jobs that are already queued keep the layout they asked for.

## Running more than one job at once

Default: one job at a time. Two ways to add capacity:

- **`WORKER_CONCURRENCY=2`** in the server's env file, then `docker compose up -d worker` (when no job is
  RUNNING). One worker process runs two jobs at once and shares one copy of the Whisper and CLIP models, so it
  costs little extra memory. 2 is the limit on the 4 vCPU / 8 GB droplet: each job's ffmpeg and Whisper already
  use every core, so two jobs each run slower, but a second customer no longer waits for the first to finish.
  Values above 2 are rejected at start.
- **A second worker container** (only on a bigger server, or a second one): each container loads its own
  models (check the extra memory with `docker stats` before relying on it) and claims from the same queue; a
  job is claimed by exactly one worker.
  ```bash
  docker compose up -d --scale worker=2 --no-recreate worker
  ```
  `deploy.sh` restarts with `up -d api worker`, which goes back to one container: run the scale command again
  after each deploy. Total jobs at once = containers × `WORKER_CONCURRENCY`.

After either change, run the 10-clip benchmark twice at the same time and compare with SPEC.md §10 B before
relying on it.

## Plans and Stripe Prices

Plan prices, monthly credits and limits live in `app/plans.py` and nowhere else, so every pricing change is a
reviewed PR. The `PLANS` environment variable is no longer read: delete its line from `.env`. Checkout charges a
Stripe Price that you create; the API only needs its ID.

1. In Stripe (test mode first, then live mode), create one product per plan, each with two recurring Prices in
   USD, per unit, billed every 1 month or every 1 year:

   | Plan | Monthly Price | Yearly Price |
   |---|---|---|
   | Starter | $15.99 per month | $66.96 per year |
   | Pro | $26.99 per month | $114.96 per year |
   | Scale | $139.99 per month | $839.88 per year |

2. Put each Price ID (`price_...`) in `.env`:

   ```
   STRIPE_PRICE_STARTER_MONTH=
   STRIPE_PRICE_STARTER_YEAR=
   STRIPE_PRICE_PRO_MONTH=
   STRIPE_PRICE_PRO_YEAR=
   STRIPE_PRICE_SCALE_MONTH=
   STRIPE_PRICE_SCALE_YEAR=
   ```

3. Restart: `docker compose up -d api worker`.

A plan whose Price ID is blank answers `plan_unavailable`. Before each checkout the API reads the Price from Stripe
and refuses it (`plan_unavailable`, and an error in the api log naming what differs) unless it is active, recurring,
in `CURRENCY`, every 1 month or 1 year as configured, and exactly the amount in `app/plans.py`. A typo in Stripe
therefore stops sales instead of charging the wrong amount.

**Yearly plans grant credits monthly.** The first month comes with the paid yearly invoice; the worker grants each later month on the same day of the month (its sweep runs every minute and catches up after downtime). Grants stop at a refund, a dispute, a cancellation or the end of the paid year; credits already granted stay. Migration `0007` (additive: four nullable columns on `payments`) runs with the deploy.

**Customer portal:** keep plan switching turned off for now (Settings, Billing, Customer portal: allow cancelling
and updating the card only). Every paid invoice grants a full period of credits, so a mid-period upgrade with
proration would grant a whole month of credits for a part payment. To change plan, a subscriber cancels and
subscribes again once the old plan ends.

**Subscribers from before 2026-11-17** keep their plan (`starter`, `pro`, `agency` or `scale` in `accounts.plan`),
its credits on every renewal and its limits, at the price Stripe already charges them, until their subscription
ends. To see how many there are:

```bash
docker compose exec -T db psql -U clip -d clip -c \
  "select plan, subscription_status, count(*) from accounts where stripe_subscription_id is not null group by 1, 2"
```

## Email (Resend)

The api sends verification, password-reset and account emails through Resend's HTTPS API (`app/emailer.py`).
SMTP port 587 is blocked from the droplet, so SMTP is optional. Logs never hold a link, a token or a full
address: `email_sent` and `email_delivery_failed` lines show `s***@domain`. The access log redacts
`?token=` and `/v1/files/<token>` (`app/log_redact.py`).

To switch production to Resend, follow this order. A PR never changes server settings.

1. On the droplet, add the key yourself. Never paste it in chat, a ticket or git:
   ```bash
   cd /root/clip-api
   nano .env      # EMAIL_PROVIDER=resend, RESEND_API_KEY=re_..., EMAIL_FROM=noreply@clutchclips.io
   ```
   Leave `ENV` and `AUTO_VERIFY_EMAIL` as they are for now.
2. Load the new env into the two app containers. This does not touch Caddy or Postgres:
   ```bash
   docker compose up -d api worker
   ```
3. Send one real message, then check the Resend dashboard and the inbox:
   ```bash
   docker compose exec api python scripts/admin.py send-test-email --to you@yourdomain.com
   ```
   - Exit 0 prints Resend's message id.
   - Exit 2 means a key is missing.
   - Exit 1 means Resend refused it: 401 or 403 is a wrong key, 422 means `EMAIL_FROM` is not on a verified domain.
4. Only after a real delivery succeeds, set `ENV=prod` and `AUTO_VERIFY_EMAIL=false` in `.env`, then run
   `docker compose up -d api worker` again. With `ENV=prod` the api refuses to start without working email
   settings, so a typo stops the start instead of leaving mail unsent.

### Reset and verification links that were logged

Before this change, with no email provider configured, the api wrote each email's text, reset and verification
links included, to the container log. To clean up:

1. Void every link already sent: `docker compose exec api python scripts/admin.py bump-token-epoch`.
   - Reset links already expire after 1 hour or on a password change; verification links after 48 hours.
   - The bump kills all of them at once without rotating `SECRET_KEY`, which would log everyone out.
2. Truncate the old container logs (Docker's json-file driver):
   ```bash
   for c in $(docker compose ps -q api worker); do truncate -s 0 "$(docker inspect --format='{{.LogPath}}' $c)"; done
   ```
3. Delete any copies made from those logs, such as downloads or pasted snippets.

## Link import and takedowns

Users can import a public video link (Twitch, Kick, direct https video links, Google Drive and Dropbox share
links, YouTube best effort) with `POST /v1/imports`. Every import is logged in `import_log` (account, link,
platform, consent, time) before anything is fetched. Imports are free; the job run on the imported video is what
costs credits.

`POST /v1/imports/preview {url}` shows what a link is (title, channel, length, thumbnail) before an import. It
reads metadata only, is free, and stores nothing except a log line (`clipapi.ingest`, "import preview"). Lookups
are capped at 10 a minute per account and 15 seconds each; answers are cached in memory for 5 minutes per link.
`IMPORTS_ENABLED=false` switches it off too.

- **Switch imports off:** set `IMPORTS_ENABLED=false` and restart `api` and `worker`. New imports are refused
  with "upload the file instead"; imports already queued fail the same way. Uploads keep working.
- **Caps** (defaults in brackets): `IMPORT_MAX_BYTES` (8 GB), `IMPORT_MAX_DURATION_SEC` (6 hours),
  `IMPORT_TIMEOUT_SEC` (1800, the whole download). The upload limits (`MAX_UPLOAD_BYTES`, `MAX_DURATION_SEC`,
  `MIN_DURATION_SEC`) apply too; the lower value wins.
- **yt-dlp** is pinned in `requirements.txt`. Upgrade it in its own PR: the test in
  `tests/test_ingest_platforms.py` lists every option it is given and must still pass.

**Takedown request** (a rights holder asks for a video to be removed):

1. See what would be removed, without changing anything:
   `docker compose exec -T api python scripts/admin.py takedown --url "<the link>" --dry-run`
   (or `--account <account id or email>` for everything one account imported by link).
2. Remove it: run the same command without `--dry-run`. It prints each upload, its clips and files, and the jobs
   it cancelled with the credits returned.
3. If it says a job "is still stopping", run the same command again a minute later. It is safe to run any number
   of times; a second run prints "Nothing to remove."
4. Keep the printed output with the request. The `import_log` rows are kept: they record who imported the link.

The link may be given in any form the site uses (with or without `www.`, tracking parameters, `youtu.be`): it is
matched by its canonical form. Ordinary uploads are never touched by a takedown.

## Moving files to DigitalOcean Spaces

Uploads and clips are stored on the droplet's disk by default (`STORAGE_BACKEND=local`). Spaces moves them to a
private bucket; download links become signed URLs straight from the bucket, valid for `SIGNED_URL_TTL_SEC`.

**Price** (docs.digitalocean.com/products/spaces/details/pricing, checked 2026-11-15): $5.00 per month, which
includes 250 GiB stored and 1,024 GiB of downloads; beyond that $0.02 per GiB stored per month and $0.01 per
GiB downloaded. Transfer from a Space to a Droplet in the same region group is free, so create the Space in the
droplet's region.

1. In the DigitalOcean panel: create a Space in the droplet's region with **file listing restricted**, and a
   Spaces access key limited to that bucket.
2. Add to the server's env file (keep `STORAGE_BACKEND=local` for now):
   `S3_ENDPOINT_URL=https://<region>.digitaloceanspaces.com`, `S3_REGION=<region>` (for example `nyc3`),
   `S3_BUCKET=<space name>`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`. Then `docker compose up -d api worker`
   when no job is RUNNING.
3. Check the bucket, then copy the existing files (safe to repeat; nothing local is deleted):
   ```bash
   docker compose exec -T -e STORAGE_BACKEND=s3 api python scripts/check_storage.py
   docker compose exec -T api python scripts/migrate_storage.py --dry-run
   docker compose exec -T api python scripts/migrate_storage.py
   ```
4. Switch: set `STORAGE_BACKEND=s3`, `docker compose up -d api worker` (when no job is RUNNING), then run
   `migrate_storage.py` once more to pick up anything written in between. It must end with `failed 0`.
5. Run one job and download a clip. Keep the local files for a week (`data/storage` in the `data` volume), then
   delete them. **Roll back:** set `STORAGE_BACKEND=local` and restart; files created while on Spaces are only
   in the bucket.

## One-time switch from tarballs to git

Do this when nothing is running, after `main` contains exactly the code the droplet runs
(PR #18 merged into `staging`, then a `staging` → `main` PR merged).

1. Back up the current folder and the database:
   ```bash
   cd /root
   tar czf clip-api-pre-git-$(date +%F).tgz --exclude='clip-api/data' clip-api
   docker compose -f clip-api/docker-compose.yml exec -T db pg_dump -U clip clip > clip-pre-git-$(date +%F).sql
   docker volume ls | grep clip-api_        # note the names: clip-api_pgdata, clip-api_data, clip-api_caddy_data, …
   ```
2. Give the droplet read-only access to the private repo with a deploy key:
   ```bash
   ssh-keygen -t ed25519 -N '' -f ~/.ssh/clutchclips_deploy -C clutchclips-droplet
   cat ~/.ssh/clutchclips_deploy.pub
   ```
   Add it in GitHub → repo → Settings → Deploy keys, **read-only** (leave "Allow write access" off). Then:
   ```bash
   printf 'Host github.com\n  IdentityFile ~/.ssh/clutchclips_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
   ```
3. Clone the deploy branch next to the old folder:
   ```bash
   git clone --branch main git@github.com:salaarkhan123/gta-clipping-pipeline.git /root/clutchclips
   ```
4. Check the checkout matches what is running. Only untracked files (`.env`, `data/`, caches) may differ:
   ```bash
   diff -rq /root/clip-api /root/clutchclips/clip-api -x .env -x data -x __pycache__ -x .venv -x node_modules
   ```
   Any code file that differs means `main` is not what production runs. Stop and fix that with a PR first.
5. Carry over the untracked files and pin the compose project name, so the existing volumes (database,
   uploads, TLS certificates) are reused:
   ```bash
   cp -p /root/clip-api/.env /root/clutchclips/clip-api/.env
   grep -q '^COMPOSE_PROJECT_NAME=' /root/clutchclips/clip-api/.env || echo 'COMPOSE_PROJECT_NAME=clip-api' >> /root/clutchclips/clip-api/.env
   ```
   Copy anything else step 4 listed as "Only in /root/clip-api" that is not code.
6. Swap the folders. `/root/clip-api` becomes a link into the checkout:
   ```bash
   mv /root/clip-api /root/clip-api.pre-git
   ln -s /root/clutchclips/clip-api /root/clip-api
   ```
7. Re-point the running containers at the new folder. Bind mounts (`./web`, `./Caddyfile`) still point at the
   old directory until each container is recreated, so recreate Caddy once (a few seconds of site downtime),
   then deploy api and worker with the script:
   ```bash
   cd /root/clip-api
   docker compose config --volumes            # must list the same volumes as step 1
   docker compose up -d caddy
   bash scripts/deploy.sh
   docker volume ls | grep clip-api_          # no new volumes were created
   curl -s https://api.clutchclips.io/health
   ```
8. Keep `/root/clip-api.pre-git` and the backups for a week, then delete them.

**Roll back** the switch: `rm /root/clip-api && mv /root/clip-api.pre-git /root/clip-api && cd /root/clip-api &&
docker compose up -d`.
