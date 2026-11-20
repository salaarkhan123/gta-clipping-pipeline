# CI

Primary CI is the GitHub-hosted workflow `.github/workflows/ci.yaml` (`name: ci`). Job names **`test`** and **`docker-build`** are the deploy gate’s required Check Runs (`.github/ops/config.json`).

It runs on pull requests into `staging` / `main`, on pushes to `main` (post-merge verification; does not deploy), and via `workflow_dispatch`. Concurrency cancels superseded runs for the same PR or branch.

| Job | What runs |
|---|---|
| `test` | `pytest -q -rs` in `python:3.12-slim-trixie` (production Dockerfile base, ffmpeg 7.1, git, nodejs, fonts-dejavu-core) against Postgres 16 |
| `docker-build` | `docker build` of `clip-api` for `linux/amd64` (no push), with Buildx GHA layer cache |

`AUTO_DEPLOY_ON_PUSH` stays unset — green CI does not deploy production.

## Local fallback (optional)

`ci/local-ci.sh` remains for offline or zero-minutes use. It posts commit statuses `local-ci/test` and `local-ci/docker-build`. Those statuses are **not** the deploy gate’s required checks; prefer hosted Check Runs for release merges.

```bash
ci/local-ci.sh <pr-number | commit> [all|test|docker-build]
```

## Merge helper

```bash
ci/merge-when-green.sh <pr-number> <approved-commit-sha>
```

Merges only when the head is the approved commit and the required checks are green. Money, auth, destructive-schema and >400-line PRs still need the owner’s explicit approval first (AGENTS.md).

## Never

- Never run CI on the production DigitalOcean server.
- Never mark a commit green by hand (`gh api .../statuses`) without running the job.
- Never set `AUTO_DEPLOY_ON_PUSH=true` without the owner’s OK.
