# Swarm contracts

Shared interfaces for the parity swarm (see `docs/PARITY.md`). Agents build against these, not against each other's branches. A change to anything here goes through the orchestrator first.

## Rules for every agent

- Work only in your own worktree and branch. Open a PR into `staging`. Never merge, never push to `staging` or `main`, never deploy, never touch the droplet or any env file.
- Edit only the files you own (table below). If you need a change in someone else's file, say so in your PR under "Wiring needed" and leave it to the orchestrator.
- No paid services, signups or keys. Anything that needs one is built behind a setting with a working local fallback, and listed in your PR under "Keys the owner must add".
- Money paths (credits, pricing, billing, plan limits, anything that changes what a job costs) are never changed. If parity needs one, write it up in the PR and stop there.
- Do not write migrations. The schema below is already in revision 0004. If you need more, ask the orchestrator.
- Every PR: tests for the new behaviour, the full suite passing, and the PARITY.md rows you changed updated. A feature is not "done" in PARITY.md until agent H has recorded three ticks.
- Never copy WayinVideo's text, images, template art, logo or UI. Same function, our own look. Where their behaviour is not documented, write down what is known and ask; do not guess.
- Python: `"/Users/salaarkhan/Desktop/GTA Clipping Pipeline/clip-api/.venv/bin/python" -m pytest -q` from your worktree's `clip-api/`, with `PATH=/opt/homebrew/opt/ffmpeg-full/bin:$PATH`. The full suite takes about 6 minutes and uses every core: run targeted tests while you work and the full suite once before the PR.

## File ownership

| Agent | Owns | Must not edit |
|---|---|---|
| A engine | `app/pipeline/__init__.py`, `signals.py`, `windows.py`, `variety.py`, `stt.py`, `transcribe.py`, new `app/pipeline/moments.py`, `app/ai.py`, `ClipOptions` and the clip and find routes in `app/routes_media.py`, `app/routes_tools.py` (find) | render, captions, layouts, web |
| B render | `app/pipeline/render.py`, `captions.py`, `facecam.py`, `edit.py`, new `app/pipeline/layouts.py`, `thumbs.py`, `app/render_options.py`, new `app/routes_export.py`, `app/pipeline/tools.py` (reframe, captions tools) | `app/pipeline/__init__.py`, web |
| C templates | `app/templates.py`, new `app/routes_templates.py`, `clip-api/templates/` (data and our own preview assets) | pipeline, render, web |
| D web | `clip-api/web-src/**`, `clip-api/web/**` | everything under `app/` |
| E ingestion | new `app/ingest/**`, new `app/routes_ingest.py` | pipeline, render |
| F language | new `app/languages.py`, new `app/routes_text.py` (transcripts, summaries, translation), new `app/pipeline/translate.py` | pipeline selection, render |
| G agent tools | new `clip-api/mcp/**`, `clip-api/skill/**` | `app/` |
| H QA | `clip-api/eval/**`, new `clip-api/tests/parity/**`, `docs/PARITY.md` verification columns | product code |
| Orchestrator | `app/models.py`, `app/migrations/**`, `app/main.py`, `app/worker.py`, `app/config.py`, `docs/CONTRACTS.md`, `CLAUDE.md`, `SPEC.md` | – |

`app/worker.py`, `app/main.py`, `app/config.py` and `app/models.py` are wired by the orchestrator from each PR's "Wiring needed" list.

## Engine → renderer

A calls B; B never imports from `app/pipeline/__init__.py`.

