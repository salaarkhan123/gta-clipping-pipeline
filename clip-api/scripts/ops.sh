#!/usr/bin/env bash
# The only thing GitHub Actions can run on the droplet. Installed as root-owned /usr/local/sbin/clutchclips-ops and
# reached through an SSH forced command (docs/devops/setup.md), so the request arrives as one string:
#
#   status                       read-only health: load, memory, disk, containers, queue, backup age
#   preflight [<sha>]            read-only: commit, DB revision, running jobs; with <sha>, whether it can be deployed
#                                (newer: destructive-migration check) or rolled back to (older: can its code start)
#   backup <db|full> <keep>      pg_dump -Fc, verified; full also tars the data volume; keeps the newest <keep>
#   deploy <sha>                 scripts/deploy.sh with DEPLOY_SHA=<sha>, after the migration check
#   verify <sha> [rollback]      commit, db-status, /health, containers, worker started and stable
#   rollback <sha>               code only: back to an earlier commit on main; never touches the database
#
# Only [a-z0-9 ] is accepted, at most 200 characters, a <sha> is 40 lowercase hex characters, and nothing is passed
# to eval or a shell. Machine-readable key=value lines go to stdout; everything else (build logs too) to stderr.
# Exit 0 ok, 1 refused or failed, 64 bad request.
#
# Settings below are fixed for production. The OPS_* overrides exist for tests: sudo's env_reset drops them, and
# sshd passes no client environment beyond LANG/LC_*.
set -euo pipefail
set -f
umask 077
trap '' HUP   # a dropped SSH connection must not kill a deploy halfway

export PATH="${OPS_EXTRA_PATH:+$OPS_EXTRA_PATH:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
APP_DIR=${OPS_APP_DIR:-/root/clip-api}
BACKUP_DIR=${OPS_BACKUP_DIR:-/root/backups}
LOG_DIR=${OPS_LOG_DIR:-/var/log/clutchclips-ops}
LOCK_FILE=${OPS_LOCK_FILE:-/run/lock/clutchclips-ops.lock}
INSTALLED=${OPS_INSTALLED:-/usr/local/sbin/clutchclips-ops}
PROC=${OPS_PROC:-/proc}
IDLE_WAIT_SEC=${OPS_IDLE_WAIT_SEC:-600}      # rollback waits this long for a RUNNING job to finish
WORKER_WAIT_SEC=${OPS_WORKER_WAIT_SEC:-300}  # verify waits this long for "worker started" (models load first)
STABLE_SEC=${OPS_STABLE_SEC:-20}             # then the worker must stay up, without restarts, this long
POLL_SEC=${OPS_POLL_SEC:-5}
FREE_MARGIN_MB=${OPS_FREE_MARGIN_MB:-2048}   # disk that must stay free after a backup
BRANCH=main
if [ "$(id -u)" = 0 ]; then export HOME=/root; fi   # git uses root's GitHub deploy key

log() { printf '%s\n' "$*" >&2; }
out() { printf '%s=%s\n' "$1" "$2"; }
die() { log "refusing: $*"; out result refused; exit 1; }
usage() {
  log "usage: status | preflight [<sha>] | backup <db|full> <keep 1-99> | deploy <sha> | verify <sha> [rollback] | rollback <sha>"
  log "  <sha> is a full 40-character lowercase commit sha"
  exit 64
}

# ---- the request -------------------------------------------------------------------------------------------------
if [ $# -eq 0 ]; then req=${SSH_ORIGINAL_COMMAND:-}; else req="$*"; fi
[ "${#req}" -le 200 ] || usage
[[ "$req" =~ ^[a-z0-9\ ]+$ ]] || usage
read -r -a w <<< "$req"
verb=${w[0]:-}
n=${#w[@]}
a1=${w[1]:-}
a2=${w[2]:-}
is_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }
case "$verb:$n" in   # the whole grammar, checked before anything runs
  status:1 | preflight:1) ;;
  preflight:2 | deploy:2 | verify:2 | rollback:2) is_sha "$a1" || usage ;;
  verify:3) is_sha "$a1" && [ "$a2" = rollback ] || usage ;;
  backup:3) [[ "$a1" =~ ^(db|full)$ && "$a2" =~ ^[1-9][0-9]?$ ]] || usage ;;
  *) usage ;;
