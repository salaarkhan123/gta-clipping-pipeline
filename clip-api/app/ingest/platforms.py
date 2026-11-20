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
- only five extractors can run (Twitch VOD and clip, Kick VOD and clip, YouTube video): no playlists, no channels,
  and never a live stream: a recording in progress is read from its VOD, the part the site has already published
- yt-dlp never runs ffmpeg (`ffmpeg_location` points at nothing, `fixup: never`). Picture and sound that the
  site serves as two streams are downloaded as two files and joined by our own ffmpeg call, on the saved files,
  with `-protocol_whitelist file,pipe` and a timeout (CLAUDE.md). A time range is cut the same way.

Metadata and media are separate. `metadata` asks the site what the link is and never chooses a format, so a
video whose formats we cannot use still has a title, a channel and a thumbnail. `download` chooses the formats.

A refusal by the site is a clean failure: Refused, with "upload the file instead".
"""
import copy
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

from ..pipeline.ff import SAFE_IN, Deadline, PipelineError, run
from . import UPLOAD_INSTEAD, Refused, Span, fit_span
from .fetch import USER_AGENT
from .sources import VIDEO_EXT

os.environ["YTDLP_NO_PLUGINS"] = "1"          # before yt-dlp is imported: no plugin is ever loaded

from yt_dlp import YoutubeDL  # noqa: E402
from yt_dlp.networking import Request  # noqa: E402
from yt_dlp.utils import DownloadError, ExtractorError  # noqa: E402

log = logging.getLogger("clipapi.ingest")

EXTRACTORS = ("twitch:vod", "twitch:clips", "kick:vod", "kick:clip", "youtube")
MAX_HEIGHT = 1080
RETRIES = 3                 # ordinary retries of a failed request or fragment; never a way to wait out a limit
SOCKET_TIMEOUT = 30
NO_FFMPEG = "/nonexistent/ffmpeg-is-not-for-yt-dlp"
NOWHERE = Path("/nonexistent/a-preview-writes-nothing")     # the output folder of a preview
NAMES = {"twitch": "Twitch", "kick": "Kick", "youtube": "YouTube"}
YOUTUBE_REFUSES = "YouTube often refuses automated downloads: upload the file instead"
MAX_PLAYLIST_BYTES = 8 * 1024 ** 2      # a media playlist of a very long recording is a few hundred kilobytes
INDEX_BYTES = 1024 ** 2                 # the start of a fragmented MP4 holds its header and its segment index
CHUNK_BYTES = 8 * 1024 ** 2             # one byte-range request of a stream (yt-dlp itself asks for 10 MB at a time)
RECORDING = "_recording"                # set on the metadata of a VOD whose stream is still live


@dataclass(frozen=True)
class Limits:
    max_bytes: int
    max_duration_sec: float
    timeout_sec: float
    min_duration_sec: float = 0.0


@dataclass
class Downloaded:
    path: Path
    filename: str
    span: Span = Span()                 # the part of the source that was taken (whole: Span())
    partial: bool = False               # only that part was downloaded (False: the whole video was fetched)
    fetched_bytes: int = 0              # what came over the network, all streams together
    fetched_sec: float | None = None    # the seconds of video those bytes hold (whole segments, so a little over a range)
    full_bytes: int | None = None       # the size of the whole video in the streams that were picked
    full_sec: float | None = None       # the whole video's length
    full_estimated: bool = False        # full_bytes is worked out from what was fetched: the site gave no size


class _Quiet:
    """yt-dlp's messages go to our log at debug level, never to stdout."""
    def debug(self, msg): log.debug("yt-dlp: %s", msg)
    def info(self, msg): log.debug("yt-dlp: %s", msg)
    def warning(self, msg): log.debug("yt-dlp warning: %s", msg)
    def error(self, msg): log.debug("yt-dlp error: %s", msg)


