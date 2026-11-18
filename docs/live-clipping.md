# Live clipping (4.5): investigation and design

Stage 1 of 2. Design only: no product code, no schema, no price is set here. Stage 2 (a local prototype behind `LIVE_CLIPPING=false`) starts after the owner answers section 9.

Every external fact below was read from the official page on **2026-11-18** and is quoted or linked. Where a number is an estimate and not a measurement, it says so. This is an engineering reading of the terms, not legal advice.

Tickets: #65 (4.5a recorder), #66 (4.5b detection, clip, notify), #67 (4.5c credits, caps), #68 (4.5d sizing).

## 1. Compliance

### 1.1 Verdict

| Question | Answer |
|---|---|
| May we pull a channel's live video from Twitch's playback endpoints? | **No.** Not for another party's channel, and not for the creator's own channel either. |
| How does the video reach us? | **The creator sends it.** Their encoder (OBS or similar) pushes a second output to a ClutchClips ingest URL with a per-session key. |
| What is Twitch used for? | Status, title, category and chat only, through the documented API and EventSub, with the creator's OAuth authorization. |

Why pulling is not permitted:

- a. The Developer Services Agreement allows documented interfaces only. Section XI.I: "You will not access undocumented Program Materials ... unless you have Twitch's prior written permission, will only access Program Materials documented on the Twitch Developer Site." The API reference documents no endpoint that returns live video. The playback endpoints the web player uses are not documented there.
- b. The same agreement, Schedule 1 D.1: "You must adopt and integrate our embeddable player for all Twitch video content. You may not use any other player or system to display Twitch video content without Twitch's prior written permission."
- c. Schedule 1 C: "Do not store copies of Twitch Content or Program Materials, unless you: (a) obtain prior written authorization from Twitch ...; (b) control the rights associated with such content; or (c) cache such information for only a twenty-four hour time period without further sharing it with third parties." It adds: "Re-syndication and re-distribution of Program Materials or data as available from a Twitch API is prohibited."
- d. The Terms of Service, section 7 (License), do not permit "(d) use of any data mining, robots, or similar data gathering or extraction methods; (e) downloading (except page caching) of any portion of the Twitch Services, the Materials, or any information contained in them, except as expressly permitted on the Twitch Services".
- e. The Terms of Service, section 10 (Prohibited Conduct), xi: you may not "access any website, server, software application, or other computer resource owned, used, and/or licensed by Twitch ... by means of any robot, spider, scraper, crawler, or other automated means for any purpose, or bypass any measures Twitch may use to prevent or restrict access". Item vi forbids interfering with "features that prevent or restrict use or copying of any content accessible through the Twitch Services".
- f. Our own rule (CLAUDE.md, Ingestion) already forbids client spoofing and any way around a block. Reading an interface that is offered only to Twitch's own player would mean presenting ourselves as that player.

Why creator-sent video is clean: the stream leaves the creator's encoder and reaches us directly. It never passes through Twitch, so it is the creator's own content, not "Twitch Content" obtained through Twitch. The simulcast rule (Terms of Service, section 11) covers streaming "on any other network, platform, or service that supports live streaming of user generated content". ClutchClips does not show the stream to an audience, so by our reading a private ingest is not a simulcast. If a creator uses a restream service to reach us, their other destinations are their own matter under that section.

### 1.2 What we use from Twitch

| Need | Interface | Authorization (as documented) |
|---|---|---|
| Stream went live | EventSub `stream.online` v1 | "No authorization required." Cost 0 once the creator has authorized the app |
| Stream ended | EventSub `stream.offline` v1 | "No authorization required." |
| Title or category changed | EventSub `channel.update` v2 | "No authorization required." |
| Live status, title, `game_id`, `game_name`, `started_at`, `viewer_count`, `thumbnail_url` | Helix `GET /helix/streams` | "A user access token" or "An app access token" |
| Title and category when offline, content classification labels | Helix `GET /helix/channels` | user or app access token |
| Chat messages | EventSub `channel.chat.message` v1 over WebSocket | "A user access token that includes the **user:read:chat** scope." |
| Deleted messages and bans (to drop them from counts) | EventSub `channel.chat.message_delete`, `channel.chat.clear_user_messages`, `channel.chat.clear` v1 | same scope |
| Creator disconnected the app | EventSub `user.authorization.revoke` v1 over webhook | app access token whose client ID matches |

