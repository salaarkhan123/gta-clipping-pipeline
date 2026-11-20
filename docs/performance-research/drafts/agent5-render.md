# Agent 5 — Rendering and editing performance research

**Scope:** Research only. No production code, `requirements.txt`, Docker, or PR #218 changes.  
**Date:** 2026-11-20.  
**Claim labels:** `measured` | `verified` | `inferred` | `hypothesis` | `public-source` | `not measured` (see [RESEARCH.md](../RESEARCH.md)).

**Code baseline:** Product on `main` in this checkout; PR #218 behavior read from frozen branch `origin/release/step2-candidate` (`verified` [RESEARCH.md](../RESEARCH.md)). GitHub PR #218 was not fetched (`not measured` for live PR metadata).

## Executive summary

Clip rendering today is **single-threaded ffmpeg** with **libx264** (`verified` `clip-api/app/pipeline/render.py`). Full exports use **veryfast CRF 20**; previews cap the short side at **PREVIEW_SIDE = 540** (9:16 → 540×960) with **ultrafast CRF 30** (`verified`). On the 2026-11-15 production droplet, **rendering took 578.4 s for 10 clips** (~58 s/clip, ~62% of job time) on a 2-hour 1080p VOD (`measured` SPEC.md §10 B). PR #218 adds **`render: none | preview | full`**, separate **preview vs export** URLs, and **`POST /v1/clips/export`** for on-demand full quality (`verified` `docs/CONTRACTS.md`, `origin/release/step2-candidate:clip-api/tests/test_export.py`).