esac

# ---- helpers -----------------------------------------------------------------------------------------------------
dc() { docker compose "$@"; }
head_sha() { git rev-parse HEAD; }
on_branch() { git symbolic-ref -q --short HEAD || echo detached; }
tracked_clean() { [ -z "$(git status --porcelain --untracked-files=no)" ]; }
mb_free() { df -Pk "$1" | awk 'NR==2 {print int($4/1024)}'; }
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

take_lock() {
  exec 9>"$LOCK_FILE"
  flock -n 9 || die "another ops command is running"
}

# RUNNING job lines; exit 2 when the job list cannot be read (as deploy.sh).
running_jobs() {
  local o
  o=$(dc exec -T api python scripts/admin.py stuck) || return 2
  printf '%s\n' "$o" | awk '$2 == "RUNNING"'
}

# Prints "<revision> <latest>" from db-status ("revision 0007 · latest 0007"); nothing when it cannot be read.
db_revision() {
  dc exec -T api python scripts/admin.py db-status 2>/dev/null | awk '$1 == "revision" {
    latest = "unknown"; for (i = 2; i < NF; i++) if ($i == "latest") latest = $(i + 1); print $2, latest; exit }' || true
}

fetch_main() {
  git fetch --quiet origin "$BRANCH" || die "git fetch failed"
  git cat-file -e "$1^{commit}" 2>/dev/null || die "$1 is not a known commit"
  git merge-base --is-ancestor "$1" "origin/$BRANCH" || die "$1 is not on origin/$BRANCH"
}

# check_migrations.py on <sha>'s revision files against the database revision. key=value lines prefixed migration_.
migration_check() {
  local sha=$1 rev=$2 tmp prefix checker rc=0
  prefix=$(git rev-parse --show-prefix)
  tmp=$(mktemp -d)
  git -C "$(git rev-parse --show-toplevel)" archive "$sha" "${prefix}app/migrations/versions" | tar -x -C "$tmp"
  checker="$APP_DIR/scripts/check_migrations.py"
  if [ ! -f "$checker" ]; then   # the first deploy of the checker: take it from the target
    checker="$tmp/check_migrations.py"
    git show "$sha:${prefix}scripts/check_migrations.py" > "$checker" 2>/dev/null || { rm -rf "$tmp"; die "no migration checker"; }
  fi
  python3 "$checker" --versions "$tmp/${prefix}app/migrations/versions" --current "$rev" | sed 's/^/migration_/' || rc=$?
  rm -rf "$tmp"
  return "$rc"
}

wait_health() {
  local i
  for i in $(seq 1 30); do
    if dc exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" >/dev/null 2>&1; then
      return 0
    fi
    [ "$i" -lt 30 ] && sleep 2
  done
  return 1
}

new_log() {
  mkdir -p "$LOG_DIR"
  printf '%s/%s-%s.log' "$LOG_DIR" "$1" "$(date -u +%Y%m%dT%H%M%SZ)"
}

