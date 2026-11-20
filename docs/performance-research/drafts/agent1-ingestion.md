# Agent 1 — Video acquisition and ingestion research

**Scope:** Research only. No production code, `requirements.txt`, Docker, or PR #218 changes.  
**Date:** 2026-11-20.  
**Claim labels:** `measured` | `verified` | `inferred` | `hypothesis` | `public-source` | `not measured` (see [RESEARCH.md](../RESEARCH.md)).

## Executive summary

ClutchClips today uses **yt-dlp as a library** with a **locked, non-evasive option profile** for Twitch, Kick, and YouTube VODs, then **ffprobe + SHA-256 + storage** before any clip job can run (`verified` `clip-api/app/ingest/runner.py`, `clip-api/app/ingest/platforms.py`). Historical product timing on a 2-hour VOD was dominated by **transcribe and render**, not ingest (`measured` in [RESEARCH.md](../RESEARCH.md): 932.7 s total, transcribe 257 s, render 578 s). Competitors Wayin and OpusClip publish **end-to-end** latency targets (often &lt;5 min vs 20–40 min) that **include** acquisition and analysis (`public-source`); their ingest stacks are **not** public (`not measured`).

The largest **ingest-side** levers that stay inside CLAUDE.md rules appear to be: (1) **overlapping download with analysis** via HLS segment scheduling or ffmpeg input-seeking on manifests (`hypothesis`, technically supported by HLS/ffmpeg literature `public-source`); (2) **raising safe concurrency** on fragment downloads where yt-dlp already supports it (`inferred`); (3) **optional timeframe / partial fetch** for user-selected windows (`public-source` Wayin UX; `hypothesis` for ClutchClips). Replacing yt-dlp with Streamlink offers little for **VOD-only, no-browser** operation and conflicts with Twitch **client-integrity** flows (`public-source`). Alternative downloaders (Lux, N_m3u8DL-RE, twitch-dlp) are noted for **partial HLS** patterns but most assume proxies, impersonation, or non-Python deployment (`public-source`).

---

## 1. North-star and competitive context

