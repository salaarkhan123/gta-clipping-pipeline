""".github/ops/opsctl.py: the CI gate, the monitor thresholds, the ops issue and the deploy report."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

OPSCTL = Path(__file__).resolve().parents[2] / ".github" / "ops" / "opsctl.py"
if not OPSCTL.exists():
    pytest.skip("the .github folder is not in this checkout", allow_module_level=True)
spec = importlib.util.spec_from_file_location("opsctl", OPSCTL)
opsctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opsctl)

REQ = ["test", "docker-build"]
SHA, HEAD = "1" * 40, "2" * 40


def run(name, status="completed", conclusion="success"):
    return {"name": name, "status": status, "conclusion": conclusion}


GREEN = [run("test"), run("docker-build")]


@pytest.mark.parametrize("runs,state", [
    (GREEN, "ok"),
    (GREEN + [run("lint", conclusion="failure")], "ok"),                 # only the required checks count
    ([run("test")], "missing"),
    ([run("test"), run("docker-build", "in_progress", None)], "pending"),
    ([run("test", conclusion="failure"), run("docker-build")], "failed"),
    ([run("test", conclusion="skipped"), run("docker-build")], "failed"),  # skipped is not passed
    ([run("test"), run("test", conclusion="failure"), run("docker-build")], "failed"),  # every latest run
])
def test_check_state(runs, state):
    assert opsctl.check_state(runs, REQ)[0] == state


def merged_pr(head=HEAD, merge=SHA, base="main"):
    return [{"number": 142, "merge_commit_sha": merge, "merged_at": "2026-11-18T04:02:37Z",
             "base": {"ref": base}, "head": {"sha": head}}]


def evidence(runs_by_sha, pulls, trees=None):
    trees = trees or {SHA: "t1", HEAD: "t1"}
    return opsctl.ci_evidence("o/r", SHA, REQ, runs=lambda repo, sha: runs_by_sha.get(sha, []),
                              pulls=lambda: pulls, tree=lambda rev: trees[rev])


def test_green_target_passes():
    ok, pr, text = evidence({SHA: GREEN}, merged_pr())
    assert ok and pr == "142" and "on 1111111" in text


def test_merge_commit_uses_the_pr_head_when_the_tree_is_identical():
    ok, pr, text = evidence({HEAD: GREEN}, merged_pr())
    assert ok and pr == "142" and "same tree" in text


def test_merge_commit_with_a_different_tree_is_refused():
    ok, _, text = evidence({HEAD: GREEN}, merged_pr(), trees={SHA: "t1", HEAD: "t2"})
    assert not ok and "different trees" in text


def test_a_failing_check_on_the_target_is_never_bypassed_by_the_pr():
    ok, _, text = evidence({SHA: [run("test", conclusion="failure"), run("docker-build")], HEAD: GREEN}, merged_pr())
    assert not ok and "failed" in text


@pytest.mark.parametrize("runs,pulls", [
    ({HEAD: [run("test", conclusion="failure"), run("docker-build")]}, merged_pr()),
    ({HEAD: [run("test")]}, merged_pr()),
    ({HEAD: GREEN}, []),
    ({HEAD: GREEN}, merged_pr(base="staging")),
    ({HEAD: GREEN}, merged_pr(merge="3" * 40)),
])
def test_without_ci_evidence_the_gate_refuses(runs, pulls):
    assert not evidence(runs, pulls)[0]


LIMITS = json.loads((OPSCTL.parent / "config.json").read_text())["monitor"]
HEALTHY = {"result": "ok", "load1": "0.5", "cpus": "4", "mem_avail_mb": "4000", "disk_free_mb": "40000",
           "disk_used_pct": "40", "container_db": "running/healthy", "container_api": "running/healthy",
           "container_worker": "running", "container_caddy": "running", "queue_readable": "yes",
           "oldest_queued_min": "-1", "stalest_heartbeat_min": "-1", "backup_age_hours": "3",
           "email_configured": "1", "stripe_configured": "1", "stripe_webhook_configured": "1",
           "stripe_webhook_ok_1h": "4", "stripe_webhook_errors_1h": "1", "email_failures_1h": "0"}


def breaches(status, rc=0):
    return [name for name, _, _, ok in opsctl.evaluate(status, rc, LIMITS) if not ok]


def test_healthy_server_has_no_breach():
    assert breaches(HEALTHY) == []


@pytest.mark.parametrize("change,breach", [
    ({"load1": "9"}, "CPU load per core (1 min)"),
    ({"mem_avail_mb": "100"}, "memory available"),
    ({"disk_free_mb": "500"}, "disk free"),
    ({"disk_used_pct": "97"}, "disk used"),
    ({"container_worker": "restarting"}, "container worker"),
    ({"container_api": "running/unhealthy"}, "container api"),
    ({"container_caddy": "missing"}, "container caddy"),
    ({"queue_readable": "no"}, "queue readable (admin.py ops-status)"),
    ({"oldest_queued_min": "90"}, "oldest QUEUED job"),
    ({"stalest_heartbeat_min": "30"}, "stalest RUNNING heartbeat"),
    ({"backup_age_hours": "100"}, "newest verified backup"),
    ({"backup_age_hours": "-1"}, "newest verified backup"),       # no backup at all
    ({"disk_free_mb": "unknown"}, "disk free"),                   # unreadable counts as a breach
    ({"email_configured": "0"}, "email provider set (SMTP_HOST)"),
    ({"stripe_webhook_configured": "0"}, "Stripe webhook secret set"),
    ({"stripe_webhook_errors_1h": "3"}, "Stripe webhook deliveries failed (4xx/5xx, 1 h)"),
    ({"email_failures_1h": "1"}, "emails failed or not sent (1 h)"),
])
def test_each_threshold_breaches(change, breach):
    assert breaches({**HEALTHY, **change}) == [breach]


def test_an_unreachable_server_is_a_breach():
    assert breaches({}, rc=255) == ["server reachable"]


class FakeGh:
    def __init__(self, issues):
        self.issues, self.calls = issues, []

    def __call__(self, *args):
        self.calls.append(args[1:3])
        return json.dumps(self.issues) if args[1:3] == ("issue", "list") else "https://example/issues/9"


def issue_args(tmp_path, healthy, sig):
    body = tmp_path / "health.md"
    body.write_text("table")
    return SimpleNamespace(healthy=healthy, body=str(body), signature=sig, assignee="owner", run_url="run")


def test_opens_one_issue_then_updates_it_without_duplicates(tmp_path):
    gh = FakeGh([])
    opsctl.cmd_issue(issue_args(tmp_path, "no", "disk free"), gh)
    assert ("issue", "create") in gh.calls
    existing = [{"number": 9, "title": opsctl.ISSUE_TITLE, "body": "x <!-- ops-signature: disk free -->"}]
    gh = FakeGh(existing)
    opsctl.cmd_issue(issue_args(tmp_path, "no", "disk free"), gh)
    assert ("issue", "edit") in gh.calls and ("issue", "create") not in gh.calls
    assert ("issue", "comment") not in gh.calls   # same breach: no new email
    gh = FakeGh(existing)
    opsctl.cmd_issue(issue_args(tmp_path, "no", "container worker,disk free"), gh)
    assert ("issue", "comment") in gh.calls       # what is broken changed: tell the owner


def test_closes_the_issue_when_healthy(tmp_path):
    gh = FakeGh([{"number": 9, "title": opsctl.ISSUE_TITLE, "body": ""}])
    opsctl.cmd_issue(issue_args(tmp_path, "yes", ""), gh)
    assert ("issue", "close") in gh.calls
    gh = FakeGh([])
    opsctl.cmd_issue(issue_args(tmp_path, "yes", ""), gh)
    assert gh.calls == [("issue", "list")]


def write_steps(d: Path, steps: dict[str, tuple[int, dict[str, str]]]) -> None:
    for name, (rc, kv) in steps.items():
        (d / f"{name}.env").write_text("".join(f"{k}={v}\n" for k, v in kv.items()))
        (d / f"{name}.rc").write_text(str(rc))
        (d / f"{name}.sec").write_text("3")


PRE = {"commit": "a" * 40, "db_revision": "0007", "jobs_running": "0", "target_relation": "newer",
       "migration_pending": "0008"}
BAK = {"backup_db_file": "/root/backups/db-x.dump", "backup_db_bytes": "10485760", "backup_db_verified": "yes",
       "backup_db_tables": "14"}
VER = {"commit": "b" * 40, "db_revision": "0008", "verify_commit": "ok", "verify_db": "ok", "verify_health": "ok",
       "verify_worker": "ok", "result": "ok"}


def report(tmp_path, steps, kind="deploy", dry=False):
    write_steps(tmp_path, steps)
    return opsctl.build_report(kind, tmp_path, "b" * 40, dry, "142", "test, docker-build passed", "run")


def test_report_for_a_good_deploy(tmp_path):
    summary, comment = report(tmp_path, {"preflight": (0, PRE), "backup": (0, BAK),
                                         "deploy": (0, {"selftest": "passed", "restarted": "yes"}), "verify": (0, VER)})
    assert "deployed bbbbbbb" in summary and "`0007` | `0008`" in summary and "10.0 MB" in summary
    assert comment.startswith("[devops] [deploy] ✅") and len(comment.splitlines()) <= 8


def test_report_for_a_rolled_back_deploy(tmp_path):
    summary, comment = report(tmp_path, {
        "preflight": (0, PRE), "backup": (0, BAK), "deploy": (1, {"restarted": "yes", "selftest": "failed"}),
        "rollback": (0, {"result": "ok", "commit": "a" * 40}),
        "verify_rollback": (0, {**VER, "commit": "a" * 40, "db_revision": "0007"})})
    assert "code rolled back to aaaaaaa" in summary and "database was not touched" in summary
    assert "❌" in comment


def test_report_for_a_dry_run(tmp_path):
    summary, _ = report(tmp_path, {"preflight": (0, PRE)}, dry=True)
    assert "dry run" in summary and "(unchanged)" in summary


@pytest.mark.parametrize("mode,dry,event,actor,confirm,ok", [
    ("", True, "workflow_dispatch", "devops-bot", "", True),                 # a dry run changes nothing
    ("environment", False, "push", "anyone", "", True),                      # the environment reviewer approves
    ("", False, "workflow_dispatch", "salaarkhan123", SHA[:7], True),
    ("", False, "workflow_dispatch", "SalaarKhan123", SHA[:7], True),
    ("", False, "workflow_dispatch", "salaarkhan123", "", False),           # no confirmation
    ("", False, "workflow_dispatch", "salaarkhan123", "2222222", False),    # confirmation for another commit
    ("", False, "workflow_dispatch", "someone-else", SHA[:7], False),
    ("", False, "push", "salaarkhan123", SHA[:7], False),                   # push needs environment reviewers
    ("confirm", False, "workflow_dispatch", "salaarkhan123", SHA, False),   # exactly 7 characters
])
def test_the_human_gate(mode, dry, event, actor, confirm, ok):
    assert opsctl.approval(mode, dry, event, actor, "salaarkhan123", confirm, SHA)[0] is ok
