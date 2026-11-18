"""scripts/deploy.sh against a stub `docker` and a real local git remote: never restarts while a job runs."""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "deploy.sh"

STUB = """#!/usr/bin/env bash
echo "$*" >> "$DOCKER_LOG"
case "$*" in
  *"admin.py stuck"*) [ -n "${STUCK_FAIL:-}" ] && exit 1; printf '%b' "${STUCK_OUT:-}";;
  *"admin.py migrate"*) [ -n "${MIGRATE_FAIL:-}" ] && { echo "boom" >&2; exit 1; }; echo "schema 0001 -> 0002";;
  *"admin.py selftest"*) [ -n "${SELFTEST_FAIL:-}" ] && { echo "FAIL  whisper"; exit 1; }; echo "OK    all";;
esac
exit 0
"""


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def server(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git not installed")
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(work, "config", k, v)
    (work / "clip-api" / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, work / "clip-api" / "scripts" / "deploy.sh")
    git(work, "add", "-A"); git(work, "commit", "-qm", "one"); git(work, "push", "-q", "origin", "main")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker").write_text(STUB)
    (bindir / "docker").chmod(0o755 | stat.S_IEXEC)
    log = tmp_path / "docker.log"
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "DOCKER_LOG": str(log)}
    return work, env, log


def deploy(work, env, **extra):
    return subprocess.run(["bash", str(work / "clip-api" / "scripts" / "deploy.sh")], env={**env, **extra},
                          capture_output=True, text=True)


def calls(log: Path) -> str:
    return log.read_text() if log.exists() else ""


def test_refuses_while_a_job_is_running(server):
    work, env, log = server
    r = deploy(work, env, STUCK_OUT="job_abc RUNNING  stage=rendering progress=71\\n")
    assert r.returncode == 1 and "a job is RUNNING" in r.stderr and "job_abc" in r.stderr
    assert "build" not in calls(log) and " up " not in f" {calls(log)} "


def test_queued_jobs_do_not_block(server):
    work, env, log = server
    r = deploy(work, env, STUCK_OUT="job_q QUEUED   stage=None progress=0\\n")
    assert r.returncode == 0, r.stderr
    assert "compose build api worker" in calls(log) and "compose up -d api worker" in calls(log)


def test_refuses_when_jobs_cannot_be_listed(server):
    work, env, log = server
    r = deploy(work, env, STUCK_FAIL="1")
    assert r.returncode == 1 and "could not list jobs" in r.stderr
    assert "build" not in calls(log)


def test_pulls_rebuilds_then_selftests(server):
    work, env, log = server
    other = work.parent / "dev"
    git(work.parent, "clone", "-q", str(work.parent / "origin.git"), str(other))
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(other, "config", k, v)
    (other / "new.txt").write_text("x")
    git(other, "add", "-A"); git(other, "commit", "-qm", "two"); git(other, "push", "-q", "origin", "main")
    r = deploy(work, env)
    assert r.returncode == 0, r.stderr
    assert (work / "new.txt").exists()
    order = [line for line in calls(log).splitlines() if "stuck" not in line and "health" not in line and "urllib" not in line]
    assert order == ["compose build api worker", "compose run --rm -T api python scripts/admin.py migrate",
                     "compose up -d api worker", "compose exec -T api python scripts/admin.py selftest"]


def test_a_failed_migration_restarts_nothing(server):
    work, env, log = server
    r = deploy(work, env, MIGRATE_FAIL="1")
    assert r.returncode == 1 and "migration FAILED" in r.stderr and "git checkout --detach" in r.stderr
    assert "compose up" not in calls(log) and "selftest" not in calls(log)


def test_no_migration_while_a_job_runs(server):
    work, env, log = server
    r = deploy(work, env, STUCK_OUT="job_abc RUNNING  stage=rendering progress=71\\n")
    assert r.returncode == 1 and "migrate" not in calls(log)


def test_selftest_failure_prints_rollback(server):
    work, env, _ = server
    r = deploy(work, env, SELFTEST_FAIL="1")
    assert r.returncode == 1 and "selftest FAILED" in r.stderr and "git checkout --detach" in r.stderr


def test_refuses_edited_tracked_files_and_wrong_branch(server):
    work, env, log = server
    (work / "clip-api" / "scripts" / "deploy.sh").write_text((work / "clip-api" / "scripts" / "deploy.sh").read_text() + "\n")
    r = deploy(work, env)
    assert r.returncode == 1 and "edited on the server" in r.stderr
    git(work, "checkout", "-q", "--", ".")
    r = deploy(work, env, DEPLOY_BRANCH="staging")
    assert r.returncode == 1 and "deploy branch is 'staging'" in r.stderr
    assert "build" not in calls(log)


def test_deploy_sha_fast_forwards_to_that_commit_only(server):
    work, env, _ = server
    other = work.parent / "dev"
    git(work.parent, "clone", "-q", str(work.parent / "origin.git"), str(other))
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(other, "config", k, v)
    shas = []
    for name in ("a.txt", "b.txt"):
        (other / name).write_text("x")
        git(other, "add", "-A"); git(other, "commit", "-qm", name); git(other, "push", "-q", "origin", "main")
        shas.append(subprocess.run(["git", "rev-parse", "HEAD"], cwd=other, capture_output=True, text=True).stdout.strip())
    r = deploy(work, env, DEPLOY_SHA=shas[0])
    assert r.returncode == 0, r.stderr
    assert (work / "a.txt").exists() and not (work / "b.txt").exists()


@pytest.mark.parametrize("sha", ["f" * 40, "abc", "A" * 40])
def test_deploy_sha_must_be_a_full_sha_on_main(server, sha):
    work, env, log = server
    r = deploy(work, env, DEPLOY_SHA=sha)
    assert r.returncode == 1 and "refusing" in r.stderr
    assert "build" not in calls(log)