```python
# app/pipeline/layouts.py (B)
LAYOUTS = ("auto", "full", "fit", "split2", "trio", "grid4", "pip", "ots", "screen_first", "gameplay_a", "gameplay_b")
ALLOWED = {"16:9": (...), "9:16": (...), "1:1": (...), "4:5": (...)}     # per PARITY.md section 1
def plan_layout(info, frames, requested: str, aspect: str) -> LayoutPlan   # decides the scene type and the boxes
#   scene types: "gameplay_cam" | "camera" | "gameplay". People are never blurred or cropped out.

# app/pipeline/render.py (B): signature is stable; new arguments are keyword-only with defaults
render_clip(src, start, end, out, *, src_w, src_h, vertical, zoom, chat, words, font, layout, facecam, style, aspect,
            max_side, deadline, segments, punch, has_audio, hook, flash, loudness, plan: LayoutPlan | None = None,
            resolution: str | None = None, preview: bool = False)
```

A's side, in `app/pipeline/moments.py`:

```python
@dataclass
class Moment:           # one candidate clip, before rendering
    start: float; end: float; score: float            # seconds; score 0-100 once judged
    kind: str | None                                  # funny | argument | reaction | clutch | fail | story
    why: str | None; peak: float | None
    signals: dict; features: dict; meta: dict | None
BUCKETS = {"0-30": (0, 30), "0-90": (0, 90), "30-60": (30, 60), "60-90": (60, 90), "90-180": (90, 180), "180-300": (180, 300)}
```

## API (our names; the values and allowed sets are Wayin's)

Owner's decisions (2026-11-16, PARITY.md "Decisions"):
- Our own names, with the mapping to Wayin's options published in the API docs.
- Defaults become Wayin's: `render` `none`, captions off, reframe off, hook off, `resolution` `480`. This is one change, made in a single PR by the engine and render agents together with the dashboard, which must send every choice explicitly from then on. Every existing field stays accepted; nothing is removed.
- Every clip returns `rank_index` (from 0, by virality score) and `timeline_index` (from 1, by position in the video). The existing `rank` and `index` fields stay as aliases for compatibility.
- Enterprise-only switches are not built. Paid services are researched and priced, never integrated without approval.