def format_spec(cap: int, hls_only: bool = False) -> str:
    """Which streams to take, best first. Picture and sound may be two streams (YouTube serves nothing else above
    360p): they are joined after the download. Preferred: H.264 with AAC at up to 1080p, which every part of the
    pipeline reads without converting; then any codec at up to 1080p (VP9, AV1, Opus: all readable); then
    whatever the video has. The picture stream must fit the size cap, so a long recording comes in at the highest
    resolution that fits. `hls_only`: only streams served as a segment list, from which a time range can be
    downloaded on its own."""
    cap = int(cap)
    fit = ("[protocol^=m3u8]" if hls_only else "") + f"[filesize<=?{cap}][filesize_approx<=?{cap}]"
    sound = "[protocol^=m3u8]" if hls_only else ""
    aac = sound or "[acodec^=mp4a]"         # segment-list sound streams do not name their codec (it is AAC)
    return "/".join((
        f"bv*[height<={MAX_HEIGHT}][vcodec^=avc1]{fit}+ba{aac}",
        f"b[height<={MAX_HEIGHT}][vcodec^=avc1]{fit}",
        f"bv*[height<={MAX_HEIGHT}]{fit}+ba{sound}",
        f"b[height<={MAX_HEIGHT}]{fit}",
        f"bv*{fit}+ba{sound}",
        f"b{fit}",
    ))


