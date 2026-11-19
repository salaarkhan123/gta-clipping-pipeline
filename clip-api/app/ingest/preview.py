"""Link preview: what a pasted link is (platform, title, channel, length, thumbnail) before anything is imported.

Metadata only: nothing is downloaded, nothing is written, nothing is charged. The same rules as an import apply,
through the same code: the allow-list and URL checks (sources.classify), the private-address refusal for direct
links (fetch.check_hop, a name lookup only), and for Twitch, Kick and YouTube the same fixed yt-dlp options and the
same checks (platforms.preview), plus the minimum length the worker checks after a download. Direct, Google Drive
and Dropbox links get no request beyond that name lookup: their file is checked when it is imported.

Every lookup is bounded: LOOKUP_TIMEOUT_SEC in all (SOCKET_TIMEOUT_SEC for each request), at most PARALLEL at once
in this process. A lookup that fails or runs out of time is a refusal that says to upload the file instead. The
caller rate-limits lookups per account (LOOKUPS_PER_MINUTE); answers are cached in memory per canonical URL for
CACHE_TTL_SEC (FAILURE_TTL_SEC for a site that refused), so a cached answer makes no request and is not counted.
"""
import logging
import re
import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import PurePosixPath
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from ..config import get_settings
from . import UPLOAD_INSTEAD, Refused, Span, fit_span
from .sources import DIRECT, MAX_URL_LEN, Source

log = logging.getLogger("clipapi.ingest")

LOOKUPS_PER_MINUTE = 10     # per account; = routes_ingest.BULK_MAX, so a full bulk paste can be previewed
LOOKUP_TIMEOUT_SEC = 15.0   # one lookup in all, however many requests the site needs
SOCKET_TIMEOUT_SEC = 10     # each request of a lookup (an import uses platforms.SOCKET_TIMEOUT)
PARALLEL = 4                # lookups running at once in this process; more wait their turn within the timeout
CACHE_TTL_SEC = 300         # an answer from the site's metadata
FAILURE_TTL_SEC = 60        # the site refused or did not answer: try again soon, but not on every keystroke
CACHE_MAX = 1000
NAMES = {"twitch": "Twitch", "kick": "Kick", "youtube": "YouTube", "gdrive": "Google Drive", "dropbox": "Dropbox",
         "direct": "This link's server"}

_pool = ThreadPoolExecutor(max_workers=PARALLEL, thread_name_prefix="link-preview")
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _text(value: Any, limit: int = 300) -> str | None:
    return (value.strip()[:limit] or None) if isinstance(value, str) else None


def _https(value: Any) -> str | None:
    return value if isinstance(value, str) and value.startswith("https://") and len(value) <= 2000 else None


def _thumbnail(source: Source | None, info: dict, state: str | None) -> str | None:
    """The thumbnail the site's public metadata names (https only). Never fetched or proxied by us.
    The metadata is read without choosing formats, so yt-dlp has not picked "the" thumbnail: the best listed one
    is taken here (highest `preference`, then the largest; yt-dlp lists them worst first). Twitch names its
    thumbnails by size: the full-size original is swapped for 640x360. A Twitch recording in progress has no
    thumbnail of its own yet (Twitch shows a "processing" placeholder), so the channel's live preview image
    stands in."""
    url = _https(info.get("thumbnail"))
    if url is None:
        thumbs = [(t.get("preference") or 0, (t.get("width") or 0) * (t.get("height") or 0), n, t["url"])
                  for n, t in enumerate(info.get("thumbnails") or []) if isinstance(t, dict) and _https(t.get("url"))]
        url = max(thumbs)[3] if thumbs else None
    if source is not None and source.platform == "twitch":
        if url is not None:
            url = re.sub(r"-(?:0x0|\d+x\d+)(\.\w+)$", r"-640x360\1", url)
        elif state == "recording" and re.fullmatch(r"[a-z0-9_]{3,25}", str(info.get("uploader_id") or "")):
            url = f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{info['uploader_id']}-640x360.jpg"
    return url


def _is_clip(source: Source) -> bool:
    return source.url.startswith("https://clips.twitch.tv/") or "/clips/" in source.url


