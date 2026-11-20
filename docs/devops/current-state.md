# DevOps: current state, gaps, design

Written before the deploy pipeline was built (2026-11-17). Setup steps are in [setup.md](setup.md).

## What exists

| Piece | What it does |
|---|---|
| `clip-api/scripts/deploy.sh` | Run by hand on the droplet. Refuses while a job is RUNNING (`admin.py stuck`, checked before the pull and again before the restart), on edited tracked files and on the wrong branch. Fast-forwards to `origin/main`, builds `api` and `worker`, runs `admin.py migrate` from the new image, restarts `api` and `worker` only, runs `admin.py selftest`, and prints a rollback command. Tested in `tests/test_deploy_script.py` with a stub `docker`. |
| `clip-api/scripts/admin.py` | `stuck` (QUEUED and RUNNING jobs), `db-status` (revision now and latest, exit 0 at head), `migrate`, `selftest`, `takedown`, account tools. |
| `docker-compose.yml` | `db` (Postgres 16, `pgdata` volume), `api` (healthcheck on `/health`), `worker`, `caddy`. Volumes `pgdata`, `data`, `caddy_*`. The project name is pinned to `clip-api` in `.env`. |
| `/health` | `{"ok": true, "accepting_jobs": ...}` after a `SELECT 1`. |
| Worker | Jobs carry `started_at` and `heartbeat_at`. A sweep fails and refunds RUNNING jobs with no heartbeat for 5 minutes. When idle, the worker writes nothing to the database, so "is the worker alive" is not visible from the database. |
| `DEPLOY.md` | Every deploy is `bash scripts/deploy.sh`. Backups are a manual `pg_dump` (plain SQL) in the one-time git switch. Rollback is `git checkout --detach <before>` plus a rebuild. |
| `.github/workflows/ci.yml` | `test` (pytest on Postgres) and `docker-build`, on pull requests into `staging` and `main` only. |
| Super Board | Merges go through `super-board-merge-gate.sh`, pinned to the reviewed head SHA. `merge_policy.default` is `human`, and production is never auto-merged. The board ends at Done (merged). It has no deploy lane. |

## Gaps

1. Deploys run only from a terminal on the droplet, usually from the owner's Mac. Nothing records who deployed what.
2. No automatic backup before a deploy, and no check that a backup can be restored.
3. `deploy.sh` deploys whatever `origin/main` is when it runs, not a chosen commit.
4. No check that CI passed on the deployed commit. CI runs only on pull requests, so a merge commit on `main` has no check runs of its own. Its tree equals the release PR's head tree. Example: #142 merged `91753cf` as `dfbd2a6`, and both have tree `1b078ab`.
5. Destructive migrations are prevented only by review. Nothing stops one at deploy time.
6. **A code rollback across a migration breaks startup.** `init_db()` runs `migrate()` at start. Alembic raises `Can't locate revision identified by '<rev>'` when the database is at a revision the older code does not have, so the older `api` and `worker` would not start. The "additive, so a code rollback needs no schema rollback" promise holds only for the schema, not for the startup. Checked locally: `migrate()` on a database stamped at an unknown revision raises `CommandError`.
7. After a rollback the checkout is detached, so the next `deploy.sh` refuses ("checkout is on 'HEAD'").
8. When `deploy.sh` fails before the restart (a failed migration, or a job started during the build), the checkout is left fast-forwarded. `web/` is served from the checkout, so the site is already on the new code while `api` and `worker` are on the old code.
9. No monitoring: disk, memory, containers, the queue and the age of the last backup are not watched.
10. The board's `migrations.globs` (`alembic/versions/**`, `**/migrations/*.sql`) do not match `clip-api/app/migrations/versions/*.py`, so the board's migration gate never fires on this repo. Not changed here, because config is not hand-edited mid-run. It needs a `/super-board onboard` repair.
11. **The repo is private on a personal account.** GitHub offers required reviewers on environments only for public repositories or on GitHub Enterprise. GitHub Pro and Team allow environments, environment secrets and branch rules on private repos, but not reviewers. GitHub Free allows no environments on private repos at all (docs.github.com, "Managing environments for deployment", checked 2026-11-18).
12. Email and billing failures are invisible. The production audit found `STRIPE_WEBHOOK_SECRET` and SMTP unset. Without the secret, `/webhooks/stripe` answers 503 and Stripe's deliveries fail. An unsent email is only a log line.

## Design

```
owner merges release PR (by hand or via the merge gate)
owner runs: gh workflow run deploy.yml -f ref=<sha>       (or the Actions UI)
  gate job (no secrets): target on main, CI evidence for the exact tree
  deploy job (environment: production; human gate: reviewer approval or the owner's confirm)
    ssh clipops@droplet "preflight <sha>"   forced command, so only ops.sh runs
    runner + server: destructive-migration check on pending revisions
    "backup db|full <keep>"                 pg_dump -Fc, verified, retention
    "deploy <sha>"                          wraps deploy.sh with DEPLOY_SHA=<sha>
    "verify <sha>"                          commit, db-status, /health, worker, containers
    on failure after a restart: "rollback <previous>" then "verify <previous> rollback"
  job summary and a comment on the release PR
```