| Source | Claim | Label |
|--------|--------|--------|
| SPEC §14 / [RESEARCH.md](../RESEARCH.md) | 2-hour VOD → 30–50 clips in ≤10 min (stretch 5 min); first clips &lt;90 s | `verified` |
| Wayin marketing | Full gaming VOD processed in &lt;5 minutes | `public-source` [wayin.ai gaming clip generator](https://wayin.ai/tools/ai-gaming-clip-generator/) |
| Wayin help | Long / high-res VODs take longer; timeframe clipping saves time/credits | `public-source` [Game Clipping](https://help.wayin.ai/en/articles/15691790-how-to-use-game-clipping) |
| OpusClip help | ClipAnything ~20–40 minutes depending on length and queue | `public-source` [ClipAnything QA](https://help.opus.pro/docs/article/clipanything-qa-4) |
| Competitor ingest implementation | Unknown (CDN-side vs full download vs upload-first) | `not measured` |

**Inference:** Published competitor times are **wall-clock product latency**, not download-only (`inferred`). Beating them on speed requires **parallel ingest + analysis + progressive clip output**, not only a faster downloader (`inferred`).

---

## 2. Hard ingest rules (ClutchClips)

From `CLAUDE.md` / `AGENTS.md` and implementation:

| Rule | Enforcement in code | Label |
|------|---------------------|--------|
| Public, non-DRM only | Refusal mapping; `allow_unplayable_formats: False` | `verified` `clip-api/app/ingest/platforms.py` |
| No cookies, logins, netrc, client certs | Options pinned to `None` / `False` | `verified` `platforms.py`, `test_ingest_platforms.py` |
| No proxy / direct connection | `proxy: ""` (empty string blocks env proxies) | `verified` `platforms.py` L93; test L93 |
| No impersonation / curl_cffi | `impersonate: None`; curl_cffi not installed | `verified` `platforms.py` L1–18 |
| No geo-bypass, extractor_args, JS runtimes, remote components | Explicitly off (YouTube challenges fail clean) | `verified` `platforms.py` L96–98 |
| No external downloaders, no yt-dlp ffmpeg | `external_downloader: None`, `ffmpeg_location` → nonexistent, `fixup: never` | `verified` `platforms.py` L110–114 |
| Honest User-Agent | `ClutchClips-LinkImport/1.0` | `verified` `fetch.py` L25; `platforms.py` L101 |
| Live streams refused | `_check` raises `live_stream` | `verified` `platforms.py` L166–167 |
| Fail clean → upload instead | `Refused` + `UPLOAD_INSTEAD` | `verified` `platforms.py` |
| ffprobe/ffmpeg only on saved files with whitelist | `runner.py`, `as_video_file` | `verified` |
| Link import consent / takedown | SPEC / routes (out of scope for tool choice) | `verified` SPEC.md |

**Platform ToS (downstream risk, not tool license):** Twitch Terms restrict downloading except where Twitch permits (`public-source` [Twitch ToS](https://legal.twitch.com/en/legal/terms-of-service/) §7). Tool BSD/Unlicense does **not** grant content rights (`inferred`).

---

## 3. Current ClutchClips ingestion architecture

```mermaid
sequenceDiagram
    participant API as routes_ingest
    participant W as worker run_import
    participant Y as yt-dlp platforms.download
    participant S as storage
    participant P as run_pipeline job

    API->>W: imp_* job claimed
    W->>Y: full VOD download to temp
    Y->>Y: optional TS→MP4 remux (our ffmpeg)
    W->>W: ffprobe + sha256
    W->>S: put upload object
    Note over P: Separate clip job; needs stored upload
    P->>S: fetch upload
```

| Step | Behavior | Speed implication | Label |
|------|----------|-------------------|--------|
| Import timeout | Default 1800 s (30 min) whole download | Caps worst-case wait | `verified` `config.py` L59 |
| Max import size / duration | 8 GiB, 6 h (configurable) | Large Twitch VODs fit | `verified` `config.py` L57–58 |
| Progress | Bytes via yt-dlp hook; 2–92% import stage | User sees download only | `verified` `runner.py` L107–116 |
| Direct URLs (Drive/Dropbox) | Streamed to disk, 256 KiB chunks | Same “full file first” pattern | `verified` `fetch.py` L28 |
| Pipeline start | **After** import succeeds and upload row is visible | No overlap today | `verified` `worker.py` L144–146 vs L151+ |

**Bottleneck note:** On historical 2 h baseline, ingest fraction of total job time was **not measured** in [RESEARCH.md](../RESEARCH.md); transcribe + render dominated (`measured`). For **link-import-only** wall clock before clipping can start, ingest can be **100% of wait** (`inferred`).

---

## 4. yt-dlp (in production)

### 4.1 How we use it

| Item | Value | Label |
|------|--------|--------|
| Package pin | `yt-dlp==2026.10.26` | `verified` `clip-api/requirements.txt` L13 |
| Pin test | Installed version must match requirements line | `verified` `test_ingest_platforms.py` L144–148 |
| Library entry | `YoutubeDL(ydl_options(...))` | `verified` `platforms.py` |
| Extractors allow-list | `twitch:vod`, `twitch:clips`, `kick:vod`, `kick:clip`, `youtube` only | `verified` `platforms.py` L40, L77 |
| Format selector | `b[height<=?1080][filesize<=?cap][filesize_approx<=?cap]` — single muxed A+V | `verified` `platforms.py` L76 |
| HLS | `hls_prefer_native: True` | `verified` L114 |
| Fragment concurrency | `concurrent_fragment_downloads: 1` | `verified` L108 |
| Resume | `continuedl: False` | `verified` L82 |
| Post-download | HLS often MPEG-TS → our `ffmpeg -c copy` + `faststart` | `verified` `platforms.py` L245–265 |

### 4.2 Project activity and license

| Item | Value | Label |
|------|--------|--------|
| Last push (GitHub API) | 2026-11-19 | `public-source` https://api.github.com/repos/yt-dlp/yt-dlp |
| PyPI release used | 2026-10-26 | `public-source` https://pypi.org/project/yt-dlp/ |
| License (source/wheel) | Unlicense | `public-source` README / PyPI |
| License (standalone binaries) | May bundle GPLv3+ / ISC / MIT pieces | `public-source` https://github.com/yt-dlp/yt-dlp#licensing |
| Python dep | ≥3.11 (PyPI) | `public-source` |
| Open issues | ~2793 (high churn) | `public-source` GitHub API 2026-11-20 |

### 4.3 Dependencies and hardware

| Item | Value | Label |
|------|--------|--------|
| Runtime deps | Pure Python + stdlib networking (no GPU) | `public-source` / `inferred` |
| Optional evasion deps | `curl_cffi`, browser JS runtimes — **not installed / disabled** | `verified` `platforms.py` |
| Hardware | Network + CPU; disk for temp file; RAM modest | `inferred` |
| Our ffmpeg | Used **after** yt-dlp save, not by yt-dlp | `verified` |

### 4.4 Features relevant to speed (not all enabled)

| Feature | What it does | Fits our rules? | Label |
|---------|----------------|-----------------|--------|
| `HttpFD` + `Range` | Resume / chunked HTTP | Resume disabled (`continuedl: False`) | `public-source` [HTTP downloader wiki](https://opendeep.wiki/yt-dlp/yt-dlp/5-download-engine/http-and-fragment); `verified` options |
| `http_chunk_size` | Split single URL into Range chunks | Allowed; **not set** | `public-source`; `verified` |
| `concurrent_fragment_downloads` | Parallel HLS/DASH fragments | Allowed if no evasion; **set to 1** | `public-source`; `verified` |
| `--download-sections` / `download_ranges` | Time-range via ffmpeg | yt-dlp’s implementation expects **yt-dlp-invoked ffmpeg**; we forbid that | `public-source` README; `verified` `fixup: never`, `ffmpeg_location` |
| `hls_prefer_native` + merge | Native HLS fragment loop | In use; sequential concurrency 1 | `verified` |
| External aria2c/curl | Faster parallel HTTP | **Forbidden** `external_downloader: None` | `verified` |
| `impersonate` / `extractor_args` | YouTube/Twitch workarounds | **Forbidden** | `verified` |

### 4.5 Platform notes (Twitch / Kick / YouTube)

| Platform | Typical CDN shape | Our constraints | Label |
|----------|-------------------|-----------------|--------|
| **Twitch VOD** | HLS (`.m3u8` + `.ts` segments) | Full playlist download → TS; EVENT playlists broke some partial-VOD tools in 2025 (`public-source` [Twitch-Utils](https://github.com/TheDrHax/Twitch-Utils/)) | `public-source` + `inferred` |
| **Kick** | Often HLS-like via yt-dlp extractors | Same downloader path | `inferred` |
| **YouTube** | DASH/HLS; frequent bot checks | No JS runtime → **best effort, often refuses** (`verified` module docstring L11–12) | `verified` |

### 4.6 Production suitability

| Criterion | Assessment | Label |
|-----------|------------|--------|
| Maturity / maintenance | Very active | `public-source` |
| License for SaaS | Unlicense wheel OK; compliance = content/TOS | `public-source` + `inferred` |
| Determinism | Pin + allow-list + option snapshot tests | `verified` |
| Security | No arbitrary URL extractors; DNS-checked direct fetch separate | `verified` |
| Version drift risk | Frequent extractor fixes — pin must be **reviewed** per bump | `verified` requirements comment |

### 4.7 Commercial / legal restrictions

- **Software:** Unlicense permits commercial use (`public-source`).
- **Content:** YouTube/Twitch/Kick terms may restrict automated download (`public-source` Twitch ToS; YouTube ToS not re-quoted here — `not measured` for Kick).
- **ClutchClips model:** Owner permission + takedown (`verified` SPEC) — legal review of automated import `not measured`.

---

## 5. Streamlink

### 5.1 Overview

| Item | Value | Label |
|------|--------|--------|
| Role | Python library/CLI: resolve URL → `Stream` objects → `open()` byte stream | `public-source` https://streamlink.github.io/ |
| PyPI | streamlink 8.6.3, BSD-2-Clause, Python ≥3.10 | `public-source` https://pypi.org/project/streamlink/ |
| GitHub activity | Pushed 2026-11-18; ~72 open issues | `public-source` https://api.github.com/repos/streamlink/streamlink |
| In ClutchClips | **Not** a dependency | `verified` `requirements.txt` |

### 5.2 Overlap vs yt-dlp

| Dimension | Streamlink | yt-dlp (us) | Label |
|-----------|------------|-------------|--------|
| **VOD URL → file on disk** | Supported (e.g. Twitch plugin) | Primary path today | `public-source` |
| **Live** | Core strength; pipe to player | We **reject** live | `verified` `platforms.py`; `public-source` Streamlink |
| **Site breadth** | Plugin per service | Hundreds of extractors (we allow 5) | `public-source` |
| **Library API** | `session.streams()` / `HLSStream.open()` | `YoutubeDL.extract_info` + `process_ie_result` | `public-source` |
| **Metadata without download** | Via plugin | `extract_info(..., download=False)` — used in preview | `verified` `platforms.py` L177–188 |

### 5.3 Fit with hard rules

| Issue | Detail | Label |
|-------|--------|--------|
| Twitch **client-integrity token** | Plugin docs: `$webbrowser` required for integrity token in some paths | `public-source` [twitch.py plugin](https://github.com/streamlink/streamlink/blob/master/src/streamlink/plugins/twitch.py) |
| Headless server | Browser-based token = **evasion / impersonation** territory we avoid | `inferred` vs `verified` CLAUDE.md |
| SOCKS proxy | Optional PySocks | Not used; would violate policy if enabled | `inferred` |
| Partial VOD | `--hls-start-offset` **broken** for EVENT playlists (2025) | `public-source` Twitch-Utils README |

### 5.4 Production suitability for ClutchClips

| Use case | Verdict | Label |
|----------|---------|--------|
| Replace yt-dlp for Twitch/Kick/YouTube VOD | **Low** — duplicate maintenance; integrity token path conflicts | `hypothesis` |
| Parallel **read-only** stream while downloading | **Possible** via `HLSStream.open()` if token works without browser | `hypothesis` |
| Live clipping (future SPEC 4.x) | Theoretical; still needs official API or permissive live access | `hypothesis` SPEC.md |

### 5.5 License and commercial use

BSD-2-Clause: commercial use OK with notice (`public-source`). Content restrictions same as §2 (`inferred`).

---

## 6. Can analysis start before the full download?

### 6.1 What the pipeline requires today

| Requirement | Reason | Label |
|-------------|--------|--------|
| Complete file (or stable path) | `probe(path)`, `sha256` whole file, `storage.put` | `verified` `runner.py` L118–146 |
| `-protocol_whitelist file,pipe` | ffmpeg/ffprobe safety | `verified` CLAUDE.md |
| No URL demux in worker | `fetch.py` doc: probe on saved file only | `verified` `fetch.py` L7–8 |

### 6.2 Mechanisms (literature + tools)

| Mechanism | How it works | Seek / partial? | Rule-safe? | Label |
|-----------|----------------|-------------------|------------|--------|
| **HTTP Range on single MP4** | Byte ranges if CDN supports `Accept-Ranges` | Start mid-file after enough `moov` | Yes if URL from trusted extractor | `public-source` yt-dlp HttpFD; `hypothesis` for analysis |
| **HLS segment index** | Sum `#EXTINF`; fetch overlapping `.ts` only | Segment-granular (~2–6 s) | Yes; same public CDN URLs | `public-source` [m3u8 partial blog](https://www.videodownloader-ofa.com/blog/download-section-of-m3u8-stream) |
| **ffmpeg `-ss` before `-i` on m3u8** | Demuxer skips unneeded segments | Fast section extract; keyframe-aligned with `-c copy` | Uses **our** ffmpeg, not yt-dlp’s | `public-source` same article |
| **yt-dlp `download_sections`** | Time range | Needs yt-dlp ffmpeg integration we disable | **No** unless policy exception | `verified` + `public-source` |
| **Pipe / FIFO** | Decode while downloading | ffprobe on partial files often **incomplete** | Would need pipeline changes | `hypothesis` |
| **Signed segment URLs** | Short TTL tokens | Long jobs may 403 mid-stream | Risk for multi-hour VOD | `public-source` m3u8 blog |

### 6.3 Architectural patterns (research hypotheses)

1. **Two-phase job:** (A) metadata + playlist URL via yt-dlp `download=False`; (B) **segment scheduler** fetches batches while a **decode worker** consumes completed segments from disk (`hypothesis`). Aligns with SPEC “first clips &lt;90 s” if analysis does not wait for hour 8 (`verified` target).
2. **Timeframe import:** User selects window (Wayin-style) → download **only** that HLS range → faster to first byte (`public-source` Wayin; `hypothesis` ClutchClips).
3. **Upload-first for YouTube:** Keep current YouTube refusal rate; do not optimize YouTube at cost of policy (`inferred`).
4. **Do not** enable yt-dlp impersonation/JS to shave seconds (`verified` policy).

**Competitor parallelization:** Wayin documents multi-URL background processing (`public-source`); may include server-side fetch while user waits (`not measured`).

---

## 7. Related tools (independent discovery)

### 7.1 N_m3u8DL-RE

| Item | Value | Label |
|------|--------|--------|
| Role | Cross-platform DASH/HLS/MSS; `--custom-range` time/index | `public-source` https://github.com/nilaoda/N_m3u8DL-RE |
| License | MIT | `public-source` |
| Stack | .NET binary | `public-source` |
| Activity | ~9.1k stars; 373 open issues | `public-source` GitHub API |
| Partial download | `--custom-range "00:10:00-00:15:00"` | `public-source` |
| LOCAL_HTTP concat | Serves segments on 127.0.0.1 for ffmpeg-friendly merge | `public-source` README |
| ClutchClips fit | **Reference** for segment-parallel design; extra binary + ops burden | `hypothesis` |

### 7.2 Lux (formerly Annie)

| Item | Value | Label |
|------|--------|--------|
| Role | Go CLI/library, many sites | `public-source` https://github.com/iawia002/lux |
| License | MIT | `public-source` |
| Overlap | YouTube/Twitch in ecosystem; proxies documented in forks | `public-source` |
| Fit | Not Python-native; overlaps yt-dlp; no policy advantage | `inferred` |

### 7.3 gallery-dl

| Item | Value | Label |
|------|--------|--------|
| Role | Image galleries; optional yt-dlp for HLS | `public-source` https://github.com/mikf/gallery-dl |
| License | GPLv2 | `public-source` |
| Fit | Wrong problem domain for gaming VOD | `inferred` |

### 7.4 twitch-dlp (DmitryScaletta)

| Item | Value | Label |
|------|--------|--------|
| Role | Twitch-focused; `--download-sections`, hidden VOD | `public-source` https://github.com/DmitryScaletta/twitch-dlp |
| Policy flags | Documents `--proxy`, impersonation toggles | `public-source` README — **incompatible** with our rules |
| Fit | Partial-section **syntax** reference only | `inferred` |

### 7.5 VodRecovery / cutvod (community)

| Item | Value | Label |
|------|--------|--------|
| Role | Twitch m3u8 + `--start`/`--end` trim | `public-source` https://github.com/MacielG1/VodRecovery |
| Fit | Scripts for personal use; not production service pattern | `inferred` |

---

## 8. Option matrix (speed vs policy)

| Knob | Current | Faster? | Policy | Evidence needed |
|------|---------|---------|--------|-----------------|
| `concurrent_fragment_downloads` | 1 | Likely on HLS | OK | `not measured` bench on Twitch 4 h VOD |
| `continuedl` | False | Retry cost only | OK | `inferred` |
| `http_chunk_size` | unset | Maybe on single-url MP4 | OK | `not measured` |
| `download_sections` via yt-dlp | off (no yt-dlp ffmpeg) | Large for time windows | Needs design: **our** ffmpeg vs policy | `hypothesis` |
| External aria2c | forbidden | Yes on paper | **No** | — |
| `impersonate` + JS | forbidden | YouTube reliability | **No** | — |
| Streamlink pipe | N/A | Overlap download/analysis | Token/browser risk | `not measured` |
| Skip full-file SHA until complete | always hash | Marginal | OK if hash after complete | `verified` current behavior |

---

## 9. Recommendations for next research phases (not implementation)

1. **Benchmark ingest isolated** from pipeline: Twitch/Kick 2 h / 6 h HLS, pinned yt-dlp, measure MB/s and time-to-first-GB (`not measured`).
2. **A/B `concurrent_fragment_downloads`** {1, 4, 8} under same option profile (`hypothesis`).
3. **Prototype “segment ledger”** downloader: public m3u8 + httpx ranged GETs + hand off growing TS/MP4 to ffprobe slice probes — policy review for URL handling (`hypothesis`).
4. **Product: timeframe import** aligned with Wayin UX (`public-source`); legal copy in consent UI (`inferred`).
5. **Do not** adopt Streamlink for VOD replace until headless Twitch works **without** browser integrity (`not measured` on our servers).
6. **Keep** yt-dlp pin discipline; track [releases](https://github.com/yt-dlp/yt-dlp/releases) for Twitch/Kick extractor regressions (`verified` process).

---

## 10. References

### Repository paths (read-only)

- `clip-api/app/ingest/platforms.py` — yt-dlp options and download path
- `clip-api/app/ingest/runner.py` — import job; full download before store
- `clip-api/app/ingest/fetch.py` — direct HTTPS import
- `clip-api/app/config.py` — import limits
- `clip-api/requirements.txt` — yt-dlp pin
- `clip-api/tests/test_ingest_platforms.py` — option contract tests
- `docs/performance-research/RESEARCH.md` — labels, hardware, north-star
- `SPEC.md` §14 — product timing goals

### External URLs

- https://github.com/yt-dlp/yt-dlp
- https://pypi.org/project/yt-dlp/
- https://github.com/streamlink/streamlink
- https://pypi.org/project/streamlink/
- https://streamlink.github.io/latest/api_guide/quickstart.html
- https://github.com/nilaoda/N_m3u8DL-RE
- https://github.com/iawia002/lux
- https://github.com/mikf/gallery-dl
- https://legal.twitch.com/en/legal/terms-of-service/
- https://help.wayin.ai/en/articles/15691790-how-to-use-game-clipping
- https://help.opus.pro/docs/article/clipanything-qa-4
- https://www.videodownloader-ofa.com/blog/download-section-of-m3u8-stream

---

## Appendix A — yt-dlp option snapshot (verified defaults)

Key fields from `ydl_options` (see tests for full dict): format height cap 1080; `concurrent_fragment_downloads: 1`; `hls_prefer_native: True`; `continuedl: False`; retries 3; socket timeout 30 s; User-Agent `ClutchClips-LinkImport/1.0`.