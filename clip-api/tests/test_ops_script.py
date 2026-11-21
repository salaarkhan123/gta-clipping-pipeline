"""scripts/ops.sh (the forced-command wrapper) against a stub `docker`, a stub `flock` and a real local git remote."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

DOCKER = r"""#!/usr/bin/env bash
echo "$*" >> "$DOCKER_LOG"
gen=$(cat "$STATE/gen" 2>/dev/null || echo 1)
case "$*" in
  *"admin.py stuck"*) [ -n "${STUCK_FAIL:-}" ] && exit 1; printf '%b' "${STUCK_OUT:-}";;
  *"admin.py db-status"*) echo "revision ${DB_REV:-0002} · latest ${DB_LATEST:-0002}"; exit "${DBSTATUS_RC:-0}";;
  *"admin.py ops-status"*) printf 'jobs_running=0\njobs_queued=0\noldest_queued_min=-1\nstalest_heartbeat_min=-1\nlast_claim_min=7\n';;
  *"admin.py migrate"*) [ -n "${MIGRATE_FAIL:-}" ] && { echo "boom" >&2; exit 1; }; echo "schema ok";;
  *"admin.py selftest"*) [ -n "${SELFTEST_FAIL:-}" ] && { echo "FAIL  whisper"; exit 1; }; echo "OK    all";;
  *"python -c"*) echo '{"ok": true, "accepting_jobs": true}';;
  "compose ps -q api worker") echo "api$gen"; echo "worker$gen";;
  "compose ps -q api") echo "api$gen";;
  "compose ps -q worker") echo "worker$gen";;
  "compose ps -q db") echo "db1";;
  "compose ps -q caddy") echo "caddy1";;
  "compose build api worker") [ -n "${BUILD_FAIL:-}" ] && exit 1; true;;
  "compose up -d api worker") echo $((gen + 1)) > "$STATE/gen";;
  "compose logs --no-color --since 1h api worker") printf '%b' "${APP_LOGS:-}";;
  "compose logs"*) echo "worker started (captions: small.en)";;
  *pg_database_size*) echo " 5";;
  *pg_tables*) echo " ${LIVE_TABLES:-3}";;
  *pg_dump*) echo "PGDMP fake archive";;
  *"pg_restore --list"*) cat > /dev/null; [ -n "${RESTORE_FAIL:-}" ] && exit 1
    for i in $(seq 1 "${DUMP_TABLES:-3}"); do echo "$i; 1259 1 TABLE public t$i clip"; echo "$i; 0 1 TABLE DATA public t$i clip"; done;;
  "inspect -f {{.State.Status}}"*) echo running;;
  *"State.Health"*) case "$*" in *api*) echo healthy;; esac;;
  *RestartCount*) echo 0;;
  *StartedAt*) echo 2026-11-17T10:00:00Z;;
  *Mounts*) echo clip-api_data;;
  *"{{.Image}}"*) echo sha256:img;;
  "volume inspect"*) echo "$DATA_SRC";;
  "run --rm"*) tar -czf - -C "$DATA_SRC" .;;
