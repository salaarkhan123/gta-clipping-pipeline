# Local CI (zero cost)

The `ci` and `ops-lint` GitHub workflows are disabled (repository Actions settings, `disabled_manually`) because the
included GitHub-hosted minutes are used up. CI now runs on the owner's Mac, at no cost, and reports to GitHub as
commit statuses. This repository's plan has no branch protection, so the merge gate is a script (`merge-when-green.sh`).

## Run it

```bash
ci/local-ci.sh <pr-number | commit> [all|test|docker-build]
```

| Job | What runs | Same as GitHub? |
|---|---|---|
| `local-ci/docker-build` | `docker build --platform linux/amd64 clip-api` (runs first when both jobs run; one automatic retry; failure status quotes the log), image removed afterwards | Same command, pinned to the production droplet's platform. |
| `local-ci/test` | `pytest -q -rs` in `python:3.12-slim` with apt ffmpeg and fonts-dejavu-core, against a throwaway Postgres 16 (`TEST_DATABASE_URL` set as in `ci.yml`); 4 CPUs, 5 GB memory, 45 min limit | Same Python, Postgres, ffmpeg source and command. Runs linux/arm64 natively; GitHub ran linux/amd64. |

- It checks out the exact commit in a temporary worktree under `~/.cache/clutchclips-ci/` (no uncommitted file, no settings file, no secret goes into a container), then removes it with its containers and network.
- It sets `pending`, then `success` or `failure`, on that commit. The description holds the pytest summary; the full log stays on the Mac at `~/.cache/clutchclips-ci/logs/<sha>-<job>.log`.
- Heavy jobs wait for the shared queue `~/ClutchClips-eval/heavy.sh` (one heavy job at a time on this Mac: pipeline runs, Whisper, renders, CI).
- A change made only of Markdown files outside `clip-api/` and `web-src/` gets `success` on both contexts with "docs only" and runs nothing. No test reads those files.
- The test dependency image `clutchclips-ci:<requirements hash>` is built once per requirements change and reused.

## Merge

```bash
ci/merge-when-green.sh <pr-number> <approved-commit-sha>
```

Merges only when the head is the approved commit, `local-ci/test` and `local-ci/docker-build` are `success` on it, and
no GitHub check that ran on it failed. A GitHub-hosted job that GitHub never started (billing or spending limit, zero
steps) is not a test result and does not block. Money, auth, destructive-schema and >400-line PRs still need the
owner's explicit approval first (AGENTS.md); this script does not change that.

## Never

- Never run CI on the production DigitalOcean server.
- Never re-enable the GitHub workflows or re-run hosted jobs without the owner's OK; they cost money once the free minutes are gone.
- Never mark a commit green by hand (`gh api .../statuses`) without running the job.

## Self-hosted GitHub runner on the Mac: evaluation

Not set up. Recommended only if the owner wants checks to start automatically on every push.

- **Cost:** self-hosted runner minutes are not billed today. GitHub announced a $0.002/min platform fee for self-hosted runners in private repositories from March 2026 and then postponed it; re-check GitHub's Actions billing page before relying on this.
- **Workflow changes needed:** `services:` (the Postgres container) and `container:` jobs work only on Linux runners. On a macOS runner, `ci.yml` would have to start Postgres with `docker run` in a step, or call `ci/local-ci.sh`.
- **Security:** the runner executes whatever workflow a pushed branch contains, with the runner user's access. Run it as a separate macOS user with no access to `~/Desktop/GTA Clipping Pipeline/clip-api` settings files, `~/.ssh` or keychains, and keep the repository private.
- **Load:** it competes with agent work for CPU, memory and disk. Set it to one job at a time and route its jobs through `heavy.sh`.
- **Verdict:** `local-ci.sh` gives the same checks with none of the runner's security surface. Add the runner later if waiting for manual runs becomes the bottleneck.
