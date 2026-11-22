# Deploying from git

The droplet deploys from git only: `/root/clip-api` is the `clip-api/` folder of a checkout of the deploy
branch (`main`). Code reaches `main` only through reviewed PRs (`staging` → `main`).

## Every deploy

From GitHub Actions, once `docs/devops/setup.md` is done: `deploy.yml` (with an approval, a backup that is
verified first, and an automatic code rollback), `rollback.yml`, and `monitor.yml` every 15 minutes. They reach the
server only through `scripts/ops.sh`, which wraps `deploy.sh`. By hand on the server:

```bash
cd /root/clip-api && bash scripts/deploy.sh
```

`DEPLOY_SHA=<full sha>` deploys that commit of `main` instead of its head.

**Env changes:** after editing `.env`, run `docker compose up -d api worker` (when no job is RUNNING).
`docker compose restart` does not re-read `.env`.

`scripts/deploy.sh` refuses while a job is RUNNING (it checks `admin.py stuck` before the pull and again right
before the restart), refuses if the job list cannot be read, if tracked files were edited on the server, or if
the checkout is not on the deploy branch. It then fast-forwards, builds `api` and `worker`, runs the schema
migrations from the new image (`admin.py migrate`), restarts only `api` and `worker`, and runs
`admin.py selftest`. A failed migration stops before the restart, so the old code keeps serving on an unchanged
schema. On a selftest failure it prints the rollback command. Caddy and Postgres are
not restarted; `web/` is served straight from the checkout, so the site updates with the pull. A change to the
`Caddyfile` needs `docker compose up -d caddy` as well.

**Security headers** (in the `Caddyfile`, on both domains): HSTS (one year, includeSubDomains, no preload),
nosniff, `strict-origin-when-cross-origin`, `X-Frame-Options: DENY` plus `frame-ancestors 'none'`, a minimal
`Permissions-Policy`, and no `Server` or `Via` header. The site's Content-Security-Policy allows only itself, the API
domain and `*.digitaloceanspaces.com` for media. When the site starts loading from a new origin (fonts, a CDN,
analytics), add that origin to the policy in the same PR, or the browser blocks it.

## Schema migrations

Alembic, in `app/migrations/`. Migrations are additive only (new tables, new nullable or defaulted columns, new
indexes), so the old code keeps working while it still serves and a code rollback needs no schema rollback.
Anything that drops, renames or rewrites data needs its own PR and the owner's OK, with a backup first.

- **See where the database is (read-only):** `docker compose exec -T api python scripts/admin.py db-status`.
  Exit 0 means it is at the latest revision. It lists anything that differs from the models.
- **First deploy with migrations:** the production database predates them. Before that deploy, run `db-status`
  and back up the database (`pg_dump`, as in step 1 below). It should report "from before migrations" plus, at
  most, a missing `ix_accounts_stripe_customer_id` index. `deploy.sh` then brings the database to the baseline
  (adding the missing columns and indexes, and making `uploads.analyzed` NOT NULL, which changes no values) and
  stamps it. After the deploy, `db-status` must report `revision 0001 · latest 0001`.

## Measuring speed

Every job records where its time went: `result.stages` (seconds per pipeline stage), `result.counts` (candidates,
clips, seconds transcribed and rendered), `result.queue_sec` and `result.total_sec` (queue + run: what a customer
waits). Failed and cancelled jobs record it too. The goal is a 2-hour video in 10 minutes and a 4-hour video in 15.

```bash
curl -s $API/v1/jobs/<job_id> -H "authorization: Bearer $KEY" > job.json
python scripts/job_timings.py job.json                           # stage table and the target for that length
python scripts/job_timings.py job.json --baseline before.json    # change against an earlier job
python scripts/job_timings.py job.json --baseline before.json --md   # the same, as a table for a PR
```

A job from before stage timing existed has only the coarse stages shown in the dashboard; comparing with one
uses those. Without a server: `python scripts/bench_pipeline.py <video> --max-clips 10` runs the pipeline locally
(no AI judge) and prints the same stages.

## Transcription settings

- `TRANSCRIPTION_PROVIDER=local` (the only provider so far): whole recordings are transcribed by the local Whisper
  models, in chunks cut at quiet points. Hosted providers are added with their adapters; an unknown name stops the
  worker at start with a clear message.
