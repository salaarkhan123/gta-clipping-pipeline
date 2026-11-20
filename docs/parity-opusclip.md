# Parity plan: OpusClip's feature pages → ClutchClips, for gaming

Planning document. No product code, schema, price or credit change comes with it. Written 2026-11-18 against `origin/staging` at `8068c5b` and the open PRs named in each row.

`docs/PARITY.md` maps WayinVideo's gaming product. This file maps a second reference, OpusClip's public feature pages, and orders the work. Where both ask for the same thing, the PARITY.md row and its ticket stay the source of truth and are cited here.

## 0. Rules for this plan

| Rule | Value |
|---|---|
| Reference use | Functional reference only. Same kinds of function, our own code, names, copy, artwork and brand. NEVER copy their code, wording, assets or branding. |
| Their backend | Unknown to us. Nothing here says how they build anything. Every "how" below is our own design. |
| Their benchmark table (f33) | NOT reproduced, NOT quoted on our site, NOT a target. We do not run those academic benchmarks and make no claim against them. |
| Our numbers | We publish only statistics we have measured, with the script and the footage named. A row with no measurement says "not measured". |
| Creators | A creator appears on our site only with their permission, and is called a customer only if they are one (#190 credits each creator of site media). |
| Unbuilt features | Hidden or marked "Coming soon" (SPEC.md section 13). |
| Money | Every feature that costs money per use gets a credit price shown before the user confirms. Each price needs the owner's OK in its PR. This plan sets none. |
| Footage and providers | Customer footage, audio and transcripts go only to providers whose terms say they do not train on API inputs. Section 3 lists what each provider's page said on the day it was read. |
| Current phase | CLAUDE.md: speed track and understanding track first. Release 0 below is that work; nothing here jumps ahead of it. |

## 1. What the reference shows

Screenshots are in `~/ClutchClips-eval/reference/` on the owner's machine. They are not in the repo and are not embedded here.

| Shot | Page | What it shows (function only) |
|---|---|---|
| f31 | Prompt clipping page | Analysis of a video by frame, audio and sentiment: characters or objects, actions, emotions, sounds, scenes, on-screen text; boxes drawn on people with an action label and a one-line scene description; each scene rated |
| f31, f32 | Prompt clipping page | A typed prompt that compiles every matching moment and makes a teaser from them |
| f32 | Prompt clipping page | Reframing that finds a subject, tracks it across frames and crops to 9:16, 1:1 or 16:9 (labelled alpha) |
| f33 | Prompt clipping page | A table of academic benchmark scores. Out of scope (section 0) |
| f34 | Editor page | Two entry points: long video to short clips (clip, reframe, edit, publish in one flow); raw footage to a finished video by chatting with an AI editor |
| f35, f36 | Captions page | Animated caption templates; the same clip captioned in 1:1, 9:16 and 16:9; captions adapt to ratio and layout |
| f37 | Captions page | Caption font family, weight, colour (hex), size in px, italic, underline, case (upper or as typed); upload a custom font |
| f38 | Captions page | Text-based editing on the transcript: edit words, split and trim, add emoji, highlight, add AI B-roll at a word range, remove caption, remove caption and video, add a section |
| f39 | Captions page | Grid: AI clipping, AI captioning, social media calendar (publish, schedule, manage), AI B-roll, AI voiceover, analytics, audio cleaning (filler words, pauses, enhance), AI reframe |
| f40 | Livestreamer page | A row of source types (video podcast, interview, webinar, Twitch and three streaming tools); a creator showcase; three headline statistics |
| f41 | Livestreamer page | A creator case study; automatic B-roll switch; switching between 9:16, 1:1 and 16:9 |
| f42 | Livestreamer page | Schedule to post: connected accounts per platform, title, description, visibility, post now or at a time; one click to several channels; layout that switches per scene; a call-to-action overlay and an outro |
| `opus-site/` | Home | Paste a link or upload; clip cards with a score; caption preset list; fill and gameplay layouts with a before and after; B-roll on the timeline; filler words struck out in the transcript; text-to-speech hook with voice and speed; brand templates, team workspace, API; import, edit and schedule on a timer |
| `opus-app/` | App | Job setup: range slider, language, genre, layout, SRT upload, "moments to include" prompt, caption presets, a credit summary before Create. Brand kit: logo, caption and headline styles, layout per ratio, intro and outro per ratio, music. Asset library: censored word list, brand vocabulary, two fonts, media |
| `opus-producer/` | AI editor | A chat box with "add raw footage" and "add reference", a gallery of creator styles to recreate, and a question list |

## 2. Gap matrix

**Status:** `have` = on staging with tests. `partial` = part of it on staging, or built in an open PR that is not merged. `missing` = no code. `defer` = not planned (reason given). "Have" never means verified against the reference: no row is verified on output.

**Size:** S = one PR under 400 changed lines. M = two to four such PRs. L = five or more, or a new subsystem.

**Cost** names the paid service a feature would need and its unit cost from section 3. "none" means it runs on what we already run. Any credit price is a proposal for the owner.

### 2.1 Video understanding (f31)

| # | Sub-feature | Status | Today (file or PR) | Missing | Gaming angle | Size | Depends on | Per-use cost | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 1.1 | Speech: whole transcript with word times | partial | Candidates and the search index are transcribed (`app/pipeline/transcribe.py`, `translate.whole_transcript`); one transcript per upload is #139; hosted providers #167 | Merge #139, #167; whole transcript on by default once S3 makes it fast | Callouts, trash talk and RP dialogue carry most GTA RP moments | S | #139, #167, #95 | Hosted STT per #167 (owner picks) | Audio leaves the server when hosted: Terms must say so |
| 1.2 | Speakers | missing | `speaker` is always null (`app/routes_text.py`); #139 stores turns only when a provider returns them | A provider or local model that returns turns; captions for the streamer only | Streamer versus teammates on voice chat versus NPC dialogue | M | #139, #167 | Deepgram or AssemblyAI diarization (#167); local model needs a token | Wrong speaker on overlapping voice chat |
| 1.3 | Sounds | partial | Loudness per second (`signals.audio_rms_db`); laughter bursts and spectral flux in #154 | Named sound events: gunfire, explosion, siren, crash, scream | Gunfire and sirens mark chases and shootouts before anyone speaks | M | #154 | none (local classifier) | False events from game music |
| 1.4 | Scenes | partial | Scene type per source and per moment (`facecam.classify`, `moment_facecam`); scene change and standby in #154 | Scene boundaries stored per upload; menu, loading, lobby, map and cutscene classes | Drop loading screens, lobbies and pause menus; keep cutscenes only when the streamer reacts | M | #154 | none | Thresholds differ per game |
| 1.5 | Characters and objects | partial | Face and webcam box (`app/pipeline/facecam.py`); frame embeddings for search (`app/pipeline/visual.py`) | Labels a user can read: vehicle, weapon, police, player character, explosion | Vehicles, weapons and wanted stars are the nouns of GTA clips | M | 1.4 | none with local zero-shot tags; VLM frames optional (section 3) | Local tags are coarse; a wrong tag shown to the user looks worse than none |
| 1.6 | Actions | missing | None on staging (a gameplay-signals branch exists, no PR) | Game events on the timeline: kill, death, crash, chase start, wasted or busted, win, loss | The core of gaming clips; the generic product reads speech first | L | 1.4, 1.8, #174 HUD regions, #105 labels | none (HUD and audio), or VLM on candidates | Per-game work; SPEC allows HUD detectors only when the eval set can measure them |
| 1.7 | Emotions | partial | Judge v2 emotion sub-score from the words (#153); face distance from the resting face in thumbnails (#138) | A voice excitement signal on the timeline; the webcam expression signal reused for ranking | Rage, laughter and shock on the webcam are the reaction clip | M | #153, #154, #138 | none | Face analysis of a person: say what is analysed in Privacy; no identity, no stored face data |
| 1.8 | On-screen text | missing | Chat motion only (`signals.onscreen_chat_motion`); no text is read | Read the kill feed, mission banners, wasted or busted, score and timer inside measured HUD regions | Kill feed and banners are exact, timestamped events | M | #174 HUD regions measured | none (local OCR on sparse crops) | Stylised game fonts read badly; decode cost on long VODs |
| 1.9 | Every scene rated | partial | Four-part AI rating on candidates (`app/ai.py`); five sub-scores #153; per-game weights #177; calibration is issue #104 | A rating for every scene, not only the candidates sent to the judge; calibrated 0 to 100 | Ratings fitted per game on the owner's labels | M | #153, #177, #104 | Judge calls scale with scenes rated (money if the count per job rises) | A score shown before calibration misleads |
| 1.10 | The analysis shown to the user | partial | `signals`, `why`, `kind` on each clip (`app/routes_media.py`); "AI rating" tab in #187 | Tags per clip (who, what, sound, text read), a one-line scene description, markers on the source timeline | "3 kills, police chase, streamer laughing" on the card | S | 1.3 to 1.8 | none | Never show a tag the pipeline did not measure |

### 2.2 Clipping by prompt (f31, f32)

| # | Sub-feature | Status | Today | Missing | Gaming angle | Size | Depends on | Per-use cost | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 2.1 | Free-text prompt on a clip job | partial | `prompt` on `POST /v1/clips` (`app/routes_media.py`): it moves the judge's ratings only, same candidates; not tried with the real judge | The prompt must change which moments are nominated | "every police chase", "all clutch wins", "when I rage" | M | #137, #153 | none if the call count stays the same; more calls is a money PR | A prompt is user text sent to the judge: keep it as data, never as instructions |
| 2.2 | Prompt finds what was said | partial | Keyword and phrase search (`tools.search_transcript`, `POST /v1/find`) | Meaning, not keywords: the LLM pass (#137) reads the transcript with the prompt | Slang and callouts never match keywords | S | #137, #139 | Included in the pass | None new |
| 2.3 | Prompt finds what was shown | partial | Frame embeddings every 2 s matched to text (`visual.search_visual`); weak on game footage | Use tags, events and text read (1.5 to 1.8) as the visual index | "the helicopter crash" with nobody saying it | M | 1.5 to 1.8 | none | Recall on visuals stays the hardest number to move |
| 2.4 | Compilation and teaser | missing | None (issue #55; `POST /v1/highlights` in #185's gap list) | Join chosen or prompted moments into one video, ordered and trimmed, with a length target | Kill montage, fail compilation, "best of the stream" | M | 2.1, export route | Render seconds (money PR); music needs a licence | Music rights; a montage of weak moments is worse than none |
| 2.5 | Quick-pick prompts | partial | Field and quick picks are the website's (PARITY.md section 6, job form) | Gaming picks per game from the template's focus | Per-game picks: heists, chases, RP arguments | S | 2.1, templates | none | None |

### 2.3 Reframing with tracking (f32, f41, f42)

| # | Sub-feature | Status | Today | Missing | Gaming angle | Size | Depends on | Per-use cost | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 3.1 | 9:16, 1:1, 16:9 (and 4:5) | have | `aspect` on every tool (`app/render_options.py`) | Nothing | Shorts, feed and YouTube from one clip | – | – | none | – |
| 3.2 | Layouts and automatic webcam | partial | Eleven layouts (`app/pipeline/layouts.py`), webcam found automatically (`facecam.detect_facecam`); `trio`, `grid4`, `ots` provisional; boxes contract in #174 | Verify the provisional three on real footage or drop them | Webcam plus gameplay is the gaming frame | S | #174 | none | Provisional layouts shipped unverified |
| 3.3 | Subject tracking: a crop that follows the action | missing | #174 adds `Panel.path` (a crop that moves); nothing sets a path | Choose the subject per moment, track it, smooth the path, hold on cuts | Third-person character, the car in a chase, the crosshair in a shooter; never crop the kill feed or minimap away when they matter | L | #174, 1.4 | none (local tracking) | Jitter and lost subjects are worse than a still crop; decode cost |
| 3.4 | Layout that switches per scene | partial | `auto` picks per moment (`facecam.moment_facecam`), on only with `PROVISIONAL_LAYOUTS` | Switch inside a clip at scene changes; verify; turn on | Webcam full-frame for the reaction, gameplay for the play | M | #154 scene changes, 3.2 | none | A switch on the wrong frame is jarring |
| 3.5 | Manual control of the boxes | partial | Editor layout and shape chips (#189); draggable boxes are issue #43 | Drag the webcam and crop boxes; pin the subject by hand | Odd overlays and custom webcam frames | M | #189, #174 | none | None new |
| 3.6 | Change the ratio after the fact | have | `POST /v1/clips/export` renders a saved clip with new options (`app/routes_export.py`) | Nothing (the price of a re-export is the owner's open money PR) | One clip, three platforms | – | – | Render seconds | – |

### 2.4 Two ways to create (f34, `opus-producer/`)

| # | Sub-feature | Status | Today | Missing | Gaming angle | Size | Depends on | Per-use cost | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 4.1 | Long video to clips in one flow | partial | Link or upload, clip, edit, export (`app/routes_media.py`, `routes_ingest.py`, #172, #187, #189) | Publish as the last step | Stream VOD in, shorts out | – | Release 4 | – | – |
| 4.2 | Polish footage without clipping | missing | None (`POST /v1/polish` in #185's gap list) | Captions, cleanup and hook on a whole short video | A clip already cut in the game's own recorder | M | export route | Render seconds (money PR) | None new |
| 4.3 | Editor on any range of an upload | missing | The editor opens only on a clip (`POST /v1/clips/manual` in #185's gap list) | Make a clip from a chosen range, no job | "I know the moment, just let me cut it" | S | #189 | none until export | None |
| 4.4 | Raw footage to a finished video by chat | missing | None | A chat that turns requests into edits on the edit document (trim, cuts, captions, layout, B-roll) with undo, and shows the price before any paid step | "Make a 40 s montage of my three best kills with big captions" | L | Release 3 edit operations, 2.4 | One model call per message (section 3): a credit price per message or per session, owner's call | The model edits only through checked operations; user text is data; cost runs away without a cap |
| 4.5 | Recreate another creator's style | defer | None | – | – | – | – | – | Copying a named creator's look invites likeness and trade-dress complaints. Our templates are our own |

### 2.5 Captions (f35 to f37)

| # | Sub-feature | Status | Today | Missing | Gaming angle | Size | Depends on | Per-use cost | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 5.1 | Animated templates | partial | Twelve styles (`app/pipeline/captions.py`, `CaptionStyle` in `app/render_options.py`); active-word pop and gaming keywords in #180; presets as data is issue #48 | Twenty or more presets as data with a preview each; per-game sets | Kill counts, names and game terms as the highlighted word | M | #178, #180 | none | A new preset must pass the #178 checks |
| 5.2 | Captions adapt to ratio and layout | partial | `caption_position` and the seam rule (`layouts.caption_y`); measurable checks #178; off the HUD, webcam and head #182 | Merge the stack; HUD regions measured per game | Never cover the minimap, health or kill feed | S | #174, #178, #182 | none | HUD table empty until measured |
| 5.3 | Font family | missing | One bundled font, Anton (`app/fonts/`), plus the server's default | A set of bundled open-licence fonts and a `caption_font` option | Heavy display faces read on busy gameplay | S | #178 | none | Each font's licence file ships with it |
| 5.4 | Weight, size, italic, underline, case | missing | Fixed per style | Options with limits; the #178 checks run for every allowed value | Bigger text for mobile shooters, smaller for UI-heavy games | S | 5.3 | none | Long words overflow at large sizes |
| 5.5 | Colours | partial | `caption_accent` only (`app/render_options.py`) | Text, outline and highlight colours; contrast check | Team or brand colours | S | 5.3 | none | Unreadable colour pairs |
| 5.6 | Upload a custom font | missing | None (issue #51; "Caption fonts" in #185's gap list) | Upload, validate, store per account, use at render | A streamer's channel font | M | 5.3, additive migration for brand assets | none (storage) | A font file is untrusted input to the renderer; the user must confirm they hold the licence |
| 5.7 | Emoji | missing | Not built: the subtitle renderer draws no colour emoji (PARITY.md section 6) | Emoji drawn as images over the caption, from an open-licence set | Skull, fire and crying-laughing are the gaming caption staples | M | #178, #182 | none | Emoji set licence; placement over the HUD |
| 5.8 | Languages and translated captions | partial | 99 spoken languages, translation off by default (`app/languages.py`, `app/pipeline/translate.py`) | Owner's provider pick; burn translated lines | Non-English streamers; English subtitles for a wider audience | S | Owner decision | Translation per use (PARITY.md decisions) | Money |
| 5.9 | Censor list and brand vocabulary | partial | Built-in swear mask (`app/pipeline/censor.py`) | An account's own word list; proper nouns handed to transcription | Gamertags, server names and RP character names | S | #188 | none | None |

### 2.6 Text-based editing (f38)

| # | Sub-feature | Status | Today | Missing | Gaming angle | Size | Depends on | Per-use cost | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 6.1 | Edit words | partial | `caption_lines` in the edit document (`ClipEditDoc`, `app/exports.py`): a line's time is shared evenly between its words | Word-level edits that keep each word's own time | Fix a misheard gamertag | S | #189 | none | None |
| 6.2 | Split and trim | partial | `trim` and `cuts` (`ClipEditDoc`); timeline and transcript cut in #189 | Split one clip into two | Two kills in one clip become two shorts | S | #189 | none until export | None |
| 6.3 | Add emoji at a word | missing | None | An emoji tied to a word's time | See 5.7 | S | 5.7 | none | – |
| 6.4 | Highlight chosen words | missing | The keyword is picked automatically (#180) | The user marks words; colour per mark | Mark the number, the name, the insult | S | #180 | none | None |
| 6.5 | B-roll at a word range | missing | None | A range of the edit document shows other media: first the user's own uploads or another part of the same source | Replay of the kill, the map, the other player's view | M | additive edit-document field, render | none for own media; generated or stock is Release 5 | Rights in third-party media |
| 6.6 | Remove caption only | partial | Lines can be rewritten; hiding a range without cutting is untested | A `hidden` range on captions | Hide captions over a cutscene | S | #189 | none | None |
| 6.7 | Remove caption and video | have | `cuts` (`ClipEditDoc`), rendered exactly (`app/exports.py`) | Nothing | Cut the dead walk between fights | – | – | – | – |
| 6.8 | Add a section | partial | `trim` may reach outside the clip's first cut | Add a separate part of the source to the clip | Setup and payoff minutes apart | S | 6.2 | none until export | None |

### 2.7 Feature grid (f39) and the livestreamer page (f40 to f42)

| # | Sub-feature | Status | Today | Missing | Gaming angle | Size | Depends on | Per-use cost | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 7.1 | AI clipping | have | `POST /v1/clips`, `run_pipeline` (`app/pipeline/__init__.py`) | The north-star targets (SPEC.md section 14) | Built for gameplay plus a webcam | – | Release 0 | – | – |
| 7.2 | AI captioning | have | `POST /v1/captions` (`app/pipeline/tools.py`) | See 2.5 | – | – | – | – | – |
| 7.3 | Publish to social accounts | missing | None (issues #57, #58) | Connect accounts; post now | Shorts, TikTok and Reels are where gaming clips live | L | Platform approvals (#57), the publishing agent's `docs/publishing.md` | none (platform APIs are free; review takes weeks) | Platform review; tokens are secrets; each platform's posting rules |
| 7.4 | Schedule and calendar | missing | None (issue #59) | Post at a time; calendar; cancel | Post while the stream is still talked about | M | 7.3 | none | A missed or duplicate post |
| 7.5 | One click to several channels, bulk schedule | missing | None | Fan out one clip; schedule a batch | 40 clips from one stream across a week | M | 7.4 | none | Rate limits per platform |
| 7.6 | Generated B-roll | missing | None (issue #56) | Generate a short insert from a prompt | Low: gameplay is the picture | M | 6.5 | Generated video: price not confirmed (section 3) | Cost; made-up footage inside a gameplay clip can mislead; provider terms |
| 7.7 | Stock B-roll | missing | None (issue #56) | Search and insert stock video | Low for the same reason | S | 6.5 | Pexels API: free with attribution and limits (section 3) | Their rule against rebuilding their core search; attribution |
| 7.8 | AI voiceover: hook voice, narration | missing | On-screen hook text only (`hook_overlay`, 13 styles); voice is issue #53 | Speak the hook; later a narration track | A hyped one-line intro over the first two seconds | M | 6.5 audio track, owner's provider pick | Text to speech (section 3) | Voice cloning is out: stock voices only; label synthetic voice where platforms ask |
| 7.9 | Dubbing | missing | None | Translate and re-voice a clip | Reach non-English audiences | L | 5.8, 7.8 | Dubbing per minute (section 3) | Sends the streamer's voice to a provider: terms first; quality on shouted speech |
| 7.10 | Analytics | missing | None | Views, likes and retention per posted clip; which moments perform | Feed real outcomes back to ranking (the deferred learned ranker) | M | 7.3 | none (the same platform APIs) | Extra scopes at review |
| 7.11 | Remove filler words | have | `edit.filler_spans`, `tighten` option | A user-visible list and undo in the editor (issue #44) | – | S | #189 | none | – |
| 7.12 | Remove pauses | have | `edit.silences`, `speech_gaps`, `select_cuts` (never over 35% of a clip) | Same as 7.11 | Dead air between fights | S | #189 | none | – |
| 7.13 | Enhance audio | partial | Loudness to platform level with a limiter (`render.loudness_filter`) | Noise reduction, voice clarity, game-audio ducking under speech (issue #52) | Keyboard clatter, fan noise, game audio drowning the voice | M | – | none locally; hosted voice isolation optional (section 3) | Artefacts on gunfire and music; hosted sends audio out |
| 7.14 | AI reframe tool | have | `POST /v1/reframe` | See 2.3 | – | – | – | – | – |
| 8.1 | Stream sources | partial | Twitch and Kick VOD and clip links, direct links, Drive and Dropbox share links, uploads (`app/ingest/`, #172, #175); recordings from any streaming tool arrive as uploads | The site lists only sources verified to work | Twitch and Kick first | S | #172, #175 | none | The ingestion rule in CLAUDE.md; #192's note on Twitch's developer agreement |
| 8.2 | Live clipping | missing | Design only (#192; issues #65 to #68) | Stage 2 after the owner's answers in that doc | Clips while the stream is live | L | #192 | Live minutes (money) | In #192 |
| 8.3 | Creator showcase and statistics on the site | partial | Site media credited to each creator (#190); invented numbers removed (#193) | A showcase only of creators who agreed; statistics only from our measurements | Gaming creators, not podcasts | S | Owner supplies permissions | none | Section 0 rules |
| 8.4 | Call-to-action overlay | missing | None | A text or image card at a chosen time | "Live on Twitch every night", follow prompts | S | 6.5 overlay track | none | Platform rules on promotional overlays |
| 8.5 | Intro and outro | missing | None (issue #51) | Per-ratio intro and outro clips joined at render | Channel sting | M | 5.6 brand assets | Render seconds | Uploaded media is untrusted input |
| 8.6 | Brand kit | partial | Saved looks (`/v1/templates/custom`, #188) | Logo, fonts, intro, outro, per-ratio layout, default kit | Channel identity across 40 clips | M | additive migration | none | – |
| 8.7 | AI hook text | have | `hook_overlay`, `hook_style`, `hook_position` (`app/render_options.py`); copy checks #179 | Not tried with the real judge | – | – | #153, #179 | Included | – |
| 8.8 | Import, edit and schedule on a timer | missing | None (SPEC.md 4.6) | When a stream ends: import, clip, queue for review or post | The north-star flow | L | 7.4, 8.1, a credit cap | Credits per run (money) | Spending without a person present: cap and confirm |
| 8.9 | AI thumbnails | partial | Best frame with hook text #138; generated option #152 | Merge; owner's OK on the price | Thumbnail from the kill frame | – | #138, #152 | In #152 | In #152 |
| 8.10 | Music | missing | None | A licensed library or the user's own track | Montages | M | 2.4 | Licence fee or per-song generation (section 3) | Music rights are the top takedown cause on every platform |
| 8.11 | Team workspace | defer | – | – | – | – | – | – | SPEC.md section 11 |
| 8.12 | Public API | have | Every route under `/v1`; the site uses the same API | Response models in OpenAPI (#185's gap list) | Agents and tools for clip channels | S | – | – | – |

### 2.8 Counts

| Status | Rows |
|---|---|
| have | 10 |
| partial | 29 |
| missing | 28 |
| defer | 2 |
| Total | 69 |

Counted with `grep -c` on the status column of the tables above.

## 3. Paid services: prices and data terms

Read on 2026-11-18 from each provider's own page. SPEC.md section 13 still applies: every non-Claude price is read again in its ticket before approval. Nothing here was signed up for or called.

### 3.1 Prices

| Use | Provider and unit price | Page | Worked cost |
|---|---|---|---|
| AI judge, chat editor | Claude Haiku 5.5 (the configured `ai_model`): $0.10 per million input tokens, $0.50 per million output tokens, for prompts up to 100,000 tokens | platform.claude.com/docs/en/about-claude/pricing | Already in use; cost per job is reported by the judge PRs |
| Video read by a model | Gemini API, paid tier: `gemini-3.5-flash-lite` $0.30 per million input tokens (text, image, video, audio); `gemini-3.6-flash` $0.75, rising to $1.50 on 2027-01-01. Their video guide: about 100 tokens per second of video at the default low resolution, about 300 at high | aistudio.google.com/docs/pricing, aistudio.google.com/docs/video-understanding | One source minute at low resolution is about 6,000 tokens: $0.0018 at $0.30, $0.0045 at $0.75, $0.009 at $1.50. A 2-hour VOD: $0.22, $0.54, $1.08. Forty 60-second candidates only: about 240,000 tokens, $0.07 at $0.30 |
| Text to speech | ElevenLabs API: Flash or Turbo $0.04 per 1,000 characters; Multilingual v2 and v3 $0.08. OpenAI: `tts-1` $15 and `tts-1-hd` $30 per million characters | elevenlabs.io/pricing/api, developers.openai.com/api/docs/pricing | An 80-character hook: $0.0032 to $0.0064 (ElevenLabs), $0.0012 to $0.0024 (OpenAI). A 900-character narration: $0.036 to $0.072, or $0.0135 to $0.027 |
| Dubbing | ElevenLabs: v1 $0.33 per minute with a watermark, $0.50 without; v2 $2.20 per minute | elevenlabs.io/pricing/api | A 60-second clip: $0.50 or $2.20 |
| Voice isolation | ElevenLabs: $0.12 per minute | elevenlabs.io/pricing/api | A 60-second clip: $0.12. Local noise reduction costs nothing per use |
| Stock B-roll | Pexels API: free; 200 requests an hour and 20,000 a month by default; a prominent link to Pexels is required; "You may not copy or replicate core functionality of Pexels" | pexels.com/api/documentation | $0. Ask Pexels in writing whether a B-roll picker inside an editor is allowed |
| Generated music | Gemini API `lyria-3-clip-preview`: $0.04 per 30-second clip; `lyria-3-pro-preview`: $0.08 per song (both preview models) | aistudio.google.com/docs/pricing | $0.04 per montage. Commercial-use terms of the output not read |
| Generated video (B-roll) | Not confirmed. No per-second price for a video model was found on the pages read | – | Price it in its own ticket before any estimate is used |
| Hosted transcription, diarization | In #167 (Groq, Deepgram, AssemblyAI) | – | In #167 |
| Generated thumbnails | In #152 | – | In #152 |
| Publishing and analytics | Platform APIs carry no per-call fee | The publishing agent's `docs/publishing.md` | $0; the cost is review time and quota |

**What a credit is worth** (PARITY.md section 6, plans in `app/plans.py`): $0.023 to $0.032 at monthly prices, $0.0096 to $0.0117 billed yearly. A price in credits that covers a cost at the monthly rate can lose money at the yearly rate; every proposal in section 6 is checked against $0.0096.

### 3.2 Data terms

| Provider | What their page says | Customer footage or audio allowed |
|---|---|---|
| Anthropic API | "By default, we will not use your inputs or outputs from our commercial products" to train; feedback a user sends is the exception (privacy.claude.com article 7996868) | Yes (in use for transcripts and prompts) |
| Google Gemini API, paid tier | "Google doesn't use your prompts" or "responses to improve our products"; prompts and responses are logged for a limited period for abuse detection (terms effective 2026-03-23). The unpaid tier is used to improve products and may be read by human reviewers | Paid tier only. A free-tier key must never be configured. #152 already sends `store: false` |
| ElevenLabs | Terms updated 2026-10-09: section 4(d) licenses content, input and output, "to improve the Services"; section 4(i) lets an account opt out of training in its "Data use" menu, for content from then on | Not by default. Text we wrote (a hook line) only with the opt-out set. The streamer's audio (dubbing, voice isolation) only after the opt-out or a contract term is confirmed in writing |
| OpenAI API | Not read for this plan | No, until its terms are read in the ticket |
| Black Forest Labs | Removed by the owner on 2026-11-18 because its policy allows training on inputs (#152) | No |
| Groq, Deepgram, AssemblyAI | Per-request opt-outs and deletion are in #167 | As decided in #167 |
| Pexels | Nothing of ours is sent except the search words | Yes; a search made from a transcript should send only the words the user typed |

## 4. Roadmap

Releases are ordered by dependency. Each PR goes into `staging`, under 400 changed lines, with tests; hosted CI is off, so each PR shows local test output (#170). Selection PRs report precision@20, precision@40 and recall on eval set v2 (`clip-api/eval/`), with the held-out video as totals only. Speed PRs report `scripts/job_timings.py` before and after.

**Thresholds below are acceptance targets proposed here, not measurements.** The first ticket of each release records the baseline; the owner may move a target once the baseline is known.

### Release 0: finish the north-star tracks (in flight, no new tickets)

| Piece | PRs and issues | Owner |
|---|---|---|
| Speed | #95, #97, #98, #99; #167 (hosted transcription); #175 (uploads) | Speed agents |
| Understanding | #139 (U1), #154 (U2), #137 (U3), #153 (U4), #177 (per-game weights), #104 (U5), #138 and #152 (U7) | Engine agent (A) |
| Captions | #178, #180, #182, #179 (copy) | Captions agent (B) |
| Reframing | #174 | Reframing agent (B) |
| Rendering | #176, #181 | Render agent (B) |
| Website | #183 to #191, #193 | Website agents (D) |

- **Done when:** the stacks above are merged and SPEC.md section 14's eval and timing reports exist for the merged tree.
- **Quality check:** the numbers each of those PRs already names. Nothing new is defined here.

### Release 1: understanding you can see and steer (features 1 and 2)

What the user gets: each clip says what happens in it, a typed prompt changes which moments are found, and matching moments can be joined into one video.

| Step | Ticket (section 5) | Owner | Parallel with |
|---|---|---|---|
| a | R1-1 (#197) prompt benchmark and labels | QA agent (H), owner labels | everything |
| b | R1-2 (#198) scene record on each moment | Engine agent (A), on #154 | c, d |
| c | R1-3 (#199) named sound events | Engine agent (A), on #154 | b, d |
| d | R1-4 (#202) text read inside HUD regions | Engine agent (A) with reframing (#174) | b, c; needs R2-2 (#201), which therefore starts with Release 1 |
| e | R1-5 (#203) the prompt changes nomination | Engine agent (A), on #137 and #153 | after b |
| f | R1-6 (#204) compilation from chosen clips (money) | Render agent (B) | b to e |
| g | R1-7 (#205) tags, quick picks and source markers on the site | Website agent (D) | after b |

**Acceptance criteria**
- Every clip object carries a `scene` record whose fields are each either measured or null; no field is filled by a guess.
- A prompt changes at least one nominated candidate on the benchmark videos, and a job with no prompt nominates the same candidates as before, byte for byte.
- A prompt never changes the number of judge calls or the price of a job (a test asserts the call count), unless a money PR says otherwise.
- A compilation is quoted before it renders, reserved once and settled once; every failure path refunds, with a test.

**Tests**
- Unit tests per signal on fixtures, including the absent case (no HUD table for the game, no audio track).
- A prompt-injection test: a prompt or transcript line that looks like instructions changes no field outside the ratings and nominations.
- Ledger tests for the compilation path: success, failure, timeout, cancel, worker loss.

**Measurable quality check**
- Prompt benchmark (R1-1): a fixed list of gaming prompts over the eval videos, with the owner's labels of which moments match. Report precision@10 and recall per prompt, before and after R1-5. Target: recall up on at least 7 of 10 prompts and precision@10 down on none, on the tuning videos; held-out video as totals only.
- Scene record: against hand labels on 60 moments from the six game videos in `~/ClutchClips-eval/`, each field's precision. Target 0.9 for any field shown to users; a field under it is stored but not shown.
- Text read: exact-match rate on labelled kill-feed and banner frames. Target 0.9 before events from it feed ranking.
- No regression: precision@20, precision@40 and recall on eval set v2 with no prompt.

### Release 2: reframing that follows the action, and a caption studio (features 3 and 5)

| Step | Ticket (section 5) | Owner | Parallel with |
|---|---|---|---|
| a | R2-1 (#200) reframing benchmark with labelled subject boxes | QA agent (H), owner labels | everything |
| b | R2-2 (#201) HUD regions measured per game | Reframing agent (B), follow-up to #174 | c, e |
| c | R2-3 (#206) a crop path that follows the subject | Reframing agent (B), on #174 | e, f |
| d | R2-4 (#207) layout switches at scene changes | Reframing agent (B) | after c |
| e | R2-5 (#208) caption font, weight, size, colour, italic, underline, case | Captions agent (B), on #178 | b, c |
| f | R2-6 (#209) upload a custom font | Captions agent (B), orchestrator for the migration | after e |
| g | R2-7 (#210) emoji drawn as images | Captions agent (B) | after e |
| h | R2-8 (#211) caption studio and ratio switch on the site | Website agent (D) | after e |

**Acceptance criteria**
- A tracked crop is used only when the tracker's confidence holds for the whole clip; otherwise the clip renders with the still crop it has today.
- Every caption option has limits in `GET /v1/options`, and `scripts/caption_checks.py measure` (#178) exits 0 for every allowed value on the six eval videos.
- An uploaded font is parsed and checked before it is stored, is never executed, is private to its account, and is deleted by the takedown and account-deletion flows.
- No option here changes what a job costs.

**Tests**
- Golden-graph tests: a clip with no path renders the same filter graph as today.
- Path tests on synthetic video with a known moving box: lag, overshoot and hold across a cut.
- Font upload: oversized, malformed, wrong type, and a font with no glyphs for the caption text.
- Constant 30 fps (#176's test) on every new render path.

**Measurable quality check**
- Reframing benchmark (R2-1): hand-labelled subject boxes on clips from the six game videos. Report the share of frames where the subject box is at least 90% inside the crop, and the crop's peak acceleration (jitter), for the still crop (baseline) and the tracked crop. Target: subject-in-frame up on every game with no game worse on jitter than a bound the baseline sets; a game that misses keeps the still crop.
- HUD: overlap of captions with labelled HUD boxes (`scripts/caption_eval_boxes.json`, #178) is zero with the measured table.
- Captions: the #178 numbers (word timing error, dead air, reading speed, HUD overlap) inside their limits for every font and size offered.
- Speed: preview render time per clip within 10% of today's on `scripts/job_timings.py`, or the tracked crop is export-only.

### Release 3: text-based editor and audio cleaning (feature 6, part of 7)

| Piece | Rows | Owner | Existing tickets |
|---|---|---|---|
| Word-level edits, split, highlight, hide caption, add a section | 6.1 to 6.4, 6.6, 6.8 | Website agent (D) with render agent (B) for the edit document | #41, #42, #44 |
| Overlay and insert track: own-media B-roll, call-to-action card | 6.5, 8.4 | Render agent (B) | – |
| Editor on any range; polish without clipping | 4.2, 4.3 | Engine agent (A), website agent (D) | #185 gap list |
| Noise reduction, voice clarity, ducking | 7.13 | Render agent (B) | #52 |
| Custom censor list, brand vocabulary | 5.9 | Engine agent (A), website agent (D) | #188 |

- **Acceptance criteria:** every edit is an operation on `ClipEditDoc` in source seconds; saving is free; an export of an edited clip matches its edit exactly (cut times within one frame); undo restores the previous document.
- **Tests:** edit-document round trips; export golden tests per operation; the site's API contract test (#185) covers each new field.
- **Quality check:** audio: on `~/ClutchClips-eval/bench-audio`, speech level against noise level before and after, and word error rate of the transcript before and after cleaning (cleaning must not raise it). Editing: a scripted set of 20 edits renders to the expected cut list. Runs in parallel with Release 2.

### Release 4: publish, schedule, calendar, analytics (feature 7; f42)

| Piece | Rows | Owner | Existing tickets |
|---|---|---|---|
| Platform apps and review | 7.3 | Owner | #57 |
| Connect accounts, post now | 7.3 | Publishing agent (E), `docs/publishing.md` | #58 |
| Schedule, calendar, cancel, bulk schedule, several channels | 7.4, 7.5 | Publishing agent (E), website agent (D) | #59 |
| Analytics read | 7.10 | Publishing agent (E) | – |
| Brand kit: logo, intro, outro | 8.5, 8.6 | Render agent (B), website agent (D) | #51 |

- **Acceptance criteria:** tokens are stored encrypted and never logged; a post is sent once (idempotency key per clip, account and time); a platform appears only when its app is configured and approved; a failed post is reported with the platform's reason and can be retried.
- **Tests:** each platform client against recorded responses; scheduler tests with a fake clock (missed tick, restart, duplicate tick); revoke and reconnect.
- **Quality check:** on a test account per platform, 20 scheduled posts land once each, inside one minute of their time. This release is blocked by platform review, not by Releases 1 to 3; the owner can start #57 today.

### Release 5: paid AI extras (B-roll, voiceover, dubbing, music)

Rows 7.6 to 7.9 and 8.10. Every item is a money PR and waits for the decisions in section 6.

- **Acceptance criteria:** a quote before every use; reserve once, settle once; refund on every failure path, with tests; the provider adapter is behind a setting that is off by default with a local or own-media fallback; no customer media goes to a provider that section 3.2 does not allow.
- **Tests:** provider fully mocked; ledger tests per failure path; a test that the disallowed-provider setting refuses to start in production.
- **Quality check:** voiceover: the owner rates 30 hook lines per voice, and words are checked against the hook text by transcribing the result. Dubbing: only after a pilot on 10 clips the owner rates.

### Release 6: the chat editor (feature 4)

Row 4.4. Depends on Release 3's edit operations and Release 1's compilation.

- **Acceptance criteria:** the model can only call checked edit operations; every paid step shows its price and waits for a click; a session has a credit cap; undo works per message.
- **Quality check:** a fixed list of 30 requests on the eval clips ("cut the first five seconds", "make the captions yellow", "montage of the three best kills"); each is scored done or not done against the resulting edit document. The owner sets the pass rate.

### Release 7: live and automatic runs

Rows 8.2 and 8.8. Owned by the live agent under #192 and its issues (#65 to #68); automatic runs after a stream ends need Release 4 and a credit cap (money). Not re-planned here.

### Running through every release: an honest site

Rows 8.1 and 8.3. Owned by the website agents (#183 to #193).

- The platform row lists only sources verified to import.
- Statistics appear only with a measurement behind them (script, footage, date).
- A creator appears only with permission, and as a customer only if they are one.
- Every unbuilt feature shows "Coming soon".

### Order and what runs side by side

| Order | Release | Can run alongside |
|---|---|---|
| 0 | North-star tracks | – |
| 1 | Understanding and prompt | Release 2, Release 3, owner's platform applications (#57) |
| 2 | Reframing and caption studio | Release 1, Release 3 |
| 3 | Text editor and audio cleaning | Releases 1 and 2 |
| 4 | Publishing and analytics | Anything, once the platforms approve |
| 5 | Paid AI extras | After Release 3's overlay track and the owner's decisions |
| 6 | Chat editor | After Releases 1 and 3 |
| 7 | Live and automatic runs | Its own track (#192) |

File ownership follows `docs/CONTRACTS.md`. Two agents never edit the same file in the same release: the engine agent owns `app/pipeline/__init__.py`, `signals.py`, `timeline.py` and `app/ai.py`; the render agents own `layouts.py`, `captions.py`, `render.py`; migrations and `app/models.py` are the orchestrator's.

## 5. Draft tickets for Releases 1 and 2

Format: `docs/agents/issue-tracker.md`. Reference screenshots are a competitor's pages and are not embedded.

| Ticket | Issue |
|---|---|
| R1-1 | #197 |
| R1-2 | #198 |
| R1-3 | #199 |
| R1-4 | #202 |
| R1-5 | #203 |
| R1-6 | #204 |
| R1-7 | #205 |
| R2-1 | #200 |
| R2-2 | #201 |
| R2-3 | #206 |
| R2-4 | #207 |
| R2-5 | #208 |
| R2-6 | #209 |
| R2-7 | #210 |
| R2-8 | #211 |

Issues #197 to #211 were created on 2026-11-18 with the board's labels (`feature`, plus `track:understanding` for Release 1, `phase:2` for Release 2, `money` on R1-6). No issue exists for Releases 3 to 7 beyond the older tickets cited in section 4.

### R1-1 · #197 · 🧪 [test] understanding: prompt benchmark with owner labels

Labels: `feature`, `track:understanding`

#### Problem
Nothing measures whether a typed prompt finds the right moments. A prompt change today is judged by eye.

#### Context
- **Where:** `clip-api/eval/`, `clip-api/scripts/eval_clips.py`
  - a. The owner picks 10 gaming prompts (for example "police chases", "clutch wins", "when I rage").
  - b. The owner marks, per eval video, which labelled moments match each prompt.
  - c. A script scores a job run with a prompt against those labels.
- **Who:** the owner and every agent changing prompt clipping
- **Plan:** `docs/parity-opusclip.md`, Release 1, ticket R1-1

#### Fix
Add `eval/prompts-v1.csv` (prompt, video, moment, match) and a `--prompt` mode in `eval_clips.py` that prints precision@10 and recall per prompt; the held-out video prints totals only.

#### Acceptance Criteria
- [ ] `eval_clips.py --prompt` prints precision@10 and recall for each prompt from a saved run, with hit and label counts
- [ ] The held-out video's rows are never printed without `--show-held-out`
- [ ] A labelling page or sheet lets the owner mark matches without editing CSV by hand
- [ ] The baseline (staging with `prompt` set) is saved under `eval/runs/` and reported in the PR

#### Risk
🟢 **Low** · eval files and a script; no product code.

#### Blocked by
- #105 — the eval videos and labels it builds on

### R1-2 · #198 · ✨ [feature] understanding: scene record on every moment

Labels: `feature`, `track:understanding`

#### Problem
A clip says why it scored but not what happens in it. The user cannot see who or what is on screen, the sound, or the kind of scene.

#### Context
- **Where:** `app/pipeline/__init__.py`, `app/pipeline/timeline.py`, clip object in `app/routes_media.py`
  - a. A VOD is clipped.
  - b. The user opens a clip and reads its reason.
- **Who:** every clipper
- **Plan:** `docs/parity-opusclip.md`, Release 1, ticket R1-2

#### Fix
Store `features.scene` per candidate from signals we already compute: scene type, webcam present, speech share, loudness peak, laughter bursts, standby share, picture-change rate. Return it as `scene` on the clip. A field that was not measured is null.

#### Acceptance Criteria
- [ ] Every clip returns `scene` with the listed fields; each is a measured value or null (test with a silent source and a source with no webcam)
- [ ] No new decode: the record is built from the timeline and frames the job already read (stage timings unchanged within 2%)
- [ ] A job's candidates, ratings and price are identical with the record on or off
- [ ] Against 60 hand-labelled moments, each field's precision is reported in the PR

#### Risk
🟢 **Low** · additive JSON in `clips.features`; no schema change.

#### Blocked by
- #101 — the per-second timeline (PR #154) it reads

### R1-3 · #199 · ✨ [feature] understanding: named sound events on the timeline

Labels: `feature`, `track:understanding`

#### Problem
The timeline knows how loud a second is, not what the sound is. Gunfire, explosions, sirens and crashes mark gaming moments before anyone speaks.

#### Context
- **Where:** `app/pipeline/timeline.py`
  - a. A VOD with a shootout and no speech is clipped.
  - b. The shootout is ranked on loudness alone.
- **Who:** every clipper; strongest for GTA and shooters
- **Plan:** `docs/parity-opusclip.md`, Release 1, ticket R1-3

#### Fix
Add a local sound-event signal (gunfire, explosion, siren, crash, scream) from the audio already extracted, off by default with weight 0 until measured.

#### Acceptance Criteria
- [ ] Each event class has a per-second value on the timeline and a count in `scene`
- [ ] The model runs locally; no audio leaves the server (test: no network call)
- [ ] With weight 0 a job's candidates are byte-identical to today
- [ ] Precision and recall per class on labelled seconds of the six game videos are in the PR, and a weight is proposed only for a class at 0.9 precision or better
- [ ] Added time on the 2-hour benchmark is reported with `scripts/job_timings.py`

#### Risk
🟡 **Medium** · a new model in the image (size, licence, CPU time); game music can read as events.

#### Blocked by
- #101 — the timeline (PR #154)

### R1-4 · #202 · ✨ [feature] understanding: read on-screen text in HUD regions

Labels: `feature`, `track:understanding`

#### Problem
No text on screen is read. Kill feeds, mission banners and "wasted" or "busted" cards are exact, timestamped events we ignore.

#### Context
- **Where:** `app/pipeline/layouts.py` (`HUD_REGIONS`), new `app/pipeline/screen_text.py`
  - a. A GTA VOD is clipped with a game template.
  - b. A kill-feed line appears; nothing records it.
- **Who:** clippers of games with a measured HUD table
- **Plan:** `docs/parity-opusclip.md`, Release 1, ticket R1-4

#### Fix
Read text with a local OCR model on sparse frames, only inside the game's measured HUD regions, and write events (`text`, `region`, `t`) to the timeline. An unknown game reads nothing.

#### Acceptance Criteria
- [ ] A game with no HUD table produces no events and adds no decode (test)
- [ ] Events carry the region, the time and the text; they appear in `scene.text_events`
- [ ] Exact-match rate on labelled kill-feed and banner frames is reported; events feed ranking only at 0.9 or better (weight 0 until then)
- [ ] Added time on the 2-hour benchmark is reported with `scripts/job_timings.py`

#### Risk
🟡 **Medium** · stylised game fonts read badly; decode cost on long VODs; a new local model.

#### Blocked by
- #201 — the measured HUD regions per game

### R1-5 · #203 · ✨ [feature] understanding: a prompt changes which moments are found

Labels: `feature`, `track:understanding`

#### Problem
A typed prompt only moves ratings among candidates already chosen. A moment the signals did not nominate is never found, whatever the user asks for.

#### Context
- **Where:** `POST /v1/clips` option `prompt`; `app/pipeline/llm_pass.py`, `app/pipeline/__init__.py`
  - a. The user types "every police chase".
  - b. The job nominates the same candidates as with no prompt.
- **Who:** every clipper who types a prompt
- **Plan:** `docs/parity-opusclip.md`, Release 1, ticket R1-5

#### Fix
Hand the prompt to the transcript pass (PR #137) and to the visual index so matching moments are proposed, inside the existing candidate budget.

#### Acceptance Criteria
- [ ] With a prompt, at least one nominated candidate differs on the benchmark videos; with none, nominations are byte-identical to before
- [ ] The number of AI calls and the job's price do not change (test asserts the call count)
- [ ] A prompt or transcript line written as instructions changes nothing but nominations and ratings (test)
- [ ] Prompt benchmark: recall up on at least 7 of 10 prompts and precision@10 down on none, tuning videos; held-out totals reported
- [ ] precision@20, precision@40 and recall on eval set v2 with no prompt are unchanged

#### Risk
🟡 **Medium** · selection change; needs the real judge, which only the owner can run.

#### Blocked by
- #197 — the benchmark that measures it
- #102 — the transcript pass (PR #137)
- #103 — judge v2 (PR #153)

### R1-6 · #204 · ✨ [feature] highlights: join chosen clips into one video

Labels: `feature`, `track:understanding`, `money`

#### Problem
A user cannot turn the kills or fails of a stream into one compilation. Each clip exports alone.

#### Context
- **Where:** Results page bar "Create montage"; new `POST /v1/highlights`, `POST /v1/highlights/quote`
  - a. The user selects clips on the results page (or a prompt selects them).
  - b. The user asks for one video.
- **Who:** every clipper; montage channels
- **Plan:** `docs/parity-opusclip.md`, Release 1, ticket R1-6

#### Fix
`POST /v1/highlights {job_id, clips[], target_sec?}` renders the clips in order with crossfades and one caption style, no music in v1. Priced by the approved re-export rule: reserve the worst case, charge the seconds rendered.

#### Acceptance Criteria
- [ ] `/quote` returns the credits before anything renders, and the charge equals the quote's rule
- [ ] One reserve and one settle (`settle:<job_id>`); failure, timeout, cancel and worker loss each refund once (tests)
- [ ] Output is constant 30 fps with audio in step across joins (the PR #176 test on this path)
- [ ] A `target_sec` trims the weakest clips first and never cuts inside a sentence

#### Risk
🔴 **High** · money path: needs the owner's OK on the price rule in the PR.

#### Blocked by
- #97 — previews first and export on demand (the export route it reuses)

### R1-7 · #205 · ✨ [feature] web: clip tags, prompt quick picks, source markers

Labels: `feature`, `track:understanding`

#### Problem
The results page shows a rating and a reason, not what is in the clip or where it came from in the stream.

#### Context
- **Where:** Results page, `/dashboard/project`
  - a. Open a finished project.
  - b. Look at a clip card and the source timeline.
- **Who:** every signed-in user
- **Plan:** `docs/parity-opusclip.md`, Release 1, ticket R1-7

#### Fix
Show tags from the clip's `scene` record on each card, gaming quick picks under the prompt field, and a marker per clip on the source timeline. A tag appears only when its field is present.

#### Acceptance Criteria
- [ ] A clip with no `scene` shows no tags and no empty row (test)
- [ ] Quick picks come from the template's game; with no template the five general picks show
- [ ] Each clip has a marker at its source time; clicking it selects the clip
- [ ] The API contract test passes and there is no horizontal scroll at 390 px

#### Risk
🟢 **Low** · display only.

#### Blocked by
- #198 — the `scene` record it shows

### R2-1 · #200 · 🧪 [test] reframe: benchmark with labelled subject boxes

Labels: `feature`, `phase:2`

#### Problem
Nothing measures whether a vertical crop keeps the action in frame. Reframing changes are judged by eye.

#### Context
- **Where:** `clip-api/scripts/` (new `reframe_checks.py`), `clip-api/eval/`
  - a. Clips are cut from the six game videos.
  - b. A person marks the subject box on sampled frames.
  - c. A script scores a crop against the boxes.
- **Who:** the owner and the reframing agent
- **Plan:** `docs/parity-opusclip.md`, Release 2, ticket R2-1

#### Fix
Add labelled subject boxes for about 30 clips and a script that reports, per game, the share of frames with the subject at least 90% inside the crop and the crop's peak acceleration.

#### Acceptance Criteria
- [ ] `reframe_checks.py measure` prints both numbers per game for any layout and exits 1 when a limit is broken
- [ ] The labels file records who labelled each clip and from which source seconds
- [ ] The baseline for today's still crop is saved and reported in the PR
- [ ] No third-party footage is committed: labels and source times only

#### Risk
🟢 **Low** · eval files and a script.

#### Blocked by
- #174 — reframe boxes v1 define the crop it reads

### R2-2 · #201 · ✨ [feature] reframe: HUD regions measured per game

Labels: `feature`, `phase:2`

#### Problem
The HUD table is empty, so captions and crops cannot avoid the minimap, health or kill feed.

#### Context
- **Where:** `app/pipeline/layouts.py` (`HUD_REGIONS`, `hud_regions`)
  - a. A clip of a game with a HUD is rendered.
  - b. The caption lands on the minimap.
- **Who:** every clipper
- **Plan:** `docs/parity-opusclip.md`, Release 2, ticket R2-2

#### Fix
Measure HUD boxes on the eval footage for the games we have video of and fill `HUD_REGIONS`; a game without measurements stays empty.

#### Acceptance Criteria
- [ ] Each filled game has boxes measured on at least 20 frames, with the source noted in a comment
- [ ] A game with no measurement returns no HUD (test); nothing is guessed
- [ ] Caption overlap with the labelled HUD boxes is zero on `caption_checks.py measure` for the filled games

#### Risk
🟢 **Low** · data only; HUDs move with game settings and resolution.

#### Blocked by
- #174 — reframe boxes v1

### R2-3 · #206 · ✨ [feature] reframe: a crop that follows the subject

Labels: `feature`, `phase:2`

#### Problem
The vertical crop is still for the whole clip. When the car or character moves across the frame it leaves the picture.

#### Context
- **Where:** `app/pipeline/layouts.py` (`Panel.path`), `app/pipeline/facecam.py`, new `app/pipeline/track.py`
  - a. A chase clip is reframed to 9:16 with the `full` layout.
  - b. The car drives out of the crop.
- **Who:** every clipper using a full-frame layout
- **Plan:** `docs/parity-opusclip.md`, Release 2, ticket R2-3

#### Fix
Find the subject per moment (motion and saliency on sparse frames), track it, smooth the path and write it to `Panel.path`. Use it only when confidence holds for the whole clip; otherwise keep the still crop.

#### Acceptance Criteria
- [ ] A clip with low tracking confidence renders the same filter graph as today (golden test)
- [ ] On synthetic video with a known moving box, the path lags by at most 0.3 s and never overshoots the frame (test)
- [ ] The path holds across a cut and never crops a HUD region marked keep
- [ ] Reframing benchmark: subject-in-frame is higher than the still crop on every game it is turned on for, with jitter inside the baseline bound
- [ ] Preview render time per clip is within 10% of today's, or the path is used on export only

#### Risk
🟡 **Medium** · a jittery or lost crop is worse than a still one; decode cost.

#### Blocked by
- #200 — the benchmark that gates it
- #201 — HUD regions to keep in frame
- #174 — adds `Panel.path`

### R2-4 · #207 · ✨ [feature] reframe: layout switches at scene changes

Labels: `feature`, `phase:2`

#### Problem
A clip keeps one layout from start to end. When the streamer hides the game or the webcam, the frame wastes half its space.

#### Context
- **Where:** `app/pipeline/facecam.py` (`moment_facecam`), `app/pipeline/layouts.py`
  - a. A clip starts on gameplay with a webcam and cuts to a full-screen webcam.
  - b. The split layout stays, with an empty panel.
- **Who:** every clipper using `auto`
- **Plan:** `docs/parity-opusclip.md`, Release 2, ticket R2-4

#### Fix
Let `auto` choose a layout per scene inside a clip, switching only on a detected scene change, and take it out from behind `PROVISIONAL_LAYOUTS` once measured.

#### Acceptance Criteria
- [ ] A clip with one scene renders the same filter graph as today (golden test)
- [ ] A switch happens only on a scene-change frame and never more than once in 2 s (test)
- [ ] Captions and the hook stay inside the #178 limits across a switch
- [ ] On labelled clips with a scene change, the owner's rating of before and after is recorded in the PR

#### Risk
🟡 **Medium** · a switch on the wrong frame is jarring.

#### Blocked by
- #101 — scene changes on the timeline (PR #154)
- #206 — shares the per-clip path in the layout plan

### R2-5 · #208 · ✨ [feature] captions: font, weight, size, colour, italic, case

Labels: `feature`, `phase:2`

#### Problem
A user cannot change how captions look beyond picking a style and one accent colour.

#### Context
- **Where:** `app/render_options.py` (`LayoutOptions`), `app/pipeline/captions.py`
  - a. The user picks a caption style.
  - b. The font, size and colours are fixed.
- **Who:** every clipper; brand kits
- **Plan:** `docs/parity-opusclip.md`, Release 2, ticket R2-5

#### Fix
Add `caption_font` (a bundled open-licence set), `caption_weight`, `caption_size`, `caption_color`, `caption_outline`, `caption_italic`, `caption_underline`, `caption_case` (`upper`, `typed`), each with limits and listed in `GET /v1/options`.

#### Acceptance Criteria
- [ ] Absent options render exactly as today (golden test per style)
- [ ] Each bundled font ships with its licence file, and a test checks the font file against the name
- [ ] `scripts/caption_checks.py measure` exits 0 for every allowed size and font on the six eval videos
- [ ] A colour pair under a set contrast ratio is refused with a 422 that names the limit
- [ ] No option changes a job's price (quote test)

#### Risk
🟢 **Low** · render options; long words can overflow at large sizes.

#### Blocked by
- #178 — the caption checks it must pass

### R2-6 · #209 · ✨ [feature] captions: upload a custom font

Labels: `feature`, `phase:2`

#### Problem
A streamer cannot use their channel's own font in captions.

#### Context
- **Where:** Brand kit page; new `POST /v1/brand/fonts`, `GET /v1/brand/fonts`, `DELETE /v1/brand/fonts/{id}`
  - a. Open the brand kit.
  - b. Upload a font file.
  - c. Pick it as the caption font.
- **Who:** every signed-in user
- **Plan:** `docs/parity-opusclip.md`, Release 2, ticket R2-6

#### Fix
Accept TTF and OTF up to a size cap, parse and check them before storing (through `app/storage.py`), keep them private to the account, and accept the font id in `caption_font`. The user confirms they hold the licence. Needs one additive revision (`brand_assets`).

#### Acceptance Criteria
- [ ] A malformed, oversized or wrong-type file is refused with a clear error and nothing is stored (tests)
- [ ] Another account cannot read or use the font (test)
- [ ] Takedown and account deletion remove the font file and its row (tests)
- [ ] A font with no glyph for a caption's characters falls back to the bundled font for that clip and says so in the clip's features
- [ ] The upload records the licence confirmation with account and time

#### Risk
🟡 **Medium** · a font file is untrusted input to the subtitle renderer; additive schema.

#### Blocked by
- #208 — the `caption_font` option
- #51 — brand kit (the `brand_assets` table)

### R2-7 · #210 · ✨ [feature] captions: emoji drawn as images

Labels: `feature`, `phase:2`

#### Problem
Captions cannot show emoji: the subtitle renderer draws no colour emoji.

#### Context
- **Where:** `app/pipeline/captions.py`, `app/pipeline/render.py`
  - a. A caption line should carry a skull or fire emoji.
  - b. Nothing can draw it.
- **Who:** every clipper
- **Plan:** `docs/parity-opusclip.md`, Release 2, ticket R2-7

#### Fix
Bundle an open-licence emoji image set and overlay the image next to its word, timed with the word. `caption_emoji` picks emoji automatically from a fixed word list; the editor can set one per word later.

#### Acceptance Criteria
- [ ] With `caption_emoji` off, renders are unchanged (golden test)
- [ ] An emoji appears and leaves with its word, inside the frame and off the keep-out boxes (test)
- [ ] The emoji set's licence file ships with it
- [ ] Render time per clip with emoji on is reported with `scripts/job_timings.py`

#### Risk
🟡 **Medium** · extra overlay inputs slow the render; licence of the set.

#### Blocked by
- #208 — caption sizing it follows
- #182 — caption placement off the keep-out boxes

### R2-8 · #211 · ✨ [feature] web: caption studio and ratio switch

Labels: `feature`, `phase:2`

#### Problem
The editor offers a caption style list and nothing else. A user cannot set font, size or colours, or see the clip in another ratio before exporting.

#### Context
- **Where:** Editor, `/dashboard/edit`
  - a. Open a clip in the editor.
  - b. Open Captions.
  - c. Look for font, size, colour and case.
- **Who:** every signed-in user
- **Plan:** `docs/parity-opusclip.md`, Release 2, ticket R2-8

#### Fix
Build the Captions panel from `GET /v1/options` (font, weight, size, colours, italic, underline, case, emoji), a font upload control, and 9:16, 1:1, 16:9 chips that re-lay the preview. A control appears only when the API lists its option.

#### Acceptance Criteria
- [ ] A control is absent when `GET /v1/options` does not list its option (test)
- [ ] Changes save to the clip's edit and survive a reload
- [ ] Export waits for a server quote; no price is worked out in the browser
- [ ] The API contract test passes; no horizontal scroll at 390 px

#### Risk
🟢 **Low** · website only.

#### Blocked by
- #208 — the options it shows
- #209 — font upload

## 6. Owner decisions

### 6.1 Paid features and prices

Credit prices are proposals, checked against the lowest credit value ($0.0096, yearly Starter). Nothing is built until the owner answers.

| # | Decision | Options | Recommendation |
|---|---|---|---|
| 1 | Compilation price (R1-6) | The approved rule for re-exports (reserve the worst case, charge the seconds rendered), or a flat price | The approved rule. No new price list |
| 2 | Hook voiceover | Off; a hosted voice at about $0.001 to $0.006 a hook; an open-source voice on our own server | Hosted, stock voices only, 1 credit per voiced clip, if the provider's terms pass section 3.2. One credit covers the cost at every plan |
| 3 | Narration track | Same providers; about $0.014 to $0.072 a minute of speech | Defer until hook voice is used |
| 4 | Dubbing | $0.50 a minute (v1) or $2.20 (v2) at the one provider priced | Defer. At $0.50 a minute the break-even is 53 credits a minute at the yearly rate, and the streamer's voice would go to a provider whose default terms allow training |
| 5 | Generated B-roll | Price not confirmed | Defer. Build own-media B-roll (free) in Release 3 first; gameplay clips rarely need generated inserts |
| 6 | Stock B-roll | Pexels (free, attribution, limits) | Ask Pexels in writing first; then free to the user |
| 7 | Music | The user's own track; a licensed library (fee); generated at $0.04 a clip | The user's own track first, with a rights confirmation. A library is a contract for the owner |
| 8 | Hosted voice isolation | $0.12 a minute, or local noise reduction at no cost | Local only |
| 9 | Video read by a model | Local signals only; candidates only (about $0.07 a 2-hour VOD at $0.30 per million tokens); the whole VOD ($0.22 to $1.08) | Local signals in Release 1. Decide candidates-only after R1's numbers show what local signals miss. Whole-VOD reading costs up to 94% of a yearly credit per minute at the 2027 price |
| 10 | Chat editor price | Per message; per session; included with a cap | Decide at Release 6, from measured tokens per session |
| 11 | Live minutes, automatic runs | In #192 | In #192 |

### 6.2 Providers

| # | Decision | Recommendation |
|---|---|---|
| 12 | Rule: no customer footage, audio or transcript to a provider that may train on it | Adopt as written in section 0; a provider is added only with its terms quoted and dated in the PR |
| 13 | Judge and chat model | Stay on the Anthropic API (in use; no training by default) |
| 14 | A second model provider for frames or video | Google's paid tier is the only one read that qualifies. Decide with decision 9. Never a free-tier key |
| 15 | Text to speech provider | ElevenLabs only with the training opt-out confirmed for API use; otherwise read OpenAI's terms in the ticket, or use a local open-source voice |
| 16 | Diarization and hosted transcription | Decide in #167 |
| 17 | Privacy and Terms wording | Every provider that receives audio, frames or text is named there before it is switched on (#163) |

### 6.3 What to defer

| # | Item | Why |
|---|---|---|
| 18 | Recreate a named creator's style (4.5) | Likeness and trade-dress risk; our templates are our own |
| 19 | Team workspace (8.11) | SPEC.md section 11 |
| 20 | Dubbing, generated B-roll, narration | Decisions 3 to 5 |
| 21 | Any benchmark claim against other products | Section 0 |
| 22 | `trio`, `grid4`, `ots` layouts | Verify on footage in Release 2 or remove from the option list |

### 6.4 What the owner supplies

| # | Item | Needed for |
|---|---|---|
| 23 | Labels for the prompt benchmark (about one hour) | R1-1 (#197) |
| 24 | Subject boxes for the reframing benchmark (about one hour, or approve an agent's boxes) | R2-1 (#200) |
| 25 | Platform developer apps and review (#57) | Release 4 |
| 26 | Written permission from each creator shown on the site | Row 8.3 |
| 27 | The second and third eval videos (`clip-api/eval/README.md`) | Every selection number in Release 1 |
