#!/usr/bin/env python3
"""GitHub-side helpers for deploy.yml, rollback.yml and monitor.yml. Standard library plus the `gh` and `git` CLIs.

  gate --ref REF --repo OWNER/NAME [--approval MODE --dry-run --event E --actor A --owner O --confirm SHA7]
        resolve REF to a commit on origin/main, require CI evidence for that exact tree, and the human gate
  migrations --sha SHA --current REV
        run clip-api/scripts/check_migrations.py on SHA's revision files (the server runs it again)
  monitor --status FILE --ssh-rc N
        compare `ops.sh status` output with the thresholds; markdown on stdout
  issue --healthy yes|no --body FILE --signature SIG --assignee LOGIN
        open, update or close the one `ops` issue
  report --kind deploy|rollback --dir DIR --target SHA [--dry-run] [--pr N] [--evidence TEXT] [--run-url URL]
        the job summary (stdout) and the PR comment (DIR/comment.md)

Thresholds and required checks: .github/ops/config.json. Never prints secrets: it only sees key=value output.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).resolve().parent / "config.json"
ISSUE_TITLE = "[ops] Production health"
SIG_RE = re.compile(r"<!-- ops-signature: (.*?) -->")


def config() -> dict:
    return json.loads(CONFIG.read_text())


def sh(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def gh_json(path: str):
    return json.loads(sh("gh", "api", "-H", "Accept: application/vnd.github+json", path))


def set_output(**values: str) -> None:
    for k, v in values.items():
        print(f"{k}={v}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def fail(msg: str) -> int:
    print(f"::error::{msg}")
    return 1


def read_kv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


# ---- gate ---------------------------------------------------------------------------------------------------------
def check_state(runs: list[dict], required: list[str]) -> tuple[str, str]:
    """('ok' | 'missing' | 'pending' | 'failed', detail) over the latest check runs of one commit.
    Every latest run of every required check must have concluded success; nothing is skipped or overridden."""
    missing, pending, failed = [], [], []
    for name in required:
        mine = [r for r in runs if r.get("name") == name]
        if not mine:
            missing.append(name)
        elif any(r.get("status") != "completed" for r in mine):
            pending.append(name)
        elif any(r.get("conclusion") != "success" for r in mine):
            failed.append(f"{name}: {', '.join(sorted({str(r.get('conclusion')) for r in mine}))}")
    if failed:
        return "failed", "; ".join(failed)
    if pending:
        return "pending", ", ".join(pending)
    if missing:
        return "missing", ", ".join(missing)
    return "ok", ", ".join(required)


def runs_for(repo: str, sha: str) -> list[dict]:
    return gh_json(f"repos/{repo}/commits/{sha}/check-runs?filter=latest&per_page=100").get("check_runs", [])


def ci_evidence(repo: str, sha: str, required: list[str], runs=runs_for, pulls=None, tree=None) -> tuple[bool, str, str]:
    """(ok, pr number or '', evidence). CI runs on pull requests only, so a merge commit on main has no runs of its
    own: then the merged PR's head must have passed AND have the identical tree, so CI tested exactly these files."""
    pulls = pulls or (lambda: gh_json(f"repos/{repo}/commits/{sha}/pulls"))
    tree = tree or (lambda rev: sh("git", "rev-parse", f"{rev}^{{tree}}"))
    state, detail = check_state(runs(repo, sha), required)
    merged = [p for p in pulls() if p.get("merge_commit_sha") == sha and p.get("merged_at")
              and p.get("base", {}).get("ref") == "main"]
    pr = str(merged[0]["number"]) if merged else ""
    if state == "ok":
        return True, pr, f"{detail} passed on {sha[:7]}"
    if state != "missing":
        return False, pr, f"CI on {sha[:7]} is {state}: {detail}"
    if not merged:
        return False, "", f"{sha[:7]} has no CI runs and is not the merge commit of a PR into main"
    head = merged[0]["head"]["sha"]
    state, detail = check_state(runs(repo, head), required)
    if state != "ok":
        return False, pr, f"CI on PR #{pr} head {head[:7]} is {state}: {detail}"
    subprocess.run(["git", "fetch", "-q", "origin", f"pull/{pr}/head"], check=False, capture_output=True)
    try:
        same = tree(sha) == tree(head)
    except subprocess.CalledProcessError:
        same = False
    if not same:
        return False, pr, f"{sha[:7]} and PR #{pr} head {head[:7]} have different trees; CI did not test this exact code"
    return True, pr, f"{detail} passed on PR #{pr} head {head[:7]} (same tree as {sha[:7]})"


