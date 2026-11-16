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
