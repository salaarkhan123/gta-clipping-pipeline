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
- One keyword per caption in the accent colour. Default accent: our lime. The keyword is (2026-11-18, captions agent) the first number, else the first name (capitalised inside a sentence in the transcript), else the first game term (`captions.GAME_TERMS` plus the template game's own), else the first word said with "!", else the longest word that is not a stop word. A masked swear never is.
- The word being said is marked (2026-11-18): from its start it grows from 92% to 108% of the line's size over 90 ms; words of the caption not said yet are see-through, said ones solid. A caption appears at its first word's start and stays at most 0.3 s after its last word, never into the next caption.
- Position `auto`: centred on the line between the panels in split layouts, in the lower third (about 70% down) otherwise.
- It is the default `caption_style`. The five existing styles stay.

## Thumbnails (U7)

`thumb_url` on every clip (job, project, library and clip responses; a signed link like `video_url`) is the clip's thumbnail: a JPEG with the clip's own shape and layout, 720 px on its short side (never above the source), about 70–150 KB. `null` only when no frame could be drawn. Made by `app/pipeline/thumbs.py`, free, no AI:

- The frame: the keyframes inside the clip (about one every 2 s) are scored on the streamer's face (whole in the camera, how far from their resting face), action, loudness, sharpness and nearness to the judge's peak. Frames that are standby (a "be right back", "starting soon" or intro screen, an empty chair: the picture frozen between its neighbouring keyframes with no face in the camera box, or with nobody talking), dark, flat, blurred, a menu or results card (or next to one), a transition, on a cut or in removed dead air lose to any frame that is none of these.
- The text: the clip's `hook`, else its `title` (swears masked when `censor` is on), upper case in Anton, the keyword in `caption_accent` (default lime), white with a dark outline and shadow. As large as fits (capitals 10% of the short side, down to 5.5%), wrapped to at most three balanced lines, cut short with "…" rather than overflowing. Inside 6% side margins and the safe rows (13%–87% of the height in 9:16, the 3:4 crop profile grids show; 7%–93% otherwise). On the line between stacked panels when there is one, else the upper third, then the lower third; never on the person's head or an inset camera. Text in a script our fonts lack (Anton, then DejaVu Sans Bold: CJK, Devanagari and Thai for now) gives the frame alone.
- Option `thumbnail_text` (render options, every tool, listed by `GET /v1/options`; default `true`): `false` gives the frame alone. It is independent of `hook_overlay`, which is only the hook burned into the video.
- When the title arrives after the clip (the find tool, or a clip the judge could not rate), the worker sets it on the same frame then. The AI is always shown the frame without text.
- The frame without text is stored with the clip (`clips/<job>/<clip>.frame.jpg`, its key in `features.thumbnail.frame_key`) and deleted with it (expiry, lost jobs, takedown). `PATCH /v1/clips/{id}` takes `title` and/or `hook` (max 48 characters, one line, at most six words: the AI's own rules). When the words the thumbnail carries change, it is drawn again on that frame inside the request (about 0.1 s, no video read, free) and stored over the same key, so `thumb_url` links already on a page show the new picture (a browser may need a reload). A hook burned into the video does not change. Clips made before frames were kept keep their thumbnail.
- `features.thumbnail` records the choice: `at` (source second), `frames` looked at, `score`, `face`, `failed` (checks the frame failed, when every frame failed some), `text` (whether text was drawn), `standby` (the share of the clip's keyframes that looked like standby, 0 to 1), `frame_key` and `canvas` (where text may go, so the text can be set again later).

### Premium thumbnails (#140, paid, behind `PREMIUM_THUMBNAILS`)

- `GET /v1/clips/{id}/thumbnails`: `{selected, thumbnails: [{id ("original" or thb_…), kind, style, url, text, show_text, editable, selected}], pending: [job ids], premium: null | {credits, styles: [{id, name}], instruction_max, consent, note}}`. Free.
- `POST /v1/clips/{id}/thumbnails/{thumb_id}/select`: the clip's `thumb_url` shows that one (`clips.thumb_chosen_key`); `original` goes back to `thumb_key`, which the job made and `PATCH /v1/clips/{id}` redraws. Free.
- `PATCH /v1/clips/{id}/thumbnails/{thumb_id}` `{text?, show_text?}`: that thumbnail's own words, redrawn on its picture without text by `thumbs.write_thumbnail` into a new file. Free. For `original` the new picture is a copy; the job's `thumb_key` keeps following the title and hook.
- `POST /v1/clips/{id}/thumbnails/premium/quote` `{style, instruction?}`: `{credits_reserved, credits, likeness_consent_required, consent, note}`. Reserves nothing.
- `POST /v1/clips/{id}/thumbnails/premium` `{style, instruction?, confirm: true, credits?, likeness_consent}` with optional `Idempotency-Key`: a job `thm_…` (tool `premium_thumbnail`) to poll. 422 `confirm_required`, `likeness_consent_required`, `instruction_not_allowed`, `unknown_style`; 409 `price_changed`, `no_clean_frame`; 402; 404 `premium_thumbnails_off`. An identical request while one is queued or running returns that job.
- The model never draws text; our renderer draws the hook on the result. A result is never chosen for the user.
- Schema revision 0009 (additive, after #158's 0008): `clips.thumb_id`, `clips.thumb_chosen_key`; tables `clip_thumbnails` and `likeness_consents` (append-only). The frame comes from `features.thumbnail.frame_key`.
## Captions and on-screen text v1 (captions agent, 2026-11-18)

Owner: the captions agent owns `app/pipeline/captions.py`, `render.text_track` (the ASS file a clip burns in), the new `app/pipeline/placement.py` and `app/pipeline/copy_check.py`, and `scripts/caption_checks.py`. The reframing agent owns the layout geometry and writes "Reframe boxes v1" (`layouts.reframe_boxes`), which placement only reads.

Inputs (agreed with U1/U2 and the reframing agent):
- Words: `(start, end, text)`, clip-relative seconds after cuts (`edit.remap_words`), the caption model's own text only (#139), sorted by start, `end > start`; back-to-back words may touch. There is no per-word confidence.
- Standby: `features.standby_spans` (`[[start, end], ...]` source seconds) when U2 provides it. Without it the word gaps decide (below).
- Boxes: `reframe_boxes(...)["keep_out"]`, canvas `[x0, y0, x1, y1]` px, static for the clip. In a two-panel layout the camera panel is not a keep-out box (captions sit on the seam); the head inside it is.

Checks (`scripts/caption_checks.py`, run on the owner's six eval videos with the hand-labelled boxes in `scripts/caption_eval_boxes.json`; every number is measured on the ASS file `render.text_track` writes, for 9:16 auto and the 16:9 original frame):

| Number | Definition | Limit |
|---|---|---|
| `active_p95_ms` | 95th percentile of \|when a word lights up as the word being said − its start\|. An event that marks word *i* as the one being said is named `w<i>` | ≤ 120 ms, for every word (`active_share` 1.0) |
| `appear_early_p95_ms` | how long before it is said a word is already on screen (95th percentile; impact shows it see-through until then) | ≤ 700 ms (`captions.IMPACT_LEAD`) |
| `dead_air_share` | share of caption time with nobody speaking: outside every word + 0.3 s, and inside any word gap of 0.6 s or more | ≤ 2% |
| `cps_p95`, `over_cps_share` | characters per second of each caption (letters, no spaces) | over 20 cps in ≤ 5% of captions |
| `flash_share` | captions on screen under 0.3 s | reported |
| `over_max_words_share` | captions with more than 3 words (impact) | 0 |
| `caption_overlap_share`, `hook_overlap_share` | share of frames with text on screen in which a caption or the hook covers a keep-out box | 0 |
| `out_of_frame` | text events drawn past an edge of the frame | 0 |

`measure` exits 1 while a limit is broken. `sheet` renders each eval window as a preview and cuts a contact sheet per game and aspect for the owner (renders are deleted; footage is never committed).

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
| `WAITING` | `importing` | "Importing": `import.progress` (0 to 100) as the bar; `import.stage` is null (waiting for a worker), `reading`, `downloading` (with `import.bytes_done` of `import.bytes_total`), `copying`, `merging`, `checking` or `storing`. |
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

## Link metadata, ranges and reuse (ingestion, 2026-11-18)

Additions to the URL clipping contract above. Everything is additive: no field or code that was there is renamed, with the exceptions listed under "Changed values". Code: `app/ingest/platforms.py` (metadata and download), `app/ingest/preview.py` (the answer), `app/ingest/copies.py` (reuse), `app/ingest/runner.py` (progress). No schema change.

### Preview: `POST /v1/imports/preview`

Request: `{url, options?, start_sec?, end_sec?}`. `start_sec` / `end_sec` (seconds of the source video, numbers, 0 or more) choose a part of it; left out, the whole video. Re-ask as the customer moves the range: the site's answer is cached, so only the first ask makes a request.

The answer is metadata only. Nothing is downloaded, stored, logged or charged. Fields added:

| Field | Values |
|---|---|
| `video_type` | `video`, `short` (YouTube Short), `live_recording` (a finished YouTube broadcast), `vod` (a Twitch or Kick recording), `clip`, `ongoing_recording` (a VOD whose stream is still live), `live_stream` (a broadcast that is live now and has no recording to read), `live_channel` (a channel page: `twitch.tv/<name>`, `kick.com/<name>`), `upcoming`, `file` (a direct, Drive or Dropbox link), or null when the site gave nothing |
| `live_status` | `not_live`, `was_live`, `recording`, `live`, `upcoming`, or null (a channel page, a file link, or no answer). Whether a channel is live right now is never looked up. |
| `channel`, `channel_url` | The creator's display name and page. For a Twitch clip, `channel` is the broadcaster, not the person who made the clip. |
| `category` | The game or category the site names (Twitch and Kick: the game, the one played longest when a VOD has several; YouTube: its broad category such as "Gaming"), or null. No id. |
| `started_at` | When the video was published or the stream began, ISO 8601 UTC, or null. There is no end time: the sites do not give one. |
| `duration_sec`, `available_sec` | The length. For `ongoing_recording` both are the seconds published so far (they grow; the answer is cached for 1 minute instead of 5). |
| `thumbnail_url` | https, served by the site, never by us. Null when the site has none (a Twitch VOD just after the stream ended): show a placeholder. |
| `options` | `{"import": bool, "clip": bool, "range": bool, "range_download": "partial" | "full" | null}`. `import` / `clip`: the buttons to enable for what was asked. `range`: a part of this video can be chosen, also when the whole video is refused as too long. `range_download`: `partial` means only the chosen part is downloaded; `full` means the whole video is downloaded and the part is cut from it (the price is the part's either way). |
| `range` | `{"start_sec", "end_sec"}`: the part an import would take, clamped to the video (`end_sec` null: to the end), or null for the whole video. For `ongoing_recording` it always has an end: what exists now. |
| `lookup_ms` | How long the site took to answer; 0 when the answer came from the cache. |
| `kind` | Kept: `video`, `clip`, `live` (also for `ongoing_recording`), `upcoming`, and new `channel`. Prefer `video_type`. |

`estimate` is priced on `range` when there is one (the same price function, on the part's length). A video longer than the import limit (6 hours) answers `supported: false`, `refusal.code: "video_too_long"`, `options.range: true`: ask again with a range that fits.

```json
{"url": "https://www.twitch.tv/videos/2932305259", "platform": "twitch", "supported": true,
 "title": "PLAYING GTA 6 FOR THE FIRST TIME", "channel": "KaiCenat", "channel_url": "https://www.twitch.tv/kaicenat",
 "category": "Grand Theft Auto VI", "duration_sec": 39840.0, "available_sec": 39840.0,
 "started_at": "2026-11-18T12:59:57Z",
 "thumbnail_url": "https://static-cdn.jtvnw.net/previews-ttv/live_user_kaicenat-640x360.jpg",
 "video_type": "ongoing_recording", "live_status": "recording", "kind": "live",
 "options": {"import": true, "clip": true, "range": true, "range_download": "partial"},
 "range": {"start_sec": 3600.0, "end_sec": 5400.0}, "lookup_ms": 913, "refusal": null,
 "estimate": {"credits": 30, "basis": "source_minutes", "duration_sec": 1800.0, "balance": 300, "enough": true, "note": "..."}}
```

### Refusal codes

Every message says what to do instead (upload the file). New codes in bold.

| Code | When |
|---|---|
| **`live_channel`** | A channel page. Decided from the address alone; the site is not asked anything. |
| `live_stream` | A broadcast that is live with no recording to read (YouTube live). |
| **`upcoming`** | A stream or premiere that has not started. |
| **`private_video`** | The video is private. |
| **`age_restricted`** | The site wants a signed-in viewer to confirm their age. |
| **`members_only`** | Channel members or subscribers only. |
| `login_required` | Any other sign-in wall. |
| `drm_protected` | DRM. Now also said by the preview, not only by the import. |
| **`expired`** | Twitch or Kick no longer has the recording (expired or deleted). |
| `not_found` | Unavailable or removed (YouTube). |
| `geo_blocked`, `source_refused`, `source_failed`, `preview_timeout` | As before. `source_refused` now includes a bot check. |
| `no_format` | The video has no stream with a picture. |
| `file_too_large` | No version fits the size limit, even at the lowest resolution. The message suggests a shorter range. |
| `video_too_long`, `video_too_short` | Of the part asked for. |
| **`bad_range`** | `start_sec` / `end_sec` are not a range, or lie outside the video. |
| **`unsupported_media`** | The downloaded streams could not be joined into one file (import only). |

### Range on import and on clips from a link

`POST /v1/imports {url, consent, start_sec?, end_sec?}` and `POST /v1/clips/from-url {url, consent, start_sec?, end_sec?, options, webhook_url?}`. Only that part is imported, and the clip job is priced on its length. Clip times in the results count from the start of the imported part; add `import.range.start_sec` for the time in the source video. `options.range` (analyse only a part of an upload) is a different thing and still applies inside the imported part.

### Import status: `GET /v1/imports/{import_id}` and the `import` part of a job

| Field | Meaning |
|---|---|
| `stage` | null (waiting for a worker), `reading` (asking the site what the link is), `downloading`, `copying` (taking the part from a copy the account already has: no download), `merging` (joining picture and sound, cutting the range), `checking`, `storing`, `done`. |
| `progress` | 0 to 100. |
| `bytes_done`, `bytes_total` | While `downloading`: bytes so far, and the bytes expected (null when the site does not say). Null in other stages. |
| `range` | `{"start_sec", "end_sec"}` the import takes, or null for the whole video. |
| `reused` | True when the account already had exactly this part of this link stored: nothing was downloaded. |

### Never the same video twice

For one account and one link: the same part asked for again hands back the stored upload (`reused: true`); a part inside a stored copy (the whole video, or a longer range) is cut from that copy without a download; the same part already being imported is joined, not started again. A repeated `POST /v1/clips/from-url` with the same link, range and options returns the job that is already waiting or running (`200`), and a repeated `Idempotency-Key` returns the job it started: one reservation either way.

### Changed values (tell your tests)

- `import.stage`: `importing` is now `reading` then `downloading`. The clip job's own `stage` while it waits is still `importing`.
- A bot check on YouTube is `source_refused`, not `login_required`. A subscriber-only Twitch VOD is `members_only`, not `login_required`. A Twitch VOD that does not exist is `expired`, not `not_found`. An upcoming stream is `upcoming`, not `live_stream`. A channel page is `live_channel`, not `unsupported_link`.
- A Twitch VOD that is still being recorded is no longer refused: it is `ongoing_recording` and `supported: true`.
## Reframe boxes v1 (reframing agent → captions agent, agreed 2026-11-18)

Where the camera, the head and the HUD land on one clip's output, so text never covers them. Reframing owns the function and the HUD table; captions owns placement (`app/pipeline/placement.py`) and only reads this.

```python
# app/pipeline/layouts.py
reframe_boxes(plan: LayoutPlan | None, *, src: tuple[int, int] | None = None, cam=None, face=None,
              game: str | None = None, confidence: float | None = None) -> dict
hud_regions(game: str | None) -> tuple[tuple[str, Rect], ...]      # (kind, [x, y, w, h] fractions); HUD_REGIONS
```

Units, one rule: source boxes are `[x, y, w, h]` fractions of the source (the same as the `facecam_box` API); canvas boxes are `[x0, y0, x1, y1]` pixels of `canvas` (the same as `LayoutPlan.head`). Scale canvas pixels to the output size.

| Key | Value |
|---|---|
| `v` | `1` |
| `canvas` | `[w, h]`: the plan's canvas (`ASPECTS[aspect]`, e.g. `[1080, 1920]`); the source size when there is no plan |
| `layout`, `scene` | what is drawn (`LayoutPlan.layout`, or `"original"` with no plan) and the scene type |
| `seam` | the line between two stacked panels (canvas px) or null |
| `panels` | `[{"role": "gameplay" \| "camera", "out": [x0, y0, x1, y1]}]` in drawing order |
| `text_span` | `[f0, f1]`: the share of the width text is centred in (`LayoutPlan.text_span`) |
| `facecam` | `{"src": [x, y, w, h], "out": [x0, y0, x1, y1] \| null, "confidence": 0-1 \| null}` or null (no camera). `out` is the camera panel, the inset, or where the camera lands inside a gameplay picture. `confidence` null: given by the user, or not measured |
| `head` | the person's head on the canvas or null (`LayoutPlan.head`; when only the camera box is known, its upper 85%) |
| `hud` | `[{"kind": "killfeed" \| "minimap" \| "speedometer" \| "hud", "src": [x, y, w, h], "out": [x0, y0, x1, y1] \| null}]`; `out` null when the crop never shows it. Empty for an unknown game, `"other"` or no game: never guessed |
| `keep_out` | canvas boxes no text may overlap: the head, a camera inset (`border`) or a camera drawn inside a gameplay picture, and every HUD element shown. A stacked camera panel adds only the head, so the seam stays a caption line |
| `crop_path` | `[{"t": seconds from the clip start, "box": [x, y, w, h]}]`: the gameplay panel's moving crop, or null (static) |

Rules:
- `keep_out` is static for the whole clip: the worst case over every point of `crop_path`. Place captions once per clip.
- No plan (`vertical=False`, the 16:9 original, `classic`): `reframe_boxes(None, src=(w, h), cam=..., face=..., game=...)` gives `canvas = [w, h]`, one gameplay panel, and `keep_out` = head + camera + HUD in source pixels.
- `game` is a `templates.GAMES` id (the template's `game`). `gta6` and `gta-online` fold to `gta5`'s HUD. The table and how each box was measured go in `docs/REFRAME_EVAL.md` with the first measured entries; until then the table is empty and `hud` is `[]`.
- A change to this shape bumps `v` and is agreed with the captions agent first.

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
