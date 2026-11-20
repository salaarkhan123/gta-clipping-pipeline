# Agent 7 — Competitive analysis: WayinVideo vs OpusClip (gaming clip workflows)

**Scope:** Research only. No product code, pricing, or PR changes.  
**Date read:** 2026-11-20.  
**Claim labels:** `measured` | `verified` | `inferred` | `hypothesis` | `public-source` | `not measured` (see [RESEARCH.md](../RESEARCH.md)).

## Executive summary

WayinVideo and OpusClip are the two public references ClutchClips is explicitly chasing: Wayin via `docs/PARITY.md` (gaming parity target), OpusClip via `docs/parity-opusclip.md` on `release/step2-candidate` (multimodal understanding, prompt clipping, editor). **Neither competitor’s internal pipeline is public** (`not measured`). Everything below is from their docs, marketing pages, help centre, pricing tables, and our parity artifacts—labeled so product bets do not treat marketing copy as engineering fact.

**Wayin** is the closer **gaming** analogue: per-game templates, Game Clipping UX, gameplay layouts (`Gameplay A` / `Gameplay B`), link ingest breadth, progressive clip metadata while tasks are `ONGOING`, and 1 credit per input minute on the website (`public-source`). Speed claims on their gaming landing page (“under 5 minutes” for long VODs) are **not reproducible here** (`hypothesis` until timed on identical inputs).

**OpusClip** is the broader **speech + multimodal** leader: ClipAnything (visual, audio, sentiment), prompt and reprompt clipping, virality score 0–99, rich transcript editor, object-tracking reframe on Pro+, and a mature publish/schedule stack (`public-source`). Published wall-clock times skew **slower** than Wayin’s marketing (help centre: ~20–40 minutes typical; user guides cite 5–45 minutes) (`public-source`). **Gaming is a genre option and layout feature**, not a separate product surface with per-title templates (`inferred` from pricing + API `genre` field, vs Wayin’s explicit game gallery).

ClutchClips (from `PARITY.md`, swarm run log, `parity-opusclip.md`) sits **between** them on gaming depth (GTA-first templates, partial Wayin parity) and **behind** on editor, publish, tracking reframe, and Opus-style prompt nomination—not on intentional ingest ethics (public-only, no evasion) (`verified` repo rules).

---

## Sources (what this draft used)