def _video_type(source: Source | None, info: dict, state: str | None) -> str | None:
    """video | short | live_recording (a finished YouTube broadcast) | vod (a Twitch or Kick recording) | clip |
    ongoing_recording (a VOD whose stream is still live) | live_stream | upcoming | file (a direct, Drive or
    Dropbox link). A channel page (live_channel) never gets here: it is refused by its URL."""
    if source is None:
        return None
    if source.downloader == DIRECT:
        return "file"
    if state == "upcoming":
        return "upcoming"
    if _is_clip(source):
        return "clip"
    if state == "live":
        return "live_stream"
    if source.platform in ("twitch", "kick"):
        return "ongoing_recording" if state == "recording" else "vod"
    if state is None:
        return None                         # YouTube, and the site did not answer
    if state == "was_live":
        return "live_recording"
    return "short" if info.get("media_type") == "short" else "video"


def _kind(source: Source | None, state: str | None) -> str | None:
    """The first version of `video_type`, kept for clients that read it: video | clip | live | upcoming."""
    if source is None:
        return None
    if state == "upcoming":
        return "upcoming"
    if state in ("live", "recording"):
        return "live"
    return "clip" if _is_clip(source) else "video"


def _category(info: dict) -> str | None:
    """The game or category the site lists: Twitch and Kick name the game; YouTube names a broad category.
    A Twitch VOD that moved between games lists each as a chapter: the one played longest is given."""
    listed = [c for c in info.get("categories") or [] if isinstance(c, str) and c.strip()]
    if listed:
        return _text(listed[0], 100)
    chapters = [c for c in info.get("chapters") or [] if isinstance(c, dict) and isinstance(c.get("title"), str)]
    if not chapters:
        return None
    longest = max(chapters, key=lambda c: (c.get("end_time") or 0) - (c.get("start_time") or 0))
    return _text(longest["title"], 100)


def _channel_url(source: Source | None, info: dict) -> str | None:
    url = _https(info.get("channel_url") or info.get("uploader_url"))
    login = str(info.get("uploader_id") or "")
    if url is None and source is not None and not _is_clip(source) and re.fullmatch(r"[A-Za-z0-9_-]{2,60}", login):
        if source.platform == "twitch":
            url = f"https://www.twitch.tv/{login}"
        elif source.platform == "kick":
            url = f"https://kick.com/{login}"
    return url


def _started_at(info: dict) -> str | None:
    stamp = info.get("release_timestamp") or info.get("timestamp")
    if not isinstance(stamp, (int, float)) or stamp <= 0:
        return None
    return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _range_download(source: Source, info: dict) -> str:
    """What to expect for a chosen range. "partial": it is downloaded on its own (the site lists the video as
    segments, or serves each stream as one indexed MP4 file that can be read by byte range); "full": the whole
    video is downloaded and the range is cut from it. A forecast from the metadata: what an import really did is
    its `fetched.mode`."""
    def by_part(f) -> bool:
        protocol = str(f.get("protocol") or "")
        return f.get("vcodec") != "none" and (protocol.startswith("m3u8") or (
            source.platform == "youtube" and protocol == "https" and f.get("ext") == "mp4"))
    return "partial" if any(isinstance(f, dict) and by_part(f) for f in info.get("formats") or []) else "full"


def answer(url: str, source: Source | None, info: dict | None = None, refusal: Refused | None = None) -> dict:
    """The response body. `url` is the canonical link when the link is one we import from."""
    info = info if isinstance(info, dict) else {}
    about = getattr(refusal, "about", None) or {}          # a channel page: refused by its URL, but named
    duration = info.get("duration")
    duration = float(duration) if isinstance(duration, (int, float)) and duration >= 0 else None
    state = None
    if source is not None and source.downloader != DIRECT and info:
        from .platforms import live_state
        state = live_state(info)
    if refusal is not None and refusal.code == "upcoming":      # the site says so in place of any metadata
        state = "upcoming"
    ok = refusal is None
    return {
        "url": source.url if source else about.get("url") or url.strip()[:MAX_URL_LEN],
        "platform": source.platform if source else about.get("platform"),
        "supported": ok,
        "title": _text(info.get("title")),
        "channel": _text(info.get("channel") or info.get("uploader")) or about.get("channel"),
        "channel_url": _channel_url(source, info) or about.get("url"),
        "category": _category(info),
        "duration_sec": duration,
        "available_sec": duration,          # an ongoing recording: the seconds published so far
        "started_at": _started_at(info),
        "thumbnail_url": _thumbnail(source, info, state),
        "video_type": about.get("video_type") or _video_type(source, info, state),
        "live_status": state,
        "kind": about.get("kind") or _kind(source, state),
        "options": {"import": ok, "clip": ok and bool(duration), "range": ok,
                    "range_download": (_range_download(source, info) if ok and source else None)},
        "refusal": {"code": refusal.code, "message": refusal.message} if refusal else None,
    }