def approval(mode: str, dry_run: bool, event: str, actor: str, owner: str, confirm: str, sha: str) -> tuple[bool, str]:
    """The human gate. "environment": the `production` environment's required reviewer approves in GitHub's UI (needs
    a public repo or GitHub Enterprise). Anything else, the default: the owner dispatches the run by hand and types
    the first 7 characters of the target into `confirm`. Agents never type it (.claude/agents/devops.md)."""
    if dry_run:
        return True, "dry run: changes nothing"
    if mode == "environment":
        return True, "approval: the production environment's required reviewer"
    if event != "workflow_dispatch":
        return False, "without environment reviewers (PROD_APPROVAL != environment) only a manual dispatch can deploy"
    if actor.lower() != owner.lower():
        return False, f"only {owner} can confirm a production change (dispatched by {actor})"
    if confirm.strip() != sha[:7]:
        return False, f"type the first 7 characters of the target ({sha[:7]}) into `confirm` to approve"
    return True, f"approval: confirmed by {actor} for {sha[:7]}"


def cmd_gate(a) -> int:
    ref = a.ref.strip() or "origin/main"
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", ref) or ref.startswith("-"):
        return fail(f"not a commit or tag: {ref!r}")
    sh("git", "fetch", "-q", "--tags", "origin", "main")
    try:
        sha = sh("git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError:
        return fail(f"{ref} is not a commit here")
    if subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"]).returncode != 0:
        return fail(f"{sha[:7]} is not on main")
    ok, pr, evidence = ci_evidence(a.repo, sha, config()["required_checks"])
    set_output(sha=sha, pr=pr, evidence=evidence)
    if not ok:
        return fail(f"refusing: {evidence}")
    approved, why = approval(a.approval, a.dry_run, a.event, a.actor, a.owner, a.confirm, sha)
    print(why)
    return 0 if approved else fail(f"refusing: {why}")


# ---- migrations ---------------------------------------------------------------------------------------------------
def cmd_migrations(a) -> int:
    if not re.fullmatch(r"[0-9a-f]{40}", a.sha) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", a.current):
        return fail("bad --sha or --current")
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(["git", "archive", a.sha, "clip-api/app/migrations/versions"],
                                 check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", tmp], input=archive, check=True)
        r = subprocess.run([sys.executable, str(ROOT / "clip-api/scripts/check_migrations.py"), "--versions",
                            f"{tmp}/clip-api/app/migrations/versions", "--current", a.current], text=True,
                           capture_output=True)
    print(r.stdout, end="")
    if r.returncode != 0:
        return fail("a pending migration is destructive or unreadable; it is never run automatically. "
                    "The owner deploys it by hand after a backup (docs/devops/setup.md).")
    return 0


# ---- monitor ------------------------------------------------------------------------------------------------------
def _num(status: dict[str, str], key: str) -> float | None:
    try:
        return float(status[key])
    except (KeyError, ValueError):
        return None


def evaluate(status: dict[str, str], ssh_rc: int, limits: dict) -> list[tuple[str, str, str, bool]]:
    """[(check, value, limit, ok)]. A value that cannot be read counts as a breach."""
    if ssh_rc != 0 or status.get("result") != "ok":
        return [("server reachable", f"ssh exit {ssh_rc}", "exit 0", False)]
    rows: list[tuple[str, str, str, bool]] = []

    def row(name: str, value: float | None, limit: float, ok, unit: str = "", shown: str | None = None) -> None:
        text = "unreadable" if value is None else (shown or f"{value:g}{unit}")
        rows.append((name, text, f"{limit:g}{unit}", value is not None and ok(value)))

    load, cpus = _num(status, "load1"), _num(status, "cpus") or 1
    row("CPU load per core (1 min)", None if load is None else round(load / cpus, 2), limits["load_per_cpu_max"],
        lambda v: v <= limits["load_per_cpu_max"])
    row("memory available", _num(status, "mem_avail_mb"), limits["mem_avail_mb_min"],
        lambda v: v >= limits["mem_avail_mb_min"], " MB")
    row("disk free", _num(status, "disk_free_mb"), limits["disk_free_mb_min"],
        lambda v: v >= limits["disk_free_mb_min"], " MB")
    row("disk used", _num(status, "disk_used_pct"), limits["disk_used_pct_max"],
        lambda v: v <= limits["disk_used_pct_max"], "%")
    for c in limits["containers"]:
        state = status.get(f"container_{c}", "missing")
        rows.append((f"container {c}", state, "running", state.startswith("running") and "unhealthy" not in state))
    readable = status.get("queue_readable") == "yes"
    rows.append(("queue readable (admin.py ops-status)", "yes" if readable else "no", "yes", readable))
    if readable:
        q = _num(status, "oldest_queued_min")
        row("oldest QUEUED job", q, limits["oldest_queued_min_max"],
            lambda v: v <= limits["oldest_queued_min_max"], " min", "none" if q == -1 else None)
        h = _num(status, "stalest_heartbeat_min")
        row("stalest RUNNING heartbeat", h, limits["stalest_heartbeat_min_max"],
            lambda v: v <= limits["stalest_heartbeat_min_max"], " min", "none" if h == -1 else None)
        for key, name, needed in (("email_configured", "email provider set (SMTP_HOST)", limits["require_email"]),
                                  ("stripe_webhook_configured", "Stripe webhook secret set",
                                   limits["require_billing_webhook"])):
            if needed:
                rows.append((name, {"1": "yes", "0": "no"}.get(status.get(key, ""), "unreadable"), "yes",
                             status.get(key) == "1"))
    errors, ok_hooks = _num(status, "stripe_webhook_errors_1h"), _num(status, "stripe_webhook_ok_1h") or 0
    row("Stripe webhook deliveries failed (4xx/5xx, 1 h)", errors, limits["stripe_webhook_errors_1h_max"],
        lambda v: v <= limits["stripe_webhook_errors_1h_max"], "",
        None if errors is None else f"{errors:g} of {errors + ok_hooks:g}")
    row("emails failed or not sent (1 h)", _num(status, "email_failures_1h"), limits["email_failures_1h_max"],
        lambda v: v <= limits["email_failures_1h_max"])
    age = _num(status, "backup_age_hours")
    row("newest verified backup", age, limits["backup_age_hours_max"],
        lambda v: 0 <= v <= limits["backup_age_hours_max"], " h", "none" if age == -1 else None)
    return rows


def cmd_monitor(a) -> int:
    status = read_kv(Path(a.status))
    rows = evaluate(status, a.ssh_rc, config()["monitor"])
    breaches = [name for name, _, _, ok in rows if not ok]
    lines = [f"## Production health: {'healthy' if not breaches else 'needs attention'}", "",
             "| Check | Value | Limit | |", "|---|---|---|---|"]
    lines += [f"| {n} | {v} | {lim} | {'ok' if ok else '**BREACH**'} |" for n, v, lim, ok in rows]
    extra = {k: status[k] for k in ("time_utc", "commit", "db_revision", "jobs_running", "jobs_queued",
                                     "last_claim_min", "backup_newest") if k in status}
    if extra:
        lines += ["", " · ".join(f"{k} `{v}`" for k, v in extra.items())]
    print("\n".join(lines))
    signature = ",".join(sorted(breaches))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"healthy={'no' if breaches else 'yes'}\nsignature={signature}\n")
    return 0


def find_issue(gh=sh) -> dict | None:
    found = json.loads(gh("gh", "issue", "list", "--label", "ops", "--state", "open", "--limit", "50",
                          "--json", "number,title,body"))
    return next((i for i in found if i["title"] == ISSUE_TITLE), None)


def cmd_issue(a, gh=sh) -> int:
    """One open issue at most. A comment (which emails the assignee) only when it opens, when the set of breached
    checks changes, and when it closes; otherwise the body is edited in place, which notifies nobody."""
    issue = find_issue(gh)
    body_text = Path(a.body).read_text() + f"\n\n{a.run_url}\n<!-- ops-signature: {a.signature} -->\n"
    if a.healthy == "yes":
        if issue:
            gh("gh", "issue", "close", str(issue["number"]), "--comment", f"Healthy again. {a.run_url}")
            print(f"closed #{issue['number']}")
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body_text)
    if not issue:
        url = gh("gh", "issue", "create", "--title", ISSUE_TITLE, "--label", "ops", "--assignee", a.assignee,
                 "--body-file", f.name)
        print(f"opened {url}")
        return 0
    old = SIG_RE.search(issue.get("body") or "")
    gh("gh", "issue", "edit", str(issue["number"]), "--body-file", f.name)
    if not old or old.group(1) != a.signature:
        gh("gh", "issue", "comment", str(issue["number"]), "--body",
           f"Now breached: {a.signature or 'none'} (was: {old.group(1) if old else 'unknown'}). {a.run_url}")
    print(f"updated #{issue['number']}")
    return 0