**Remotion** is a poor fit for the server pipeline: it would duplicate the existing ASS/layout filter graph in Node/Chromium, add operational cost, and fight the Python worker model (`inferred`; seed `verified` [REPOSITORY-EVALUATION.md](../REPOSITORY-EVALUATION.md)). **Parallel clip previews** are a north-star design choice (SPEC §14, ticket S2 #97) but **clips still render sequentially** in `run_pipeline` on both `main` and step2-candidate (`verified`). The **editor** (`web-src`) can open quickly for UI shell, but **“assets ready” under 2 s** is an unmeasured research target: it depends on project JSON, caption fetches, and **metadata preload of the full source upload** (`not measured`).

---

## 1. North-star and historical render cost

| Source | Claim | Label |
|--------|--------|--------|
| SPEC §14 | 2-hour VOD → 30–50 ranked clips with previews in ≤10 min (stretch 5 min) | `verified` SPEC.md |
| SPEC §14 | One 1080p export ≤30 s; batch 40 exports ≤3 min | `verified` SPEC.md |
| SPEC §14 design | Previews first (540×960, fast preset, **all clips in parallel**); 1080p on export only | `verified` SPEC.md §14 |
| Server run B (2026-11-15) | 10 clips, **578.4 s rendering**, 257.0 s transcribing, 932.7 s total; DigitalOcean `s-4vcpu-8gb` | `measured` SPEC.md §10 B |
| Share of job time | Rendering ~62% (run B) | `measured` SPEC.md §10 B |
| Per-clip implied | 578.4 / 10 ≈ **57.8 s/clip** on droplet for server benchmark options (split, captions, 9:16) | `inferred` from `measured` |
| M4 dev machine (same VOD class) | 1080×1920 veryfast **6.3 s**; 540×960 ultrafast preview **3.0 s**; **8 previews in parallel: 8 s** wall | `measured` docs/super-board/runs/2026-11-15-autonomous.md |
| Droplet vs M4 | ~9× slower render than M4 for comparable clip (`measured` run log: 57.8 s vs ~6.3 s) | `inferred` from two `measured` points |

**Interpretation:** Preview resolution and preset already cut single-clip encode time roughly in half on the same hardware (`measured` M4; `verified` `test_a_preview_is_smaller_and_faster_than_the_full_render`). The droplet bottleneck is **serial full-quality renders at job time**, not preview math alone (`inferred`).

---

## 2. `render.py`: libx264, sizes, and filter graph

### 2.1 Encode presets and preview cap

```27:29:clip-api/app/pipeline/render.py
PREVIEW_SIDE = 540       # a preview render's short side: 540x960 for 9:16
FULL_ENCODE = ["-preset", "veryfast", "-crf", "20"]
PREVIEW_ENCODE = ["-preset", "ultrafast", "-crf", "30"]     # a preview is for looking at, not for posting
```

Final ffmpeg invocation (main):

```356:359:clip-api/app/pipeline/render.py
        run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{lo:.3f}", "-t", f"{hi - lo:.3f}",
             *SAFE_IN, "-i", src, *vf, *scale,
             "-c:v", "libx264", *(PREVIEW_ENCODE if preview else FULL_ENCODE), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "96k" if preview else "160k", "-ar", "48000", "-movflags", "+faststart", out], deadline)
```

| Knob | Full | Preview | Label |
|------|------|---------|--------|
| Codec | libx264 software | same | `verified` |
| Preset / CRF | veryfast / 20 | ultrafast / 30 | `verified` |
| Short side cap | resolution ladder up to source | **min(side, 540)** via `output_size(..., preview=True)` | `verified` |
| Output FPS | 30 (`OUT_FPS`) | same | `verified` |
| Audio | AAC 160k | AAC 96k | `verified` |
| GPU (NVENC) | none in code | S5 #99 benchmark only | `verified` / `not measured` |

`output_size` clamps preview, resolution, and plan `max_side` (`verified` `render.py` L111–130). Tests lock 9:16 preview to **540×960** and assert preview encodes faster and smaller than full (`verified` `clip-api/tests/test_render_sizes.py`).

### 2.2 Work per clip (why renders are slow)

| Stage inside `render_clip` | Cost driver | Label |
|------------------------------|-------------|--------|
| Seek + decode window from **full VOD** | Long GOP streams; each clip re-reads source | `inferred` |
| `filter_complex` (layouts, punch, segments, ASS) | CPU filters; split layouts multiply crops | `verified` layouts + render |
| Loudness | `ebur128` measure + gain + limiter on audio | `verified` `measure_loudness` |
| Captions | libass burn; impact style bundles font in temp dir | `verified` |
| Direct draw at preview/resolution | Skips post-scale when `direct` (`verified` L328–330) | `verified` |

**chat_region** (classic vertical chat panel) forced **6.5×** wall time on a 2 h local bench by decoding the whole video for motion (`measured` SPEC.md §10 B local table). Not part of server benchmark runs but shows decode scope dominates when video is scanned (`verified`).

---

## 3. PR #218: `render` none | preview | full + export

Contract (`verified` `docs/CONTRACTS.md`):

| Mode | Job-time behavior | URLs / storage (PR #218) |
|------|-------------------|---------------------------|
| `none` | Metadata, thumbnail, captions; **no mp4** | `video_url` null; export via `POST /v1/clips/export` |
| `preview` | `render_clip(..., preview=True)` → 540 short side | `preview_url` plays; `export_url` null until export |
| `full` | Full resolution ladder (default job behavior on main: always full) | `video_url` / export fields per worker wiring |

PR #218 pipeline (`verified` `origin/release/step2-candidate:clip-api/app/pipeline/__init__.py`):

- `PipelineOptions.render: str = "full"` with values `none | preview | full`.
- `video = ... if options.render != "none" else None`; `preview=options.render == "preview"`.
- `ClipResult.video_path` may be `None` for `none`.

PR #218 API surface (`verified` step2 tests):

- `test_render_none_stores_no_video_and_an_export_renders_it` — export charges **rendered seconds**, idempotent storage (`clip-api/tests/test_export.py` on step2).
- `test_render_preview_is_small_and_is_what_plays` — **(540, 960)** probe on `preview_url`.
- Export always `render: "full"`; quote/reserve pattern in `app/routes_export.py` (`verified` step2).

Schema already anticipates split keys on `main` (`verified` `clip-api/app/models.py`: `preview_key`, `export_key`; migration `0004_swarm_interfaces.py`).

**Gap on `main` today:** `render_clip` supports `preview: bool` but clip jobs **always call it without preview** and there is **no `render` option** on `LayoutOptions` (`verified` `clip-api/app/pipeline/__init__.py` L383–389 vs step2). `routes_export.py` **missing** on `main` (`verified` glob).

**Defaults PR (planned):** CONTRACTS sets post-default `render: none`, `resolution: 480` (Wayin parity) — not on `main` (`verified` CONTRACTS.md).

---

## 4. Parallel previews (S2) — design vs implementation

| Claim | Label |
|-------|--------|
| SPEC §14: “all clips in parallel” for preview phase | `verified` SPEC.md |
| Ticket S2 #97 “previews first, export on demand” | `verified` SPEC.md speed track |
| `run_pipeline` renders clips in a **serial `for` loop** (best-first progressive **delivery**, not parallel encode) | `verified` `clip-api/app/pipeline/__init__.py` L347–411 |
| No `ThreadPoolExecutor` around per-clip `render_clip` on main or step2 | `verified` git grep step2 pipeline |
| M4: 8 simple previews in parallel ≈ 8 s wall (feasibility, not product code) | `measured` 2026-11-15 run log |
| `WORKER_CONCURRENCY=2` runs **two jobs**, not parallel clips inside one job | `verified` `clip-api/DEPLOY.md` |

**Hypothesis:** On a 16-vCPU render worker (SPEC §14 infra B), **N parallel ffmpeg processes** (one per clip, preview preset) could approach the M4 parallel demo if disk bandwidth and RAM fit (`hypothesis`). **Risk:** duplicate decode of the same 2 h source × N (`inferred`); mitigations: segment-local inputs, shared RAM disk, or NVENC (S5) (`hypothesis`).

**S4** (dedicated render machine roles) and **S5** (NVENC benchmark) are the planned infra levers (`verified` SPEC.md); neither is implemented in this checkout (`not measured`).

---

## 5. Remotion vs ffmpeg (server pipeline)

| Dimension | FFmpeg (current) | Remotion | Label |
|-----------|----------------|----------|--------|
| Runtime | C subprocess in Python worker | Node + headless Chromium render | `public-source` Remotion architecture |
| Layout/captions | `filter_complex`, ASS, `layouts.layout_graph` | React components reimplementing same | `inferred` |
| Deploy | Same Docker image as API/worker | Second stack, font/video asset bundling | `inferred` |
| Determinism / CI | `test_render_sizes`, pixel probes | Version skew React/ffmpeg | `inferred` |
| Fit for batch 30–50 clips | Already integrated; proven on droplet | Cold start + per-clip browser cost | `inferred` |

**Conclusion:** Keep **ffmpeg as the single render engine** for server-side batch and export. Remotion remains reasonable only for **marketing previews or a separate client-side export toy**, not replacement of `render_clip` (`inferred`; aligns with `verified` REPOSITORY-EVALUATION “likely unfit”).

Optional: Remotion Lambda for competitor-style cloud export is **paid, multi-tenant ops** — out of scope without owner OK (`verified` CLAUDE.md deferred/money rules).

---

## 6. Editor load &lt;2 s (`web-src`)

Research target (`verified` [RESEARCH.md](../RESEARCH.md)): editor **interactive with assets ready** in under 2 seconds.

### 6.1 Critical path (verified structure)

```mermaid
sequenceDiagram
    participant Page as edit/page.tsx
    participant API as GET /v1/projects/:id
    participant Opt as GET /v1/options
    participant Rt as routes manifest
    participant Ed as Editor.tsx
    participant Vid as source_url video

    Page->>API: project + clips + source_url
    Page->>Opt: clipOptions (shared promise)
    Page->>Rt: useRoutes
    Page->>Ed: mount when all ready
    Ed->>Ed: loadWords(clip) captions_url or /subtitles
    Ed->>Vid: preload=metadata on full upload
```

| Step | What loads | Perf note | Label |
|------|------------|-----------|--------|
| `GET /v1/projects/{upload_id}` | All clips, jobs, **`source_url`** (full upload URL) | One JSON round-trip | `verified` `routes_projects.py`, `edit/page.tsx` |
| `useClipOptions` | `/v1/options` | Cached per visit (`clipOptions()` singleton) | `verified` `web-src/lib/options.ts` |
| `loadWords` | `captions_url` or authenticated VTT | Second fetch after mount | `verified` `web-src/lib/edit.ts` |
| Preview playback | **`project.source_url`** (entire VOD), not clip mp4 | Browser must open/seek multi-GB file; `preload="metadata"` | `verified` `Editor.tsx` L183 |
| “Current file” tab | `clip.export_url \|\| clip.video_url` | Clip-sized file | `verified` |

Shell states (`verified` `edit/page.tsx` L30): blocked on `project`, `clip`, `listed`, `known` — **four async sources** before editor UI.

### 6.2 vs 2 s target

| Claim | Label |
|-------|--------|
| No RUM/Lighthouse or scripted **time-to-interactive** for `/dashboard/edit/` in repo | `not measured` |
| Full-VOD `source_url` for trim preview can dominate “ready to scrub” on large uploads | `hypothesis` |
| Using **preview mp4** (540p) for editor playback would reduce decode cost vs full upload | `hypothesis` |
| `render: none` jobs still support editing via source + transcript, but export required to see styled output | `verified` step2 tests + Editor copy |

**Recommendations (research only):**

1. Define “&lt;2 s” as: project JSON + options + routes + **caption words** loaded; video **first frame** optional (`hypothesis`).
2. Measure p95 on staging with 2 h upload: project payload size, `source_url` TTFB, `loadedmetadata` (`not measured`).
3. Prefer **clip preview URL** or byte-range on upload for editor timeline when PR #218 preview mode is default (`hypothesis`).

---

## 7. Integration roadmap (render track only)

| Priority | Change | Expected effect | Risk | Label |
|----------|--------|-----------------|------|--------|
| P0 | Ship PR #218 **`render: preview`** as default clip job path | Cuts job-time encode ~2× per clip vs full (M4 `measured`); droplet impact `not measured` until bench | Dashboard must send explicit options | `verified` design |
| P0 | **`render: none`** for rank-only pass + batch export | Removes 578 s render phase from initial job (`inferred` from `measured` baseline) | UX needs playable preview or thumb + export CTA | `verified` CONTRACTS |
| P1 | **Parallel preview encodes** inside worker (S2) | Wall ∝ longest clip, not sum (`hypothesis`) | CPU/RAM contention; 4 vCPU droplet may not benefit | `verified` SPEC intent |
| P1 | **NVENC** for export path (S5) | 2–5× encode speed on GPU box (`hypothesis`, industry `public-source`) | Quality parity tests required | `not measured` |
| P2 | Editor: preview asset for player | Helps &lt;2 s “scrub ready” (`hypothesis`) | Timeline mapping already uses `segments` when exact | `verified` `sourceTime` |
| — | Remotion | — | Not recommended server-side | `inferred` |

Every speed change should report with `scripts/job_timings.py` against SPEC §10 B baseline (`verified` SPEC.md, `clip-api/scripts/job_timings.py`).

---

## 8. Open questions / `not measured`

- End-to-end droplet time for **`render: preview`** on 30–50 clips (PR #218 not deployed on measured hardware).
- GPU NVENC quality/speed vs libx264 veryfast on split+impact captions (S5).
- Editor p95 load time on production upload sizes.
- Whether parallel preview should share one **decoded segment cache** per job (no code; `hypothesis`).

---

## References (cited)

| Path | Use |
|------|-----|
| `clip-api/app/pipeline/render.py` | libx264, PREVIEW_SIDE, `render_clip` |
| `clip-api/app/pipeline/__init__.py` | Serial render loop (`main`); step2 adds `render` mode |
| `clip-api/app/pipeline/layouts.py` | Filter graph complexity |
| `clip-api/app/pipeline/ff.py` | SAFE_IN, subprocess timeouts |
| `clip-api/tests/test_render_sizes.py` | Preview vs full timing/size |
| `origin/release/step2-candidate:clip-api/tests/test_export.py` | none/preview/full + export |
| `origin/release/step2-candidate:clip-api/app/routes_export.py` | Export quote/charge |
| `origin/release/step2-candidate:clip-api/app/render_options.py` | `RenderMode` |
| `docs/CONTRACTS.md` | API contract for `render` and export |
| `SPEC.md` §10 B, §14 | 578 s render, parallel preview design |
| `docs/super-board/runs/2026-11-15-autonomous.md` | M4 per-clip and 8× parallel preview timings |
| `clip-api/web-src/app/dashboard/edit/page.tsx`, `Editor.tsx`, `lib/edit.ts` | Editor load path |
| `docs/performance-research/RESEARCH.md` | Claim legend, editor &lt;2 s objective |
| `docs/performance-research/REPOSITORY-EVALUATION.md` | Remotion seed note |