- `TRANSCRIBE_PARALLEL` (default 1, up to 8): chunks transcribed at once, for whole-recording transcription (Video
  Finder's index today). Leave it at 1 on the 4 vCPU droplet: one model already uses every core. On a machine
  with 8 or more cores try 2 to 4 and compare with `scripts/job_timings.py`. Each extra one adds memory.
- `TRANSCRIBE_CHUNK_SEC` (default 300): the chunk length.
- **One transcript per upload (U1).** Every job on an upload reads what earlier jobs transcribed and keeps what
  it transcribes, so nothing is transcribed twice:
  - `transcripts/<upload>.json` is the whole transcript (Video Finder, Transcripts, Summaries, whole mode below):
    segments, words with start and end, the model that made it. Speakers appear only when the provider identified
    them; the local Whisper models do not, so there are none (never guessed).
  - `transcripts/<upload>.parts.json` keeps the pieces a Clip Maker job transcribed (its candidate windows).
    A re-run on the same upload reads them instead of transcribing again; Video Finder or a transcript job later
    transcribes only the rest. A whole transcript only exists once all of it was transcribed, so Video Finder's
    pricing (which checks for one) is unchanged.
  - A rough pass (what the judge reads) takes text from any model; captions only from the caption model's own
    text. Both files go with the upload at retention and takedown.
- `TRANSCRIBE_WHOLE` (default `false`): Clip Maker transcribes the whole recording first, with word timings, and
  every candidate reads it. Off by default because the local model makes a 2-hour job slower on the droplet
  (numbers in the U1 PR); turn it on with a hosted provider or a bigger machine. It helps only with the AI judge
  (without one, candidates are transcribed by the caption model anyway). A single job can also opt in with
  `options.transcribe_whole: true` on `POST /v1/clips` (listed on `GET /v1/options`); that does not change
  credits. The worker runs whole mode when the env **or** the job option is true.
- `LLM_PASS` (default `true`, U3): with `ANTHROPIC_API_KEY` set and a whole transcript of the upload (whole mode
  above, or an earlier Video Finder or transcript job), the AI reads the transcript in 5-minute chunks (1 minute
  overlap, 8 at a time) and proposes moments; the judge rates them mixed with the strongest signal windows, the
  same number of candidates as before. Without a whole transcript, or when the AI fails (3 tries per chunk,
  60 s each, 150 s for the whole pass), candidates come from the signals exactly as before. A job's counts
  show what happened: `llm_chunks`, `llm_chunks_failed`, `llm_tokens_in`, `llm_tokens_out`, `llm_pass_skipped`,
  `llm_pass_failed`. `false` turns it off. **U3 only runs when Heard covers the analysed range** (whole mode
  via env or per-job opt-in, or an earlier full transcript): keep the global default false on CPU; opt in per
  job or set `TRANSCRIBE_WHOLE=true` once hosted transcription lands.
- `CLIP_QUALITY_FLOOR` (default 40, U4): with a clip-length bucket and no clip count (automatic discovery), a moment
  becomes a clip only when the AI rates it at least this (0-100; an ordinary clip is about 50). There is no quota: a
  long video gets as many clips as it has moments this good, at most 50, and none becomes filler; a job with none is
  `no_moments` and refunded. Tune it on the tuning videos only.
- `SCORE_WEIGHTS` (default empty): per-game weights of the judge's five sub-scores, for ranking only, as JSON
  `{"<game, genre or default>": {"hook": n, "payoff": n, "clarity": n, "emotion": n, "pacing": n}}`. A job's game is
  its template's; it uses the game's weights, else its genre's, else `default`, else the plain mean. Empty: every
  game ranks by the plain mean. The AI rating, the stored sub-scores and the quality floor never change with it.
  Make the value with `python scripts/fit_score_weights.py eval/labels-v2.csv <vod>=<job.json> ... --out w.json`,
  which fits on the owner's labels (tuning videos only, at least 30 rated clips per game) and prints each
  sub-score's rank correlation and precision@k against them. A clip records which weights ranked it
  (`features.rank_weights`, `features.rank_score`).
- Repeats (no setting): two candidates on the same screen (a lobby, a respawn or starting-soon screen, a loop) are
  one moment and only the better is kept; off in a video whose frames all look alike (a fixed camera). Job counts
  `repeat_picture`, `repeat_topic`, `repeat_speech` say how many candidates were dropped as repeats.

## Moment signals (U2)

- Moments are scored per second from loudness (`audio`, 0.7), how fast the sound changes (`audio_flux`, 0.35) and
  laughter-like bursts (`audio_bursts`, 0.35), plus on-screen chat motion when a chat region is set. The two new
  signals come from the loudness decode (one ffmpeg process, two outputs), so audio is still decoded once; they
  add about 17 CPU-seconds per 2-hour video for their FFTs. `pipeline/timeline.py` has them.
- `scene` (picture change between key frames) is built but off (weight 0): it costs a key-frame decode.
- Standby: a candidate whose picture stands still with nobody talking for 90% of its seconds never becomes a clip
  (starting-soon and BRB screens, an empty chair, a menu left open). Each clip records `features.standby`, the
  share. It decodes only the key frames inside each candidate.

## Provisional layouts

`PROVISIONAL_LAYOUTS` (default `false`) controls the layouts that are built but not yet checked on real gaming
footage: `trio`, `grid4`, `ots`, and the `auto` layout that picks a layout for each moment.

- Off (the default):
  - `GET /v1/options` does not list `trio`, `grid4` or `ots`.
  - A request that asks for one of them gets `400 layout_not_available`. This applies to clip jobs, quotes,
    Reframe, Captions, exports and saved templates.
  - `auto` picks one layout for the whole video, as it did before PR #136.
- On: the three layouts are offered, and `auto` looks at each moment. When the camera is hidden, the moment
  fills the frame with gameplay. When the face fills the frame, the moment is framed on the person.

To turn it on:

1. Render a few real VODs with each of the three layouts and with `auto`.
2. Check the frames.
3. Set `PROVISIONAL_LAYOUTS=true` in the server's env file.
4. Run `docker compose up -d api worker`. The API and the worker both read the setting.

Jobs that are already queued keep the layout they asked for.

## Running more than one job at once

Default: one job at a time. Two ways to add capacity:

- **`WORKER_CONCURRENCY=2`** in the server's env file, then `docker compose up -d worker` (when no job is
  RUNNING). One worker process runs two jobs at once and shares one copy of the Whisper and CLIP models, so it
  costs little extra memory. 2 is the limit on the 4 vCPU / 8 GB droplet: each job's ffmpeg and Whisper already
  use every core, so two jobs each run slower, but a second customer no longer waits for the first to finish.
  Values above 2 are rejected at start.
- **A second worker container** (only on a bigger server, or a second one): each container loads its own
  models (check the extra memory with `docker stats` before relying on it) and claims from the same queue; a
  job is claimed by exactly one worker.
  ```bash
  docker compose up -d --scale worker=2 --no-recreate worker
  ```
  `deploy.sh` restarts with `up -d api worker`, which goes back to one container: run the scale command again
  after each deploy. Total jobs at once = containers × `WORKER_CONCURRENCY`.