def cached(canonical_url: str) -> dict | None:
    with _lock:
        hit = _cache.get(canonical_url)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        _cache.pop(canonical_url, None)
        return None


def _remember(canonical_url: str, body: dict, ttl: float) -> None:
    now = time.monotonic()
    with _lock:
        if len(_cache) >= CACHE_MAX:
            for key in [k for k, (expires, _) in _cache.items() if expires <= now]:
                del _cache[key]
            while len(_cache) >= CACHE_MAX:
                del _cache[next(iter(_cache))]                # the oldest entry
        _cache[canonical_url] = (now + ttl, body)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _refused(platform: str, why: str, code: str) -> Refused:
    from .platforms import YOUTUBE_REFUSES
    if platform == "youtube":
        return Refused(code, f"{YOUTUBE_REFUSES}. ({why})")
    return Refused(code, f"{why} {UPLOAD_INSTEAD}")


def _bounded(platform: str, work: Callable[[], dict]) -> dict:
    """Run one lookup with the wall-clock limit. Any failure is a refusal, never an error for the caller."""
    future = _pool.submit(work)
    try:
        return future.result(timeout=LOOKUP_TIMEOUT_SEC)
    except FutureTimeout:
        future.cancel()             # still waiting for a free slot: it never starts. Running: its sockets time out.
        raise _refused(platform, f"{NAMES.get(platform, 'The site')} did not answer within "
                                 f"{LOOKUP_TIMEOUT_SEC:g} seconds.", "preview_timeout") from None
    except Refused:
        raise
    except Exception:
        log.exception("link preview crashed for %s", platform)
        raise _refused(platform, f"{NAMES.get(platform, 'The site')} could not be read.", "source_failed") from None


def _lookup(source: Source) -> dict:
    s = get_settings()
    if source.downloader == DIRECT:
        if source.platform == "direct":
            from .fetch import check_hop
            check_hop(source.fetch_url)     # a name lookup only: private and local addresses are refused
            name = PurePosixPath(unquote(urlsplit(source.url).path)).name
            return answer(source.url, source, {"title": name})
        return answer(source.url, source)
    from . import platforms
    # No length limit here: a video longer than the limit can still be imported one range at a time, so "too
    # long" is decided for the part that is asked for (fit), not for the link.
    limits = platforms.Limits(max_bytes=min(s.import_max_bytes, s.max_upload_bytes),
                              max_duration_sec=float("inf"), timeout_sec=LOOKUP_TIMEOUT_SEC)
    info, refusal = platforms.preview(source.platform, source.fetch_url, limits, SOCKET_TIMEOUT_SEC)
    return answer(source.url, source, info, refusal)


def fit(body: dict, span: Span) -> tuple[Span | None, Refused | None]:
    """The part of a previewed video that `span` takes, checked against the import's length limits: (the span an
    import would take, None), or (None, why not). A link whose length is not known before the download (a direct,
    Drive or Dropbox link) is checked when it is imported."""
    s = get_settings()
    try:
        return fit_span(span, body.get("duration_sec"), s.min_duration_sec,
                        min(s.import_max_duration_sec, s.max_duration_sec),
                        open_end=body.get("live_status") == "recording"), None
    except Refused as e:
        if e.code == "video_too_long" and body.get("platform") == "youtube":
            from .platforms import YOUTUBE_REFUSES
            return None, Refused(e.code, f"{YOUTUBE_REFUSES}. ({e.message})")
        return None, e


def look(source: Source) -> dict:
    """The preview of a link that passed sources.classify. Makes the outbound request(s) and caches the answer.
    `lookup_ms`: how long the site took to answer."""
    started = time.monotonic()
    try:
        body = _bounded(source.platform, lambda: _lookup(source))
        ttl = CACHE_TTL_SEC if body["live_status"] != "recording" else FAILURE_TTL_SEC   # it grows by the minute
    except Refused as e:
        body, ttl = answer(source.url, source, refusal=e), FAILURE_TTL_SEC
    body["lookup_ms"] = int((time.monotonic() - started) * 1000)
    _remember(source.url, body, ttl)
    return body
