#!/bin/bash
# Local CI: the jobs of .github/workflows/ci.yml, run on this Mac in Docker at no cost, for one exact commit.
# Each result goes to GitHub as a commit status on that commit (local-ci/test, local-ci/docker-build), so merge
# gates can require it. Heavy jobs wait for the shared queue (~/ClutchClips-eval/heavy.sh), one at a time.
#
# Usage: ci/local-ci.sh <pr-number | commit> [all|test|docker-build]
#
# test          the production image's base (python:3.12-slim-trixie, Debian ffmpeg 7.1) with git and node, against Postgres 16,
#               `pytest -q -rs`, like the GitHub job. Runs natively (linux/arm64 on Apple silicon); GitHub ran amd64.
# docker-build  `docker build clip-api` for linux/amd64, the production droplet's platform. The image is removed after.
# A change made only of Markdown files outside clip-api/ and web-src/ needs neither job; both get a success status
# that says so. Nothing here reads the repository's settings files, and no secret goes into a container.
#
# docker-build runs before test when both are requested. Building first fails fast and avoids starting the amd64
# image build after a 30-minute test has already stressed Docker Desktop's VM (which produced a 1-second false
# failure on edd8a9c4 with a hardcoded "image built" status line).
set -euo pipefail

target="${1:?usage: ci/local-ci.sh <pr-number | commit> [all|test|docker-build]}"
which="${2:-all}"
HOME_DIR="${LOCAL_CI_HOME:-$HOME/.cache/clutchclips-ci}"
QUEUE="${LOCAL_CI_QUEUE:-$HOME/ClutchClips-eval/heavy.sh}"
TEST_CPUS="${LOCAL_CI_CPUS:-4}"
TIMEOUT_SEC=2700   # 45 min, the GitHub job's limit
ROOT="$(git rev-parse --show-toplevel)"
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
mkdir -p "$HOME_DIR/logs"

if [[ "$target" =~ ^[0-9]+$ ]]; then
  sha="$(gh pr view "$target" --json headRefOid --jq .headRefOid)"
  base="$(gh pr view "$target" --json baseRefName --jq .baseRefName)"
else
  git -C "$ROOT" fetch -q origin
  sha="$(git -C "$ROOT" rev-parse "$target^{commit}")"
  base="staging"
fi
git -C "$ROOT" fetch -q origin "$sha" "$base"
short="${sha:0:8}"
log="$HOME_DIR/logs/$short"

status() {  # context state description
  gh api -X POST "repos/$REPO/statuses/$sha" -f state="$2" -f context="local-ci/$1" \
    -f description="${3:0:139}" >/dev/null
}

jobs=()
# docker-build first when both run: image check before the long pytest, and Docker Desktop stays fresh.
case "$which" in
  all) jobs=(docker-build test) ;;
  test|docker-build) jobs=("$which") ;;
  *) echo "unknown job: $which" >&2; exit 2 ;;
esac

changed="$(git -C "$ROOT" diff --name-only "origin/$base...$sha")"
if [ -n "$changed" ] && ! grep -vE '\.md$' <<<"$changed" | grep -q . \
   && ! grep -qE '^(clip-api|web-src)/' <<<"$changed"; then
  n="$(wc -l <<<"$changed" | tr -d ' ')"
  for j in "${jobs[@]}"; do status "$j" success "docs only: $n Markdown file(s) outside clip-api/ and web-src/, no job needed"; done
  echo "$short: docs only ($n file(s)); statuses set to success"
  exit 0
fi

for j in "${jobs[@]}"; do status "$j" pending "queued on this Mac"; done

MAIN="$(dirname "$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)")"
src="$MAIN/.claude/worktrees/ci-$short"   # worktrees live only under .claude/worktrees/
net="lci-$short"
cleanup() {
  docker rm -f "lci-pg-$short" "lci-test-$short" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
  docker image rm -f "lci-build:$short" >/dev/null 2>&1 || true
  git -C "$ROOT" worktree remove --force "$src" >/dev/null 2>&1 || rm -rf "$src"
}
trap cleanup EXIT
git -C "$ROOT" worktree add -q --detach "$src" "$sha"

queue() {  # label command... : wait for the shared queue when it exists
  if [ -x "$QUEUE" ]; then "$QUEUE" "$@"; else shift; "$@"; fi
}

with_timeout() {  # container-name command... : kill the container after TIMEOUT_SEC
  local name="$1"; shift
  ( sleep "$TIMEOUT_SEC"; docker kill "$name" >/dev/null 2>&1 ) & local guard=$!
  local rc=0; "$@" || rc=$?
  kill "$guard" 2>/dev/null || true
  return $rc
}

