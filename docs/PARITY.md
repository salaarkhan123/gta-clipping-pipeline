# Parity map: WayinVideo's gaming product → ClutchClips

**Standard (owner, 2026-11-16): identical behaviour.** Same options, allowed values and defaults; same flow in the same number of steps or fewer; same kinds of output per clip. Ours: brand, name, logo, colours, copy, template artwork.

**Source of the "Wayin" column:** their public API docs, product pages and help centre, read on 2026-11-16 (24 API pages, 2 product pages, about 25 help articles). Nothing here was observed in their app. Where their docs disagree with each other or say nothing, the row is marked **ASK** and listed under "Questions for the owner": we do not guess.

**Status:** done · partial · missing · skip (not gaming-relevant).
**Verified** (agent H, per feature, against Wayin's output for the same input in `~/Downloads/wayin-benchmark/`): options / flow / outputs, each ✓ or ✗. A feature is done only with three ✓. **No row is verified yet.** The folder now holds twelve screenshots of their app (section 6) and no rendered clips or source video, so nothing can be compared on output yet.

## 1. AI Clipping

| Option / behaviour | Wayin (documented) | ClutchClips today | Status | Agent · ticket | Verified O/F/O |
|---|---|---|---|---|---|
| Input | Platform link or uploaded file id | Uploaded file only | partial | E · 4.4a | – |
| Project name | Optional label, default empty | None | partial | A | – |
| Source language | ISO code from a list of 100, default auto-detect | `source_lang` on clips, reframe, captions, find, transcripts, summaries: the 100 codes of the installed Whisper tokenizer (`GET /v1/languages`); null = detected from up to three 30 s samples and stored on the upload. English keeps the English-only models; other languages use the multilingual model of the same size. Cantonese (`yue`) needs a large-v3 model and is refused on the default models | partial: built, not verified | F · 2.3 | – |
| Target language (titles, descriptions, subtitles) | ISO code, default same as source | `target_lang`: the AI judge writes titles, hook, description in it (default: the spoken language; English requests unchanged). Translated subtitles need a translation provider, off by default (`TRANSLATION_PROVIDER`, money question open) | partial: built, translation off | F · 2.3 | – |
| Clip length | Buckets 0–30, 0–90, 30–60, 60–90, 90–180, 180–300 s; default 0–90 | Fixed length 10–60 s (default 30); the AI may pick 15–45 s | partial | A | – |
| Clip limit | Top N by score; default all | 1–10, default 3 | partial | A | – |
| Time range | Whole video or a chosen range (web product; not in the API) | Whole video only | partial | A | – |
| Render on request | Off by default: results are metadata; on renders every clip | `render`: `full` (every clip rendered, still the default until the defaults PR), `preview` (540 on the short side, fast preset; `preview_url`), `none` (times, copy, scores, captions file and a thumbnail from the source; no video). `POST /v1/clips/export` renders them later | partial: built, not verified | B · S2 | – |
| Resolution | 480, 720, 1080, 2K, 4K; default 480; never above the source | 1080 (capped by plan) | partial | B · S2 (plan caps: money) | – |
| Captions | Off by default | On by default | partial | B | – |
| Caption display | Original, translation or both; default original | `caption_display` original / translation / both on clip jobs and on subtitle and transcript downloads (TXT, SRT, VTT). Burned-in captions stay original until the renderer takes the translated lines (B) | partial: downloads only | F · 2.3 | – |
| Caption style | 53 styles: 4 word-emphasis, 18 animated, 6 static, 25 gaming; default the 8th animated one | 12 styles: `impact` (the default), the five word-highlight styles, and `bounce`, `karaoke`, `reveal` (animated), `outline`, `subtitle` (still) and `tag` (box behind the keyword). No per-game sets | partial | B · 2.2 | – |
| AI hook | Off by default; 13 script styles (default serious); position beginning or end | On by default; `hook_style` (the 13 names; anything but `serious` adds one tone line to the judge's instructions), `hook_position` `beginning` or `end` | partial: built, not tried with the real judge | B · 3.2 | – |
| Hook keywords, hook duration | On re-export only | `hook_duration_ms` (500 to 10000; default 2.5 s) on clip jobs and exports. `hook_keywords`: not built (Wayin documents the name only) | partial | B | – |
| Reframe | Off by default (keeps source ratio) | On by default (9:16) | partial | B | – |
| Ratio | 9:16, 1:1, 4:5, 16:9 | Same four | done | B | – |
| Reframe layout | Auto, Full, Fit, Grid 4, Split 2, Trio, PiP, OTS, Screen First, Gameplay A, Gameplay B; allowed set depends on the ratio; default Auto | All eleven, per ratio as Wayin. `trio`, `grid4`, `ots` are our own reading of the names (provisional; panels tile the frame, the person is never cut). `auto` is chosen per moment: a moment with the camera hidden fills the frame with gameplay | partial: built, provisional | B · 2.1a/b | – |
| What moments to find | Optional free text with five quick picks (their app, w08; not in the API docs) | `prompt` clip option, max 300 characters: handed to the AI judge as the viewer's interest, next to the template's focus. It moves ratings only: the same candidates, AI calls and price. Not tried with the real judge; the form field and quick picks are D's | partial | A, D | – |
| More results, express mode | Enterprise-only switches | None | skip (owner: wait) | – | – |
| Task states | Created, queued, ongoing, succeeded, failed | Queued, running, succeeded, failed, cancelled | partial | A | – |
| Results while running | Clips appear as they are found | Clips appear as they render (PR #111) | partial | A · S1 | – |
| Per clip: rank | Index in rank order, from 0 | Number in video order, from 1, plus rank | partial | A | – |
| Per clip: times | Begin and end in milliseconds | Start and end in seconds | partial | A | – |
| Per clip: title, description, tags | One each | Title (3 options), description, hashtags | done | A | – |
| Per clip: score | 0–100 | Raw 0–100 from the AI, plus `display_score`: calibrated per job on every read (best clip 90 to 99, none under 55, order kept), in the job, project, library and clip-edit responses. The website still shows rank and tier | partial | A · U4/U5; D shows it | – |
| Score breakdown | Five dimensions (Hook, Story, Value, Engagement, Reach) with grades and explanations on paid plans | Four parts (hook, flow, value, trend), one reason | partial | A · U4 | – |
| Per clip: thumbnail | Image URL | Frame from the clip | done | B | – |
| Per clip: download link | Only when rendered; new link on every read, valid 24 h | Signed link, valid for a configured time | partial | B | – |
| Result expiry, cost used | Reported per task | Expiry reported; credits charged reported | done | – | – |
| Markers on the source timeline | Results show where each clip came from | Not shown | missing | D | – |

## 2. Other tools

| Feature | Wayin (documented) | ClutchClips today | Status | Agent · ticket | Verified O/F/O |
|---|---|---|---|---|---|
| Find Moments | Prompt search; same clip format and render options as clipping; limit; no length bucket | Video Finder: speech and on-screen search, returns matches and optional clips | partial | A · 3.3 | – |
| Re-export clips | Render all or chosen clips of a finished task again with new options | `POST /v1/clips/export` (`job_id`, `clips` or all, render options on top of the job's, one clip's `edit`) and `/quote`. Charged for the seconds rendered (money PR: owner's OK) | partial: built, not verified | B · S2 | – |
| One-Click Highlights | Prompt-driven montage from one or several videos; ratio, duration, language, subtitles, hook, B-roll, music; five prompt presets | None | missing | B · 3.4 (music licence: owner) | – |
| Game Clipping | Per-game templates: a layout, a subtitle style and detection tuned to the game | 5 GTA templates (options and tuning) | partial: 31 game templates for 12 games, and 7 game-type presets (`GET /v1/templates?kind=preset`: a layout, panel sizes in `panels`, a caption style; all provisional). Template options now carry the real layout names. Not reaching a job yet: panel sizes (B: `camera`, `split_ratio`), the `impact` caption style (B; presets use `pop` until then), length buckets and hook styles (A, B), and the dashboard (D). Gameplay A / B are provisional; not verified | C · 2.4 | – |
| Game list | LoL, GTA 5, WoW, OW2, Minecraft, Apex, Valorant, Fortnite, Dota 2 / Rust, More | GTA only | partial: all 11 games plus "other" built on `feat/game-template-gallery` (`GET /v1/templates/games`, `?game=`); not verified | C | – |
| Which templates sit under each game | Not in the docs (needs their app) | – | **ASK** (still open: the built catalogue is our own choice of template kinds per game) | C | – |
| Video Editor | Canvas, layered timeline, trim, transcript-based cutting, reframe, subtitles, elements, hook, text, audio, transitions, details; autosave | None | missing | D · 1.4a–d (re-render charging: money) | – |
| AI Subtitles | 100 languages; styles; line editing; original / translated / both; punctuation toggle; max characters per line; emoji; TXT, SRT, VTT export | 99 languages on the default models; 5 styles; SRT, VTT, TXT export in original, translation or both (translation when configured). Burning translated captions: B | partial | F · 2.3, B · 2.2 | – |
| Video Transcripts | Segments with text, language, start, end, speaker; optional translation | `POST /v1/transcripts` then `GET /v1/transcripts/{upload_id}` (segments: start, end, text, language, speaker, translation) and `/download` as TXT, SRT, VTT. Shared with Video Finder's index, reused when it is in the same language. `speaker` is always null: no speaker model without an account or token | partial: no speakers | F · U1 | – |
| Video Summary | Title, summary, tags, timed highlights | `POST /v1/summaries` (title, summary, tags, timed highlights) through a summary provider; off by default (`SUMMARY_PROVIDER`: `ai` uses the existing AI client; money question open) | partial: built, off | F | – |
| AI Note Taker, mind map, chat with video | Notes with prompt, length, timestamps, images | None | skip | – | – |
| AI Reframe | Bulk, per clip, or a whole long video; automatic per scene or fixed | Reframe tool for a range, fixed layout | partial | B | – |
| Video Enhancer | Upscale to 1080p, 2K or 4K; sharper on-screen text; range up to 10 minutes | None | missing | B (needs an upscaling model: cost to verify) | – |
| AI Thumbnail | Generated options, an uploaded image, or a chosen frame | Frame only | partial | B · U7 (generated: paid service, money) | – |
| AI Hook voice | Generated voiceover | None | missing | B · 3.2 (TTS: paid service, money) | – |
| AI B-roll / AI Video | Generated, stock or own media, auto-placed | None | missing | B · 3.5 (paid services, money) | – |
| Live Clipping | By application only; no public behaviour documented | None | missing | E · 4.5 | – |
| Bulk edit | One format, style, hook, cleanup or template across many clips | None | missing | D · 1.5 | – |
| Custom templates | Save hook, audio cleanup, filler and silence removal, intro and outro | Saved looks on `feat/template-presets-custom`: `GET`, `POST /v1/templates/custom`, `PATCH`, `DELETE /v1/templates/custom/{id}`. A look is a name and clip options (layout, shape, captions, the editing switches incl. dead-air cut and on-screen hook); never an option that sets a price or a quality. 20 per account, the same on every plan. Not built: intro and outro, audio cleanup, the website's "add template" tile (D) | partial; not verified | C | – |
| Brand kit | Logos, colours, subtitle and text styles, fonts, media | None | missing | D · 2.5 | – |
| Scheduler and publishing | Connect accounts; post now or on a schedule to YouTube, TikTok, Instagram, Facebook, LinkedIn, X; calendar; bulk schedule; cancel | None | missing | E · 4.1/4.2 (platform approvals: owner) | – |
| Agent integration | Agent skills and a remote MCP server | A skill exists; no MCP server | partial | G | – |
| Export | MP4; 480 to 4K, never above the source; no watermark | MP4; `resolution` 480 to 4k, never above the source, capped by plan; no watermark; `export_url` per clip | partial | B · S2 | – |

## 3. Ingestion

| Feature | Wayin (documented) | ClutchClips today | Status | Agent · ticket | Verified O/F/O |
|---|---|---|---|---|---|
| File upload | Ask for an upload URL, send the file to storage, use the returned id; MP4, MOV, WEBM, AVI | Send the file to the API; more formats accepted | partial | E · 4.4b | – |
| Link import | 17 sources in the web importer: YouTube, Instagram, TikTok, Facebook, X, Twitch, Kick, Google Drive, Dropbox, Box, Zoom, Loom, StreamYard, Vimeo, Dailymotion, Rumble, Medal. Links must be public | API: `POST /v1/imports` for Twitch (VODs, clips), Kick (VODs, clips), direct https video links, YouTube best effort; consent and a log row per import; takedown (`admin.py takedown`). Website form not built | partial | E · 4.4a | – |
| Google Drive | Connected file picker or a share link | Public share links (Drive and Dropbox) through `POST /v1/imports`; no connected picker | partial | E · 4.4c | – |
| Bulk import | Several videos per batch (10, 30 or 50 by plan) | `POST /v1/imports/bulk`, up to 10 links for everyone (per-plan limits are the owner's call) | partial | E · 4.3 (batch limits: money) | – |

Our ingestion rule stays (CLAUDE.md): public, non-DRM content only; no logins, cookies, proxies or block evasion; fail cleanly and say "upload instead"; consent and a log per import. Wayin's own docs state the same access rule (links must open in a signed-out browser). Sources that need a login will fail on both; the site lists only sources we have verified.

## 4. Web app flow

| Step | Wayin (documented and from the owner's screenshots) | ClutchClips today | Status | Agent |
|---|---|---|---|---|
| Home | Link or upload box, Upload and Bulk import buttons, tool grid, recent projects | Projects page with upload | partial | D |
| Sidebar | Home, Library, Scheduler, Brand kit, Pricing, API | Projects, Library, Brand kit and Publishing (coming soon), API keys, Billing | partial | D |
| Settings before a run | Clip length, ratio or template, subtitle style, hook | Template, clips, length, shape, caption style, editing switches | partial | D |
| Results | Ranked by score, sortable by time, preview, edit, export or publish | Ranked, sortable, preview, download | partial | D |
| Template gallery | Game filter tabs, preview clip per template, "use template" | Template select | partial: API side built (game list, game and kind filters, schematic posters served at `GET /v1/templates/{id}/poster`, one per template and per preset); the gallery page and the preset tiles are D's; no preview clips (no rights-cleared footage) | C, D |

## 5. Money (owner decides; nothing here is built without an OK in the PR)

Their plans, credits and per-plan limits (export resolution, storage, upload size, bulk batch size, connected accounts, scheduled posts, custom templates, fonts, seats) are listed in the research notes. Owner's decision: we keep our own pricing. Tiers, credits and limits will be recommended from measured processing costs and need the owner's approval before anything changes.

## 6. Observed in the owner's screenshots (2026-11-16)

Twelve screenshots of their web app, in `~/Downloads/wayin-benchmark/` (`w01` to `w12`). This is what the pictures show, measured by eye; it is the spec for the items below. **Observed, not verified:** no clip of ours has been compared with a clip of theirs.

### Layouts (w01 to w07, all 9:16)

| Shot | Game type | Top panel | Bottom panel | Caption |
|---|---|---|---|---|
| w01 | MOBA | Gameplay, about 63% of the height | Camera, about 37%, cropped tight on the person | none shown |
| w02 | – | Camera, about one third | Gameplay | none shown |
| w03 | – | Camera, about 30% | Gameplay | One word, on the line between the panels |
| w04 | Shooter | Gameplay fills the frame | – | One word, in the lower third |
| w05 | MOBA | Gameplay fills the frame | – | Two words, in the lower third |
| w06 | – | Gameplay, about 66% | Camera | One word in the accent colour, on the line between the panels |
| w07 | Fighting | Gameplay, about 57% | Camera, about 43% | none shown |

- The owner describes the split as "about 50/50". The seven shots measure between 57% and 70% for the larger panel. Ours: gameplay 60%, camera 40% when gameplay is on top; camera 33%, gameplay 67% when the camera is on top; adjustable per template. **Built (B):** two clip options on the two-panel layouts (`split2` and the old `split`, `screen_first`, `gameplay_a`, `gameplay_b`, and `auto` when it draws two panels): `camera` (`top` or `bottom`) and `split_ratio` (0.25 to 0.75, the top panel's share of the height). Null keeps each layout's own panels, so nothing that renders today changes. Every other layout ignores both. In 16:9 the panels sit side by side: `top` is the left panel and the ratio its share of the width. Not compared with a Wayin clip.
- The camera panel is cropped tight on the person (head and shoulders fill it), never the whole webcam box with its border.
- Shooter and "MOBA Full" presets show gameplay only.

### Caption style (w03 to w07, and the preset tiles in w09)

- One or two words on screen at a time (three at most in the tiles).
- Very large, heavy, bold, with a thick dark outline; mostly upper case. One tile uses lower case with a filled box behind the keyword.
- One keyword per caption in an accent colour (green in w06; yellow, red and blue appear in the tiles).
- Position: on the line between the two panels in split layouts; in the lower third when gameplay fills the frame.
- Ours: a new style, `impact`, in our own font, becomes the default caption style. Agent B.
- **Built (B), not compared with a Wayin clip:** `impact` is the default `caption_style`. Font: Anton (SIL Open Font License 1.1), shipped in `clip-api/app/fonts/` and handed to the subtitle renderer directly, so it does not depend on what the server has installed. Capitals are 6% of the frame height (the shots measure 4.4% to 5.9%), the outline 8% of the font size, with a soft shadow. One or two words, a third when the three have 12 characters or fewer; the keyword (longest word that is not a stop word) in the accent colour, lime unless `caption_accent` is sent. `caption_position`: `auto` (the line between the panels, else the lower third), `seam`, `lower`, `center`; a caption moves off the streamer's head wherever it is asked to sit. A word too long for the line is drawn smaller.
- Not built: `caption_emoji`. The caption font has no emoji and the subtitle renderer found no other font that could draw one (tested with three emoji: "failed to find any fallback"); it draws outline fonts, not colour emoji. The option is left out of the API until emoji are drawn as images or an outline emoji font is shipped.
- Not checked: in the source's own frame (reframing off) no camera is detected, so a caption there is not moved off a face.

### Job form (w08)

| Control | What it shows | Default |
|---|---|---|
| Source | The link as a chip, and a card with the video's thumbnail and title | – |
| Language | One select | "Auto", no translation |
| Clip length | One select | "Auto (<90s)", then the documented buckets |
| What moments to find | Optional free text with five quick picks: funny reactions, clutch wins, epic fails, emotional moments, high-energy scenes | empty |
| Where to find clips | A two-handle range slider with start and end times | whole video |

### Pre-editing (w09, w10)

- A switch turns pre-editing on. Two tabs: **Presets** and **Custom**.
- Presets: a ratio select (9:16), a "show my templates only" checkbox, an "add template" tile, then preset tiles named by game type and layout: Racing Gameplay, Racing 2 Gameplay, Shooting Gameplay, Fighting Screen First, MOBA Screen First, MOBA Full, MOBA Gameplay, and more below the fold (names cut off in the picture).
- Custom: checkboxes for Resize (with the ratio select; ticked), Subtitles, Emojis, Hook text, Logo, Intro, Outro. Emojis, Intro and Outro carry a paid badge; Hook text and Logo a Pro badge. Which of our plans unlock what is a pricing decision (section 5).

### Results (w12)

- Tabs: "Viral Moments" with the selected count ("2/38 selected") and "Find Moments".
- A select-all checkbox with "2 of 38 selected"; a bar with Bulk Edit, Bulk Schedule, Bulk Export and Create Montage; a sort select ("Highest Viral Score").
- A grid of cards, three across. Each card: a checkbox, "#N" and the title, a time range badge on the thumbnail ("38:58 - 40:30"), an "Edited" badge when changed, the score as "99 /100", a two-line description, six quick actions (schedule, trim, reframe, captions, download, more), and like, dislike and bookmark on hover.
- 38 clips from a video at least 78 minutes long. Clip lengths among the top 15: 36 to 92 seconds.

### Scores (w12)

Their top 15 of 38: 99, 97, 96, 96, 93, 91, 91, 91, 89, 87, 87, 85, 82, 80, 80. Ours: a `display_score` calibrated per video so the best clips land in the same range while the order stays the order of the raw scores; raw score and sub-scores stay available and are shown in the tooltip. Agent A. Formula in `docs/CONTRACTS.md`.

### Moment benchmark (w12)

The 15 moments above, with their times, are in `clip-api/eval/wayin-zias-iceman.csv`. Once the source video is supplied:

```bash
python scripts/eval_clips.py eval/wayin-zias-iceman.csv job.json     # found, and the rows no clip landed on
```

Run on 2026-11-16 without the AI judge (selection only): 7 of the 15 found, 8 missed. Details and causes in `docs/super-board/runs/2026-11-16-swarm.md`, "Moment benchmark". Clip #4 ends 1:13:31 (the screenshot; confirmed by the owner).

### Their pricing (w11), for the cost model only

| Plan | Monthly | Billed yearly, per month | Credits per month | Export | Bulk edit and export | Bulk import | Storage | Social accounts | Custom templates |
|---|---|---|---|---|---|---|---|---|---|
| Starter | $15.99 | $5.58 | 500 | 1080p | 20 clips | 10 videos | 50 GB | 3 | 1 |
| Pro | $26.99 | $9.58 | 1,000 | 2K and 4K | 50 clips | 30 videos | 100 GB | 10 | 3 |
| Scale | $139.99 | $69.99 | 6,000 | 2K and 4K | unlimited | 50 videos | 150 GB | 50 | 10 |

1 credit processes 1 minute of source video. Pro adds 2 seats, brand kit, custom fonts, AI music, speech enhancement, B-roll and hook generation; Scale adds 4 seats and priority processing. Per credit: $0.032 (Starter), $0.027 (Pro), $0.023 (Scale) at monthly prices; $0.011, $0.0096, $0.0117 billed yearly.

## Decisions (owner, 2026-11-16)

1. **API names:** our own parameter names, with a published mapping to Wayin's documented options. ClutchClips stays an independent platform with equivalent function.
2. **API defaults:** match Wayin's documented defaults: rendering off, captions off, reframing off, AI hook off, 480p. The dashboard lets users choose their own settings and sends them explicitly. Existing API clients stay compatible wherever possible (every existing field keeps working).
3. **Clip indexing:** return both. `rank_index` starts at 0 and orders clips by virality score; `timeline_index` starts at 1 and orders them by position in the video. Users can sort by either.
4. **Templates, caption styles, layouts:** keep building the documented layouts and per-game templates with our own branding and artwork. Gameplay A and Gameplay B stay **provisional** until compared with Wayin's real output. The owner will supply screenshots and recordings. **Nothing is marked verified until that comparison is done.**
5. **Enterprise switches** (more results, express mode): wait. Not built. Consumer-facing platform first.
6. **Paid services:** research and price, in this order: hosted transcription and translation; AI thumbnail generation; text-to-speech for hooks; AI-generated or stock B-roll; video enhancement and upscaling. Compare providers on price, speed, quality and estimated cost per video; prefer affordable and open-source options. **No paid service is integrated without the owner's approval.**
7. **Plans and pricing:** keep our own structure. Before subscriptions are finalised, calculate real processing costs (transcription, AI analysis, rendering, storage, bandwidth) and recommend tiers, credit allocations and usage limits from them. **No pricing change is implemented without the owner's approval.**

## Still open

- Which screenshot (w01 to w07) belongs to which preset name, and the preset names below the fold in w09.
- What Gameplay A and Gameplay B look like next to each other: still **provisional**.
- Rendered clips from Wayin: the owner will not pay for exports now, so **output parity stays unverified**. We benchmark against the 12 screenshots and the 15 documented moments.
- The moment benchmark with the AI judge (no key on the build machine).
