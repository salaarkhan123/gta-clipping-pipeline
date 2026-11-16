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

Panel sizes travel as `split_ratio` (the top panel's share of the height, 0.25 to 0.75) and `camera` (`top` or `bottom`) in the template's `options`; B's renderer reads them. The camera panel is always cropped tight on the person.

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

## Merge order

1. Done: #111, #112, #113 (this file, revision 0004), #115 (templates, C), #116 (app shell, D).
2. Open: B (layouts and render options), then the worker wiring for B's and A's options; #117 (A: buckets, limit, range) waits for the owner's answers on what those options cost.
3. Wave 1b, from the screenshots: A2 (prompt, score calibration), B2 (`impact` captions), C2 (presets, posters, custom templates), D2 (job form, pre-editing, results grid).
4. Wave 2: F, E, G. H gates every merge once Wayin clips exist to compare with.
Money PRs stay open for the owner.