- **Scopes requested: `user:read:chat` only.** Schedule 1 A: "You must only request access to the data and publishing permissions necessary to implement Your Services' current features". `clips:edit` (Create Clip on Twitch) and `channel:manage:broadcast` (stream markers) are not requested; they are possible later features with their own approval.
- **Chat transport:** EventSub, not IRC. The chat docs: "The preferred method of viewing and sending chats on Twitch is through EventSub and Twitch API." IRC with `chat:read` stays a documented fallback; we do not build it.
- **Transports:** "webhooks uses app access tokens and WebSockets uses user access tokens". Chat runs on one WebSocket per connected creator with their user token (up to 300 subscriptions per connection). Status, updates and revoke run on a webhook with the app token.
- **OAuth flow:** authorization code flow, confidential client, tokens stored encrypted with a key from the environment. Refresh tokens are used on a 401.
- **Token validation:** "Your app must validate the OAuth token when it starts and on an hourly basis thereafter." Twitch audits this. An invalid token ends the Twitch side of every session that uses it.
- **Rate limits:** token bucket, shown in the `Ratelimit-Limit` header (the doc's example is 800 points a minute). We poll `GET /helix/streams` at most once a minute per live session and rely on EventSub otherwise.
- **Subscription limits:** `max_total_cost` 10,000 per app; subscriptions for a user who authorized the app cost 0.

### 1.3 Data rules that shape the design

| Rule (Developer Services Agreement) | What we do |
|---|---|
| VI.C: Twitch Data and "insights derived from that data, may not be sold, licensed, monetized, distributed for commercial purposes, made available to, or otherwise shared with, any affiliates or third parties" without written permission | Chat text, usernames, title and category never leave our servers. They are **not** sent to the AI judge or to a hosted transcription provider. The judge gets the transcript and a frame, which come from the creator's own stream |
| Schedule 1 D.2: "You must only retain chat logs as long as necessary for the operation of Your Services ... You must enable, and process, all requests by end users to block, discontinue, delete, or otherwise opt-out of any retention of chat logs" | Chat is reduced to per-second counts in memory (messages, unique chatters, a short list of hype keywords and emote names). Message text and usernames are never written to disk or the database. Each clip stores only its numbers |
| VI.F and Schedule 1 C: delete all Twitch Data on revoke, on request, or on termination | `user.authorization.revoke` and "Disconnect Twitch" delete the tokens, the Twitch user ID link and any stored Twitch metadata, and stop chat for running sessions |
| Schedule 1 A: public privacy policy that says what is collected and how it is used, stored and retained | Privacy page update before launch (section 9) |
| IV.C: no circumvention of rate limits | One poll a minute, back off on 429 using `Ratelimit-Reset` |
| VI.B(d): Twitch Data may be used "as necessary to process transactions (e.g., charging broadcasters for certain functionality)" | Charging creators for live clipping is a contemplated use |

### 1.4 Link preview for a channel URL (agreed with the ingestion agent)

- A channel page (`twitch.tv/<login>`, `kick.com/<slug>`) is recognised by URL shape only. No request is made, and no stream extractor is enabled.
- Preview answer: `supported: false`, `kind: "channel"`, `video_type: "live_channel"`, `live_status: null`, `channel: "<login>"`, `refusal.code: "live_channel"`. An import of it fails with 422 `live_channel`; nothing is logged or charged.
- Whether the channel is live is not looked up in the preview.
- The website may show "Clip this while you stream" on that answer only when the server flag is on. The live agent adds an optional `live_clipping: {"available": bool}` field in Stage 2; the ingestion agent does not.

## 2. Architecture

The engine is reused, not forked. `run_pipeline` stays one function for recordings. Live adds a package `clip-api/app/live/` that calls the same parts: `signals.baseline_z` and `normalise`, the `Transcriber`, `transcribe.snap_to_speech`, the judge in `app/ai.py`, `render.render_clip` with `preview=True`, `render.render_thumb`, `captions`, `facecam`. The live package has no web or database code in its core loop; a thin service wires it to sessions, storage and the ledger.

### 2.1 Parts

| Part | Choice | Notes |
|---|---|---|
| Ingest server | **MediaMTX** (MIT, single binary, self-hosted, free) | Accepts RTMP and SRT from OBS, authenticates each publish through an HTTP call to our API, records to disk in fMP4 or MPEG-TS, and runs hooks on connect, disconnect and segment complete. nginx-rtmp (BSD 2-clause) is the fallback: RTMP only, no SRT |
| Stream key | Per session, random, stored hashed like API keys, shown once | Checked in MediaMTX's HTTP auth call (`action: publish`). RTMP sends the key in clear, so the docs for the creator recommend SRT with a passphrase or RTMPS; Stage 2 verifies both on MediaMTX |
| Rolling buffer | MediaMTX writes the stream to disk, stream copy, **2-second segments** | No transcode at ingest. Segments start on keyframes, so the creator's keyframe interval must be 2 s or less (OBS's own guide uses 2). Our ffmpeg reads those files only, so the `-protocol_whitelist file,pipe` rule holds with no exception. If MediaMTX cannot cut segments that short, the fallback is one loopback-only reader and needs the owner's OK |
| Retention | **10 minutes** of segments per session, then deleted | About 460 MB at 6 Mbps. Enough for the pre-roll, a manual "clip the last 2 minutes" and a judge-chosen recut. The whole stream is not kept unless the owner turns on the recording option in section 9 |
| Audio timeline | Each closed segment: decode audio once to 16 kHz mono, append to a 10-minute ring, one RMS value per second | Same measurement as `signals.audio_rms_db` |
| Signal timeline | One row per second: audio z-score, chat rate z-score, exclamation hits when a transcript exists | `baseline_z` uses a centred window today. Live needs a trailing 5-minute window; the first 60 seconds of a session only warm up the baseline |
| Trigger | Fused score above a threshold for 2 of 3 seconds, then a 45-second refractory period | Weights start from the pipeline's (`chat` 1.0, `audio` 0.7). A manual trigger (`POST .../clip`) skips the threshold |
| Window | Pre-roll 20 s, post-roll 10 s, then snapped to speech and, with the judge, cut to the bucket | The pre-roll audio is transcribed while the post-roll is still arriving |
| Transcript | Candidate windows only, with the local model (`base.en` for the first preview on CPU) | Continuous transcription of the whole stream is a later step: it needs a GPU or a hosted provider (PR #167), and hosted means the Terms and Privacy pages say so |
| Cut and render | Segments joined by stream copy, then `render_clip(preview=True)`: 540x960, captions, facecam layout, hook | 1080p only on export, same as recordings |
| AI rating | The existing judge, one call per candidate, in parallel with the render | A candidate under `JUDGE_FLOOR` is dropped and never shown |
| Delivery | The clip row is written when the preview is stored; the dashboard reads `GET /v1/live/sessions/{id}/events` (server-sent events) and falls back to polling the session | Same progressive pattern as S1 |

### 2.2 Session state machine

| State | Meaning | Leaves when |
|---|---|---|
| `CREATED` | Key issued, credits reserved, nothing received | first frames arrive; or 10 minutes pass (ends as `FAILED`, full refund) |
| `LIVE` | Segments arriving, detector running | publisher drops; a stop condition |
| `RECONNECTING` | Publisher dropped | publisher returns within 120 s with the same key (back to `LIVE`, the baseline is kept, the gap is not billed); or the grace runs out |
| `ENDING` | No new triggers; clips in flight finish | all clips stored or 3 minutes pass |
| `ENDED` | Settled; buffer deleted | final |
| `FAILED` | A system fault ended it | final; refunded |

Stop conditions, any of which moves `LIVE` to `ENDING`:

- a. The creator calls stop.
- b. Twitch sends `stream.offline` and no video arrives for 120 s.
- c. The publisher is gone for longer than the reconnect grace.
- d. The reserved minutes are used up.
- e. The session reaches the maximum length.
- f. The kill switch (`LIVE_CLIPPING=false` or `ACCEPT_JOBS=false`), a suspended account, or a takedown.

A lost Twitch authorization does not stop the session: chat stops, Twitch data is deleted, audio detection continues. The session worker heartbeats like a job; a session with no heartbeat for 5 minutes is failed and refunded by the sweep.

### 2.3 Proposed API (public, the website uses the same calls)

```
GET    /v1/live/twitch/connect           -> {authorize_url}            start OAuth (scope user:read:chat)
GET    /v1/live/twitch/callback          OAuth redirect target
DELETE /v1/live/twitch                   disconnect: revoke token, delete Twitch data
POST   /v1/live/sessions                 {options, max_minutes, rights_confirmed: true}, Idempotency-Key
                                         -> 201 {id, state, ingest: {rtmp_url, srt_url, stream_key}}   key shown once
GET    /v1/live/sessions/{id}            state, minutes received, credits reserved, clips so far
GET    /v1/live/sessions/{id}/events     server-sent events: state, clip.ready, clip.rated, warning
POST   /v1/live/sessions/{id}/clip       {seconds_back}                manual "clip that"
POST   /v1/live/sessions/{id}/stop
GET    /v1/live/sessions                 list
POST   /webhooks/twitch/eventsub         Twitch only, HMAC-verified
```

- Clips are ordinary clip rows (`GET /v1/clips/{id}`, export, feedback, subtitles unchanged) with a live session as their source.
- With the flag off every `/v1/live/*` route answers 404 `not_found`.
- New tables (additive, written by the orchestrator in Stage 2 or later): `live_sessions`, `twitch_links`.

## 3. Latency budget

Latency is measured from **the second the trigger fires** (stream time, as received at our ingest) to **the preview being readable from storage**. The post-roll is inside it: a clip cannot be cut before its last second exists.

| Stage | Under 60 s, CPU (now) | Under 30 s (later) | What it needs |
|---|---|---|---|
| Segment closes and is read | 2 to 3 s | 1 to 1.5 s | 2 s segments now, 1 s later; the creator's keyframe interval sets the floor |
| Trigger confirmation | 1 to 2 s | 1 s | per-second timeline |
| Post-roll | 10 s | 5 s, the clip is extended on export | fixed wait, no hardware helps |
| Cut (stream copy) | under 1 s | under 1 s | disk |
| Transcript of a 30 s window | 5 to 15 s after the post-roll, **estimate** | 1 to 2 s, **estimate** | Now: `base.en` (74 M parameters), CPU int8, pre-roll transcribed during the post-roll. Later: `turbo` (809 M, about 6 GB VRAM) or `small.en` on a GPU, or a hosted provider |
| Preview render 540x960 with captions | 10 to 25 s, **estimate** | 2 to 4 s, **estimate** | Now: libx264 ultrafast on 4 vCPU. Later: NVENC (S5, #99) or the 16-vCPU render worker |
| AI rating | 0 s added (runs beside the render) | 0 s added | one judge call |
| Store and notify | 1 to 2 s | 1 s | local disk or Spaces, server-sent events |
| **Total** | **about 30 to 55 s, unproven** | **about 12 to 16 s, unproven** | |

- The only measured numbers so far are for recordings on the droplet (SPEC section 10 B): 1080p `veryfast` renders took 58 to 132 s per 30-second clip, and `small.en` took about 0.9 s per second of audio with all four cores. `small.en` alone would spend the whole 60 s budget, which is why the first preview uses `base.en`.
- No target is claimed. Stage 2 delivers `scripts/live_bench.py`, which replays a file with `ffmpeg -re` into a local ingest and reports wall and CPU seconds per stage, median and p95. The server numbers need a run on the droplet by the owner.
- A recording job on the same machine uses every core. On one shared droplet a live trigger that lands during a recording job will miss the budget. Live needs its own cores (section 4).

## 4. Costs and limits

Prices are DigitalOcean's public list prices read on 2026-11-18. Per-session loads are **estimates** until Stage 2 measures them.

### 4.1 Per live hour, one session (creator sends 1080p60 at about 6 Mbps, an assumption capped by a setting)

| Resource | Amount | Cost |
|---|---|---|
| Inbound transfer | about 2.6 GiB | $0 ("Inbound transfer to Droplets is free.") |
| Rolling buffer on disk | about 460 MB, constant | none beyond the disk |
| Clips stored (10 previews an hour, estimate) | about 50 MB | inside the Spaces plan ($5 a month for 250 GiB, then $0.02 per GiB) |
| Outbound transfer for previews | about 50 MB | inside the droplet's pool (5,000 GiB; then $0.01 per GiB) |
| CPU, steady | ingest and segment writing without transcode, audio levels: a few percent of one core, estimate | |
| CPU, per highlight | 40 to 60 s of all four vCPUs (transcript and preview render), estimate | 10 highlights an hour is about 10 minutes of the whole machine |
| Memory | Whisper `base.en` plus one ffmpeg render: under 2 GB, estimate (a recording job peaked at 1.1 GB locally) | |
| AI rating | one judge call per candidate | same per-call cost as recordings; capped by clips per hour |
| Full recording, if the option is on | about 2.6 GiB per hour for the retention period | $0.02 per GiB a month beyond the plan |

### 4.2 Machines

| Machine | List price | Concurrent sessions (estimate) | Machine cost per live hour at full use |
|---|---|---|---|
| Current droplet, Basic 4 vCPU / 8 GiB, shared with the API, database and recording jobs | $48.00 a month ($0.07143 an hour) | **1**, and only when no recording job is running | no new spend, but it takes capacity from recordings |
| A second Basic 4 vCPU / 8 GiB for live only | $48.00 a month | 2 | about $0.04 |
| CPU-Optimized 16 vCPU / 32 GiB (the render worker in setup B) | $336.00 a month ($0.50 an hour) | 6 to 8 | about $0.06 to $0.08 |
| GPU Droplet, NVIDIA RTX 4000 Ada, 20 GB VRAM, 8 vCPU, 32 GiB | $0.76 per GPU hour on demand | 15 to 25 | about $0.03 to $0.05; $0.76 when it serves one session |

Droplets are billed per second since 2026-01-01, so a live machine could exist only while sessions run. Starting one takes minutes and is not designed here.

### 4.3 Proposed limits (settings, all changeable)

| Setting | Proposed |
|---|---|
| `LIVE_CLIPPING` | `false` |
| `LIVE_BILLING` | `false` until the owner approves a price; while false only accounts on an allow-list can start a session |
| `LIVE_MAX_SESSIONS` (whole service) | 1 on the current droplet |
| Sessions per account | 1 |
| Session length | 4 hours by default, 8 hours at most |
| Input | H.264 and AAC, up to 1080p60 and 8 Mbps; above that the publish is refused with a clear message |
| Clips per session hour | 20 automatic, plus manual ones |
| No video after create | session fails after 10 minutes, full refund |
| Reconnect grace | 120 s |
| Global live minutes per UTC day | its own cap, separate from `DAILY_MINUTES_CAP` |

### 4.4 Credits: model and a price for the owner to decide

The agent sets no price. The model below follows the ledger rules and is built in Stage 2 with billing switched off.

- a. **Reserve once** at session create: `max_minutes` credits times the price per live minute, key `reserve:live:<session_id>`. 402 `insufficient_credits` if short. The price and the total are shown before the creator confirms.
- b. **Settle once** at the end, key `settle:live:<session_id>`: a `commit` that keeps the minutes actually analysed (rounded up, never more than reserved) and returns the rest in the same row, exactly like `ledger.settle(..., charged=)` for jobs. A second settle is a no-op.
- c. **Refund on every failure path**, each with a test: no video ever arrived; the ingest or the session worker died (heartbeat sweep); the kill switch; account suspended; takedown; the session row could not be created after the reserve. A system fault releases the whole reservation. Minutes inside a reconnect gap, and minutes when the detector was down, are not charged.
- d. The session stops when the reserved minutes are used. Going on means a new session with a new reserve; nothing is added to an existing reservation, so "reserved once" stays true.
- e. No ledger row is ever updated or deleted. With `LIVE_BILLING=false` no ledger rows are written at all.

Price options, for the owner:

| Option | Price | For | Against |
|---|---|---|---|
| A (proposed) | 1 credit per live minute, the same unit as a recording | one rule to explain; a 3-hour stream is 180 credits; the estimated machine cost is $0.04 to $0.08 an hour | a live session holds a machine in real time, a recording does not |
| B | 2 credits per live minute | pays for a dedicated live machine sooner | a nightly streamer runs out of a Starter plan (500 credits) in about 4 hours |
| C | 1 credit per live minute, and the recording of that stream can be clipped afterwards at no further charge | matches "charge once per upload" | needs the full recording kept, which is a storage and retention decision |

## 5. Risks

| Risk | Detail | Mitigation |
|---|---|---|
| Twitch terms | Twitch "may immediately terminate or suspend this Agreement ... for any reason or no reason". It audits hourly token validation and may crawl our service (IV.E) | Documented interfaces only, one scope, hourly validation, the data rules in 1.3. Live video does not depend on Twitch at all, so a revoked key costs chat and metadata, not the product |
| The developer agreement also binds the rest of the product | Once the owner registers a Twitch app, section XI.I and Terms section 10 xi apply to everything we do with Twitch. Link import of Twitch VODs and clips reads Twitch through yt-dlp, which is not a documented interface | **Owner decision** (section 9). Not changed here; it belongs to the ingestion rules |
| Chat privacy | Chatters did not sign up to ClutchClips | Counts only, in memory; no text or names stored; nothing sent to third parties; delete on revoke; privacy page |
| Copyright, music | A live stream often carries music. The clip is the creator's export and their responsibility, but we store and serve it | Existing consent text, takedown flow and repeat-infringer policy (PR #168) apply to live clips. No music detection is built |
| Clipping a channel the user does not own | With creator-sent video this needs the creator's encoder, so a stranger cannot start it. A user could still re-encode someone else's stream into our ingest | `rights_confirmed` on every session, logged (account, Twitch user ID if linked, time, ingest address). When Twitch is linked, the session is tied to that Twitch user ID. Takedown covers sessions |
| Stream key leak | RTMP sends the key in clear | Key per session, hashed at rest, rotates every session, one publisher per key, SRT passphrase or RTMPS recommended |
| Abuse of the ingest port | An open RTMP port invites junk publishes | Publish auth before any byte is recorded, bitrate and resolution caps, per-IP connection limits, global session cap |
| Retention | Buffers hold raw stream video | Buffer deleted at session end and after 10 minutes rolling; clips follow `RETENTION_DAYS`; takedown deletes a session's clips and buffer |
| Cost runaway | A session left running overnight | Reserve bounds the spend; max length; stop on `stream.offline`; daily cap; kill switch |
| Quality | A trigger on loudness alone clips noise | The judge floor still applies; live clips are labelled; the post-stream run on the full recording (option C) gives the ranked set |
| Site copy | The home page says "Clip a Twitch or Kick stream while it's still live" (Coming soon) | Kick is not investigated here. The copy stays "Coming soon" and should say Twitch only until Kick is |

## 6. What the creator does (for the docs page, later)

- a. Connect Twitch (optional; without it there is no chat signal and no auto-stop on stream end).
- b. Start a live session and copy the ingest URL and key.
- c. Add ClutchClips as a second output in the encoder. OBS can send its recording output to a URL, or a free multiple-output plugin can be used, or a restream service can forward to a custom RTMP destination. Stage 2 tests these and writes the exact steps; none is verified yet.
- d. Stream as usual. Clips appear on the dashboard during the stream.

## 7. Stage 2 plan (after the owner's answers)

- a. `clip-api/app/live/`: segment reader, audio ring, trailing-baseline timeline, trigger, clip builder that calls the existing render and judge. Flag `LIVE_CLIPPING=false`; nothing imported by the API or the worker when it is off.
- b. Local ingest: MediaMTX binary run locally, a file pushed with `ffmpeg -re` over RTMP.
- c. `scripts/live_bench.py`: trigger-to-preview latency per stage, wall and CPU, median and p95, on the owner's test footage, run through `heavy.sh`.
- d. Session credits in `app/live/credits.py` with tests for a to e in 4.4, billing off.
- e. No production wiring, no migration, no Twitch calls (there is no app yet): chat is replayed from a synthetic per-second series.

## 8. What the owner must create (nothing is registered by an agent)

- a. A Twitch developer application at `https://dev.twitch.tv/console`: confidential client, redirect URL `https://api.clutchclips.io/v1/live/twitch/callback`. This means accepting the Twitch Developer Services Agreement.
- b. Environment variables on the server: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TWITCH_EVENTSUB_SECRET`, `LIVE_TOKEN_KEY` (encrypts stored tokens).
- c. A DNS name for ingest (for example `live.clutchclips.io`) and open ports for RTMP (1935/tcp) and SRT (one UDP port).
- d. Privacy and Terms updates: Twitch data collected, chat handling, retention, live recording.
- e. If chosen: the live machine (section 4.2).

## 9. Owner decisions before Stage 2 goes further

1. Accept the verdict: creator-sent video only, Twitch for status, metadata and chat.
2. Register the Twitch application (8a), or run Stage 2 and the first release without Twitch signals.
3. Decide what the developer agreement means for Twitch link import (risk row 2): keep it, ask Twitch for written permission, or drop Twitch links.
4. Price per live minute: A, B, C or another. Billing stays off until then.
5. Where live runs: the shared droplet (1 session, latency not guaranteed), a second small droplet, the 16-vCPU render worker, or a GPU droplet.
6. Keep the full recording of a live session for a post-stream clip run, and for how long.
7. Whether the first preview may use a hosted transcription provider (ties to PR #167 and the Terms and Privacy pages).
8. The limits in 4.3.

## 10. Sources (all read 2026-11-18)

| Source | URL | Page date |
|---|---|---|
| Twitch Developer Services Agreement | https://legal.twitch.com/en/legal/developer-agreement/ | last modified 12/04/2024 |
| Twitch Terms of Service | https://legal.twitch.com/en/legal/terms-of-service/ | last modified 08/12/2026 |
| EventSub: stream online and offline | https://dev.twitch.tv/docs/eventsub/reference/stream | not dated |
| EventSub: channel update | https://dev.twitch.tv/docs/eventsub/reference/channel | not dated |
| EventSub: chat | https://dev.twitch.tv/docs/eventsub/reference/chat | not dated |
| EventSub: user authorization revoke | https://dev.twitch.tv/docs/eventsub/reference/user | not dated |
| EventSub subscription limits | https://dev.twitch.tv/docs/eventsub/manage-subscriptions | not dated |
| EventSub WebSockets | https://dev.twitch.tv/docs/eventsub/handling-websocket-events | not dated |
| Helix Get Streams, Get Stream Key | https://dev.twitch.tv/docs/api/reference/streams | not dated |
| Helix Get Channel Information | https://dev.twitch.tv/docs/api/reference/channels | not dated |
| Scopes | https://dev.twitch.tv/docs/authentication/scopes/ | not dated |
| Validating and refreshing tokens | https://dev.twitch.tv/docs/authentication/validate-tokens and /refresh-tokens | not dated |
| API rate limits | https://dev.twitch.tv/docs/api/guide | not dated |
| Chat overview | https://dev.twitch.tv/docs/chat/ | not dated |
| Embedding Twitch | https://dev.twitch.tv/docs/embed/ | not dated |
| Video broadcast (ingest URL format) | https://dev.twitch.tv/docs/video-broadcast/ | not dated |
| DigitalOcean Droplet pricing | https://www.digitalocean.com/pricing/droplets | read 2026-11-18 |
| DigitalOcean GPU Droplet pricing | https://www.digitalocean.com/pricing/gpu-droplets | read 2026-11-18 |
| DigitalOcean Spaces pricing | https://www.digitalocean.com/pricing/spaces-object-storage | read 2026-11-18 |
| DigitalOcean bandwidth billing | https://docs.digitalocean.com/platform/billing/bandwidth/ | read 2026-11-18 |
| MediaMTX (features, license, record, authentication, hooks) | https://github.com/bluenviron/mediamtx and https://mediamtx.org/docs/features/record | read 2026-11-18 |
| nginx-rtmp-module license | https://github.com/arut/nginx-rtmp-module | read 2026-11-18 |
| Whisper model sizes | https://github.com/openai/whisper | read 2026-11-18 |
| OBS advanced recording guide (keyframe interval 2) | https://obsproject.com/kb/advanced-recording-settings-guide | 2023-11-30 |

Not found or not readable, so not relied on: Twitch's broadcasting guidelines help page (bitrate limits), an official OBS page on a second stream output, and any Kick developer terms.