esac
exit 0
"""


def git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def migration(rev: str, down: str | None, body: str = 'op.add_column("t", sa.Column("c", sa.Integer()))') -> str:
    return (f'import sqlalchemy as sa\nfrom alembic import op\nrevision = "{rev}"\ndown_revision = '
            f'{repr(down)}\n\ndef upgrade():\n    {body}\n\ndef downgrade():\n    op.drop_column("t", "c")\n')


class Server:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        origin, self.work, self.dev = tmp / "origin.git", tmp / "work", tmp / "dev"
        git(tmp, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp, "clone", "-q", str(origin), str(self.dev))
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(self.dev, "config", k, v)
        app = self.dev / "clip-api"
        (app / "scripts").mkdir(parents=True)
        (app / "app" / "migrations" / "versions").mkdir(parents=True)
        for name in ("deploy.sh", "ops.sh", "check_migrations.py"):
            shutil.copy(SCRIPTS / name, app / "scripts" / name)
        self.commit({"app/migrations/versions/0001_a.py": migration("0001", None),
                     "app/migrations/versions/0002_b.py": migration("0002", "0001")}, "one")
        git(tmp, "clone", "-q", str(origin), str(self.work))
        bindir, self.state, self.data = tmp / "bin", tmp / "state", tmp / "data"
        for d in (bindir, self.state, self.data, tmp / "backups", tmp / "logs"):
            d.mkdir()
        (self.data / "clip.mp4").write_text("x")
        (bindir / "docker").write_text(DOCKER)
        (bindir / "flock").write_text("#!/bin/sh\nexit 0\n")
        for f in ("docker", "flock"):
            (bindir / f).chmod(0o755)
        (bindir / "python3").symlink_to(sys.executable)
        (tmp / "proc").mkdir()
        (tmp / "proc" / "loadavg").write_text("0.52 0.40 0.30 1/200 1234\n")
        (tmp / "proc" / "meminfo").write_text("MemTotal: 8000000 kB\nMemAvailable: 5000000 kB\n")
        self.log = tmp / "docker.log"
        self.env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "OPS_EXTRA_PATH": str(bindir),
                    "OPS_APP_DIR": str(self.work / "clip-api"), "OPS_BACKUP_DIR": str(tmp / "backups"),
                    "OPS_LOG_DIR": str(tmp / "logs"), "OPS_LOCK_FILE": str(tmp / "ops.lock"),
                    "OPS_INSTALLED": str(tmp / "installed-ops"), "OPS_PROC": str(tmp / "proc"),
                    "OPS_IDLE_WAIT_SEC": "0", "OPS_WORKER_WAIT_SEC": "0", "OPS_STABLE_SEC": "0", "OPS_POLL_SEC": "0",
                    "OPS_FREE_MARGIN_MB": "1", "DOCKER_LOG": str(self.log), "STATE": str(self.state),
                    "DATA_SRC": str(self.data)}
        self.env.pop("SSH_ORIGINAL_COMMAND", None)

    def commit(self, files: dict[str, str], msg: str) -> str:
        for rel, text in files.items():
            path = self.dev / "clip-api" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(self.dev, "add", "-A")
        git(self.dev, "commit", "-qm", msg)
        git(self.dev, "push", "-q", "origin", "main")
        return git(self.dev, "rev-parse", "HEAD")

    def head(self) -> str:
        return git(self.work, "rev-parse", "HEAD")

    def ops(self, *args: str, ssh: str | None = None, **extra: str) -> subprocess.CompletedProcess:
        env = {**self.env, **extra}
        if ssh is not None:
            env["SSH_ORIGINAL_COMMAND"] = ssh
        return subprocess.run(["bash", str(self.work / "clip-api" / "scripts" / "ops.sh"), *args], env=env,
                              capture_output=True, text=True)

    def calls(self) -> str:
        return self.log.read_text() if self.log.exists() else ""


def kv(r: subprocess.CompletedProcess) -> dict[str, str]:
    return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


@pytest.fixture
def server(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git not installed")
    return Server(tmp_path)


SHA = "a" * 40
BAD_REQUESTS = [
    "", "   ", "help", "Status", "status now", "deploy", "deploy abc123", f"deploy {SHA[:39]}", f"deploy {SHA}0",
    f"deploy {SHA.upper()}", f"deploy {SHA} {SHA}", f"deploy {SHA};id", f"deploy $(id)", f"deploy `id`",
    f"deploy {SHA}\nstatus", f"deploy ../{SHA}", "deploy -h", f"verify {SHA} now", f"rollback {SHA} rollback",
    "backup", "backup db", "backup db 0", "backup db 100", "backup all 7", "backup db 7 x", "backup db -1",
    "preflight main", "rm -rf /", "status" + " " * 200, "status\t", "status\r",
]


@pytest.mark.parametrize("request_text", BAD_REQUESTS)
def test_rejects_anything_outside_the_grammar(server, request_text):
    r = server.ops(ssh=request_text)
    assert r.returncode == 64, (request_text, r.stdout, r.stderr)
    assert "usage:" in r.stderr and r.stdout == ""
    assert server.calls() == ""   # nothing ran: not even docker


def test_takes_the_request_from_ssh_or_from_one_argument(server):
    assert kv(server.ops(ssh="status"))["result"] == "ok"
    assert kv(server.ops("status"))["result"] == "ok"


def test_status_reports_everything_the_monitor_reads(server):
    out = kv(server.ops("status"))
    for key in ("load1", "cpus", "mem_total_mb", "mem_avail_mb", "disk_free_mb", "disk_used_pct", "container_api",
                "container_worker", "container_db", "container_caddy", "jobs_running", "oldest_queued_min",
                "stalest_heartbeat_min", "last_claim_min", "backup_age_hours", "commit", "db_revision"):
        assert key in out, key
    assert out["load1"] == "0.52" and out["mem_avail_mb"] == "4882" and out["container_api"] == "running/healthy"
    assert out["backup_age_hours"] == "-1" and out["db_revision"] == "0002"
    assert out["stripe_webhook_errors_1h"] == "0" and out["email_failures_1h"] == "0"


def test_status_counts_failed_stripe_webhooks_and_emails_without_printing_logs(server):
    logs = ('api-1 | INFO: 1.2.3.4:0 - "POST /webhooks/stripe HTTP/1.1" 200 OK\n'
            'api-1 | INFO: 1.2.3.4:0 - "POST /webhooks/stripe HTTP/1.1" 503 Service Unavailable\n'
            'api-1 | INFO: 1.2.3.4:0 - "POST /webhooks/stripe HTTP/1.1" 400 Bad Request\n'
            'api-1 | INFO: 1.2.3.4:0 - "GET /health HTTP/1.1" 500 Internal Server Error\n'
            'worker-1 | WARNING clipapi.email SMTP not configured; email to someone@example.com not sent\n')
    r = server.ops("status", APP_LOGS=logs)
    out = kv(r)
    assert out["stripe_webhook_ok_1h"] == "1" and out["stripe_webhook_errors_1h"] == "2"
    assert out["email_failures_1h"] == "1" and "someone@example.com" not in r.stdout + r.stderr


def test_preflight_refuses_while_a_job_runs(server):
    r = server.ops("preflight", STUCK_OUT="job_1 RUNNING  stage=render\\n")
    assert r.returncode == 1 and kv(r)["jobs_running"] == "1" and kv(r)["result"] == "refused"
    r = server.ops("preflight", STUCK_FAIL="1")
    assert r.returncode == 1 and kv(r)["jobs_running"] == "unknown"


def test_preflight_with_a_target_reports_relation_and_pending_migrations(server):
    sha = server.commit({"app/migrations/versions/0003_c.py": migration("0003", "0002")}, "two")
    r = server.ops(f"preflight {sha}")
    out = kv(r)
    assert out["result"] == "ok" and out["target_relation"] == "newer" and out["migration_pending"] == "0003"
    r = server.ops(f"preflight {'b' * 40}")
    assert r.returncode == 1 and kv(r)["target_on_main"] == "no"


def test_deploys_the_requested_commit_not_the_branch_head(server):
    first = server.commit({"a.txt": "1"}, "two")
    server.commit({"b.txt": "2"}, "three")
    r = server.ops(f"deploy {first}")
    assert r.returncode == 0, r.stderr
    out = kv(r)
    assert server.head() == first == out["commit"] and out["restarted"] == "yes" and out["selftest"] == "passed"
    assert "compose build api worker" in server.calls()


def test_refuses_a_destructive_migration_and_builds_nothing(server):
    sha = server.commit({"app/migrations/versions/0003_c.py": migration("0003", "0002", 'op.drop_column("t", "c")')},
                        "drop")
    before = server.head()
    r = server.ops(f"deploy {sha}")
    assert r.returncode == 1 and "destructive" in r.stderr
    assert "migration_finding=" in r.stdout and "drop_column" in r.stdout
    assert "build" not in server.calls() and server.head() == before


def test_refuses_commits_not_on_main_and_older_commits(server):
    before = server.head()
    assert server.ops(f"deploy {'c' * 40}").returncode == 1
    newer = server.commit({"a.txt": "1"}, "two")
    assert server.ops(f"deploy {newer}").returncode == 0
    r = server.ops(f"deploy {before}")
    assert r.returncode == 1 and "use rollback" in r.stderr and server.head() == newer


def test_a_failure_before_the_restart_puts_the_checkout_back(server):
    before = server.head()
    sha = server.commit({"a.txt": "1"}, "two")
    r = server.ops(f"deploy {sha}", MIGRATE_FAIL="1")
    out = kv(r)
    assert r.returncode == 1 and out["restarted"] == "no" and out["checkout_restored"] == "yes"
    assert server.head() == before and git(server.work, "symbolic-ref", "--short", "HEAD") == "main"


def test_a_selftest_failure_after_the_restart_is_reported_for_rollback(server):
    before = server.head()
    sha = server.commit({"a.txt": "1"}, "two")
    out = kv(server.ops(f"deploy {sha}", SELFTEST_FAIL="1"))
    assert out["result"] == "failed" and out["restarted"] == "yes" and out["previous"] == before
    assert out["selftest"] == "failed" and server.head() == sha


def test_rollback_then_deploy_again(server):
    before = server.head()
    sha = server.commit({"a.txt": "1"}, "two")
    assert server.ops(f"deploy {sha}").returncode == 0
    server.log.unlink()
    r = server.ops(f"rollback {before}")
    assert r.returncode == 0, r.stderr
    assert server.head() == before and kv(r)["previous"] == sha
    assert git(server.work, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"   # detached, as deploy.sh prints
    assert "compose up -d api worker" in server.calls() and "admin.py migrate" not in server.calls()   # code only
    assert kv(server.ops(f"verify {before} rollback"))["result"] == "ok"
    r = server.ops(f"deploy {sha}")   # deploy.sh would refuse a detached checkout; ops.sh reattaches it
    assert r.returncode == 0, r.stderr
    assert server.head() == sha and git(server.work, "symbolic-ref", "--short", "HEAD") == "main"


def test_rollback_refuses_when_the_old_code_cannot_start_on_the_database(server):
    before = server.head()
    sha = server.commit({"app/migrations/versions/0003_c.py": migration("0003", "0002")}, "two")
    assert server.ops(f"deploy {sha}", DB_REV="0002").returncode == 0
    r = server.ops(f"rollback {before}", DB_REV="0003")
    assert r.returncode == 1 and "code rollback is not possible" in r.stderr
    assert server.head() == sha


def test_rollback_refuses_newer_commits_and_running_jobs(server):
    before = server.head()
    sha = server.commit({"a.txt": "1"}, "two")
    assert server.ops(f"rollback {sha}").returncode == 1
    assert server.ops(f"deploy {sha}").returncode == 0
    r = server.ops(f"rollback {before}", STUCK_OUT="job_1 RUNNING  stage=render\\n")
    assert r.returncode == 1 and "still RUNNING" in r.stderr and server.head() == sha


def test_verify_checks_the_commit_and_the_revision(server):
    head = server.head()
    assert kv(server.ops(f"verify {head}"))["result"] == "ok"
    r = server.ops(f"verify {'d' * 40}")
    assert r.returncode == 1 and kv(r)["verify_commit"] == "fail"
    r = server.ops(f"verify {head}", DBSTATUS_RC="1")
    assert r.returncode == 1 and kv(r)["verify_db"] == "fail"
    assert kv(server.ops(f"verify {head} rollback", DBSTATUS_RC="1"))["verify_db"] == "ok"


def test_backup_is_verified_and_old_ones_are_pruned(server):
    files = []
    for _ in range(3):
        out = kv(server.ops("backup db 2"))
        assert out["result"] == "ok" and out["backup_db_verified"] == "yes" and out["backup_db_tables"] == "3"
        files.append(Path(out["backup_db_file"]))
        subprocess.run(["sleep", "1"])   # names carry the second
    kept = sorted(p.name for p in (server.tmp / "backups").glob("db-*.dump"))
    assert kept == sorted(p.name for p in files[1:]) and all(Path(f"{p}.ok").exists() for p in files[1:])
    assert not list((server.tmp / "backups").glob("*.partial"))
    assert kv(server.ops("status"))["backup_age_hours"] == "0"


@pytest.mark.parametrize("bad", [{"DUMP_TABLES": "2"}, {"RESTORE_FAIL": "1"}])
def test_an_unverifiable_backup_is_refused_and_removed(server, bad):
    r = server.ops("backup db 3", **bad)
    assert r.returncode == 1 and kv(r)["result"] == "refused"
    assert not list((server.tmp / "backups").iterdir())


def test_full_backup_includes_the_data_volume(server):
    out = kv(server.ops("backup full 3"))
    assert out["result"] == "ok" and out["backup_data_verified"] == "yes"
    names = subprocess.run(["tar", "-tzf", out["backup_data_file"]], capture_output=True, text=True).stdout
    assert "clip.mp4" in names


def test_backup_refuses_without_disk_space(server):
    r = server.ops("backup db 3", OPS_FREE_MARGIN_MB="999999999")
    assert r.returncode == 1 and "not enough disk" in r.stderr and "pg_dump" not in server.calls()


SSH_STUB = """#!/usr/bin/env bash
# Stands in for ssh + the forced command: checks the options the workflow relies on, then runs ops.sh with
# the request as SSH_ORIGINAL_COMMAND, as sshd would.
args="$*"
for need in "StrictHostKeyChecking=yes" "BatchMode=yes" "IdentitiesOnly=yes" "UserKnownHostsFile="; do
  case "$args" in *"$need"*) ;; *) echo "missing $need" >&2; exit 99;; esac
