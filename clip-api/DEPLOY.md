# Deploying from git

The droplet deploys from git only: `/root/clip-api` is the `clip-api/` folder of a checkout of the deploy
branch (`main`). Code reaches `main` only through reviewed PRs (`staging` → `main`).

## Every deploy

```bash
cd /root/clip-api && bash scripts/deploy.sh
```

`scripts/deploy.sh` refuses while a job is RUNNING (it checks `admin.py stuck` before the pull and again right
before the restart), refuses if the job list cannot be read, if tracked files were edited on the server, or if
the checkout is not on the deploy branch. It then fast-forwards, builds `api` and `worker`, restarts only those
two, and runs `admin.py selftest`. On a selftest failure it prints the rollback command. Caddy and Postgres are
not restarted; `web/` is served straight from the checkout, so the site updates with the pull. A change to the
`Caddyfile` needs `docker compose up -d caddy` as well.

## Running more than one job at once

Default: one job at a time. Two ways to add capacity:

- **`WORKER_CONCURRENCY=2`** in the server's env file, then `docker compose up -d worker` (when no job is
  RUNNING). One worker process runs two jobs at once and shares one copy of the Whisper and CLIP models, so it
  costs little extra memory. 2 is the limit on the 4 vCPU / 8 GB droplet: each job's ffmpeg and Whisper already
  use every core, so two jobs each run slower, but a second customer no longer waits for the first to finish.
  Values above 2 are rejected at start.
- **A second worker container** (only on a bigger server, or a second one): each container loads its own
  models (about 1.5 GB more memory) and claims from the same queue; a job is claimed by exactly one worker.
  ```bash
  docker compose up -d --scale worker=2 --no-recreate worker
  ```
  `deploy.sh` restarts with `up -d api worker`, which goes back to one container: run the scale command again
  after each deploy. Total jobs at once = containers × `WORKER_CONCURRENCY`.

After either change, run the 10-clip benchmark twice at the same time and compare with SPEC.md §10 B before
relying on it.

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