def ydl_options(dest_dir: Path, max_bytes: int) -> dict:
    """Every option yt-dlp is given. Nothing here comes from a request or from settings except the size cap."""
    return {
        # What to fetch: one video, at most 1080p when the video has that, within the cap (format_spec).
        "format": format_spec(max_bytes),
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


def _has(text: str, *words: str) -> bool:
    return any(w in text for w in words)


def _refusal(platform: str, raw: str) -> Refused:
    """Our own words for a yt-dlp failure. Its text is logged, not shown: it can suggest ways around a block.
    The order matters: the specific reasons are read before the general ones they also match."""
    name, text = NAMES.get(platform, "The site"), raw.lower().replace("’", "'")
    if "drm" in text:
        code, why = "drm_protected", "This video is DRM protected and cannot be imported."
    elif _has(text, "not a bot", "captcha", "impersonat", "cloudflare"):
        code, why = "source_refused", f"{name} refused the request from our servers."
    elif _has(text, "confirm your age", "age-restricted", "age restricted", "inappropriate for some users"):
        code, why = "age_restricted", ("This video is age-restricted, so it needs a signed-in viewer. Only videos "
                                       "anyone can watch without signing in can be imported.")
    elif _has(text, "members-only", "members only", "join this channel", "channel's members", "subscriber",
              "subscription", "premium"):
        code, why = "members_only", ("This video is for members or subscribers only. Only videos anyone can "
                                     "watch without signing in can be imported.")
    elif "private" in text:
        code, why = "private_video", ("This video is private. Only videos anyone can watch without signing in "
                                      "can be imported.")
    elif _has(text, "will begin in", "premieres in", "has not started", "is_upcoming"):
        code, why = "upcoming", "This stream has not started yet. Import the recording after it ends."
    elif _has(text, "sign in", "log in", "login", "logged in", "cookies", "authentication", "password"):
        code, why = "login_required", ("This video needs a login. Only videos anyone can watch without signing in "
                                       "can be imported.")
    elif _has(text, "geo", "in your country", "your location", "your region"):
        code, why = "geo_blocked", "This video is not available where our servers are."
    elif "requested format is not available" in text or "no video formats" in text:
        code, why = "no_format", "This video has no version with a picture that can be imported."
    elif "unsupported url" in text or "is not a valid url" in text:
        code, why = "unsupported_link", f"{name} has no single video at this link."
    elif _has(text, "403", "429", "forbidden", "too many requests", "blocked"):
        code, why = "source_refused", f"{name} refused the download."
    elif platform in ("twitch", "kick") and _has(text, "does not exist", "not found", "404", "expired"):
        code, why = "expired", (f"{name} no longer has this video: recordings there expire after a while, or it "
                                "was deleted.")
    elif _has(text, "does not exist", "not found", "404", "unavailable", "removed", "deleted", "terminated",
              "no longer available"):
        code, why = "not_found", f"{name} has no video at this link (it is unavailable or was removed)."
    else:
        code, why = "source_failed", f"{name} could not be read."
    if platform == "youtube":
        return Refused(code, f"{YOUTUBE_REFUSES}. ({why})")
    return Refused(code, f"{why} {UPLOAD_INSTEAD}")


def _new_ydl(dest_dir: Path, limits: Limits, hook: Callable[[dict], None] | None = None,
             socket_timeout: int = SOCKET_TIMEOUT) -> YoutubeDL:
    options = ydl_options(dest_dir, limits.max_bytes)
    options["socket_timeout"] = socket_timeout
    if hook is not None:
        options["progress_hooks"] = [hook]
    return YoutubeDL(options)


# ---- what the link is -------------------------------------------------------------------------------------------

@dataclass
class Playlist:
    """An HLS media playlist: the segments of one stream, in order."""
    segments: list[tuple[float, float, str]]    # (starts at, lasts, address)
    init: str | None                            # the header segment of fragmented MP4 streams
    ended: bool                                 # the site has closed the list: nothing more will be added
    plain: bool                                 # nothing we do not handle (encryption, byte ranges, a master list)

    @property
    def seconds(self) -> float:
        return self.segments[-1][0] + self.segments[-1][1] if self.segments else 0.0


def read_playlist(text: str, base_url: str) -> Playlist:
    segments, at, lasts, init, plain = [], 0.0, None, None, True
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            try:
                lasts = float(line[8:].split(",")[0])
            except ValueError:
                plain = False
        elif line.startswith("#EXT-X-MAP:"):
            found = re.search(r'URI="([^"]+)"', line)
            if init is not None or not found or "BYTERANGE" in line:
                plain = False               # more than one header, or a header inside another file
            else:
                init = urljoin(base_url, found.group(1))
        elif line.startswith(("#EXT-X-BYTERANGE", "#EXT-X-STREAM-INF")):
            plain = False
        elif line.startswith("#EXT-X-KEY") and "METHOD=NONE" not in line:
            plain = False
        elif line and not line.startswith("#") and lasts is not None:
            segments.append((at, lasts, urljoin(base_url, line)))
            at, lasts = at + lasts, None
    return Playlist(segments, init, "#EXT-X-ENDLIST" in text, plain and bool(segments))


def _playlist(ydl: YoutubeDL, fmt: dict) -> Playlist:
    with ydl.urlopen(fmt["url"]) as response:
        return read_playlist(response.read(MAX_PLAYLIST_BYTES).decode("utf-8", "replace"), fmt["url"])


def _is_hls(fmt: dict) -> bool:
    return str(fmt.get("protocol") or "").startswith("m3u8") and bool(fmt.get("url"))


@dataclass
class Index:
    """The segment index of a fragmented MP4 stream served as one file (its `sidx` box): where each few seconds
    of the stream are in the file, so a part of it can be asked for by byte range, as a player does."""
    header_end: int                                 # bytes [0, header_end) are the stream's header (ftyp, moov)
    segments: list[tuple[float, float, int, int]]   # (starts at, lasts, first byte, the byte after its last)


def read_index(data: bytes) -> Index | None:
    """The index in the first bytes of a file, or None when it has none there (a plain MP4, WebM, anything else)."""
    at = 0
    while at + 8 <= len(data):
        size, kind, head = int.from_bytes(data[at:at + 4], "big"), data[at + 4:at + 8], 8
        if size == 1 and at + 16 <= len(data):
            size, head = int.from_bytes(data[at + 8:at + 16], "big"), 16
        if size < head or kind in (b"moof", b"mdat"):
            return None                             # not a box, or the media starts before any index
        if kind == b"sidx":
            if at + size > len(data):
                return None
            body, version = data[at + head:at + size], data[at + head]
            timescale = int.from_bytes(body[8:12], "big")
            wide = 8 if version else 4
            starts = int.from_bytes(body[12:12 + wide], "big")
            first = int.from_bytes(body[12 + wide:12 + 2 * wide], "big")
            p = 12 + 2 * wide + 2
            count, p = int.from_bytes(body[p:p + 2], "big"), p + 2
            if not timescale or len(body) < p + 12 * count:
                return None
            segments, byte, tick = [], at + size + first, starts
            for n in range(count):
                ref = int.from_bytes(body[p + 12 * n:p + 12 * n + 4], "big")
                lasts = int.from_bytes(body[p + 12 * n + 4:p + 12 * n + 8], "big")
                if ref >> 31:
                    return None                     # an index of indexes: not something a single stream file has
                segments.append((tick / timescale, lasts / timescale, byte, byte + (ref & 0x7FFFFFFF)))
                byte, tick = byte + (ref & 0x7FFFFFFF), tick + lasts
            return Index(at, segments) if segments else None
        at += size
    return None


def _index(ydl: YoutubeDL, fmt: dict) -> Index | None:
    """Ask for the first megabyte of a stream and read its index. None when the server does not serve byte
    ranges (it must answer 206) or the stream has no index there."""
    with ydl.urlopen(Request(fmt["url"], headers={"Range": f"bytes=0-{INDEX_BYTES - 1}"})) as response:
        if getattr(response, "status", None) != 206:
            return None
        return read_index(response.read(INDEX_BYTES))


def _settle_recording(platform: str, info: dict, ydl: YoutubeDL) -> None:
    """Whether a Twitch VOD is really still being recorded. yt-dlp guesses it from the thumbnail: while Twitch
    shows its "processing" placeholder the VOD is called live, and that placeholder also stays for a while after
    a stream has ended. The VOD's own segment list is the fact: closed means the recording is complete; open
    means the stream is still live, and the list is the part published so far (its length is the VOD's length
    right now). One small request, made only for a VOD yt-dlp calls live. If it fails, the VOD stays "live"."""
    if platform != "twitch" or not info.get("is_live"):
        return
    streams = [f for f in info.get("formats") or [] if isinstance(f, dict) and _is_hls(f)]
    if not streams:
        return
    try:
        playlist = _playlist(ydl, streams[0])
    except Exception as e:      # a refused or failed request: keep what yt-dlp said
        log.warning("could not read the segment list of %s: %s", info.get("id"), e)
        return
    if not playlist.segments:
        return
    info["duration"] = round(playlist.seconds, 3)
    if playlist.ended:
        info["is_live"], info["live_status"] = False, "was_live"
    else:
        info[RECORDING] = True


def live_state(info: dict) -> str:
    """not_live | was_live (a finished broadcast) | recording (a VOD whose stream is still live: the part so far
    can be read) | live (a broadcast with no recording to read yet) | upcoming."""
    status = info.get("live_status")
    if status == "is_upcoming":
        return "upcoming"
    if info.get(RECORDING):
        return "recording"
    if info.get("is_live") or status in ("is_live", "post_live"):
        return "live"
    if info.get("was_live") or status == "was_live":
        return "was_live"
    return "not_live"


def metadata(platform: str, url: str, ydl: YoutubeDL) -> dict | None:
    """The video's public metadata, unchecked. No format is chosen and nothing is downloaded. A refusal by the
    site is Refused."""
    try:
        info = ydl.extract_info(url, download=False, process=False)
    except (DownloadError, ExtractorError) as e:
        log.warning("import refused by %s for %s: %s", platform, url, e)
        raise _refusal(platform, str(e)) from None
    if isinstance(info, dict) and info.get("_type", "video") == "video":
        info = dict(info)
        info["formats"] = [f for f in (info.get("formats") or []) if isinstance(f, dict)]
        _settle_recording(platform, info, ydl)
    return info


def _check(platform: str, info: dict | None, limits: Limits, span: Span = Span()) -> Span:
    """Refuse what cannot be imported, from the metadata alone. Returns the part that will be taken."""
    if not isinstance(info, dict) or info.get("_type", "video") != "video":
        raise Refused("unsupported_link", f"Use a link to one video. {UPLOAD_INSTEAD}")
    state = live_state(info)
    if state == "upcoming":
        raise Refused("upcoming", "This stream has not started yet. Import the recording after it ends.")
    if state == "live":
        raise Refused("live_stream", "Live streams cannot be imported. Wait for the recording, or upload the file.")
    formats = info.get("formats") or []
    if (formats and all(f.get("has_drm") for f in formats)) or (not formats and info.get("_has_drm")):
        raise _refusal(platform, "This video is DRM protected")
    duration = info.get("duration")
    duration = float(duration) if isinstance(duration, (int, float)) and duration > 0 else None
    return fit_span(span, duration, limits.min_duration_sec, limits.max_duration_sec, open_end=state == "recording")


def look(platform: str, url: str, dest_dir: Path, limits: Limits, ydl: YoutubeDL | None = None,
         span: Span = Span()) -> tuple[dict, Span]:
    """Read the video's public metadata, exactly as an import does before it downloads, and check it. Returns
    (metadata, the part that will be taken). Nothing is downloaded."""
    info = metadata(platform, url, ydl or _new_ydl(dest_dir, limits))
    return info, _check(platform, info, limits, span)


def preview(platform: str, url: str, limits: Limits, socket_timeout: int) -> tuple[dict | None, Refused | None]:
    """(metadata, refusal) for a link preview: the same options and the same checks as an import, with a shorter
    socket timeout. The metadata is kept when a check refuses (a video that is too long still has a title).
    Nothing is downloaded and nothing is written: the output folder does not exist."""
    info = metadata(platform, url, _new_ydl(NOWHERE, limits, socket_timeout=socket_timeout))
    try:
        _check(platform, info, limits)
    except Refused as e:
        return (info if isinstance(info, dict) else None), e
    return info, None


# ---- the download -----------------------------------------------------------------------------------------------

def _size(fmt: dict) -> float | None:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    return float(size) if isinstance(size, (int, float)) and size > 0 else None


def _select(ydl: YoutubeDL, info: dict, spec: str) -> tuple[dict, list[dict]] | None:
    """(the processed metadata, the streams yt-dlp's own selector picks for `spec`), or None when none match."""
    ydl.format_selector = ydl.build_format_selector(spec)
    try:
        done = ydl.process_ie_result(copy.deepcopy(info), download=False)
    except (DownloadError, ExtractorError) as e:
        if "requested format is not available" in str(e).lower() or "no video formats" in str(e).lower():
            return None
        raise
    streams = list(done.get("requested_formats") or [done])
    if all(f.get("vcodec") == "none" for f in streams):     # yt-dlp settles for sound alone when there is no picture
        return None
    return done, streams


def _share(info: dict, span: Span) -> float:
    """The part of the video's length that `span` takes (1.0 when that is not known)."""
    duration = info.get("duration")
    if span.whole or not isinstance(duration, (int, float)) or duration <= 0:
        return 1.0
    return max(1e-6, min(1.0, ((span.end if span.end is not None else duration) - span.start) / duration))


def choose(ydl: YoutubeDL, platform: str, info: dict, limits: Limits,
           span: Span) -> tuple[dict, list[dict], list[tuple[dict, float]] | None]:
    """(processed metadata, the streams to download, their cut-down pieces when only the span is downloaded).
    A range is taken from segment-list streams when the video has them, with the size cap applied to the range's
    share of the video; otherwise the whole video is fetched and the range is cut from it afterwards."""
    share = _share(info, span)
    if share < 1.0 or info.get(RECORDING):
        picked = _select(ydl, info, format_spec(int(limits.max_bytes / share), hls_only=True))
        if picked:
            pieces = [_piece(ydl, fmt, span) for fmt in picked[1]]
            if all(pieces):
                return picked[0], picked[1], pieces
        # No segment list (YouTube does not always answer with one): the streams served as one indexed file each
        # give the same part by byte range.
        picked = None if info.get(RECORDING) else _select(ydl, info, format_spec(int(limits.max_bytes / share)))
        if picked:
            pieces = [_byte_piece(ydl, fmt, span) for fmt in picked[1]]
            if all(pieces):
                return picked[0], picked[1], pieces
    picked = _select(ydl, info, format_spec(limits.max_bytes))
    if picked:
        return picked[0], picked[1], None
    if _select(ydl, info, format_spec(2 ** 62)):       # there is something, but nothing small enough
        raise Refused("file_too_large", f"Every version of this video is larger than the import limit of "
                                        f"{limits.max_bytes // 1024 ** 2} MB. Choose a shorter range of it, or "
                                        "upload a smaller file.")
    raise _refusal(platform, "Requested format is not available")


def _piece(ydl: YoutubeDL, fmt: dict, span: Span) -> tuple[dict, float] | None:
    """The stream cut down to the segments that hold `span`: (a format yt-dlp's own segment downloader takes,
    where its first segment starts in the video). None when the segment list is not one we handle."""
    try:
        playlist = _playlist(ydl, fmt)
    except Exception as e:
        log.warning("could not read a segment list: %s", e)
        return None
    if not playlist.plain:
        return None
    wanted = [s for s in playlist.segments
              if s[0] + s[1] > span.start and (span.end is None or s[0] < span.end)]
    if not wanted:
        raise Refused("bad_range", f"The range is outside what the video has right now. {UPLOAD_INSTEAD}")
    fragments = [{"url": address, "duration": lasts} for _at, lasts, address in wanted]
    if playlist.init:
        fragments.insert(0, {"url": playlist.init})
    return {"protocol": "http_dash_segments", "fragments": fragments, "ext": "mp4" if playlist.init else "ts",
            "is_live": False, "seconds": round(sum(s[1] for s in wanted), 3)}, wanted[0][0]


def _byte_piece(ydl: YoutubeDL, fmt: dict, span: Span) -> tuple[dict, float] | None:
    """The same for a stream served as one indexed MP4 file: (the byte ranges that hold `span`, where the first
    of its segments starts in the video). None when the stream is not such a file."""
    if str(fmt.get("protocol") or "") not in ("https", "http") or fmt.get("ext") not in ("mp4", "m4a") or not fmt.get("url"):
        return None
    try:
        index = _index(ydl, fmt)
    except Exception as e:
        log.warning("could not read a stream's index: %s", e)
        return None
    if index is None:
        return None
    wanted = [s for s in index.segments if s[0] + s[1] > span.start and (span.end is None or s[0] < span.end)]
    if not wanted:
        raise Refused("bad_range", f"The range is outside what the video has right now. {UPLOAD_INSTEAD}")
    first, last = wanted[0][2], wanted[-1][3]
    ranges = [(0, index.header_end)] + [(a, min(a + CHUNK_BYTES, last)) for a in range(first, last, CHUNK_BYTES)]
    return {"byte_ranges": ranges, "ext": fmt["ext"], "seconds": round(sum(s[1] for s in wanted), 3)}, wanted[0][0]


def _fetch_ranges(ydl: YoutubeDL, fmt: dict, ranges: list[tuple[int, int]], target: Path,
                  hook: Callable[[dict], None]) -> None:
    """Write the byte ranges of a stream to `target`, one request each, through yt-dlp's own connection (the
    fixed options above). A failed request is tried again RETRIES times; a server that stops serving ranges
    is a failure, never a fall back to the whole file from here."""
    with open(target, "wb") as out:
        for start, end in ranges:
            for attempt in range(RETRIES + 1):
                at = out.tell()
                try:
                    with ydl.urlopen(Request(fmt["url"], headers={"Range": f"bytes={start}-{end - 1}"})) as response:
                        if getattr(response, "status", None) != 206:
                            raise DownloadError("the server did not serve a byte range")
                        while True:
                            block = response.read(1024 * 1024)
                            if not block:
                                break
                            out.write(block)
                            hook({"status": "downloading", "downloaded_bytes": out.tell()})
                    if out.tell() - at != end - start:
                        raise OSError(f"a byte range came back short: {out.tell() - at} of {end - start}")
                    break
                except (DownloadError, Refused):
                    raise
                except Exception as e:      # a dropped or refused request
                    out.seek(at)
                    out.truncate()
                    if attempt == RETRIES:
                        raise DownloadError(f"unable to download video data: {e}") from None
        got = out.tell()
    hook({"status": "finished", "downloaded_bytes": got, "total_bytes": None})


def download(platform: str, url: str, dest_dir: Path, limits: Limits,
             on_progress: Callable[[int, int | None], None] | None = None, span: Span = Span(),
             on_stage: Callable[[str], None] | None = None) -> Downloaded:
    """Download one public video, or the `span` of it, into dest_dir as a file the pipeline can read. Raises
    Refused otherwise. `on_progress(bytes so far, expected bytes or None)`; `on_stage(name)` for
    "downloading" and "merging"."""
    started = time.monotonic()
    before, expected = [0], [None]          # bytes of the streams already finished; the expected total

    def hook(status: dict) -> None:
        got = int(status.get("downloaded_bytes") or 0)
        done = before[0] + got
        # The cap is checked against the streams already finished plus this one (what it has, or what it says it
        # will have), before this stream joins the finished ones, so a finished stream is never counted twice.
        if done > limits.max_bytes or before[0] + (status.get("total_bytes") or 0) > limits.max_bytes:
            raise Refused("file_too_large", f"Maximum import size is {limits.max_bytes // 1024 ** 2} MB.")
        if status.get("status") == "finished":
            before[0] = done
        if time.monotonic() - started > limits.timeout_sec:
            raise Refused("import_timeout", f"The download took longer than {int(limits.timeout_sec // 60)} "
                                            f"minutes and was stopped. {UPLOAD_INSTEAD}")
        if on_progress:
            total = expected[0] or status.get("total_bytes") or status.get("total_bytes_estimate")
            on_progress(done, max(int(total), done) if total else None)

    ydl = _new_ydl(dest_dir, limits, hook)
    info, span = look(platform, url, dest_dir, limits, ydl, span)
    parts: list[tuple[Path, float]] = []
    fetched_bytes, full_bytes = 0, None
    try:
        done, streams, pieces = choose(ydl, platform, info, limits, span)
        sizes = [_size(f) for f in streams]
        full_bytes = int(sum(sizes)) if all(sizes) else None
        if all(sizes):
            expected[0] = sum(sizes) * (_share(info, span) if pieces else 1.0)
        if on_stage:
            on_stage("downloading")
        base = {k: v for k, v in done.items() if k not in ("formats", "requested_formats")}
        for n, fmt in enumerate(streams):
            piece, offset = pieces[n] if pieces else ({}, 0.0)
            target = dest_dir / f"download.{n}.{piece.get('ext') or fmt.get('ext') or 'mp4'}"
            if piece.get("byte_ranges"):
                _fetch_ranges(ydl, fmt, piece["byte_ranges"], target, hook)
                ok = True
            else:
                ok, _real = ydl.dl(str(target), {**base, **fmt, **piece})
            if not ok or not target.is_file() or target.stat().st_size == 0:
                raise DownloadError("nothing was downloaded")
            parts.append((target, offset))
            fetched_bytes += target.stat().st_size
    except (DownloadError, ExtractorError) as e:
        log.warning("import download refused by %s for %s: %s", platform, url, e)
        _remove_partials(dest_dir)
        raise _refusal(platform, str(e)) from None
    except Refused:                     # a cap in the progress hook: yt-dlp leaves .part and .ytdl files behind
        _remove_partials(dest_dir)
        raise
    if on_stage:
        on_stage("merging")
    left = max(60.0, limits.timeout_sec - (time.monotonic() - started))
    path = assemble(parts, span, dest_dir, Deadline(left))
    title = re.sub(r"[^\w.\- ]+", "_", str(info.get("title") or info.get("id") or platform)).strip(" ._")[:200]
    length = info.get("duration")
    length = float(length) if isinstance(length, (int, float)) and length > 0 else None
    # The picture stream's segments are what was fetched of the video's length; a whole fetch is all of it.
    seconds = pieces[0][0]["seconds"] if pieces else length
    estimated = full_bytes is None and bool(pieces) and bool(seconds) and bool(length)
    if estimated:                       # segment-list streams have no size: the same rate over the whole length
        full_bytes = int(fetched_bytes / seconds * length)
    return Downloaded(path, f"{title or platform}{path.suffix}", span, pieces is not None,
                      fetched_bytes, seconds, full_bytes, length, estimated)


def _remove_partials(dest_dir: Path) -> None:
    for p in dest_dir.glob("download.*"):
        p.unlink(missing_ok=True)


# ---- our own ffmpeg, on the saved files -------------------------------------------------------------------------

def assemble(parts: list[tuple[Path, float]], span: Span, dest_dir: Path, deadline: Deadline) -> Path:
    """One video file from what was downloaded. `parts`: (file, where it starts in the source video); two parts
    are the picture and the sound. A whole video in one file is kept as it is (as_video_file); otherwise one
    ffmpeg call joins the streams and keeps `span`, copying, never re-encoding."""
    if len(parts) == 1 and span.whole:
        return as_video_file(parts[0][0], deadline)
    # MP4 holds H.264, AAC and the rest of what MP4 and transport-stream downloads carry; WebM streams go in MKV.
    out = dest_dir / ("video.mp4" if all(p.suffix.lower() in (".mp4", ".m4a", ".m4v", ".ts", ".mov")
                                         for p, _ in parts) else "video.mkv")
    cmd: list = ["ffmpeg", "-loglevel", "error", "-y"]
    for path, offset in parts:
        skip = max(0.0, span.start - offset)
        cmd += [*SAFE_IN, *(["-ss", f"{skip:.3f}"] if skip > 0 else []),
                *(["-t", f"{span.end - span.start:.3f}"] if span.end is not None else []), "-i", path]
    cmd += (["-map", "0:v:0", "-map", "1:a:0"] if len(parts) == 2 else ["-map", "0:v:0", "-map", "0:a:0?"])
    cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero",
            *(["-movflags", "+faststart"] if out.suffix == ".mp4" else []), out]
    try:
        run(cmd, deadline, cap=1800)
    except PipelineError:
        out.unlink(missing_ok=True)
        raise Refused("unsupported_media", f"The downloaded video could not be put together. {UPLOAD_INSTEAD}") from None
    for path, _ in parts:
        path.unlink(missing_ok=True)
    return out


def cut(path: Path, span: Span, dest_dir: Path, deadline: Deadline) -> Path:
    """`span` of a saved video file, as a new file (a copy, nothing is re-encoded)."""
    return assemble([(path, 0.0)], span, dest_dir, deadline)


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
