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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import PurePosixPath
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from ..config import get_settings
from . import UPLOAD_INSTEAD, Refused
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


def _thumbnail(info: dict) -> str | None:
    """The thumbnail the site's public metadata names, as given (https only). Never fetched or proxied by us."""
    url = _https(info.get("thumbnail"))
    if url is None:
        thumbs = [t for t in info.get("thumbnails") or [] if isinstance(t, dict) and _https(t.get("url"))]
        url = thumbs[-1]["url"] if thumbs else None           # yt-dlp lists them worst first
    return url


def _kind(source: Source | None, info: dict) -> str | None:
    if source is None:
        return None
    if info.get("live_status") == "is_upcoming":
        return "upcoming"
    if info.get("is_live") or info.get("live_status") in ("is_live", "post_live"):
        return "live"
    if source.url.startswith("https://clips.twitch.tv/") or "/clips/" in source.url:
        return "clip"
    return "video"


def answer(url: str, source: Source | None, info: dict | None = None, refusal: Refused | None = None) -> dict:
    """The response body. `url` is the canonical link when the link is one we import from."""
    info = info if isinstance(info, dict) else {}
    duration = info.get("duration")
    return {
        "url": source.url if source else url.strip()[:MAX_URL_LEN],
        "platform": source.platform if source else None,
        "supported": refusal is None,
        "title": _text(info.get("title")),
        "channel": _text(info.get("channel") or info.get("uploader")),
        "duration_sec": float(duration) if isinstance(duration, (int, float)) and duration >= 0 else None,
        "thumbnail_url": _thumbnail(info),
        "kind": _kind(source, info),
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
    limits = platforms.Limits(max_bytes=min(s.import_max_bytes, s.max_upload_bytes),
                              max_duration_sec=min(s.import_max_duration_sec, s.max_duration_sec),
                              timeout_sec=LOOKUP_TIMEOUT_SEC)
    info, refusal = platforms.preview(source.platform, source.fetch_url, limits, SOCKET_TIMEOUT_SEC)
    duration = (info or {}).get("duration")
    if refusal is None and isinstance(duration, (int, float)) and duration < s.min_duration_sec:
        refusal = Refused("video_too_short", f"Minimum video length is {s.min_duration_sec} seconds.")
    return answer(source.url, source, info, refusal)


def look(source: Source) -> dict:
    """The preview of a link that passed sources.classify. Makes the outbound request(s) and caches the answer."""
    try:
        body = _bounded(source.platform, lambda: _lookup(source))
        ttl = CACHE_TTL_SEC
    except Refused as e:
        body, ttl = answer(source.url, source, refusal=e), FAILURE_TTL_SEC
    _remember(source.url, body, ttl)
    return body