- **One entry point on the server.** `clip-api/scripts/ops.sh` is installed as root-owned `/usr/local/sbin/clutchclips-ops`. A dedicated user `clipops` has one key in `authorized_keys`, with `restrict` (no pty, no forwarding) and a forced command that runs `sudo -n /usr/local/sbin/clutchclips-ops "$SSH_ORIGINAL_COMMAND"`. sudoers allows that one path only. `ops.sh` accepts only `[a-z0-9 ]` characters, at most 200 of them, and a fixed grammar: `status`, `preflight [<sha>]`, `backup <db|full> <keep>`, `deploy <sha>`, `verify <sha> [rollback]` and `rollback <sha>`. A SHA must be 40 lowercase hex characters. Nothing is passed to a shell or `eval`.
- **Why root at the end of it.** The checkout and `.env` live under `/root`, and the docker socket is root-equivalent anyway: membership in the `docker` group is not a security boundary. The boundary is the forced command plus a sudo rule for one script. The key logs in as an unprivileged user who cannot get a shell. The installed copy lives outside the repo, so a merged PR cannot change what the key may run until the owner reinstalls it. `preflight` reports when the installed copy differs from the repo.
- **`deploy.sh` is wrapped, not copied.** It gains one optional variable, `DEPLOY_SHA`. When set, it must be on `origin/main`, and the fast-forward goes to that commit instead of the branch head. `ops.sh deploy` adds the missing pieces around it:
  - it reattaches a detached checkout (gap 7)
  - it runs the migration check
  - it restores the checkout when `deploy.sh` fails before the restart (gap 8)
  - it tells the workflow whether containers were restarted
- **CI evidence (gap 4).** Either the target commit itself has successful `test` and `docker-build` check runs, or the target is the merge commit of a PR whose head has them and whose tree is identical. Every latest run of each check must be `success`. Pending, failed, missing or a different tree all refuse.
- **Destructive migrations (gap 5).** `clip-api/scripts/check_migrations.py` uses only the standard library. It walks the revision chain from the database's revision to head and parses each pending file with `ast`. It refuses on any `drop_*`, `rename_*` or `alter_column(type_=..., new_column_name=...)` outside `downgrade()`. It also refuses SQL text with DROP, TRUNCATE, RENAME, `DELETE FROM`, `UPDATE ... SET` or `ALTER ... TYPE`, and any non-literal `execute()` it cannot read. It runs on the runner and again on the server. It has no override: such a revision is deployed by hand by the owner, after a backup.
- **Rollback is code only (gap 6).** `rollback <sha>` refuses when the database revision is not in the target's revision files, because that code would not start. The report then says a manual decision is needed. A database restore is never automatic.
- **Backups.** `pg_dump -Fc` runs inside the `db` container and is written to `/root/backups/db-<UTC>-<sha7>.dump.partial`. It is verified before it gets its final name: the file is non-empty, `pg_restore --list` reads it, and its TOC has as many tables as the live database. The data volume is backed up only with `backup_data: true`, after a free-disk check. Retention keeps the newest N of each kind, so the newest verified backup is never deleted. Pruning only deletes files with the pipeline's own name pattern.
- **Monitoring.** `monitor.yml` runs every 15 minutes: SSH `status` (read-only, no lock), then `.github/ops/opsctl.py monitor` compares it with `.github/ops/config.json`. On a breach or failure it opens or updates one issue labelled `ops` and assigns it to the owner, which makes GitHub email the owner. It closes the issue when the server is healthy again. The check only reads from the server, but the run itself can only pick up the environment's secrets without an approval if the environment allows it, so monitoring uses its own environment, `production-readonly`, with no reviewers. It holds a second, read-only key whose forced command allows only `status`. See setup.md.
- **Worker health.** A new read-only `admin.py ops-status` command prints the RUNNING and QUEUED counts, the age of the oldest QUEUED job, the stalest heartbeat and the minutes since the last claim. `verify` also requires the worker container to log `worker started` after its restart, with an unchanged restart count.
- **The human gate has two modes** (gap 11), chosen with the repo variable `PROD_APPROVAL`:
  - `environment`: the `production` environment's required reviewer (the owner) approves each run in GitHub's UI. Use this mode only where the plan offers reviewers.
  - Anything else (the default, and the only option on Pro or Team for this private repo): the gate job refuses a non-dry run unless the owner dispatched it by hand, with the first 7 characters of the target commit typed into `confirm`.
  A dry run needs neither. The devops agent never types `confirm` and never approves an environment. In the default mode it runs dry runs and hands the owner the exact command for the real one. Both modes rest on the same rule: agents use the owner's `gh` login, so they could technically approve either way, and the agent definition forbids it. A hook that blocks `pending_deployments` calls and `confirm=` would make the rule mechanical. That is a settings change for the owner.
- **Email and billing are watched too** (gap 12). `admin.py ops-status` prints `email_configured`, `stripe_configured` and `stripe_webhook_configured` as 1 or 0, which says whether each is set and never shows a value. `ops.sh status` counts, from the last hour of `api` and `worker` logs, the 2xx and the 4xx/5xx answers to `POST .../webhooks/stripe`, plus "Failed to send email" and "SMTP not configured" lines. It prints counts only, never log lines. The monitor alerts when email or the webhook secret is unset, when more than 2 webhook deliveries failed in the hour, and when any email failed.
- **Merging stays where it is.** The pipeline never merges. A release PR is merged by the owner or by the merge gate. A deploy is a separate, approved run afterwards. See "Fit with the board" in setup.md.