# ---- verbs -------------------------------------------------------------------------------------------------------
cmd_status() {
  local load cpus total avail s id state health rev ok newest logs
  out time_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  read -r load _ < "$PROC/loadavg" 2>/dev/null || load=unknown
  out load1 "$load"
  cpus=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)
  out cpus "$cpus"
  total=$(awk '$1 == "MemTotal:" {print int($2/1024)}' "$PROC/meminfo" 2>/dev/null || true)
  avail=$(awk '$1 == "MemAvailable:" {print int($2/1024)}' "$PROC/meminfo" 2>/dev/null || true)
  out mem_total_mb "${total:-unknown}"
  out mem_avail_mb "${avail:-unknown}"
  out disk_free_mb "$(mb_free /)"
  out disk_used_pct "$(df -Pk / | awk 'NR==2 {sub("%", "", $5); print $5}')"
  for s in db api worker caddy; do
    id=$(dc ps -q "$s" 2>/dev/null | head -n 1 || true)
    if [ -z "$id" ]; then out "container_$s" missing; continue; fi
    state=$(docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || echo unknown)
    health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$id" 2>/dev/null || true)
    out "container_$s" "$state${health:+/$health}"
  done
  if ok=$(dc exec -T api python scripts/admin.py ops-status 2>/dev/null); then
    printf '%s\n' "$ok" | grep -E '^[a-z_]+=-?[0-9]+$' || true
    out queue_readable yes
  else
    out queue_readable no
  fi
  # Counts only, from the last hour of logs; no log line is printed (they can hold addresses).
  logs=$(dc logs --no-color --since 1h api worker 2>/dev/null || true)
  out stripe_webhook_ok_1h "$(printf '%s\n' "$logs" | grep -Ec '"POST [^ "]*/webhooks/stripe[^ "]* HTTP/[0-9.]+" 2[0-9][0-9]' || true)"
  out stripe_webhook_errors_1h "$(printf '%s\n' "$logs" | grep -Ec '"POST [^ "]*/webhooks/stripe[^ "]* HTTP/[0-9.]+" [45][0-9][0-9]' || true)"
  out email_failures_1h "$(printf '%s\n' "$logs" | grep -Ec 'Failed to send email|SMTP not configured; email' || true)"
  newest=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'db-*.dump.ok' 2>/dev/null | sort | tail -n 1)
  if [ -n "$newest" ]; then
    out backup_newest "$(basename "${newest%.ok}")"
    out backup_age_hours "$(( ($(date +%s) - $(awk -F= '$1 == "created_epoch" {print $2}' "$newest")) / 3600 ))"
  else
    out backup_newest none
    out backup_age_hours -1
  fi
  out commit "$(head_sha)"
  rev=$(db_revision)
  out db_revision "${rev%% *}"
  out result ok
}

cmd_preflight() {
  local sha=$1 failed=0 jobs rc rev latest here relation
  here=$(head_sha)
  out commit "$here"
  out branch "$(on_branch)"
  if tracked_clean; then out tracked_edits no; else out tracked_edits yes; failed=1; log "tracked files were edited on the server"; fi
  rc=0; jobs=$(running_jobs) || rc=$?
  if [ "$rc" -ne 0 ]; then
    out jobs_running unknown; failed=1; log "could not list jobs (is the api container up?)"
  else
    out jobs_running "$(printf '%s' "$jobs" | grep -c . || true)"
    [ -z "$jobs" ] || { failed=1; log "a job is RUNNING:"; log "$jobs"; }
  fi
  read -r rev latest <<< "$(db_revision)" || true
  out db_revision "${rev:-unknown}"
  out db_latest "${latest:-unknown}"
  [ -n "${rev:-}" ] || { failed=1; log "could not read the database revision"; }
  out disk_free_mb "$(mb_free "$(dirname "$BACKUP_DIR")")"
  if [ ! -f "$INSTALLED" ]; then out ops_installed absent
  elif cmp -s "$INSTALLED" "$APP_DIR/scripts/ops.sh"; then out ops_installed same
  else out ops_installed differs; log "the installed ops script differs from scripts/ops.sh in this checkout; reinstall it (setup.md)"
  fi
  if [ -n "$sha" ]; then
    out target "$sha"
    git fetch --quiet origin "$BRANCH" || { failed=1; log "git fetch failed"; }
    if git cat-file -e "$sha^{commit}" 2>/dev/null && git merge-base --is-ancestor "$sha" "origin/$BRANCH"; then
      out target_on_main yes
      if [ "$sha" = "$here" ]; then relation=same
      elif git merge-base --is-ancestor "$here" "$sha"; then relation=newer
      elif git merge-base --is-ancestor "$sha" "$here"; then relation=older
      else relation=diverged; failed=1
      fi
      out target_relation "$relation"
      # Newer: no destructive revision may be pending. Older (a rollback): the database revision must be in the
      # target's files, because that code runs migrate() at start and fails on a revision it does not know.
      if [ -n "${rev:-}" ] && [ "$relation" != diverged ]; then
        migration_check "$sha" "$rev" || failed=1
      fi
    else
      out target_on_main no; failed=1; log "$sha is not on origin/$BRANCH"
    fi
  fi
  if [ "$failed" -ne 0 ]; then out result refused; exit 1; fi
  out result ok
}

