# Run 2026-11-15 · clutchclips

| Card | Lanes | Final | Column | Detail |
|---|---|---|---|---|
| #2 | build:halted | halted | Ready | not started: origin/staging 8b6719d behind main 8828e84; no changes made |
| #2 | build:advanced → qa:advanced → review:human-gate | human-gate | Blocked | PR #9 clean review 4/4 ACs, truth 95/100, CI pass; awaiting owner merge |
| #2 | owner merge | merged | Done | PR #9 merged to staging @ 506a638 by owner |
| #3 | build:advanced → qa:advanced → review:blocked | blocked | Blocked | PR #10 6/6 ACs, no findings; truth gate inconclusive (no sub-agent tool in lane) |
| #3 | owner merge | merged | Done | PR #10 merged to staging @ b68c664 on owner approval |
| #4 | build:advanced → qa:advanced → review:bounced | bounced | Ready | PR #13 rebuild-1: ci.yml installs only requirements.txt, moto import fails in CI |
| #4 | build:advanced → qa:advanced → review:human-gate | human-gate | Blocked | PR #13 round 2: R1 fixed (ci.yml installs dev reqs), 58 passed; needs-you: check_storage.py on real R2 |
| #5 | build:advanced → qa:advanced → review:human-gate | human-gate | Blocked | PR #14 clean review, 58 passed/13 skipped; money gate; needs-you: RUN_STRIPE_LIVE test with test key |
| #6 | build:advanced → qa:advanced → review:human-gate | human-gate | Blocked | PR #15 clean review, 63 passed; needs-you: send-test-email to owner inbox |
| #7 | build:advanced → qa:advanced → review:human-gate | human-gate | Blocked | PR #16 clean review, 62 passed; needs-you: bench on 2h+ 1080p VOD, paste JSON into SPEC §10 B |
