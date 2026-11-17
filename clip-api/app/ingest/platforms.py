"""Twitch, Kick and YouTube, through yt-dlp used as a library (version pinned in requirements.txt; Unlicense).

The options are fixed here. `ydl_options` takes a folder and the size cap, nothing from a request and nothing
from settings, so no caller can switch on a login, cookies, a proxy, impersonation, geo-bypass or anything else
that gets around a block. What is deliberately off, and why:

- no cookies, no cookies from a browser, no user name, password, netrc or client certificate: public content only
- `proxy: ""`: a direct connection; proxy environment variables are ignored
- no impersonation target, and `curl_cffi` (which yt-dlp needs to impersonate a browser) is not installed
- `geo_bypass: False`: yt-dlp's default is to fake an X-Forwarded-For header on geo-blocked sites
- `js_runtimes: {}` and no remote components: YouTube's player challenges are not solved; if YouTube asks, it fails
- no extractor arguments (no alternative client identities), no plugins
- no sleep or throttle tricks: a small, fixed number of ordinary retries
- only five extractors can run (Twitch VOD and clip, Kick VOD and clip, YouTube video): no playlists, no channels
- yt-dlp never runs ffmpeg (`ffmpeg_location` points at nothing, `fixup: never`): the one ffmpeg call is ours,
  on the saved file, with `-protocol_whitelist file,pipe` and a timeout (CLAUDE.md)

A refusal by the site is a clean failure: Refused, with "upload the file instead".
"""
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..pipeline.ff import SAFE_IN, Deadline, PipelineError, run
from . import UPLOAD_INSTEAD, Refused
from .fetch import USER_AGENT
from .sources import VIDEO_EXT

os.environ["YTDLP_NO_PLUGINS"] = "1"          # before yt-dlp is imported: no plugin is ever loaded

from yt_dlp import YoutubeDL  # noqa: E402
from yt_dlp.utils import DownloadError  # noqa: E402

log = logging.getLogger("clipapi.ingest")

EXTRACTORS = ("twitch:vod", "twitch:clips", "kick:vod", "kick:clip", "youtube")
MAX_HEIGHT = 1080
RETRIES = 3                 # ordinary retries of a failed request or fragment; never a way to wait out a limit
SOCKET_TIMEOUT = 30
NO_FFMPEG = "/nonexistent/ffmpeg-is-not-for-yt-dlp"
NAMES = {"twitch": "Twitch", "kick": "Kick", "youtube": "YouTube"}
YOUTUBE_REFUSES = "YouTube often refuses automated downloads: upload the file instead"


@dataclass(frozen=True)
class Limits:
    max_bytes: int
    max_duration_sec: float
    timeout_sec: float


@dataclass
class Downloaded:
    path: Path
    filename: str


class _Quiet:
    """yt-dlp's messages go to our log at debug level, never to stdout."""
    def debug(self, msg): log.debug("yt-dlp: %s", msg)
    def info(self, msg): log.debug("yt-dlp: %s", msg)
    def warning(self, msg): log.debug("yt-dlp warning: %s", msg)
    def error(self, msg): log.debug("yt-dlp error: %s", msg)


