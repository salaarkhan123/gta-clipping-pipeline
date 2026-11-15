# Pre-flight — ClutchClips build board #2

Written by `super-board lint` on 2026-11-15 from cards #2–#7 and PROJECT.md. Each `[ ]` is a halt gate: `super-board run` refuses to start until it is `[✓]`.

## 🔑 Credentials the loop will need

None. Every check that needs a real secret is a `needs-you:` step the owner runs after merge, never the robot.

Owner-run later (not run gates):

| Card | What you run | Needs |
|---|---|---|
| #4 storage | `python scripts/check_storage.py` | R2 bucket keys (`S3_*` names in the example env file) |
| #5 billing | `RUN_STRIPE_LIVE=1 pytest -q tests/test_stripe_live.py` | Stripe test-mode secret key |
| #6 email | `python scripts/admin.py send-test-email --to <inbox>` | SMTP provider keys |
| #7 bench | `python scripts/bench_pipeline.py <vod>` | a 2h+ 1080p VOD, server shell |

## 🛠 Tools the loop will need

- [✓] gh CLI authenticated as salaarkhan123, `project` scope (verified)
- [✓] Node 26 (verified; `super-board-wave.js` passes `node --check`)
- [✓] Python 3.12 at `/opt/homebrew/bin/python3.12` (matches `python:3.12-slim` in the Dockerfile; 3.15 cannot build `av`)
- [✓] ffmpeg with libass at `/opt/homebrew/opt/ffmpeg-full/bin` (keg-only; `verify_commands` puts it first on PATH)
- [✓] `verify_commands` run from a clean venv: 53 passed, 2 skipped (Postgres-only)
- [✓] Docker not needed locally (card #2 builds the image in CI)

## 🌐 Environment

- [ ] `staging` contains the board config: run `git push origin main:staging` from your own terminal (the push guard blocks agents)
- [ ] Dynamic workflows are ON in `/config` (owner confirms)
- [✓] Live API reachable: https://api.clutchclips.io/health returned `{"ok":true}`