After either change, run the 10-clip benchmark twice at the same time and compare with SPEC.md §10 B before
relying on it.

## Plans and Stripe Prices

Plan prices, monthly credits and limits live in `app/plans.py` and nowhere else, so every pricing change is a
reviewed PR. The `PLANS` environment variable is no longer read: delete its line from `.env`. Checkout charges a
Stripe Price that you create; the API only needs its ID.

1. In Stripe (test mode first, then live mode), create one product per plan, each with two recurring Prices in
   USD, per unit, billed every 1 month or every 1 year. Use the product names
   `Clutch Clips Starter`, `Clutch Clips Pro` and `Clutch Clips Scale`. Both Checkout and invoice
   processing check the product against the plan. Confirm the names before changing a live catalog.

   | Plan | Monthly Price | Yearly Price |
   |---|---|---|
   | Starter | $15.99 per month | $66.99 per year |
   | Pro | $26.99 per month | $114.99 per year |
   | Scale | $139.99 per month | $839.99 per year |

2. Put each Price ID (`price_...`) in `.env`:

   ```
   STRIPE_PRICE_STARTER_MONTH=
   STRIPE_PRICE_STARTER_YEAR=
   STRIPE_PRICE_PRO_MONTH=
   STRIPE_PRICE_PRO_YEAR=
   STRIPE_PRICE_SCALE_MONTH=
   STRIPE_PRICE_SCALE_YEAR=
   ```

3. Restart: `docker compose up -d api worker`.

4. Check: `docker compose exec -T api python scripts/admin.py stripe-check` (read-only, prints no secret) shows
   the key mode, one `OK` per Price and `ALL OK`. For a real payment test with minimal spend, follow
   `docs/ops/stripe-e2e-test.md`; to change a Stripe key or secret, `docs/ops/credential-rotation.md`.

A plan whose Price ID is blank answers `plan_unavailable`. Before each checkout the API reads the Price from Stripe
and refuses it (`plan_unavailable`, and an error in the api log naming what differs) unless it is active, recurring,
in `CURRENCY`, every 1 month or 1 year as configured, and exactly the amount in `app/plans.py`. A typo in Stripe
therefore stops sales instead of charging the wrong amount.

**Yearly plans grant credits monthly.** The first month comes with the paid yearly invoice; the worker grants each later month on the same day of the month (its sweep runs every minute and catches up after downtime). Grants stop at a refund, a dispute, a cancellation or the end of the paid year; credits already granted stay. Migration `0007` (additive: four nullable columns on `payments`) runs with the deploy.

**Customer portal:** keep plan switching turned off for now (Settings, Billing, Customer portal: allow cancelling
and updating the card only). Every paid invoice grants a full period of credits, so a mid-period upgrade with
proration would grant a whole month of credits for a part payment. To change plan, a subscriber cancels and
subscribes again once the old plan ends.

**Subscribers from before 2026-11-17** keep their plan (`starter`, `pro`, `agency` or `scale` in `accounts.plan`),
its credits on every renewal and its limits, at the price Stripe already charges them, until their subscription
ends. To see how many there are:

```bash
docker compose exec -T db psql -U clip -d clip -c \
  "select plan, subscription_status, count(*) from accounts where stripe_subscription_id is not null group by 1, 2"
```

## Email (Resend)

The api sends verification, password-reset and account emails through Resend's HTTPS API (`app/emailer.py`).
SMTP port 587 is blocked from the droplet, so SMTP is optional. Logs never hold a link, a token or a full
address: `email_sent` and `email_delivery_failed` lines show `s***@domain`. The access log redacts
`?token=` and `/v1/files/<token>` (`app/log_redact.py`).

To switch production to Resend, follow this order. A PR never changes server settings.

1. On the droplet, add the key yourself. Never paste it in chat, a ticket or git:
   ```bash
   cd /root/clip-api
   nano .env      # EMAIL_PROVIDER=resend, RESEND_API_KEY=re_..., EMAIL_FROM=noreply@clutchclips.io
   ```
   Leave `ENV` and `AUTO_VERIFY_EMAIL` as they are for now.
2. Load the new env into the two app containers. This does not touch Caddy or Postgres:
   ```bash
   docker compose up -d api worker
   ```
3. Send one real message, then check the Resend dashboard and the inbox:
   ```bash
   docker compose exec api python scripts/admin.py send-test-email --to you@yourdomain.com
   ```
   - Exit 0 prints Resend's message id.
   - Exit 2 means a key is missing.
   - Exit 1 means Resend refused it: 401 or 403 is a wrong key, 422 means `EMAIL_FROM` is not on a verified domain.
4. Only after a real delivery succeeds, set `ENV=prod` and `AUTO_VERIFY_EMAIL=false` in `.env`, then run
   `docker compose up -d api worker` again. With `ENV=prod` the api refuses to start without working email
   settings, so a typo stops the start instead of leaving mail unsent.

### Reset and verification links that were logged

Before this change, with no email provider configured, the api wrote each email's text, reset and verification
links included, to the container log. To clean up:

1. Void every link already sent: `docker compose exec api python scripts/admin.py bump-token-epoch`.
   - Reset links already expire after 1 hour or on a password change; verification links after 48 hours.
   - The bump kills all of them at once without rotating `SECRET_KEY`, which would log everyone out.