# ---- report -------------------------------------------------------------------------------------------------------
def _mb(b: str | None) -> str:
    return f"{int(b) / 1048576:.1f} MB" if b and b.isdigit() else "?"


def build_report(kind: str, d: Path, target: str, dry_run: bool, pr: str, evidence: str, run_url: str) -> tuple[str, str]:
    """(job summary markdown, PR comment of at most 8 lines)."""
    step = {name: read_kv(d / f"{name}.env") for name in ("preflight", "backup", "deploy", "rollback", "verify",
                                                         "verify_rollback")}
    rc = {name: (d / f"{name}.rc").read_text().strip() if (d / f"{name}.rc").exists() else None for name in step}
    sec = {name: (d / f"{name}.sec").read_text().strip() if (d / f"{name}.sec").exists() else None for name in step}
    pre, bak, dep, rb, ver, vrb = (step[n] for n in step)
    main_step = "deploy" if kind == "deploy" else "rollback"
    before = pre.get("commit", "?")
    rolled_back = kind == "deploy" and rc["rollback"] is not None
    if dry_run:
        outcome = "dry run: every check ran, nothing was changed"
    elif rc["verify"] == "0" and rc[main_step] == "0":
        outcome = f"{'deployed' if kind == 'deploy' else 'rolled back to'} {target[:7]}"
    elif rolled_back:
        outcome = (f"FAILED, code rolled back to {before[:7]}" if rc["verify_rollback"] == "0"
                   else f"FAILED, and the rollback to {before[:7]} did not verify: needs the owner")
    elif dep.get("checkout_restored") == "yes":
        outcome = "FAILED before the restart; nothing was restarted, checkout put back"
    else:
        outcome = "FAILED or refused before any change" if rc[main_step] is None else "FAILED: needs the owner"
    final = (vrb or ver) if rolled_back else ver
    after_commit = final.get("commit") or dep.get("commit") or rb.get("commit") or before
    db_after = final.get("db_revision", pre.get("db_revision", "?"))
    lines = [f"## {kind.capitalize()} {target[:7]}: {outcome}", "",
             "| | Before | After |", "|---|---|---|",
             f"| Commit | `{before[:12]}` | `{after_commit[:12] if not dry_run else '(unchanged)'}` |",
             f"| DB revision | `{pre.get('db_revision', '?')}` | `{db_after if not dry_run else '(unchanged)'}` |", ""]
    lines.append(f"- CI: {evidence or 'n/a'}")
    if pre:
        lines.append(f"- Preflight: jobs running {pre.get('jobs_running', '?')}, target {pre.get('target_relation', '?')}, "
                     f"pending migrations `{pre.get('migration_pending') or 'none'}`, disk free "
                     f"{pre.get('disk_free_mb', '?')} MB, installed ops script {pre.get('ops_installed', '?')}")
    if bak:
        lines.append(f"- Backup: `{bak.get('backup_db_file', '?')}`, {_mb(bak.get('backup_db_bytes'))}, "
                     f"verified {bak.get('backup_db_verified', 'no')} ({bak.get('backup_db_tables', '?')} tables)"
                     + (f"; data `{bak.get('backup_data_file')}` {_mb(bak.get('backup_data_bytes'))}"
                        if bak.get("backup_data_file") else ""))
    if final:
        checks = ("verify_commit", "verify_db", "verify_health", "verify_worker")
        lines.append("- Health: " + ", ".join(f"{c.removeprefix('verify_')} {final.get(c, '?')}" for c in checks)
                     + f", selftest {(dep or rb).get('selftest', '?')}")
    if rolled_back:
        lines.append(f"- Rollback to `{before[:7]}`: {rb.get('result', 'not run')}; the database was not touched")
    timings = [f"{n} {sec[n]}s" for n in step if sec[n]]
    if timings:
        lines.append("- Timings: " + ", ".join(timings))
    if run_url:
        lines.append(f"- Run: {run_url}")
    ok = dry_run or outcome.startswith(("deployed", "rolled back to"))
    comment = [f"[devops] [{kind}] {'✅' if ok else '❌'} {outcome}",
               f"- Did: {'backup, ' if bak else ''}{main_step} `{target[:7]}`, verify",
               f"- ✅ Done: commit `{after_commit[:7]}`, DB `{pre.get('db_revision', '?')}` → `{db_after}`"
               + (f", backup {_mb(bak.get('backup_db_bytes'))} verified" if bak.get("backup_db_verified") == "yes" else ""),
               f"- ❌ Not done: {'none' if ok else outcome}",
               f"- Next: {'none' if ok else 'owner: read the run, decide by hand (DEPLOY.md)'}",
               f"- Run: {run_url}"]
    return "\n".join(lines) + "\n", "\n".join(comment) + "\n"