| Where | Field | Values | Default | Owner |
|---|---|---|---|---|
| `POST /v1/clips` options | `duration` | `0-30`, `0-90`, `30-60`, `60-90`, `90-180`, `180-300` | none (falls back to `clip_length`) | A |
| | `limit` | positive integer or null (all) | null when `duration` is sent | A |
| | `range` | `{start, end}` seconds or null | null | A |
| | `source_lang`, `target_lang` | codes in `app/languages.py` or null | null | F (A reads) |
| | `project_name` | text, max 120 | null | A |
| | `render` | `none`, `preview`, `full` | `none` (after the defaults PR; `full` until then) | B |
| | `resolution` | `480`, `720`, `1080`, `2k`, `4k` | `480` (after the defaults PR; `1080` until then) | B |
| | `caption_style` | style ids in `app/render_options.py` | `pop` | B |
| | `caption_display` | `original`, `translation`, `both` | `original` | F |
| | `hook_style` | the 13 script styles | `serious` | B |
| | `hook_position` | `beginning`, `end` | `beginning` | B |
| | `layout` | `LAYOUTS`, checked against `ALLOWED[aspect]` | `auto` | B |
| `POST /v1/clips/export` | `job_id`, `clips` (ids or null = all), the render options above, `hook_keywords`, `hook_duration_ms` | | | B (charging: money, owner) |
| Clip object | `rank_index` (0 = best), `timeline_index` (1 = earliest), `start_ms`, `end_ms`, `virality_score` (0–100), `scores` (five dimensions), `preview_url`, `export_url`, `kind`, `why` | added next to today's fields | | A, B |
| | `prompt` | text, max 300: what moments to find; goes to the judge with the template's focus | null | A |
| | `caption_style` | adds `impact` (see "Caption style: impact") | `impact` | B |
| | `caption_position` | `auto`, `seam`, `lower`, `center` | `auto` (seam in split layouts, lower third otherwise) | B |
| | `caption_accent` | `#RRGGBB` or null (the style's own) | null | B |
| | `caption_emoji` | bool | false | B |
| Clip object | `display_score` (calibrated per job, see "Score calibration"), next to the raw `score` and `scores` | | | A |
| `GET /v1/options` | every option `POST /v1/clips` accepts, with values, default and limits, read from the request model. The website builds its form from it: a control appears only once the API accepts the option | | | orchestrator (`app/routes_meta.py`) |
| `GET /v1/templates` | `?game=` filter; `?kind=preset` for the game-type presets; each template as below | | | C |
| `GET /v1/templates/{id}/poster` | the template's poster image; `preview.poster` is this path | | | C |
| `GET`, `POST /v1/templates/custom`; `PATCH`, `DELETE /v1/templates/custom/{id}` | an account's saved looks: `name` (max 80) and `options` (validated as clip options; never `template`, `max_clips`, `limit` or anything that sets a price) | | | C |
| `POST /v1/transcripts`, `POST /v1/summaries` | `upload_id`, `source_lang`, `target_lang` | | | F |
| `POST /v1/imports` | `url`, `consent: true` (required) | | | E |
| `POST /v1/clips/from-url` | `url`, `consent: true`, `options` (as `POST /v1/clips`), `webhook_url`; see "URL clipping" | | | E |
| `POST /v1/imports/preview` | `url`, `options` (optional); answer adds `estimate`; see "URL clipping" | | | E |

## Template format (C)

```python
{"id": "gta5-chase-gameplay-a", "name": "...", "game": "gta5", "genre": "racing",
 "layout": "gameplay_a", "aspect": "9:16", "caption_style": "...", "duration": "0-90",
 "hook": {"enabled": True, "style": "excited", "position": "beginning", "duration_ms": 2500},
 "options": {...},                       # other Clip Maker options it sets
 "weights": {...}, "transcript_bonus": 0.2, "judge_focus": "...",        # server-side tuning, never client-sent
 "preview": {"video": "templates/<id>/preview.mp4", "poster": "templates/<id>/poster.jpg"}}   # our own footage only
GAMES = ("lol", "gta5", "wow", "ow2", "minecraft", "apex", "valorant", "fortnite", "dota2", "rust", "cs2", "other")
```

A template never changes what a job costs: the client sends the template's options (see PR #92).

## Game-type presets (C), from the owner's screenshots

Presets are templates with `kind: "preset"` and no game: a layout, panel sizes and the `impact` caption style. Names are ours; the set matches what the screenshots show.

| Preset id | Layout | Top | Bottom |
|---|---|---|---|
| `racing-gameplay` | split | gameplay 60% | camera 40% |
| `racing-camera-top` | split | camera 33% | gameplay 67% |
| `shooter-gameplay` | full | gameplay | – |
| `fighting-screen-first` | split | gameplay 57% | camera 43% |
| `moba-screen-first` | split | gameplay 63% | camera 37% |
| `moba-full` | full | gameplay | – |
| `moba-gameplay` | split | gameplay 66% | camera 34% |

Panel sizes are a public template field, `panels: {"camera": "top" | "bottom" | null, "split_ratio": 0.25 to 0.75}` (the top panel's share of the height). They are not in the template's `options` until the renderer accepts `camera` and `split_ratio` as clip options (B); the client copies them into the request only when `GET /v1/options` lists both. The camera panel is always cropped tight on the person.

## Caption style: impact (B), from the owner's screenshots

- One or two words at a time; a third only when all three are short (12 characters in total).
- Upper case, our own heavy font (bundled, open licence), size about 9% of the frame height, dark outline about 8% of the font size, soft shadow.
- One keyword per caption in the accent colour: the longest word that is not a stop word. Default accent: our lime.
- Position `auto`: centred on the line between the panels in split layouts, in the lower third (about 70% down) otherwise.
- It is the default `caption_style`. The five existing styles stay.

## Score calibration (A)

`display_score` is computed per job when clips are read, never stored. With raw AI scores `s` (0 to 100) for the job's rated clips, `hi = max(s)`, `lo = min(s)`:

- `top = 90 + 9 * clamp((hi - 40) / 50, 0, 1)`: the best clip shows 90 to 99, higher when its raw score is higher.
- `floor = max(55, top - 40)`.
- `display = round(floor + (top - floor) * (s - lo) / (hi - lo))`; one rated clip, or all equal, shows `top`.
- Order never changes: sorting by `display_score` gives the same order as sorting by the raw score (ties stay ties). Clips the AI did not rate have no `display_score`.
- `score` and `scores` stay raw. The website shows `display_score` as "N /100" and the raw numbers in the tooltip.

## URL clipping

The customer pastes a link, sees what it is and what it costs, and clicks "Generate clips". The server imports the video and runs the clip job on it; the page makes no other call until the clips are ready. Code: `app/url_clips.py`, `app/routes_ingest.py`. This contract is stable: fields may be added, none are renamed or removed.

### What the page calls

| Step | Call | When |
|---|---|---|
| 1 | `GET /v1/imports/sources` | Once on load. `enabled` false: hide the link box and offer upload. `consent` is the exact checkbox text to show. |
| 2 | `POST /v1/imports/preview {url, options?}` | On paste (debounce about 500 ms). Show `title`, `thumbnail_url`, `duration_sec`, `channel` and `estimate`. Again when the clip options change: the answer is cached server-side for 5 minutes, so a repeat makes no request to the site. |
| 3 | `POST /v1/clips/from-url {url, consent: true, options}` | On "Generate clips". Send an `Idempotency-Key` header, one new value per click of a confirmed preview (for example a UUID). |
| 4 | `GET /v1/jobs/{job_id}` | Every 2 seconds until `status` is `SUCCEEDED`, `FAILED` or `CANCELED`. |
| 5 | `POST /v1/jobs/{job_id}/cancel` | The Cancel button, at any stage. |
| 6 | `GET /v1/credits` | After the job ends, to refresh the balance. |

All calls need `Authorization: Bearer <session token or API key>`. Every error is `{"error": {"code", "message"}}`; `message` is written for the customer, so show it as given.

### 1. Preview with price: `POST /v1/imports/preview`

Request. `options` is optional and takes exactly what `options` of `POST /v1/clips` takes. Send the same `options` here and to `POST /v1/clips/from-url`, so the price shown is the price reserved.

**Default: automatic discovery** (owner, 2026-11-18). When `options` names none of `max_clips`, `limit` or `duration`, both calls use `duration: "0-90"` with `limit: null`: every moment that passes, 0 to 90 seconds each, at most 50, best first. There is no 3-clip limit. For a first run the price is the same either way (one credit per started minute). Send `max_clips`, `limit` or `duration` to choose a count or a length yourself.

```json
{"url": "https://www.twitch.tv/videos/2301234567", "options": {"max_clips": 5, "duration": "30-60"}}
```

Response 200, a supported link:

```json
{"url": "https://www.twitch.tv/videos/2301234567", "platform": "twitch", "supported": true,
 "title": "Ranked grind: part 3", "channel": "SomeStreamer", "duration_sec": 7260.5,
 "thumbnail_url": "https://static-cdn.jtvnw.net/...jpg", "kind": "video", "refusal": null,
 "estimate": {"credits": 122, "basis": "source_minutes", "duration_sec": 7260.5, "balance": 300, "enough": true,
              "note": "One credit per started minute of the video (121.0 minutes). Never more than this; less if the video turns out shorter."}}
```

Response 200, a refused link: `supported` false, `estimate` null, and `refusal` `{code, message}` saying why and what to do instead (for example `live_stream`, `video_too_long`, `private_address`, `unsupported_source`, `login_required`). Show the message and the upload button.

`estimate`:

| Field | Meaning |
|---|---|
| `credits` | What "Generate clips" reserves. The job is never charged more. |
| `basis` | `source_minutes`: one credit per started minute of the video. `rendered`: the account already has this video and it was clipped before, so the job is charged for the seconds it renders, at most `credits`. |
| `duration_sec` | The length it is priced on. |
| `balance`, `enough` | The account's balance now, and whether it covers `credits`. When `enough` is false, disable "Generate clips" and link to buying credits. |
| `note` | One line to show under the price. |

`estimate` is null when the link is refused, or when its length cannot be known before a download (direct links, Google Drive and Dropbox). For those, use the two-step flow: `POST /v1/imports`, then `POST /v1/clips` on the upload.

Errors: `401`; `403 email_not_verified`; `503 imports_disabled`; `429 rate_limited` (10 lookups a minute per account; cached answers are not counted); `422 validation_error` (a bad body or bad options); `422 bad_range`, `range_too_short`, `too_short_for_duration` (the options do not fit this video).

### 2. Start: `POST /v1/clips/from-url`

Request. `consent` must be the JSON value `true`, sent only after the customer ticks the consent box. `options` and `webhook_url` are those of `POST /v1/clips`. No other fields are accepted.

```http
POST /v1/clips/from-url
Idempotency-Key: 6f1c2a0e-6c2b-4a55-9a51-1d2a4c1f9e01

{"url": "https://www.twitch.tv/videos/2301234567", "consent": true,
 "options": {"max_clips": 5, "duration": "30-60", "project_name": "Ranked grind"}}
```

Response `202`: the clip job, as `GET /v1/jobs/{job_id}` returns it, with the `import` part. The credits are reserved (taken from the balance) at this point, before anything is imported.

```json
{"job_id": "job_9a1b...", "tool": "clips", "status": "WAITING", "stage": "importing", "progress": 0,
 "upload_id": "upl_42cd...", "credits_reserved": 122, "credits_charged": 0, "error": null,
 "options": {"...": "..."}, "created_at": "2026-11-18T10:00:00Z", "finished_at": null, "expires_at": "...",
 "import": {"import_id": "imp_77e0...", "status": "QUEUED", "stage": null, "progress": 0,
            "url": "https://www.twitch.tv/videos/2301234567", "platform": "twitch", "reused": false,
            "upload_id": null, "error": null}}
```

- `200` instead of `202`: the same link with the same options is already waiting or running for this account (a double click). That job is returned and nothing new is reserved.
- A repeated `Idempotency-Key` returns the job the first request started, whatever the body.
- When the account already has this video stored, nothing is imported: the job starts as `QUEUED`, and `import` is `{"import_id": null, "status": "SUCCEEDED", "stage": "done", "progress": 100, "reused": true, "upload_id": "upl_...", ...}`.

Errors (nothing is reserved, imported or logged):

| Status | Code | When |
|---|---|---|
| 401 | `unauthorized` | No or bad login. |
| 402 | `insufficient_credits` | The balance does not cover the price. The message gives both numbers. |
| 403 | `email_not_verified` | The email address is not confirmed. |
| 422 | `consent_required` | `consent` is not `true`. |
| 422 | `validation_error` | A bad body or bad options. |
| 422 | the preview's refusal codes | The link is refused: `unsupported_source`, `unsupported_link`, `https_only`, `credentials_in_url`, `bad_url`, `private_address`, `unreachable`, `live_stream`, `video_too_long`, `video_too_short`, `login_required`, `drm_protected`, `geo_blocked`, `not_found`, `source_refused`, `source_failed`, `preview_timeout`, `no_format`, `file_too_large`. |
| 422 | `duration_unknown` | The link's length cannot be read before a download. Use `POST /v1/imports`, then `POST /v1/clips`. |
| 422 | `bad_range`, `range_too_short`, `too_short_for_duration`, `bad_webhook_url` | The options do not fit the video, or the webhook URL is not public https. |
| 429 | `too_many_jobs` | Two jobs are already waiting or running. A link job counts once. |
| 429 | `too_many_imports`, `rate_limited` | Too many imports at once, or too many lookups a minute. |
| 503 | `imports_disabled`, `paused`, `capacity` | Link import is switched off, new jobs are paused, or the day's capacity is used up. |

### 3. Follow: `GET /v1/jobs/{job_id}`

| `status` | `stage` | Show |
|---|---|---|
| `WAITING` | `importing` | "Importing": `import.progress` (0 to 100) as the bar; `import.stage` is null (waiting for a worker), `starting`, `importing` (downloading), `checking` or `storing`. |
| `QUEUED` | null | "Waiting for a worker". `import.status` is `SUCCEEDED`, and `upload_id` is the stored video. |
| `RUNNING` | the clip job's stages (`downloading`, `transcribing`, ... `uploading`) | `progress` (0 to 100) as the bar. `clips` fill in as each clip is ready. |
| `SUCCEEDED` | `done` | The clips. `credits_charged` is what was charged: at most `credits_reserved`, less when the video was shorter than its metadata said. |
| `FAILED` | null | `error.message`. When the import failed (`import.status` `FAILED`, for example `source_refused`, `login_required`, `video_too_long`, `import_timeout`), the message says to upload the file instead. Every failure is refunded in full: `credits_charged` is 0. |
| `CANCELED` | null | "Cancelled". Refunded in full. |

`import` is present on every job started from a link, also after it finishes. `import.error` is the import's own error; the job's `error` carries the same code.

### 4. Cancel: `POST /v1/jobs/{job_id}/cancel`

Works at every stage and returns the job. `WAITING` or `QUEUED`: cancelled and refunded at once (`status` `CANCELED`), and the import is stopped. `RUNNING`: `status` stays `RUNNING` until the worker stops at its next step (seconds), then `CANCELED` and refunded. Poll as before.

### Money, for the record (owner-approved rules, `CLAUDE.md`)

- One reservation per job (`reserve:<job_id>`), made by `POST /v1/clips/from-url` before the import, and one settle (`settle:<job_id>`): a charge of at most the reservation, or a full refund. The import itself costs nothing and holds nothing.
- The price is `price_clips` in `app/routes_media.py`, the function behind `POST /v1/clips` and `POST /v1/clips/quote`, on the metadata's length (or the stored upload's, when the account has the video).
- When the import has stored the video, the job is priced again on the real length: charged that if it is less, never more than the reservation.
- Failed, refused, timed-out or cancelled imports, a crash at any point (the worker's sweeps finish or refund the job), a cancel, a takedown, and a failed clip job all end in a full refund.

## Schema: revision 0005 (shipped by the orchestrator, additive)

| Table | Columns |
|---|---|
| `custom_templates` (new) | `id`, `account_id`, `name` text(80), `options` JSON, `created_at`, `updated_at`, `deleted_at` null |

## Schema: revision 0004 (shipped by the orchestrator, additive)

| Table | Columns |
|---|---|
| `jobs` | `name` text(120) null |
| `uploads` | `source_url` text(1000) null, `source_platform` text(40) null, `language` text(8) null |
| `clips` | `rank` int null, `kind` text(16) null, `preview_key` text(400) null, `export_key` text(400) null, `export_res` text(8) null, `edit` JSON null |
| `exports` (new) | `id`, `clip_id`, `account_id`, `resolution`, `options` JSON, `status`, `storage_key`, `created_at` |
| `import_log` (new) | `id`, `account_id`, `source_url`, `platform`, `consent` bool, `created_at` |

## Waves 2 and 3 (owner, 2026-11-16: "add these")

Everything Wayin's gaming product has that we do not. Same rules as above, plus:
- **Paid services stay off.** Each feature that could use one is built on a provider interface with a local or open-source implementation as the default, and the paid adapter (if written at all) is behind a setting that is off. Nothing is signed up for, and no key is required for the feature to work.
- **Money paths stay open for the owner:** anything that charges credits (re-export, Bulk Edit, montage renders, translation or summaries if they cost per use) follows the approved rule (reserve the worst case, charge the seconds rendered) and waits for the owner's merge. No feature is gated by plan.
- **Platform apps are the owner's:** publishing needs developer apps at each platform. The code reads client ids and secrets from settings and shows a platform only when it is configured.
- Ingestion keeps CLAUDE.md's rule: public, non-DRM content only; no logins, cookies, proxies, impersonation or block evasion; consent and a log per import; fail cleanly with "upload the file instead"; a takedown flow.

| Wave | Agent | Scope | Owns | Notes |
|---|---|---|---|---|
| 2 | E | Link import (Twitch and Kick first, YouTube best effort, direct links), Google Drive and Dropbox share links, bulk import, consent, import log, takedown | `app/ingest/**`, `app/routes_ingest.py` | `POST /v1/imports {url, consent: true}`; `POST /v1/imports/bulk`; `POST /v1/takedowns` |
| 2 | B3 | `render: none / preview / full`; `POST /v1/clips/export` (re-export with new options); layouts trio, grid 4, over-the-shoulder; layout chosen per moment; 13 hook styles and hook position; more caption styles; limiter headroom | render files, `app/routes_export.py` | export charging is a money PR |
| 2 | F | Multilingual transcription (local multilingual Whisper), translation and bilingual captions, `POST /v1/transcripts` (with speakers when a local method allows), `POST /v1/summaries` | `app/languages.py`, `app/routes_text.py`, `app/pipeline/translate.py` | translation and summaries through the AI provider already in use cost per use: price shown first, money PR |
| 2 | D3 | Editor: trim, transcript-based cutting, timeline, caption line editing; saves to `clips.edit`; re-render through the export route | `web-src/**`, `web/**` | re-render charging is B3's money PR |
| 3 | B4 + D4 | Brand kit: logo, intro, outro, fonts (upload, store, apply at render) | render files; web | needs revision 0007 (`brand_assets`) from the orchestrator |
| 3 | A3 + D4 | Bulk Edit; Create Montage (prompt-driven highlight reel from one or several videos); fifth score dimension; edge and spacing fixes from the Zias benchmark | engine files; web | montage and bulk renders are money PRs |
| 3 | E2 | Scheduler and publishing (connect accounts, post now or later, calendar, bulk schedule); live clipping | `app/publish/**`, `app/routes_publish.py` | needs revision 0007 (`social_accounts`, `scheduled_posts`); platforms appear only when the owner has configured their app |
| 3 | B5 | AI extras with local defaults: thumbnails (frame plus title text), upscaling (ffmpeg scaling and sharpening), B-roll and music from the user's own uploads, hook voice with an open-source voice if its licence allows | render files | generated thumbnails, stock or generated B-roll, AI upscalers, a music library and hosted voices are paid: priced in the research document, off until approved |
| 3 | G | MCP server and the agent skill | `clip-api/mcp/**`, `clip-api/skill/**` | |
| last | orchestrator | The single defaults PR (render, captions, reframe and hook off, 480p), with the dashboard sending every choice | `app/main.py`, `app/worker.py`, `app/config.py` | after B3 and D3 |

## Merge order

1. Done: #111, #112, #113 (this file, revision 0004), #115 (templates, C), #116 (app shell, D).
2. Open: B (layouts and render options), then the worker wiring for B's and A's options; #117 (A: buckets, limit, range) waits for the owner's answers on what those options cost.
3. Wave 1b, from the screenshots: A2 (prompt, score calibration), B2 (`impact` captions), C2 (presets, posters, custom templates), D2 (job form, pre-editing, results grid).
4. Wave 2: F, E, G. H gates every merge once Wayin clips exist to compare with.
Money PRs stay open for the owner.
