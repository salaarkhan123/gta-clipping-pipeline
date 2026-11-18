#!/usr/bin/env bash
# Deploy this server from git: pull the deploy branch, rebuild api + worker, migrate the schema, restart,
# run the selftest.
#
#   bash scripts/deploy.sh            # from clip-api/ (any directory works)
#
# Refuses to start, and refuses to restart, while a job is RUNNING (checked with `admin.py stuck`
# inside the api container, once before the pull and again after the build, right before the restart).
# If the job list cannot be read, it refuses too. Caddy and the database are never restarted; web/ is
# served straight from the checkout, so a pull updates the site.
#
# Migrations run from the new image (`admin.py migrate`) after the build and before the restart, while the old
# containers still serve. A failed migration stops the deploy with the old code running and, on Postgres, the
# schema unchanged (each upgrade runs in one transaction). Migrations must be additive, so old code keeps
# working on the new schema and a code rollback needs no schema rollback.
#
# Env: DEPLOY_BRANCH (default main).
set -euo pipefail
cd "$(dirname "$0")/.."
BRANCH="${DEPLOY_BRANCH:-main}"

running_jobs() {
  local out
  if ! out=$(docker compose exec -T api python scripts/admin.py stuck); then
    echo "refusing: could not list jobs (is the api container up?)" >&2
    return 2
  fi
  printf '%s\n' "$out" | awk '$2 == "RUNNING"'
}

require_idle() {
  local jobs
  jobs=$(running_jobs) || exit 1
  if [ -n "$jobs" ]; then
    echo "refusing: a job is RUNNING ($1). Try again when it finishes:" >&2
    printf '%s\n' "$jobs" >&2
    exit 1
  fi
}

branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" != "$BRANCH" ]; then
  echo "refusing: checkout is on '$branch', deploy branch is '$BRANCH'" >&2
  exit 1
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "refusing: tracked files were edited on the server; commit them through a PR instead:" >&2
  git status --short --untracked-files=no >&2
  exit 1
fi

require_idle "before pull"
before=$(git rev-parse --short HEAD)
git fetch --quiet origin "$BRANCH"
git merge --ff-only --quiet "origin/$BRANCH"
after=$(git rev-parse --short HEAD)
echo "code: $before -> $after"

docker compose build api worker
require_idle "after build"
if ! docker compose run --rm -T api python scripts/admin.py migrate; then
  echo "migration FAILED on $after; nothing was restarted. Put the code back with:" >&2
  echo "  git checkout --detach $before" >&2
  exit 1
fi
docker compose up -d api worker

for _ in $(seq 1 60); do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker compose exec -T api python scripts/admin.py selftest; then
  echo "selftest FAILED on $after. Roll back with:" >&2
  echo "  git checkout --detach $before && docker compose up -d --build api worker" >&2
  exit 1
fi
echo "deployed $after"