def ydl_options(dest_dir: Path, max_bytes: int) -> dict:
    """Every option yt-dlp is given. Nothing here comes from a request or from settings except the size cap."""
    cap = int(max_bytes)
    return {
        # What to fetch: one video, one file that already has picture and sound, at most 1080p, within the cap.
        "format": f"b[height<=?{MAX_HEIGHT}][filesize<=?{cap}][filesize_approx<=?{cap}]",
        "allowed_extractors": list(EXTRACTORS),
        "noplaylist": True,
        "playlist_items": "1",
        "outtmpl": str(dest_dir / "download.%(ext)s"),
        "overwrites": True,
        "continuedl": False,
        "cachedir": False,
        # Public content only: no identity of any kind.
        "cookiefile": None,
        "cookiesfrombrowser": None,
        "username": None,
        "password": None,
        "videopassword": None,
        "usenetrc": False,
        "client_certificate": None,
        # No way around a block.
        "proxy": "",
        "geo_bypass": False,
        "impersonate": None,
        "extractor_args": {},
        "js_runtimes": {},
        "remote_components": [],
        "allow_unplayable_formats": False,
        "nocheckcertificate": False,
        "http_headers": {"User-Agent": USER_AGENT},
        # Ordinary, bounded behaviour.
        "retries": RETRIES,
        "fragment_retries": RETRIES,
        "extractor_retries": 1,
        "file_access_retries": 1,
        "socket_timeout": SOCKET_TIMEOUT,
        "concurrent_fragment_downloads": 1,
        "ignoreerrors": False,
        # yt-dlp never runs ffmpeg or any other program.
        "ffmpeg_location": NO_FFMPEG,
        "fixup": "never",
        "postprocessors": [],
        "hls_prefer_native": True,
        "external_downloader": None,
        # Quiet.
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "color": "never",
        "logger": _Quiet(),
    }


def _refusal(platform: str, raw: str) -> Refused:
    """Our own words for a yt-dlp failure. Its text is logged, not shown: it can suggest ways around a block."""
    name, text = NAMES.get(platform, "The site"), raw.lower()
    if "drm" in text:
        code, why = "drm_protected", "This video is DRM protected and cannot be imported."
    elif any(w in text for w in ("sign in", "log in", "login", "logged in", "cookies", "private", "subscriber",
                                 "members-only", "members only", "age-restricted", "confirm your age",
                                 "authentication", "password")):
        code, why = "login_required", ("This video needs a login (private, subscribers-only or age-restricted). "
                                       "Only public videos can be imported.")
    elif "geo" in text or "not available in your country" in text or "your location" in text:
        code, why = "geo_blocked", "This video is not available where our servers are."
    elif "requested format is not available" in text or "no video formats" in text:
        code, why = "no_format", ("No version of this video can be imported: it needs one file with picture and "
                                  "sound, at most 1080p, within the size limit.")
    elif "unsupported url" in text or "is not a valid url" in text:
        code, why = "unsupported_link", f"{name} has no single video at this link."
    elif any(w in text for w in ("403", "429", "impersonat", "cloudflare", "not a bot", "captcha", "forbidden",
                                 "too many requests", "blocked")):
        code, why = "source_refused", f"{name} refused the download."
    elif any(w in text for w in ("does not exist", "not found", "404", "unavailable", "removed", "deleted")):
        code, why = "not_found", f"{name} has no video at this link (it may have been removed)."
    else:
        code, why = "source_failed", f"{name} could not be read."
    if platform == "youtube":
        return Refused(code, f"{YOUTUBE_REFUSES}. ({why})")
    return Refused(code, f"{why} {UPLOAD_INSTEAD}")


def _new_ydl(dest_dir: Path, limits: Limits, hook: Callable[[dict], None] | None = None) -> YoutubeDL:
    options = ydl_options(dest_dir, limits.max_bytes)
    if hook is not None:
        options["progress_hooks"] = [hook]
    return YoutubeDL(options)


def _check(platform: str, info: dict | None, limits: Limits) -> dict:
    if not info or info.get("_type", "video") != "video":
        raise Refused("unsupported_link", f"Use a link to one video. {UPLOAD_INSTEAD}")
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        raise Refused("live_stream", "Live streams cannot be imported. Wait for the recording, or upload the file.")
    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > limits.max_duration_sec:
        raise Refused("video_too_long", f"Maximum video length is {int(limits.max_duration_sec // 3600)} hours.")
    size = info.get("filesize") or info.get("filesize_approx")
    if isinstance(size, (int, float)) and size > limits.max_bytes:
        raise Refused("file_too_large", f"Maximum import size is {limits.max_bytes // 1024 ** 2} MB.")
    return info