run_test() {
  # The base and ffmpeg of clip-api/Dockerfile (python:3.12-slim-trixie, Debian ffmpeg 7.1), so the tests render
  # with the ffmpeg production renders with; plus git and node, so no test is skipped for a missing tool.
  local reqs; reqs="$(cat "$src/clip-api/requirements.txt" "$src/clip-api/requirements-dev.txt" | shasum | cut -c1-12)"
  local image="clutchclips-ci:trixie-$reqs"
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    printf '%s\n' 'FROM python:3.12-slim-trixie' 'ENV DEBIAN_FRONTEND=noninteractive' \
      "RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git nodejs ca-certificates fonts-dejavu-core && ffmpeg -version | head -1 | grep -q '^ffmpeg version 7\.1\.' && rm -rf /var/lib/apt/lists/*" \
      'COPY requirements.txt requirements-dev.txt /tmp/' \
      'RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-dev.txt' \
      | docker build -q -t "$image" -f - "$src/clip-api" >/dev/null
  fi
  docker network create "$net" >/dev/null
  docker run -d --name "lci-pg-$short" --network "$net" -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=clipapi_test postgres:16 >/dev/null
  for _ in $(seq 1 60); do docker exec "lci-pg-$short" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 2; done
  sleep 2
  with_timeout "lci-test-$short" docker run --rm --name "lci-test-$short" --network "$net" --cpus "$TEST_CPUS" \
    --memory 5g -e PYTHONDONTWRITEBYTECODE=1 \
    -e TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@lci-pg-$short:5432/clipapi_test" \
    -v "$src/clip-api:/src" -w /src "$image" pytest -q -rs -p no:cacheprovider
}

run_docker_build_once() {
  # Prove the daemon answers before the amd64 build; a dead Docker Desktop fails in ~1s otherwise.
  docker version >/dev/null
  if command -v timeout >/dev/null 2>&1; then
    timeout "$TIMEOUT_SEC" docker build --platform linux/amd64 -t "lci-build:$short" "$src/clip-api"
  else
    docker build --platform linux/amd64 -t "lci-build:$short" "$src/clip-api"
  fi
}

# One automatic retry for docker-build: clears transient Docker Desktop / qemu blips.
run_docker_build() {
  local attempt=1 rc=0
  while [ "$attempt" -le 2 ]; do
    rc=0
    run_docker_build_once || rc=$?
    [ "$rc" -eq 0 ] && return 0
    if [ "$attempt" -eq 1 ]; then
      echo "docker-build attempt 1 failed (rc=$rc); waiting 15s and retrying once" >&2
      docker builder prune -f >/dev/null 2>&1 || true
      sleep 15
    fi
    attempt=$((attempt + 1))
  done
  return "$rc"
}

log_tail_summary() {  # file -> short failure hint for the GitHub status
  local file="$1" line
  line="$(grep -Eie 'error|failed|denied|no space|cannot|killed|qemu|exec format|not found' "$file" | tail -1 \
    | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | cut -c1-90)"
  if [ -n "$line" ]; then
    printf '%s' "$line"
  else
    printf 'docker build failed (see log)'
  fi
}

export -f run_test run_docker_build run_docker_build_once with_timeout
export src net short TEST_CPUS TIMEOUT_SEC

overall=0
for j in "${jobs[@]}"; do
  status "$j" pending "running on this Mac"
  start=$(date +%s); rc=0
  fn="run_test"; [ "$j" = docker-build ] && fn="run_docker_build"
  queue "local-ci $j $short" bash -c "$fn" >"$log-$j.log" 2>&1 || rc=$?
  mins=$(( ($(date +%s) - start) / 60 ))
  if [ "$j" = test ]; then
    summary="$(grep -E '[0-9]+ (passed|failed|error)' "$log-$j.log" | tail -1 | sed 's/=//g; s/^ *//; s/ *$//')"
  elif [ $rc -eq 0 ]; then
    summary="image built for linux/amd64"
  else
    summary="$(log_tail_summary "$log-$j.log")"
  fi
  if [ $rc -eq 0 ]; then
    status "$j" success "${summary:-passed} · ${mins} min on this Mac"
  else
    overall=1
    status "$j" failure "${summary:-exit $rc} · see $log-$j.log on this Mac"
  fi
  echo "$short $j: rc=$rc ${summary:-} (${mins} min) log $log-$j.log"
done
exit $overall