done
key=$(printf '%s\\n' "$@" | awk 'prev == "-i" {print} {prev = $0}')
[ "$(stat -c %a "$key" 2>/dev/null || stat -f %Lp "$key")" = 600 ] || { echo "key is not 0600" >&2; exit 98; }
for last; do :; done
SSH_ORIGINAL_COMMAND="$last" exec bash "$OPS_SCRIPT"
"""


def test_ssh_wrapper_end_to_end(server):
    """What a workflow step does: .github/ops/ssh_ops.sh with secrets in env, outputs into GITHUB_OUTPUT."""
    wrapper = Path(__file__).resolve().parents[2] / ".github" / "ops" / "ssh_ops.sh"
    if not wrapper.exists():
        pytest.skip("the .github folder is not in this checkout")
    bindir = server.tmp / "sshbin"
    bindir.mkdir()
    (bindir / "ssh").write_text(SSH_STUB)
    (bindir / "ssh").chmod(0o755)
    gh_out, ops_dir = server.tmp / "gh_output", server.tmp / "opsdir"
    env = {**server.env, "PATH": f"{bindir}:{server.env['PATH']}", "OPS_SCRIPT": str(server.work / "clip-api/scripts/ops.sh"),
           "PROD_SSH_KEY": "-----BEGIN KEY-----secretkeymaterial", "PROD_HOST": "203.0.113.9",
           "PROD_KNOWN_HOSTS": "203.0.113.9 ssh-ed25519 AAAA", "OPS_DIR": str(ops_dir), "GITHUB_OUTPUT": str(gh_out)}
    head = server.head()
    r = subprocess.run(["bash", str(wrapper), "preflight", "preflight", head], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "secretkeymaterial" not in r.stdout + r.stderr
    outputs = gh_out.read_text()
    assert f"commit={head}" in outputs and "target_relation=same" in outputs and "rc=0" in outputs
    assert (ops_dir / "preflight.rc").read_text().strip() == "0"
    r = subprocess.run(["bash", str(wrapper), "deploy", "deploy", "not-a-sha"], env=env, capture_output=True, text=True)
    assert r.returncode == 64 and (ops_dir / "deploy.rc").read_text().strip() == "64"