| Source | Role | Label |
|--------|------|--------|
| [docs/PARITY.md](../../PARITY.md) | Wayin column from public API + help (2026-11-16); owner screenshots w01–w12 | `verified` (internal doc of `public-source`) |
| [docs/super-board/runs/2026-11-16-swarm.md](../../super-board/runs/2026-11-16-swarm.md) | Swarm decisions, moment benchmark, S1 progressive timing | `verified` |
| `docs/parity-opusclip.md` on `origin/release/step2-candidate` (878 lines) | OpusClip gap matrix and roadmap; read via git, not on `main` | `verified` |
| [Wayin AI Clipping API](https://wayin.ai/api-docs/ai-clipping/) | Ingest URLs, task lifecycle, progressive results, reframe params | `public-source` 2026-11-20 |
| [Wayin Game Clipping help](https://help.wayin.ai/en/articles/15691790-how-to-use-game-clipping) | Gaming UX, timeframe, platforms | `public-source` |
| [Wayin credits](https://help.wayin.ai/en/articles/15913299-how-credits-work) | 1 credit / input minute for clipping tools | `public-source` |
| [Wayin gaming landing](https://wayin.ai/tools/ai-gaming-clip-generator/) | Speed and gaming marketing claims | `public-source` |
| [OpusClip ClipAnything QA](https://help.opus.pro/docs/article/clipanything-qa-4) | Processing time band | `public-source` |
| [OpusClip virality score](https://help.opus.pro/docs/article/virality-score) | Score range and dimensions | `public-source` |
| [OpusClip pricing](https://www.opus.pro/pricing) | Plan features: reframe, tracking, gameplay layout, credits | `public-source` |
| [Opus credits](https://help.opus.pro/docs/article/how-are-credits-consumed) | 1 credit / minute imported; timeframe slider saves credits | `public-source` |
| [Opus API project lifecycle](https://help.opus.pro/api-reference/endpoints/social-posting/overview) | Completion webhook before clips fetch | `public-source` |
| [ClipAnything product page](https://www.opus.pro/clipanything) | Multimodal positioning, reframe alpha copy | `public-source` |

**Not used:** competitor app binaries, paid exports for A/B output, or unreleased APIs (`not measured`).

---

## Side-by-side by product dimension

Legend: **W** = WayinVideo, **O** = OpusClip, **C** = ClutchClips today (from `PARITY.md` / `parity-opusclip.md` unless noted).

### Ingest

| Dimension | Wayin (W) | OpusClip (O) | ClutchClips (C) |
|-----------|-----------|--------------|-----------------|
| Link import | 17+ sources documented (web); API lists YouTube, Twitch, Kick, TikTok, Zoom, etc. (`public-source` API + `PARITY.md`) | Plan-gated: Free YouTube + upload; Starter adds Drive/Vimeo/Zoom…; Pro adds Twitch, Dropbox, Medal, etc. (`public-source` plans doc) | Twitch, Kick, YouTube best effort, Drive/Dropbox public links, upload (`verified` `PARITY.md` §3) |
| Local upload | mp4/mov/webm/avi via upload API; Starter+ for API upload (`public-source`) | Up to 10GB (Free/Starter) or 30GB (Pro); public mp4 URL on Pro (`public-source` pricing) | Upload API; formats wider than Wayin list (`partial` `PARITY.md`) |
| Consent / public-only | Help: links must work signed-out (`public-source`); same class of rule as CLAUDE.md (`inferred`) | YouTube + verified channel auto-import on paid tiers (`public-source`) | Consent log + takedown; no cookies/proxies (`verified` rules) |
| Timeframe / partial source | Game Clipping + API copilot: process segment to save time/credits (`public-source`) | “Processing timeframe” slider; credits on selected minutes only (`public-source`) | Whole video only on jobs (`partial` `PARITY.md`; #117 open) |
| Bulk | 10/30/50 videos by plan on web (`PARITY.md` §6 w11) | Not emphasized in sources read | Bulk import up to 10 links (`partial`) |
| Gaming-specific ingest | Twitch, Kick, Medal called out in Game Clipping help (`public-source`) | Twitch on Pro import list; “Gaming” genre in calculator/category (`public-source`) | Twitch/Kick first (`verified` spec) |

**Hypothesis:** Wayin and Opus likely pull remotely and transcode in their cloud; neither publishes download-first vs stream-analysis architecture (`hypothesis`).

---

### Speed (wall-clock product latency)

| Claim or signal | W | O | C |
|-----------------|---|---|---|
| Published typical time | Marketing: “minutes” / “under 5 minutes” for long gaming VODs (`public-source` landing); help: longer VODs take longer; timeframe reduces work (`public-source`) | Help: **~20–40 minutes** typical for ClipAnything; longer under load (`public-source`); third-party reviews ~7 min for 15 min video (`public-source`, anecdotal) | SPEC §14: 2 h → clips in ≤10 min (stretch 5); **not measured** on current agent VM (`verified` goal, `not measured` proof) |
| Queue / tier | Scale plan: “priority processing” (`PARITY.md` §6); API `enable_express_mode` for Enterprise (API **unit** discount, not documented wall-clock) (`public-source`) | Free “regular”; Starter/Pro “faster”; Business dedicated queue (`public-source` pricing) | `not measured` vs competitors |
| Progressive UX | API: poll `ONGOING` → partial `clips[]` (`public-source`); web doc: results while running (`PARITY.md`) | API: wait for **project-completed** webhook before exportable clips (`public-source`); UI strings: notify when done (`public-source`) | S1: first clip watchable ~41% through run (`verified` swarm); metadata-before-render differs from Wayin (`verified` `PARITY.md`) |
| Render default | API default `enable_export: false` (metadata faster) (`public-source`) | Delivers rendered clips in standard flow (`inferred` from product positioning) | Always renders every clip (`partial` `PARITY.md`) |

**Inference:** Beating Wayin’s **marketing** 5-minute claim and Opus’s **help-centre** 20–40 minute band on a 2-hour gaming VOD requires overlapping ingest, understanding, and progressive output—not a faster ffmpeg pass alone (`inferred`).

---

### Highlights & moment finding

| Dimension | W | O | C |
|-----------|---|---|---|
| Core model | “Video understanding” + game templates (`public-source` landing); Find Moments search (`public-source` credits doc) | ClipAnything: visual + audio + sentiment; prompt / topics / reprompt (`public-source` ClipAnything + pricing) | Pipeline + AI judge; bucket picker; `prompt` moves ratings only today (`verified` `PARITY.md`, `parity-opusclip.md` 2.1) |
| Clip length | API buckets 0–30 … 180–300 s, default 0–90 (`public-source`) | Custom buckets 0–1m … 10–15m; auto up to ~3 min in reviews (`public-source`) | 10–60 s default 30; buckets in flight (#117) (`partial`) |
| Prompt / compile | Web: “what moments to find” + quick picks (`PARITY.md` w08); API prompt surface not in clipping doc read | Prompt to clip, reprompt, topics (Starter+) (`public-source`) | `prompt` option exists; nomination change is **missing** (`parity-opusclip.md` R1-5) |
| Montage / compilation | One-Click Highlights (web product) (`PARITY.md`) | Marketing: compile theme, teaser (`public-source` ClipAnything) | Missing (`PARITY.md`) |
| Non-speech highlights | Claimed via visuals (`public-source` landing) | Explicit “little or no dialogue” (`public-source` ClipAnything) | Loudness/signals partial; named game events missing (`parity-opusclip.md` 1.3, 1.6) |
| Gaming tuning | Per-game templates LoL, GTA, etc. (`public-source` landing + `PARITY.md`) | Genre-specific reframing model + screenshare/gameplay **layout** (`public-source` pricing); no per-game template gallery in sources | 5 GTA templates; 31 templates / 12 games on branch (`partial` swarm #115) |
| Eval vs Wayin moments | — | — | 7/15 Wayin top moments without judge (`verified` swarm); 8 misses documented |

---

### Virality scoring

| Dimension | W | O | C |
|-----------|---|---|---|
| Range | 0–100 on API clips (`public-source`); UI shows high 80s–99s on sample (`PARITY.md` w12) | 0–99; Starter+ only (`public-source` virality help) | Raw 0–100 + `display_score` calibrated per job (`verified` `PARITY.md`) |
| Dimensions | Five on paid (Hook, Story, Value, Engagement, Reach) (`PARITY.md`); API exposes single `score` | Hook, Flow, Value, Trend; prompt relevance when using ClipAnything (`public-source`) | Four parts + reason; five sub-scores in flight (#153) (`partial`) |
| Sort default | “Highest Viral Score” (`PARITY.md` w12) | By virality score (`public-source`) | Rank + tier on site; `display_score` in API (`partial`) |
| Trust | Marketing “viral potential” (`public-source`); **not** verified against outcomes here | Same (`public-source`) | Owner requires measurement before site stats (`parity-opusclip.md` §0) |

---

### Thumbnails

| Dimension | W | O | C |
|-----------|---|---|---|
| Default | Per-clip `thumbnail` URL in API results (`public-source`) | Auto frame; **Edit cover** / upload for publish (Pro+) (`public-source` thumbnail help) | Frame from clip (`done` `PARITY.md`) |
| AI generated | “AI thumbnail” on paid plans (`PARITY.md` pricing table) | API: thumbnail generative job, **7 credits** on success (`public-source` llms index) | Generated path #152 partial (`parity-opusclip.md`) |
| Gaming fit | Not specified in API | Custom cover before social post | Best frame + hook text #138 (`partial`) |

---

### Progressive delivery

| Dimension | W | O | C |
|-----------|---|---|---|
| Metadata-first | Default no render (`public-source` API) | `not measured` whether scores appear before render | Always render (`partial`) |
| Partial results | **`ONGOING` returns clips found so far** (`public-source` API) | API integration: **no** partial fetch documented (`public-source` social posting overview) | Clips surface as renders complete (#111) (`verified` swarm) |
| User implication | Can review/rank before paying render cost (`inferred`) | Batch + email/webhook (`public-source`) | Faster watchable MP4 may lag Wayin metadata (`inferred`) |

---

### Captions

| Dimension | W | O | C |
|-----------|---|---|---|
| Default | Off in API defaults (`public-source`); on in many web flows (`PARITY.md` decisions tension) | On in typical outputs (`public-source` reviews) | On by default (`partial` `PARITY.md`) |
| Styles | 53 templates (4+18+6+25 gaming) (`PARITY.md`) | Many animated templates; emoji/keyword highlights (`public-source` pricing) | 6 styles; `impact` default for gaming (`partial`) |
| Languages | 100 (`PARITY.md`) | 20+ in failure messages; multi-language transcription (`public-source`) | 99 on default Whisper stack (`partial`) |
| Gaming placement | Gaming sets in docs; seam/lower third in screenshots (`PARITY.md` §6) | Adapts to ratio/layout (`parity-opusclip.md` f35–f37) | `impact`, HUD overlap work (#178/#182) (`partial`) |

---

### Edit & re-export

| Dimension | W | O | C |
|-----------|---|---|---|
| Editor depth | Full timeline editor documented (`PARITY.md`) | Text + timeline editing Starter+; filler/pause cleanup (`public-source` pricing) | Clip edit doc partial; no canvas editor (`missing` `PARITY.md`) |
| Transcript-driven | Yes (product) | Core UX (`public-source` reviews) | `caption_lines`, cuts partial (#189) |
| Re-export / bulk | Re-export with new styles (`public-source` API); bulk edit on web (`PARITY.md`) | Brand template, bulk export Pro (`public-source`) | `POST /v1/clips/export` for ratio (`have` `parity-opusclip.md`); no bulk re-render |
| Chat editor | — | Agent Opus / separate product hints (`public-source` llms) | Missing (`parity-opusclip.md` 4.4) |

---

### Reframe & tracking

| Dimension | W | O | C |
|-----------|---|---|---|
| Ratios | 9:16, 1:1, 4:5, 16:9 (`public-source` API) | 9:16 Free; 1:1+16:9 Pro (`public-source` pricing) | Same four (`done` `PARITY.md`) |
| Layouts | Auto, Split 2, Gameplay A/B, etc. (`public-source` API) | Screenshare/gameplay layout; dynamic layout switch (`public-source` pricing) | eleven layouts; provisional trio/grid4/ots (`partial`) |
| Subject tracking | “Keeps main subject centered” when reframe on (`public-source` API); marketing smart hero crop (`public-source` landing) | **Moving object tracking** Pro+; ReframeAnything™ alpha copy (`public-source` ClipAnything + pricing) | Panel paths planned #174; **no** tracking crop yet (`missing` `parity-opusclip.md` 3.3) |
| Gaming split | Gameplay A/B for 9:16 / 4:5 (`public-source`) | Gameplay layout flag, not per-title (`public-source`) | `camera`, `split_ratio` built (`verified` `PARITY.md` §6) |

---

### Gaming detection (product + signals)

| Capability | W | O | C |
|------------|---|---|---|
| Product positioning | **Game Clipping** SKU; template gallery by title (`public-source` + `PARITY.md`) | Gaming as **category** + layout/reframe genre model (`public-source`) | GTA-first; expanding catalogue (`partial` swarm) |
| Detection claims | Game-specific moments (clutch, team fight, etc.) (`public-source` landing) | Multimodal generic; sports examples in marketing (`public-source`) | Judge + templates; HUD OCR/sounds on roadmap (`parity-opusclip.md` 1.3, 1.8) |
| API parity | AI Clipping API ≠ Game Clipping endpoint naming (`public-source` help vs API) | Single clip-projects API with `genre` (`public-source` API schema) | Single `run_pipeline` (`verified`) |
| Verification | Output parity **unverified** (owner declined paid Wayin exports) (`verified` swarm) | No side-by-side run in this research (`not measured`) | Moment overlap 7/15 without judge (`verified` swarm) |

---

### Cost (public pricing only)

| Meter | W | O | C |
|-------|---|---|---|
| Clip processing | **1 credit per input minute** (round up) for AI/Game/Find Moments (`public-source`); API **1 unit/min** (separate wallet) (`public-source`) | **1 credit per imported minute** (round rules in help) (`public-source`) | Credit ledger per job (`verified` rules); live prices Starter $19/600 etc. (`verified` swarm) |
| Plans (monthly anchor) | Starter ~$16 / 500 credits (screenshot `PARITY.md` §6) | Starter $15 / **150** minutes; Pro $29 / **300** (`public-source`) | Owner-confirmed tiers in swarm | 
| Implied $/minute | ~$0.032 Starter monthly (`verified` `PARITY.md` math) | $0.10 Starter, $0.097 Pro at list price (`inferred` from `public-source`) | `not measured` COGS vs either |
| Extra | Express mode: different API unit rate Enterprise (`public-source`); render toggles cost | X post 3 credits; AI thumbnail 7 credits (`public-source`) | Render-always may burn more GPU than W/O metadata-first (`hypothesis`) |

---

## What competitors imply for ClutchClips (research bets, not tickets)

1. **Speed narrative:** Wayin’s public story optimizes for **short wall-clock on long gaming VODs** + **metadata while running**; OpusClip optimizes for **finished social-ready clips** and tolerates longer queues. ClutchClips S1 progressive render is a different trade than Wayin’s `ONGOING` metadata (`verified` + `inferred`).
2. **Gaming moat:** Wayin’s defensible surface is **per-game templates + Game Clipping UX + gameplay layouts**, not raw link count. OpusClip’s is **multimodal prompt clipping + editor + distribution**. ClutchClips must not chase Opus podcast breadth before **game events, HUD text, and prompt nomination** (`parity-opusclip.md` Release 1) (`inferred`).
3. **Virality UX:** Both expose 0–99/100 scores with multi-axis rhetoric; users sort by score. `display_score` calibration is aligned with Wayin UI observations (`verified` `PARITY.md`) but **outcome validation** is missing for all three (`not measured`).
4. **Cost shape:** All three meter on **source minutes**. Metadata-first + optional render (Wayin API default) is the obvious lever to match perceived speed and credit burn (`public-source` + `inferred`); conflicts with owner default decisions in `PARITY.md` until product resolves.
5. **Tracking reframe:** OpusClip and Wayin both **claim** subject tracking in public materials; ClutchClips lists it as a large missing piece (#174 path). This is a visible quality gap on vertical gaming clips (`verified` gap matrix).

---

## Verified vs hypothesis (audit table)

| Statement | Label |
|-----------|--------|
| Wayin API returns partial clips when `status=ONGOING` | `public-source` |
| OpusClip help cites 20–40 min typical ClipAnything processing | `public-source` |
| OpusClip charges 1 credit per imported video minute | `public-source` |
| Wayin website clipping tools charge 1 credit per input minute | `public-source` |
| ClutchClips found 7/15 Wayin benchmark moments without AI judge | `verified` (swarm) |
| Wayin processes any 2 h VOD in &lt;5 min | `hypothesis` (marketing only) |
| OpusClip blog “2–5× faster than competitors” | `hypothesis` (unattributed benchmark) |
| OpusClip uses the same multimodal stack described on marketing pages | `hypothesis` (no architecture doc) |
| Wayin Game Clipping uses different models than AI Clipping API | `not measured` |
| Either competitor trains on customer VODs | `not measured` (privacy pages not fully compared here) |

---

## Open measurements (owner / hardware)

| Measurement | Why |
|-------------|-----|
| Identical 2 h gaming VOD: time-to-first-clip, time-to-N clips, time-to-all metadata | Compare W vs O vs C fairly (`not measured`) |
| Paid Wayin export vs ClutchClips render on same moments | Output parity (`blocked` per swarm) |
| OpusClip Pro run with `genre: Gaming` vs Wayin Game template | Gaming detection quality (`not measured`) |
| Credit burn: metadata-only vs full render on each platform | Cost UX (`not measured`) |

---

## References (quick links)

- Wayin: [API clipping](https://wayin.ai/api-docs/ai-clipping/), [Game Clipping](https://help.wayin.ai/en/articles/15691790-how-to-use-game-clipping/), [Credits](https://help.wayin.ai/en/articles/15913299-how-credits-work), [Gaming landing](https://wayin.ai/tools/ai-gaming-clip-generator/)
- OpusClip: [ClipAnything timing](https://help.opus.pro/docs/article/clipanything-qa-4), [Virality score](https://help.opus.pro/docs/article/virality-score), [Credits](https://help.opus.pro/docs/article/how-are-credits-consumed), [Pricing](https://www.opus.pro/pricing), [ClipAnything](https://www.opus.pro/clipanything)
- Internal: [PARITY.md](../../PARITY.md), [2026-11-16 swarm](../../super-board/runs/2026-11-16-swarm.md), `docs/parity-opusclip.md` @ `release/step2-candidate`