def look(platform: str, url: str, dest_dir: Path, limits: Limits, ydl: YoutubeDL | None = None) -> dict:
    """Read the video's public metadata, exactly as an import does before it downloads. Nothing is downloaded."""
    ydl = ydl or _new_ydl(dest_dir, limits)
    try:
        info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        log.warning("import refused by %s for %s: %s", platform, url, e)
        raise _refusal(platform, str(e)) from None
    return _check(platform, info, limits)


def download(platform: str, url: str, dest_dir: Path, limits: Limits,
             on_progress: Callable[[int, int | None], None] | None = None) -> Downloaded:
    """Download one public video into dest_dir as a file the pipeline can read. Raises Refused otherwise."""
    started = time.monotonic()

    def hook(status: dict) -> None:
        done = status.get("downloaded_bytes") or 0
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        if done > limits.max_bytes or (status.get("total_bytes") or 0) > limits.max_bytes:
            raise Refused("file_too_large", f"Maximum import size is {limits.max_bytes // 1024 ** 2} MB.")
        if time.monotonic() - started > limits.timeout_sec:
            raise Refused("import_timeout", f"The download took longer than {int(limits.timeout_sec // 60)} "
                                            f"minutes and was stopped. {UPLOAD_INSTEAD}")
        if on_progress:
            on_progress(int(done), int(total) if total else None)

    ydl = _new_ydl(dest_dir, limits, hook)
    info = look(platform, url, dest_dir, limits, ydl)
    try:
        ydl.process_ie_result(info, download=True)
    except DownloadError as e:
        log.warning("import download refused by %s for %s: %s", platform, url, e)
        raise _refusal(platform, str(e)) from None
    files = sorted((p for p in dest_dir.glob("download.*") if p.is_file() and not p.name.endswith((".part", ".ytdl"))),
                   key=lambda p: p.stat().st_size, reverse=True)
    if not files or files[0].stat().st_size == 0:
        raise _refusal(platform, "nothing was downloaded")
    left = max(60.0, limits.timeout_sec - (time.monotonic() - started))
    path = as_video_file(files[0], Deadline(left))
    title = re.sub(r"[^\w.\- ]+", "_", str(info.get("title") or info.get("id") or platform)).strip(" ._")[:200]
    return Downloaded(path, f"{title or platform}{path.suffix}")


def as_video_file(path: Path, deadline: Deadline) -> Path:
    """HLS downloads are MPEG-TS whatever yt-dlp named them: repackage those as MP4 (a copy, nothing is
    re-encoded) so the result plays and seeks like an upload. Other containers are kept under their own name."""
    try:
        res = run(["ffprobe", "-v", "error", *SAFE_IN, "-show_entries", "format=format_name", "-of",
                   "default=nw=1:nk=1", path], deadline, cap=120)
        container = res.stdout.strip().lower()
    except PipelineError:
        raise Refused("unsupported_media", f"The downloaded file is not a readable video. {UPLOAD_INSTEAD}") from None
    if "mpegts" in container:
        out = path.with_name("video.mp4")
        try:
            run(["ffmpeg", "-loglevel", "error", "-y", *SAFE_IN, "-i", path, "-map", "0:v:0", "-map", "0:a:0?",
                 "-c", "copy", "-movflags", "+faststart", out], deadline, cap=1800)
            path.unlink(missing_ok=True)
            return out
        except PipelineError:
            out.unlink(missing_ok=True)
            ts = path.with_name("video.ts")       # still a file type uploads accept
            path.rename(ts)
            return ts
    if path.suffix.lower() not in VIDEO_EXT:
        ext = next((e for e in (".mp4", ".webm", ".mkv", ".mov", ".flv", ".avi")
                    if e.strip(".") in container or (e == ".mkv" and "matroska" in container)), None)
        if ext is None:
            raise Refused("unsupported_type", f"The downloaded file is not a video type we accept. {UPLOAD_INSTEAD}")
        renamed = path.with_name(f"video{ext}")
        path.rename(renamed)
        return renamed
    return path