# prune <glob> <keep>: delete verified backups beyond the newest <keep>. keep >= 1, so the newest verified stays.
prune() {
  local pattern=$1 keep=$2 old
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "$pattern.ok" | sort | awk -v keep="$keep" '
    { line[NR] = $0 } END { for (i = 1; i <= NR - keep; i++) print line[i] }' | while read -r old; do
    rm -f -- "${old%.ok}" "$old"
    log "pruned $(basename "${old%.ok}")"
  done
}

cmd_backup() {
  local kind=$1 keep=$2 ts short db_mb data_mb=0 free need f bytes toc dumped live vol img d entries
  take_lock
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  short=$(git rev-parse --short=7 HEAD)
  db_mb=$(dc exec -T db psql -U clip -d clip -tAc "select pg_database_size(current_database()) / 1048576" | tr -dc 0-9)
  [ -n "$db_mb" ] || die "could not read the database size"
  if [ "$kind" = full ]; then
    vol=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/srv/data"}}{{.Name}}{{end}}{{end}}' "$(dc ps -q worker | head -n 1)")
    [ -n "$vol" ] || die "could not find the data volume of the worker container"
    data_mb=$(du -sk "$(docker volume inspect -f '{{.Mountpoint}}' "$vol")" | awk '{print int($1/1024)}')
  fi
  free=$(mb_free "$BACKUP_DIR")
  need=$(( db_mb + data_mb + FREE_MARGIN_MB ))
  out backup_free_mb "$free"
  out backup_need_mb "$need"
  [ "$free" -ge "$need" ] || die "not enough disk: ${free} MB free, need ${need} MB (database ${db_mb} MB, data ${data_mb} MB, margin ${FREE_MARGIN_MB} MB)"

  f="$BACKUP_DIR/db-$ts-$short.dump"
  if ! dc exec -T db pg_dump -U clip -d clip -Fc > "$f.partial"; then rm -f "$f.partial"; die "pg_dump failed"; fi
  bytes=$(wc -c < "$f.partial" | tr -d ' ')
  [ "$bytes" -gt 0 ] || { rm -f "$f.partial"; die "the dump is empty"; }
  if ! toc=$(dc exec -T db pg_restore --list < "$f.partial"); then rm -f "$f.partial"; die "pg_restore --list cannot read the dump"; fi
  dumped=$(printf '%s\n' "$toc" | grep -c ' TABLE public ' || true)
  live=$(dc exec -T db psql -U clip -d clip -tAc "select count(*) from pg_tables where schemaname = 'public'" | tr -dc 0-9)
  if [ -z "$live" ] || [ "$live" -eq 0 ] || [ "$dumped" -ne "$live" ]; then
    rm -f "$f.partial"; die "the dump has ${dumped} tables, the database ${live:-unknown}"
  fi
  mv "$f.partial" "$f"
  printf 'created_epoch=%s\nbytes=%s\ntables=%s\nsha256=%s\n' "$(date +%s)" "$bytes" "$dumped" "$(sha256 "$f")" > "$f.ok"
  out backup_db_file "$f"
  out backup_db_bytes "$bytes"
  out backup_db_tables "$dumped"
  out backup_db_verified yes

  if [ "$kind" = full ]; then
    d="$BACKUP_DIR/data-$ts-$short.tar.gz"
    img=$(docker inspect -f '{{.Image}}' "$(dc ps -q worker | head -n 1)")
    if ! docker run --rm --network none -v "$vol:/srv/data:ro" --entrypoint tar "$img" -czf - -C /srv/data . > "$d.partial"; then
      rm -f "$d.partial"; die "the data volume backup failed"
    fi
    entries=$(tar -tzf "$d.partial" 2>/dev/null | wc -l | tr -d ' ') || entries=0
    [ "$entries" -gt 0 ] || { rm -f "$d.partial"; die "the data archive cannot be read"; }
    mv "$d.partial" "$d"
    bytes=$(wc -c < "$d" | tr -d ' ')
    printf 'created_epoch=%s\nbytes=%s\nentries=%s\nsha256=%s\n' "$(date +%s)" "$bytes" "$entries" "$(sha256 "$d")" > "$d.ok"
    out backup_data_file "$d"
    out backup_data_bytes "$bytes"
    out backup_data_verified yes
    prune 'data-*.tar.gz' "$keep"
  fi
  prune 'db-*.dump' "$keep"
  out result ok
}