def cmd_report(a) -> int:
    summary, comment = build_report(a.kind, Path(a.dir), a.target, a.dry_run, a.pr, a.evidence, a.run_url)
    print(summary)
    (Path(a.dir) / "comment.md").write_text(comment)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate"); g.add_argument("--ref", default=""); g.add_argument("--repo", required=True)
    g.add_argument("--approval", default=""); g.add_argument("--dry-run", action="store_true")
    g.add_argument("--event", default=""); g.add_argument("--actor", default=""); g.add_argument("--owner", default="")
    g.add_argument("--confirm", default="")
    m = sub.add_parser("migrations"); m.add_argument("--sha", required=True); m.add_argument("--current", required=True)
    mo = sub.add_parser("monitor"); mo.add_argument("--status", required=True); mo.add_argument("--ssh-rc", type=int, default=0)
    i = sub.add_parser("issue")
    i.add_argument("--healthy", choices=("yes", "no"), required=True); i.add_argument("--body", required=True)
    i.add_argument("--signature", default=""); i.add_argument("--assignee", required=True)
    i.add_argument("--run-url", default="")
    r = sub.add_parser("report")
    r.add_argument("--kind", choices=("deploy", "rollback"), required=True); r.add_argument("--dir", required=True)
    r.add_argument("--target", required=True); r.add_argument("--dry-run", action="store_true")
    r.add_argument("--pr", default=""); r.add_argument("--evidence", default=""); r.add_argument("--run-url", default="")
    a = p.parse_args(argv)
    return {"gate": cmd_gate, "migrations": cmd_migrations, "monitor": cmd_monitor, "issue": cmd_issue,
            "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