2. Truncate the old container logs (Docker's json-file driver):
   ```bash
   for c in $(docker compose ps -q api worker); do truncate -s 0 "$(docker inspect --format='{{.LogPath}}' $c)"; done
   ```
3. Delete any copies made from those logs, such as downloads or pasted snippets.

## Link import and takedowns

Users can import a public video link (Twitch, Kick, direct https video links, Google Drive and Dropbox share
links, YouTube best effort) with `POST /v1/imports`. Every import is logged in `import_log` (account, link,
platform, consent, time) before anything is fetched. Imports are free; the job run on the imported video is what
costs credits.

`POST /v1/imports/preview {url}` shows what a link is (title, channel, length, thumbnail) before an import. It
reads metadata only, is free, and stores nothing except a log line (`clipapi.ingest`, "import preview"). Lookups
are capped at 10 a minute per account and 15 seconds each; answers are cached in memory for 5 minutes per link.
`IMPORTS_ENABLED=false` switches it off too. The preview also says what kind of link it is (`video_type`,
`live_status`), the game where the site names it, and which options apply; `start_sec` / `end_sec` price a part.

What an import downloads (`app/ingest/platforms.py`): at most 1080p when the video has it, H.264 with AAC first,
then VP9 or AV1, at the highest resolution whose size fits `IMPORT_MAX_BYTES`. YouTube serves picture and sound
as two streams: both are downloaded and joined by our own ffmpeg on the saved files (yt-dlp still runs no
program), so an import needs about twice the video's size in `WORK_DIR` while it runs. `start_sec` / `end_sec`
on `POST /v1/imports` and `POST /v1/clips/from-url` import a part: where the site serves a segment list (Twitch
and Kick VODs, most YouTube videos) only that part is downloaded. A video longer than `IMPORT_MAX_DURATION_SEC`
can be imported one part at a time. A Twitch VOD whose stream is still live is imported up to the part published
so far; the live stream itself is never read. The same part of the same link is never downloaded twice for one
account: a stored copy is handed back, or the part is cut from it (stage `copying`).
A YouTube video that comes without a segment list is read the same way by byte range (each stream is one indexed
file). What an import actually downloaded is on its status as `fetched` (mode, bytes, seconds, and the whole
video's size for comparison), apart from what it charged.

Checking a deployed stack end to end, through the public API only, as one test account:

    export CLIP_API_TOKEN=...      # a session token or API key of the test account; the script never prints it
    python scripts/live_import_smoke.py --base-url https://<api host> \
        --url "https://www.youtube.com/watch?v=<id>" --start 600 --end 660 --i-have-the-rights

It previews the link, starts clips from it with that range, follows the import (stages and bytes), prints what was
charged next to what was downloaded, lists the clips, quotes and runs an export of the first one, downloads it and
checks with ffprobe that it has a picture and sound and decodes to its full length, then prints the balance before
and after with the ledger rows. It stops at the first failing step with `FAILED stage=... code=... message=...`
(tokens and signed addresses removed). Exit 0: every step passed. 1: a step failed. 3: a failed import did not come
back to the starting balance. A passing run spends real credits (the clip job and the export). Needs `httpx` and
`ffprobe` where it runs; `--help` lists the options.

`IMPORT_TIMEOUT_SEC` (30 minutes) bounds one download. Measured from a laptop on 2026-11-18: 25 seconds of a
1080p Twitch VOD (24 MB) took 2.9 s end to end. A whole multi-hour VOD has not been timed; a download that runs
out of time fails cleanly and says to upload the file.

`POST /v1/clips/from-url {url, consent: true, options}` does both steps in one call: it reserves the quoted
credits on a clip job (status `WAITING`, stage `importing`), queues a normal import (logged the same way), and
when the import has stored the video the worker queues the clip job in the same transaction. A failed or
cancelled import refunds the job. If a worker dies between the two, the worker's one-minute sweep finishes or
refunds the job; `python scripts/admin.py stuck` lists `WAITING` jobs too. Contract: `docs/CONTRACTS.md`,
"URL clipping".

- **Switch imports off:** set `IMPORTS_ENABLED=false` and restart `api` and `worker`. New imports are refused
  with "upload the file instead"; imports already queued fail the same way (and the link clip jobs waiting for
  them are refunded). Uploads keep working.
- **Caps** (defaults in brackets): `IMPORT_MAX_BYTES` (8 GB), `IMPORT_MAX_DURATION_SEC` (6 hours),
  `IMPORT_TIMEOUT_SEC` (1800, the whole download). The upload limits (`MAX_UPLOAD_BYTES`, `MAX_DURATION_SEC`,
  `MIN_DURATION_SEC`) apply too; the lower value wins.
- **yt-dlp** is pinned in `requirements.txt`. Upgrade it in its own PR: the test in
  `tests/test_ingest_platforms.py` lists every option it is given and must still pass.

**Takedown request** (a rights holder asks for a video to be removed):

1. See what would be removed, without changing anything:
   `docker compose exec -T api python scripts/admin.py takedown --url "<the link>" --dry-run`
   (or `--account <account id or email>` for everything one account imported by link).
2. Remove it: run the same command without `--dry-run`. It prints each upload, its clips and files, and the jobs
   it cancelled with the credits returned.
3. If it says a job "is still stopping", run the same command again a minute later. It is safe to run any number
   of times; a second run prints "Nothing to remove."
4. Keep the printed output with the request. The `import_log` rows are kept: they record who imported the link.

The link may be given in any form the site uses (with or without `www.`, tracking parameters, `youtu.be`): it is
matched by its canonical form. Ordinary uploads are never touched by a takedown.

**Copyright and likeness reports** arrive through `POST /v1/trust/reports` (no login). Each one becomes a case
with a reference (`CC-XXXX-XXXX`) that is emailed to the claimant. A notice goes to `TRUST_ADMIN_EMAIL`, or to
every admin account when it is empty. A report changes no content.

- Make an account an admin (its website login can then read `/v1/admin/trust/cases`):
  `docker compose exec -T api python scripts/admin.py make-admin you@yourdomain.com` (`revoke-admin` undoes it).
  API keys never reach admin routes, even an admin's.
- Limits: `TRUST_REPORTS_PER_IP_PER_HOUR` (5), `TRUST_REPORTS_PER_IP_PER_DAY` (20),
  `TRUST_REPORTS_PER_EMAIL_PER_DAY` (3); 32 KB per report.
- Decide with `POST /v1/admin/trust/cases/{reference}/decisions {"action": ...}`. Each decision is one event in
  the case history, with who and when.
  - `forward_notice`: sends the notice to the account holder (Canada's notice-and-notice). It removes nothing.
  - `disable`: hides the content and keeps its files. `restore` and `reject` bring it back.
  - `remove`: the verified decision. It gives one strike per account; `REPEAT_INFRINGER_STRIKES` (3) suspends the
    account. Strikes never expire while `REPEAT_INFRINGER_STRIKE_DAYS` is 0.
  - `withdraw`, or `restore` after a counter-notice, cancels the case's strikes.
  - `delete_content`: removes the files, only on a case already decided `remove`.
  - `terminate {account_id, note}`: suspends an account at once for a serious violation.
- Links handed out before a `disable` keep working until they expire (`SIGNED_URL_TTL_SEC`, 1 hour).
- The reported user sees their cases at `GET /v1/trust/my-cases`, without the claimant's contact details. They can
  send a counter-notice there; a copy goes to the claimant, and the admin decides on `restore` after 10 business
  days.

## Creators League

A free monthly competition: creators enter one published clip, admins review entries and record public view
counts by hand, and the top three are approved by an admin. The rules are in `app/league.py`; the rules text shown
on `/league/` is in `app/league_rules.py`.

- Migration order. The league tables are revisions `0012_league` and `0013_league_hide`, which follow `0011`.
  The security PR #274 adds its own `0012` (admin MFA), also on `0011`. Whichever merges second must set its
  first revision's `down_revision` to the other branch's newest revision (`0012_league` is already on main, so
  #274's `0012` must revise the league's newest revision on main), or Alembic finds two heads and `deploy.sh` stops before the restart. Check with
  `python scripts/check_migrations.py --versions app/migrations/versions --current <live revision>` before a deploy.
- Run it from `/dashboard/admin/league/`, signed in as an admin account (`scripts/admin.py make-admin`).
  A new competition is a draft only admins see. "Open to the public" publishes it.
- Entries wait as pending until an admin approves them. Open each video, check that the description carries the
  attribution link, then approve or reject with a reason the creator sees.
- View counts are typed in by an admin from the video's public page. Each reading is kept; the newest one ranks
  the entry. They are shown as unverified with the time of the reading.
- After the end date, "Close entries", approve the winners first place first, then "Make results final".
  Nothing is paid by the system. Send each prize yourself, then use "Mark sent" with the payment reference.
- Every admin action is in the audit log at the bottom of the admin page (`GET /v1/admin/league/events`).
- An admin cannot review, flag, count or approve as winner an entry of their own (403 `own_entry`): another admin
  does it. A final competition takes no more reviews, flags, counts or setting changes.
- A clip removed before its retention ran out (a trust decision, a takedown, its owner) leaves the public board,
  featured clips and profile pages; the admin list marks it "Clip removed". A trust `disable` or `remove` also
  disqualifies the entry, with the case reference as the reason and `system` as the actor. In a final competition,
  or for an approved winner, the entry is flagged instead and the result is left for an admin to decide. A clip
  deleted by the normal retention sweep is not removed: its entry stays on the board.
- "Hide profile" on an entry makes the creator's profile private; the creator cannot make it public again until an
  admin unhides it. A username a creator gives up is held for them for 30 days.
- Cash prizes are locked. The public page shows no amounts until `LEAGUE_CASH_PRIZES_APPROVED=true` is set on
  the server and an admin ticks "Show cash prizes" on the competition. Set it only after a lawyer has reviewed
  the official rules: the text in `app/league_rules.py` is a draft with placeholders and claims no compliance.
  When the rules text changes, add the new version to `TEXTS` there and point `VERSION` at it; never edit a
  version in use. A competition keeps the version it was created with: its page and entry form show that text,
  and the admin page says when a newer version exists.
- Limits: `LEAGUE_SUBMITS_PER_HOUR` (5 per account), `LEAGUE_PROFILE_EDITS_PER_HOUR` (10 per account),
  `LEAGUE_READS_PER_MINUTE` (120 per address on the leaderboard, featured and creator routes). `/v1/league/current`
  and `/v1/league/rules`, read on every homepage visit, have no per-address limit; every public league read is
  sent with `Cache-Control: public, max-age=30`.
- The attribution link creators paste is `PUBLIC_WEB_URL`. Check it is the live site's address.

## Premium AI thumbnails

A paid option on top of the free thumbnail (#140). The free frame-based thumbnail is always made and stays free,
and so are choosing between a clip's thumbnails and editing or hiding their text. A premium thumbnail restyles the
clip's thumbnail frame with an image-edit model (Gemini Nano Banana 2.1, with one retry on Gemini); our
own renderer then draws the hook, so the words are spelled exactly. Every attempt's provider, time and estimated
cost is kept in the thumbnail's `info` and the job's `result`.

| Setting | Default | What it does |
|---|---|---|
| `PREMIUM_THUMBNAILS` | `false` | The feature flag. Off: the premium routes answer 404 `premium_thumbnails_off`, `/v1/options` does not list them and the website hides the panel. Leave it off until real provider tests and a quality check are done. |
| `GEMINI_API_KEY` | empty | The only provider. It must be a key from a Google project **with billing on** (paid tier): on the free tier Google trains on what is sent and people may review it (see Data handling). Empty: the routes answer 503. |
| `PREMIUM_THUMB_CREDITS` | `25` | The price of one premium thumbnail, in credits (owner OK 2026-11-17). The only price used: the quote, the confirm step and the reservation all read it. |
| `GEMINI_IMAGE_MODEL` | `gemini-nano-banana-2.1` | The Gemini model id (the stable id in Google's model page). |
| `GEMINI_IMAGE_SIZE` | `2K` | `1K`, `2K` or `4K`. 2K is $0.0504 an image. |
| `PREMIUM_THUMB_TIMEOUT_SEC` | `60` | One provider attempt, end to end. |
| `PREMIUM_THUMB_STYLES` | four presets | JSON list of `{id, name, prompt}`; each prompt describes a look only. |

- The worker runs premium thumbnails in a slot of their own (started when the flag is on), so a 20-second paid
  job never waits behind a 2-hour VOD. Restart the `worker` after turning the flag on.
- Credits: reserved once at confirm, settled once. Any failure (provider error or timeout after the retry, safety
  block, the face lost, cancel, crash, dead worker) is refunded in full.
- Likeness consent: the first premium thumbnail of a clip needs the user's confirmation that they are the streamer
  or have their permission; each one is a row in `likeness_consents` (account, clip, wording, time).

**Data handling.** A premium thumbnail sends Gemini one frame of the clip and a close-up of the face in it, plus
the prompt (the style and the user's custom styling). Nothing else: no video, no account details. Owner rule
(2026-11-18): customer footage never goes to a provider that trains on API inputs without the user's explicit,
informed authorization.

| Provider | Trains on what we send? | Kept by the provider | What we do |
|---|---|---|---|
| Google Gemini, paid tier | No: "Google doesn't use your prompts … or responses to improve our products" (Gemini API Additional Terms, Paid Services, effective 2026-03-23) | 55 days for abuse monitoring only (Gemini API abuse-monitoring page); request logs for the project unless turned off | Every request sends `store: false`. Use a billing-enabled key only. Leave AI Studio's "Logs and datasets" sharing off. |
| Google Gemini, free tier | **Yes**, and human reviewers may read inputs and outputs (Unpaid Services) | Not stated | Never use a free-tier key for this feature: the frames contain real faces. |
| Black Forest Labs (removed) | **Yes, by default**: the privacy policy (section 2) says BFL may use inputs, tasks and outputs to train its models | "As long as reasonably necessary" (section 7) | Not used. There is no API flag or account setting to turn training off; the only routes are an email request to privacy@blackforestlabs.ai (subject "Training Opt Out") that we cannot verify, or an enterprise contract. Re-adding BFL needs a verifiable opt-out first. |

- Benchmark with real calls (about $0.06 a thumbnail), from `clip-api/` with the keys in its settings file:
  `python scripts/premium_thumb_bench.py <out_dir> --video <file> <moments.csv> --per-video 20`.
## Moving files to Cloudflare R2

The production choice: R2 charges nothing for downloads, and clip files are mostly downloaded. Same code path as
Spaces (`STORAGE_BACKEND=s3`): a private bucket, and every link the site shows is a signed URL straight from the
bucket, valid for `SIGNED_URL_TTL_SEC` (at most 7 days, R2's limit; longer values are cut to 7 days).

**What differs from S3** (developers.cloudflare.com/r2, read 2026-11-17; pages under `/r2/`):
- Region is `auto` (`api/s3/api/`). Endpoint `https://<account id>.r2.cloudflarestorage.com` (`api/tokens/`).
- No full-object CRC32 checksums and no checksum headers on CopyObject or PutBucketCors (`api/s3/api/`): the
  client sends checksums only when the API requires them.
- Multipart: every part but the last the same size, 5 MiB to 5 GiB, at most 10,000 parts
  (`objects/multipart-objects/`). boto3 cuts equal parts. Unfinished multipart uploads are aborted after 7 days by
  default, so no lifecycle rule is needed for them.
- DeleteObjects takes 1,000 keys (`platform/release-notes/`, 2022-07-01); deleting a folder sends batches of 1,000.
- Signed URLs: 1 second to 7 days, GET/HEAD/PUT/DELETE, only on the S3 endpoint, not on a custom domain
  (`api/s3/presigned-urls/`). So media is served from `<account id>.r2.cloudflarestorage.com`.
- Buckets are private unless public access is turned on (`buckets/public-buckets/`). Leave the r2.dev URL and
  custom domains off.
- The site reads captions from the bucket and sends uploads to it in the browser, so the bucket needs CORS rules
  (`buckets/cors/`).
- R2 does not document the `response-content-disposition` override, so each file is also stored with
  `Content-Disposition: attachment; filename=...` (documented on PutObject). The Download button saves the clip
  under its name; `<video>` and `<img>` ignore the header.

**Price** (`r2/pricing/`, read 2026-11-17): storage $0.015 per GB-month, Class A operations (writes, lists)
$4.50 per million, Class B (reads) $0.36 per million, downloads free. Free each month: 10 GB-month, 1 million
Class A, 10 million Class B. Deletes are free.

| 1 TB stored, 5 TB downloaded per month | R2 | Spaces |
|---|---|---|
| Storage | 1,000 GB × $0.015 = $15.00 (less 10 GB free: $14.85) | $5 base (250 GiB) + 681 GiB × $0.02 = $18.62 |
| Downloads | free | 1,024 GiB in the base, then 3,633 GiB × $0.01 = $36.33 |
| Operations | about 0.4 M Class A (uploads in 8 MiB parts, clips) and 1 M Class B: inside the free tier, $0 | included |
| **Total** | **about $15 per month** | **about $55 per month** |

Downloads by the worker (R2 to the droplet) are free too. Above 1 M writes a month, Class A costs $4.50
per further million.

1. In the Cloudflare dashboard, R2, **Create bucket**: a name (for example `clutchclips-media`), Location:
   **Specify jurisdiction** off, **Location hint** nearest the droplet (NYC or TOR droplet: Eastern North America
   `enam`; SFO: `wnam`; AMS, FRA, LON: `weur`; SGP, BLR: `apac`; SYD: `oc`). Default storage class Standard.
   Hints are best effort and apply only when the bucket is created (`reference/data-location/`).
2. Bucket, **Settings**: Public Development URL **disabled**, no custom domain. **CORS policy**, Add, JSON tab,
   paste (the site is the only origin; `www` redirects to it):
   ```json
   [
     {
       "AllowedOrigins": ["https://clutchclips.io"],
       "AllowedMethods": ["GET", "HEAD", "PUT"],
       "AllowedHeaders": ["range", "content-type"],
       "ExposeHeaders": ["Content-Length", "Content-Range", "Content-Type", "ETag"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```
3. R2, **Manage API tokens**, **Create API token**: permission **Object Read & Write**, **Apply to specific
   buckets only**: the bucket from step 1, TTL forever. Copy the Access Key ID and Secret Access Key (shown once)
   and the S3 endpoint `https://<account id>.r2.cloudflarestorage.com`.
4. Add to the server's env file (keep `STORAGE_BACKEND=local` for now):
   ```
   S3_ENDPOINT_URL=https://<account id>.r2.cloudflarestorage.com
   S3_REGION=auto
   S3_BUCKET=clutchclips-media
   S3_ACCESS_KEY_ID=<access key id>
   S3_SECRET_ACCESS_KEY=<secret access key>
   SIGNED_URL_TTL_SEC=3600
   ```
   Then `docker compose up -d api worker caddy` when no job is RUNNING. Caddy adds `S3_ENDPOINT_URL` to the site's
   Content-Security-Policy (`MEDIA_ORIGIN` in `docker-compose.yml`), so the browser may load media from it.
5. Check the bucket: put, get, signed URL (bytes, type, file name), CORS for `PUBLIC_WEB_URL`, private (no
   unsigned reads), delete, delete-folder. Every line must be `ok`. Then copy the files (safe to repeat; nothing
   local is deleted):
   ```bash
   docker compose exec -T -e STORAGE_BACKEND=s3 api python scripts/check_storage.py
   docker compose exec -T api python scripts/migrate_storage.py --dry-run
   docker compose exec -T api python scripts/migrate_storage.py
   ```
   Optional, from a laptop with the repo: `tests/test_r2_live.py` runs every storage call, the migration and the
   check against the bucket (`R2_ENDPOINT_URL`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`; under
   half a cent of operations, cleans up after itself).
6. Switch: set `STORAGE_BACKEND=s3`, `docker compose up -d api worker` (when no job is RUNNING), then run
   `migrate_storage.py` once more to pick up anything written in between. It must end with `failed 0`.
7. Verify: run one job on the site, play a clip, open the editor (captions load from the bucket), press
   Download (saved under the clip's name). Upload a video: the browser's network tab shows `PUT` requests to the
   bucket host, not one long `POST /v1/uploads`. The browser console shows no CSP or CORS error. Keep the local
   files for a week (`data/storage` in the `data` volume), then delete them.

**Direct uploads** (#62): with `STORAGE_BACKEND=s3` the site sends videos straight to the bucket in parts of 16 MiB
or more, four at a time, instead of through the droplet (`app/routes_direct_upload.py`). A part that fails is
retried; after a dropped connection, picking the same file again resumes from the parts already stored (the token
lasts 24 hours). Each part URL signs its exact size, so the bucket refuses anything else. The upload is recorded
only after every part is stored at the agreed size; then the API downloads the file once (free from R2) to check
the size, hash it for re-upload detection, and read it as a video within the limits. A file that fails is
deleted. Unfinished uploads are aborted by R2 after 7 days (bucket Settings, Object lifecycle rules; 2 days is
enough, since an upload can be resumed for 24 hours). On local storage the site keeps using
`POST /v1/uploads`.

**Roll back:** set `STORAGE_BACKEND=local` and `docker compose up -d api worker`. Files created while on R2 are
only in the bucket; copy them back with `aws s3 sync` (endpoint as above, region `auto`) before deleting it.

**Storage folders** (retention and account deletion delete by folder, `delete_prefix`; ticket #150):

| Folder | Holds | Removed with |
|---|---|---|
| `uploads/<account id>/<upload id>.<ext>` | source videos | the upload; `uploads/<account id>/` with the account |
| `transcripts/<upload id>.json`, `index/<upload id>.npz` | per-upload transcript and visual index | the upload (single keys, not folders) |
| `clips/<job id>/` | clip videos, previews, thumbnails, captions | the job |
| `exports/<job id>/` | rendered exports | the job |
| `healthcheck/`, `r2-live-test/` | left only if a check was killed midway | safe to delete any time |

`delete_prefix` takes only a whole folder ending in `/`, so `uploads/acct_1/` never touches `uploads/acct_10/`,
and raises if the bucket refuses any key.

## Moving files to DigitalOcean Spaces

Uploads and clips are stored on the droplet's disk by default (`STORAGE_BACKEND=local`). Spaces moves them to a
private bucket; download links become signed URLs straight from the bucket, valid for `SIGNED_URL_TTL_SEC`.

**Price** (docs.digitalocean.com/products/spaces/details/pricing, checked 2026-11-15): $5.00 per month, which
includes 250 GiB stored and 1,024 GiB of downloads; beyond that $0.02 per GiB stored per month and $0.01 per
GiB downloaded. Transfer from a Space to a Droplet in the same region group is free, so create the Space in the
droplet's region.

1. In the DigitalOcean panel: create a Space in the droplet's region with **file listing restricted**, and a
   Spaces access key limited to that bucket. Add the CORS rule from the R2 section (Settings, CORS
   Configurations: origin `https://clutchclips.io`, GET, HEAD and PUT, headers `range` and `content-type`), and
   a lifecycle rule that aborts unfinished multipart uploads after 7 days (R2 does this by default; Spaces does
   not): `aws s3api put-bucket-lifecycle-configuration --endpoint-url $S3_ENDPOINT_URL --bucket <space> --lifecycle-configuration '{"Rules":[{"ID":"abort-parts","Status":"Enabled","Filter":{"Prefix":""},"AbortIncompleteMultipartUpload":{"DaysAfterInitiation":7}}]}'`.
2. Add to the server's env file (keep `STORAGE_BACKEND=local` for now):
   `S3_ENDPOINT_URL=https://<region>.digitaloceanspaces.com`, `S3_REGION=<region>` (for example `nyc3`),
   `S3_BUCKET=<space name>`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`. Then `docker compose up -d api worker`
   when no job is RUNNING.
3. Check the bucket, then copy the existing files (safe to repeat; nothing local is deleted):
   ```bash
   docker compose exec -T -e STORAGE_BACKEND=s3 api python scripts/check_storage.py
   docker compose exec -T api python scripts/migrate_storage.py --dry-run
   docker compose exec -T api python scripts/migrate_storage.py
   ```
4. Switch: set `STORAGE_BACKEND=s3`, `docker compose up -d api worker` (when no job is RUNNING), then run
   `migrate_storage.py` once more to pick up anything written in between. It must end with `failed 0`.
5. Run one job and download a clip. Keep the local files for a week (`data/storage` in the `data` volume), then
   delete them. **Roll back:** set `STORAGE_BACKEND=local` and restart; files created while on Spaces are only
   in the bucket.

## One-time switch from tarballs to git

Do this when nothing is running, after `main` contains exactly the code the droplet runs
(PR #18 merged into `staging`, then a `staging` → `main` PR merged).

1. Back up the current folder and the database:
   ```bash
   cd /root
   tar czf clip-api-pre-git-$(date +%F).tgz --exclude='clip-api/data' clip-api
   docker compose -f clip-api/docker-compose.yml exec -T db pg_dump -U clip clip > clip-pre-git-$(date +%F).sql
   docker volume ls | grep clip-api_        # note the names: clip-api_pgdata, clip-api_data, clip-api_caddy_data, …
   ```
2. Give the droplet read-only access to the private repo with a deploy key:
   ```bash
   ssh-keygen -t ed25519 -N '' -f ~/.ssh/clutchclips_deploy -C clutchclips-droplet
   cat ~/.ssh/clutchclips_deploy.pub
   ```
   Add it in GitHub → repo → Settings → Deploy keys, **read-only** (leave "Allow write access" off). Then:
   ```bash
   printf 'Host github.com\n  IdentityFile ~/.ssh/clutchclips_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
   ```
3. Clone the deploy branch next to the old folder:
   ```bash
   git clone --branch main git@github.com:salaarkhan123/gta-clipping-pipeline.git /root/clutchclips
   ```
4. Check the checkout matches what is running. Only untracked files (`.env`, `data/`, caches) may differ:
   ```bash
   diff -rq /root/clip-api /root/clutchclips/clip-api -x .env -x data -x __pycache__ -x .venv -x node_modules
   ```
   Any code file that differs means `main` is not what production runs. Stop and fix that with a PR first.
5. Carry over the untracked files and pin the compose project name, so the existing volumes (database,
   uploads, TLS certificates) are reused:
   ```bash
   cp -p /root/clip-api/.env /root/clutchclips/clip-api/.env
   grep -q '^COMPOSE_PROJECT_NAME=' /root/clutchclips/clip-api/.env || echo 'COMPOSE_PROJECT_NAME=clip-api' >> /root/clutchclips/clip-api/.env
   ```
   Copy anything else step 4 listed as "Only in /root/clip-api" that is not code.
6. Swap the folders. `/root/clip-api` becomes a link into the checkout:
   ```bash
   mv /root/clip-api /root/clip-api.pre-git
   ln -s /root/clutchclips/clip-api /root/clip-api
   ```
7. Re-point the running containers at the new folder. Bind mounts (`./web`, `./Caddyfile`) still point at the
   old directory until each container is recreated, so recreate Caddy once (a few seconds of site downtime),
   then deploy api and worker with the script:
   ```bash
   cd /root/clip-api
   docker compose config --volumes            # must list the same volumes as step 1
   docker compose up -d caddy
   bash scripts/deploy.sh
   docker volume ls | grep clip-api_          # no new volumes were created
   curl -s https://api.clutchclips.io/health
   ```
8. Keep `/root/clip-api.pre-git` and the backups for a week, then delete them.

**Roll back** the switch: `rm /root/clip-api && mv /root/clip-api.pre-git /root/clip-api && cd /root/clip-api &&
docker compose up -d`.
