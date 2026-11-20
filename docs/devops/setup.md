# DevOps setup (one time, owner)

This sets up the deploy, rollback and monitoring workflows (`.github/workflows/deploy.yml`, `rollback.yml` and `monitor.yml`). Why they work the way they do: [current-state.md](current-state.md).

Values used below:

- `REPO=salaarkhan123/gta-clipping-pipeline`
- `HOST` is the droplet's address. Use the same spelling everywhere, IP or name, because the pinned host key is matched against it.

Never paste a private key, the host address or any secret into a chat or an issue. Every secret below goes from a file, or from stdin, straight into `gh secret set`.

## 0. Before you start

1. Release this PR to `main`. GitHub can only start a `workflow_dispatch` workflow that exists on the default branch.
2. Deploy that release once by hand, the old way, so `scripts/ops.sh` is on the droplet:
   ```bash
   cd /root/clip-api && bash scripts/deploy.sh
   ```
   Production is at `dfbd2a6` with the database at `0006` (owner's audit), so this deploy also runs the additive migration `0007`. Back up first, as in DEPLOY.md.
3. Check which human gate your plan allows. This repo is private on a personal account:
   - **GitHub Free:** no environments at all on private repos. Upgrade to Pro, or the workflows cannot hold their secrets in an environment.
   - **GitHub Pro or Team:** environments, environment secrets and the `main` branch rule work, but required reviewers do not. Use the `confirm` gate (the default, step 1d).
   - **GitHub Enterprise, or a public repo:** required reviewers work. Use the `environment` gate.

   Source: docs.github.com, "Managing environments for deployment", checked 2026-11-18.

## 1. GitHub: environments and variables

Run these on your Mac with `gh` logged in as the owner.

a. Create `production`, limited to `main`:

```bash
REPO=salaarkhan123/gta-clipping-pipeline
gh api -X PUT "repos/$REPO/environments/production" --input - <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST "repos/$REPO/environments/production/deployment-branch-policies" -f name=main -f type=branch
```

b. Only on Enterprise or a public repo, add yourself as the required reviewer:

```bash
gh api -X PUT "repos/$REPO/environments/production" --input - <<'EOF'
{"reviewers": [{"type": "User", "id": 122457003}], "prevent_self_review": false, "can_admins_bypass": false,
 "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh variable set PROD_APPROVAL --body environment
```

- `122457003` is the id of `salaarkhan123` (`gh api users/salaarkhan123 -q .id`).
- `prevent_self_review` must be false: you start the runs yourself and approve them yourself.

Or use the UI: Settings, Environments, production, Required reviewers. Tick your name and leave "Prevent self-review" unticked.

c. Create `production-readonly` for the monitor, with no reviewers, limited to `main`:

```bash
gh api -X PUT "repos/$REPO/environments/production-readonly" --input - <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST "repos/$REPO/environments/production-readonly/deployment-branch-policies" -f name=main -f type=branch
```

The monitor runs every 15 minutes, so it cannot wait for an approval. Its key can only run `status` (step 3).

d. Without step b, the gate is `confirm`, and you need to set nothing. A real deploy or rollback then runs only when you dispatch it yourself with the target's first 7 characters typed into `confirm`. A dry run needs neither gate.

e. Set the variables. None of them is secret:

```bash
gh variable set PROD_HEALTH_URL --body "https://api.clutchclips.io/health"   # also checked from outside after a deploy
gh variable set PROD_SSH_USER --body clipops                                 # the default; set only if you change it
# gh variable set OPS_OWNER --body salaarkhan123     # who gets the ops issue; defaults to the repo owner
# gh variable set AUTO_DEPLOY_ON_PUSH --body true    # only with PROD_APPROVAL=environment: every push to main asks you
```

## 2. Your Mac: two keys

One key deploys. The other can only read status, for the monitor.

```bash
ssh-keygen -t ed25519 -N '' -C clutchclips-actions-deploy -f ~/.ssh/clutchclips_actions_deploy
ssh-keygen -t ed25519 -N '' -C clutchclips-actions-status -f ~/.ssh/clutchclips_actions_status
scp ~/.ssh/clutchclips_actions_deploy.pub ~/.ssh/clutchclips_actions_status.pub root@HOST:/tmp/
```

The keys have no passphrase, because Actions cannot type one. The server limits what each key can do.

## 3. The droplet (as root)

a. Create a user that can run one script and nothing else:

```bash
adduser --system --group --shell /bin/sh --home /home/clipops clipops
install -o root -g root -m 0755 /root/clip-api/scripts/ops.sh /usr/local/sbin/clutchclips-ops
install -d -m 700 /root/backups /var/log/clutchclips-ops
printf 'clipops ALL=(root) NOPASSWD: /usr/local/sbin/clutchclips-ops\n' > /etc/sudoers.d/clutchclips-ops
chmod 440 /etc/sudoers.d/clutchclips-ops && visudo -cf /etc/sudoers.d/clutchclips-ops
```

- `clipops` needs a real shell (`/bin/sh`), because sshd runs the forced command through it. The forced command still means that no key can get a shell.
- The script runs as root through sudo. The checkout and `.env` are under `/root`, and docker access is root-equivalent anyway, so a `docker` group would not be a real boundary. The boundary is one fixed script that accepts six verbs.
- `/usr/local/sbin/clutchclips-ops` is a copy outside the repo, so a merged PR cannot change what the key may run. After a PR changes `scripts/ops.sh`, run the `install` line again. The deploy summary shows `installed ops script differs` until you do.

b. Install the two keys, each with its forced command:

```bash
install -d -o root -g root -m 755 /home/clipops/.ssh
opts='restrict,no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding'
{
  printf '%s,command="sudo -n /usr/local/sbin/clutchclips-ops \\"$SSH_ORIGINAL_COMMAND\\"" %s\n' "$opts" "$(cat /tmp/clutchclips_actions_deploy.pub)"
  printf '%s,command="sudo -n /usr/local/sbin/clutchclips-ops status" %s\n' "$opts" "$(cat /tmp/clutchclips_actions_status.pub)"
} > /home/clipops/.ssh/authorized_keys
chmod 644 /home/clipops/.ssh/authorized_keys
rm /tmp/clutchclips_actions_*.pub
cat /home/clipops/.ssh/authorized_keys
```

The file must read exactly like this, with your two public keys:

```
restrict,no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="sudo -n /usr/local/sbin/clutchclips-ops \"$SSH_ORIGINAL_COMMAND\"" ssh-ed25519 AAAA... clutchclips-actions-deploy
restrict,no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="sudo -n /usr/local/sbin/clutchclips-ops status" ssh-ed25519 AAAA... clutchclips-actions-status
```

- The file and its folder belong to root, so `clipops` cannot add a key.
- If `/etc/ssh/sshd_config` has an `AllowUsers` line, add `clipops` to it, then `systemctl reload ssh`.

c. Back up nightly. The monitor alerts when the newest verified backup is older than 36 hours:

```bash
printf '30 4 * * * root /usr/local/sbin/clutchclips-ops backup db 7 >> /var/log/clutchclips-ops/cron-backup.log 2>&1\n' > /etc/cron.d/clutchclips-backup
```

d. Check the forced commands from your Mac:

```bash
ssh -i ~/.ssh/clutchclips_actions_deploy clipops@HOST status          # key=value lines, result=ok
ssh -i ~/.ssh/clutchclips_actions_deploy clipops@HOST 'ls /root'      # usage message, exit 64
ssh -i ~/.ssh/clutchclips_actions_deploy clipops@HOST                 # no shell: usage message
ssh -i ~/.ssh/clutchclips_actions_status clipops@HOST preflight       # runs status, whatever was asked
```

## 4. Pin the host key

On your Mac:

```bash
ssh-keyscan -t ed25519 HOST > /tmp/prod_known_hosts
ssh-keygen -lf /tmp/prod_known_hosts
```

On the droplet:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

The two fingerprints must be identical. If they differ, stop: something is between you and the server.

## 5. Secrets

Each secret goes from a file or stdin into GitHub. Nothing is typed into a prompt or shown on screen.

```bash
REPO=salaarkhan123/gta-clipping-pipeline
gh secret set PROD_SSH_KEY        --repo "$REPO" --env production          < ~/.ssh/clutchclips_actions_deploy
gh secret set PROD_KNOWN_HOSTS    --repo "$REPO" --env production          < /tmp/prod_known_hosts
gh secret set PROD_STATUS_SSH_KEY --repo "$REPO" --env production-readonly < ~/.ssh/clutchclips_actions_status
gh secret set PROD_KNOWN_HOSTS    --repo "$REPO" --env production-readonly < /tmp/prod_known_hosts
read -rs PROD_HOST_VALUE    # type the host, then Enter; it is not echoed
printf '%s' "$PROD_HOST_VALUE" | gh secret set PROD_HOST --repo "$REPO" --env production
printf '%s' "$PROD_HOST_VALUE" | gh secret set PROD_HOST --repo "$REPO" --env production-readonly
unset PROD_HOST_VALUE; rm /tmp/prod_known_hosts
```

Keep the private keys on your Mac only. To revoke a key, delete its line from `/home/clipops/.ssh/authorized_keys`.

## 6. Test

1. Run a dry run. It runs every check (CI gate, preflight, both migration checks) and restarts nothing:
   ```bash
   gh workflow run deploy.yml --repo "$REPO" --ref main -f dry_run=true
   gh run watch --repo "$REPO" "$(gh run list --repo "$REPO" --workflow deploy.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
   ```
   With `PROD_APPROVAL=environment`, approve it in the run page first. The job summary shows the commit, the DB revision and the plan.
2. Run the monitor once, then switch it on:
   ```bash
   gh workflow run monitor.yml --repo "$REPO" --ref main    # it skips until OPS_MONITOR=on
   gh variable set OPS_MONITOR --repo "$REPO" --body on
   gh workflow run monitor.yml --repo "$REPO" --ref main
   ```
   With SMTP and `STRIPE_WEBHOOK_SECRET` still unset, it opens an issue labelled `ops`, assigned to you. That is expected, and the issue closes itself once both are set.
3. Run a real deploy when a release is merged:
   ```bash
   SHA=$(gh pr view <release PR> --repo "$REPO" --json mergeCommit -q .mergeCommit.oid)
   gh workflow run deploy.yml --repo "$REPO" --ref main -f ref="$SHA" -f confirm="${SHA:0:7}"
   ```
   With `PROD_APPROVAL=environment`, leave out `confirm` and approve in GitHub instead. Tick `backup_data` only when you want the uploads volume backed up too. It is checked against free disk first.

## Day-to-day

| Task | How |
|---|---|
| Deploy | Release PR merged into `main`, then `deploy.yml` (step 6.3). The summary and a `[devops] [deploy]` comment on the release PR show the commit and DB revision before and after, the backup, the health checks and the timings. |
| Roll back the code | `gh workflow run rollback.yml --ref main -f sha=<full sha> -f confirm=<first 7>`. It backs up the database first, and never touches the database itself. It refuses when the database is at a revision the older code does not have, because that code would not start (current-state.md, gap 6). |
| A destructive migration | Never automatic. The deploy refuses and lists the operations. Back up and review, then run `bash scripts/deploy.sh` by hand on the server. |
| Restore the database | Manual, and only after you decide on it. Stop `api` and `worker` (`docker compose stop api worker`), then `docker compose exec -T db pg_restore -U clip -d clip --clean --if-exists < /root/backups/db-<time>-<sha>.dump`, then `docker compose up -d api worker`. Every credit ledger row written after the backup is lost, so check the time first. |
| Change `.env` | `docker compose up -d api worker` (when no job is RUNNING). `docker compose restart` does not re-read `.env`. |
| See backups | `ls -l /root/backups`. Each `db-*.dump` has a `.ok` file with its size, table count and sha256. The newest 7 are kept. |

## Fit with the board

- **The pipeline never merges.** The Super Board ends at Done, which means merged by the owner or by `super-board-merge-gate.sh`, pinned to the reviewed SHA. Release PRs (`staging` into `main`) stay human merges under `merge_policy.default: human`.
- **A deploy is a step after Done.** The owner, or the `devops` agent (`.claude/agents/devops.md`), dispatches `deploy.yml`. In `confirm` mode the agent runs only dry runs and hands the owner the exact command for the real deploy.
- **Ops issues are not board tickets.** Monitor alerts are issues labelled `ops`, which are not routed to Building. To make one a ticket, file it through `/super-collect` or by hand with the ticket format.
- **The board's migration gate does not fire on this repo yet.** Its `migrations.globs` do not match `clip-api/app/migrations/versions/*.py`. Run `/super-board onboard` to repair it. Until then, the deploy's destructive-migration check is the only automatic one.