cmd_deploy() {
  local sha=$1 before rev ids_before ids_after restarted rc=0 logf
  take_lock
  tracked_clean || die "tracked files were edited on the server"
  fetch_main "$sha"
  before=$(head_sha)
  git merge-base --is-ancestor "$before" "$sha" || die "$sha is older than the checkout ($before): use rollback"
  read -r rev _ <<< "$(db_revision)" || true
  [ -n "${rev:-}" ] || die "could not read the database revision"
  migration_check "$sha" "$rev" || die "a pending migration is destructive or unreadable (lines above). It is never run automatically: the owner deploys it by hand after a backup"
  if [ "$(on_branch)" = detached ]; then
    git checkout -q -B "$BRANCH"   # after a rollback; HEAD and the files stay where they are
  fi
  ids_before=$(dc ps -q api worker | sort | tr '\n' ' ')
  logf=$(new_log deploy)
  DEPLOY_SHA=$sha bash "$APP_DIR/scripts/deploy.sh" > "$logf" 2>&1 || rc=$?
  tail -n 120 "$logf" >&2
  ids_after=$(dc ps -q api worker | sort | tr '\n' ' ')
  if [ "$ids_before" = "$ids_after" ]; then restarted=no; else restarted=yes; fi
  out previous "$before"
  out restarted "$restarted"
  out deploy_log "$logf"
  if [ "$rc" -ne 0 ]; then
    if [ "$restarted" = no ] && [ "$(head_sha)" != "$before" ]; then
      git checkout -q -B "$BRANCH" "$before"   # nothing restarted: files back to what api and worker run
      out checkout_restored yes
    fi
    out commit "$(head_sha)"
    out selftest "$(grep -q 'selftest FAILED' "$logf" && echo failed || echo not-passed)"
    out result failed
    exit 1
  fi
  out commit "$(head_sha)"
  out selftest passed
  out result ok
}

cmd_verify() {
  local sha=$1 mode=$2 failed=0 here o rc rev s id state body started restarts restarts2 i
  here=$(head_sha)
  out commit "$here"
  if [ "$here" = "$sha" ]; then out verify_commit ok; else out verify_commit fail; failed=1; log "checkout is at $here, expected $sha"; fi

  rc=0; o=$(dc exec -T api python scripts/admin.py db-status 2>/dev/null) || rc=$?
  rev=$(printf '%s\n' "$o" | awk '$1 == "revision" {print $2; exit}')
  out db_revision "${rev:-unknown}"
  if [ -z "$rev" ]; then out verify_db fail; failed=1; log "db-status did not answer"
  elif [ "$mode" = deploy ] && [ "$rc" -ne 0 ]; then out verify_db fail; failed=1; log "db-status: not at the latest revision"; log "$o"
  else out verify_db ok
  fi

  body=""
  for i in $(seq 1 12); do
    body=$(dc exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health', timeout=5).read().decode())" 2>/dev/null || true)
    [[ "$body" =~ \"ok\":\ *true ]] && break
    [ "$i" -lt 12 ] && sleep "$POLL_SEC"
  done
  if [[ "$body" =~ \"ok\":\ *true ]]; then out verify_health ok; else out verify_health fail; failed=1; log "/health: ${body:-no answer}"; fi

  for s in db api worker caddy; do
    id=$(dc ps -q "$s" | head -n 1 || true)
    state=$([ -n "$id" ] && docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || echo missing)
    out "container_$s" "$state"
    [ "$state" = running ] || { failed=1; log "container $s is $state"; }
  done

  id=$(dc ps -q worker | head -n 1 || true)
  if [ -z "$id" ]; then
    out verify_worker fail; failed=1
  else
    started=$(docker inspect -f '{{.State.StartedAt}}' "$id")
    restarts=$(docker inspect -f '{{.RestartCount}}' "$id")
    o=fail
    for i in $(seq 1 $(( WORKER_WAIT_SEC / (POLL_SEC > 0 ? POLL_SEC : 1) + 1 ))); do
      if dc logs --no-color --since "$started" worker 2>&1 | grep -q 'worker started'; then o=ok; break; fi
      sleep "$POLL_SEC"
    done
    if [ "$o" = ok ]; then
      sleep "$STABLE_SEC"
      restarts2=$(docker inspect -f '{{.RestartCount}}' "$id" 2>/dev/null || echo gone)
      state=$(docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || echo gone)
      [ "$restarts2" = "$restarts" ] && [ "$state" = running ] || { o=fail; log "worker restarted or stopped after starting"; }
    else
      log "worker did not log 'worker started' within ${WORKER_WAIT_SEC}s"
    fi
    if [ "$o" = ok ] && dc exec -T worker python scripts/admin.py ops-status > /dev/null 2>&1; then
      out verify_worker ok
    else
      [ "$o" = fail ] || log "the worker container cannot read the queue"
      out verify_worker fail; failed=1
    fi
  fi
  if [ "$failed" -ne 0 ]; then out result failed; exit 1; fi
  out result ok
}

cmd_rollback() {
  local sha=$1 before before_branch rev logf i jobs rc
  take_lock
  tracked_clean || die "tracked files were edited on the server"
  fetch_main "$sha"
  before=$(head_sha)
  before_branch=$(on_branch)
  [ "$sha" != "$before" ] || die "the checkout is already at $sha"
  git merge-base --is-ancestor "$sha" "$before" || die "$sha is not earlier than the checkout ($before): deploy it instead"
  read -r rev _ <<< "$(db_revision)" || true
  [ -n "${rev:-}" ] || die "could not read the database revision"
  if ! migration_check "$sha" "$rev"; then
    die "the migration check failed for $sha with the database at $rev (lines above). When $sha does not have that revision, its api and worker would not start (migrate() at startup cannot find it), so a code rollback is not possible: decide by hand, see DEPLOY.md"
  fi

  for i in $(seq 1 $(( IDLE_WAIT_SEC / 15 + 1 ))); do
    rc=0; jobs=$(running_jobs) || rc=$?
    [ "$rc" -eq 0 ] && [ -z "$jobs" ] && break
    [ "$i" -eq 1 ] && log "waiting up to ${IDLE_WAIT_SEC}s for running jobs to finish"
    [ "$i" -le $(( IDLE_WAIT_SEC / 15 )) ] || die "a job is still RUNNING, or jobs cannot be listed; nothing was changed"
    sleep 15
  done

  restore() {
    if [ "$before_branch" = detached ]; then git checkout -q --detach "$before"; else git checkout -q "$before_branch"; fi
  }
  logf=$(new_log rollback)
  git checkout -q --detach "$sha"
  if ! dc build api worker > "$logf" 2>&1; then
    restore; tail -n 60 "$logf" >&2; die "build failed for $sha; nothing was restarted"
  fi
  rc=0; jobs=$(running_jobs) || rc=$?
  if [ "$rc" -ne 0 ] || [ -n "$jobs" ]; then restore; die "a job started during the build; nothing was restarted"; fi
  dc up -d api worker >> "$logf" 2>&1
  out previous "$before"
  out restarted yes
  out commit "$(head_sha)"
  out deploy_log "$logf"
  wait_health || log "api did not answer /health within 60s"
  if ! dc exec -T api python scripts/admin.py selftest >> "$logf" 2>&1; then
    tail -n 60 "$logf" >&2
    out selftest failed
    out result failed
    exit 1
  fi
  out selftest passed
  out result ok
}

cd "$APP_DIR"
case "$verb:$n" in
  status:1) cmd_status ;;
  preflight:*) cmd_preflight "$a1" ;;
  backup:3) cmd_backup "$a1" "$a2" ;;
  deploy:2) cmd_deploy "$a1" ;;
  verify:2) cmd_verify "$a1" deploy ;;
  verify:3) cmd_verify "$a1" rollback ;;
  rollback:2) cmd_rollback "$a1" ;;
esac
