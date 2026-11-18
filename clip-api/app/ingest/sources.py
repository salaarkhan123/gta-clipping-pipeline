"""The allow-list: which hosts may be imported from, and which downloader handles each link.

`classify(url)` is pure (no network). It returns a Source with a canonical URL: the form that is logged, stored
on the upload and matched by the takedown flow, so two spellings of one link are one source.
"""
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from . import UPLOAD_INSTEAD, Refused

MAX_URL_LEN = 1000          # uploads.source_url and import_log.source_url hold this many characters
VIDEO_EXT = frozenset({".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".flv", ".ts"})   # = routes_media.ALLOWED_EXT

PLATFORM = "platform"       # handled by platforms.py (yt-dlp)
DIRECT = "direct"           # handled by fetch.py (one https download)


@dataclass(frozen=True)
class Source:
    platform: str           # twitch | kick | youtube | gdrive | dropbox | direct
    downloader: str         # PLATFORM or DIRECT
    url: str                # canonical: logged, stored, matched by takedown
    fetch_url: str          # what the downloader is given


# What the website and the API docs list. Order is the order of support.
SOURCES = (
    {"platform": "twitch", "name": "Twitch", "accepts": "A VOD or a clip.",
     "example": "https://www.twitch.tv/videos/1234567890"},
    {"platform": "kick", "name": "Kick", "accepts": "A VOD or a clip.",
     "example": "https://kick.com/channel/videos/00000000-0000-0000-0000-000000000000"},
    {"platform": "direct", "name": "Direct link", "accepts": "An https link that ends in a video file name.",
     "example": "https://example.com/recording.mp4"},
    {"platform": "gdrive", "name": "Google Drive", "accepts": "A share link to one file, set to \"Anyone with the link\".",
     "example": "https://drive.google.com/file/d/FILE_ID/view"},
    {"platform": "dropbox", "name": "Dropbox", "accepts": "A share link to one file.",
     "example": "https://www.dropbox.com/scl/fi/ID/recording.mp4?rlkey=KEY"},
    {"platform": "youtube", "name": "YouTube", "accepts": "One video. Best effort.",
     "example": "https://www.youtube.com/watch?v=VIDEO_ID",
     "note": "YouTube often refuses automated downloads: upload the file instead."},
)

_UNSUPPORTED = ("Imports work from Twitch, Kick, YouTube, Google Drive, Dropbox, or a direct https link to a "
                f"video file ({', '.join(sorted(VIDEO_EXT))}). {UPLOAD_INSTEAD}")


def _bare(host: str) -> str:
    """Host without the www., m. or go. prefix."""
    return re.sub(r"^(?:www|m|go)\.", "", host)


def _one(query: dict, key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _twitch(host: str, path: str, query: dict) -> Source | None:
    if host == "clips.twitch.tv":
        m = re.fullmatch(r"/([A-Za-z0-9_-]{1,120})/?", path)
    elif _bare(host) == "twitch.tv":
        m = re.fullmatch(r"/(?:[A-Za-z0-9_]{1,40}/)?clip/([A-Za-z0-9_-]{1,120})/?", path)
    else:
        return None
    if m and m.group(1) != "embed":
        url = f"https://clips.twitch.tv/{m.group(1)}"
        return Source("twitch", PLATFORM, url, url)
    if _bare(host) == "twitch.tv":
        m = re.fullmatch(r"/(?:videos|[A-Za-z0-9_]{1,40}/v(?:ideo)?)/(\d{1,20})/?", path)
        if m:
            url = f"https://www.twitch.tv/videos/{m.group(1)}"
            return Source("twitch", PLATFORM, url, url)
    raise Refused("unsupported_link", "Use a link to one Twitch VOD (twitch.tv/videos/...) or one clip. Channel "
                                      "pages, live streams and collections cannot be imported.")


def _kick(host: str, path: str, query: dict) -> Source | None:
    if _bare(host) != "kick.com":
        return None
    m = re.fullmatch(r"/([\w-]{1,60})/videos/([\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12})/?", path)
    if m:
        url = f"https://kick.com/{m.group(1)}/videos/{m.group(2)}"
        return Source("kick", PLATFORM, url, url)
    m = re.fullmatch(r"/([\w-]{1,60})/clips/(clip_[\w-]{1,80})/?", path)
    clip = m.group(2) if m else None
    if not m:
        m = re.fullmatch(r"/([\w-]{1,60})/?", path)
        clip = _one(query, "clip") if m else None
        if clip and not re.fullmatch(r"clip_[\w-]{1,80}", clip):
            clip = None
    if m and clip:
        url = f"https://kick.com/{m.group(1)}/clips/{clip}"
        return Source("kick", PLATFORM, url, url)
    raise Refused("unsupported_link", "Use a link to one Kick VOD (kick.com/<channel>/videos/...) or one clip. "
                                      "Channel pages and live streams cannot be imported.")


def _youtube(host: str, path: str, query: dict) -> Source | None:
    video = None
    if host == "youtu.be":
        m = re.fullmatch(r"/([\w-]{11})/?", path)
        video = m.group(1) if m else None
    elif _bare(host) == "youtube.com":
        m = re.fullmatch(r"/(?:shorts|live|embed|v)/([\w-]{11})/?", path)
        video = m.group(1) if m else None
        if path in ("/watch", "/watch/"):
            v = _one(query, "v")
            video = v if v and re.fullmatch(r"[\w-]{11}", v) else None
    else:
        return None
    if not video:
        raise Refused("unsupported_link", "Use a link to one YouTube video. Playlists, channels and live streams "
                                          "cannot be imported.")
    url = f"https://www.youtube.com/watch?v={video}"
    return Source("youtube", PLATFORM, url, url)


def _gdrive(host: str, path: str, query: dict) -> Source | None:
    if host not in ("drive.google.com", "drive.usercontent.google.com"):
        return None
    m = re.fullmatch(r"/file/d/([\w-]{10,100})(?:/.*)?", path)
    file_id = m.group(1) if m else None
    if not file_id and path in ("/open", "/uc", "/download"):
        file_id = _one(query, "id")
        if file_id and not re.fullmatch(r"[\w-]{10,100}", file_id):
            file_id = None
    if not file_id:
        raise Refused("unsupported_link", "Use a Google Drive share link to one file (drive.google.com/file/d/...). "
                                          "Folders cannot be imported.")
    # `confirm=t` answers Drive's "this file is too large to scan for viruses, download anyway?" page, which
    # every large file gets. It does not open anything that is not shared publicly: a private file still
    # answers with a sign-in page, and that is a refusal.
    fetch = "https://drive.usercontent.google.com/download?" + urlencode(
        {"id": file_id, "export": "download", "confirm": "t"})
    return Source("gdrive", DIRECT, f"https://drive.google.com/file/d/{file_id}/view", fetch)


def _dropbox(host: str, path: str, query: dict) -> Source | None:
    if _bare(host) not in ("dropbox.com", "dl.dropbox.com", "dl.dropboxusercontent.com"):
        return None
    if not re.fullmatch(r"/(?:s|scl/fi)/[\w-]+/[^/]+", path):
        raise Refused("unsupported_link", "Use a Dropbox share link to one file (dropbox.com/scl/fi/... or "
                                          "dropbox.com/s/...). Folders cannot be imported.")
    keep = {k: query[k][0] for k in ("rlkey",) if query.get(k)}     # the share key; everything else is tracking
    base = f"https://www.dropbox.com{path}"
    canonical = base + ("?" + urlencode(keep) if keep else "")
    return Source("dropbox", DIRECT, canonical, base + "?" + urlencode({**keep, "dl": "1"}))


def _direct(host: str, port: int | None, path: str, raw_query: str) -> Source | None:
    if PurePosixPath(unquote(path)).suffix.lower() not in VIDEO_EXT:
        return None
    netloc = host if port in (None, 443) else f"{host}:{port}"
    url = f"https://{netloc}{path}" + (f"?{raw_query}" if raw_query else "")
    return Source("direct", DIRECT, url, url)


def classify(url: str) -> Source:
    """The Source for a link, or Refused (a 422 for the caller) when it is not one we import from."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL_LEN or any(c.isspace() or ord(c) < 32 for c in url):
        raise Refused("bad_url", f"Send one link of at most {MAX_URL_LEN} characters.")
    try:
        parts = urlsplit(url)
        host, port = (parts.hostname or "").lower().rstrip("."), parts.port
    except ValueError:
        raise Refused("bad_url", "This is not a valid link.") from None
    if parts.scheme.lower() != "https":
        raise Refused("https_only", f"Only https links can be imported. {UPLOAD_INSTEAD}")
    if not host:
        raise Refused("bad_url", "This is not a valid link.")
    if parts.username is not None or parts.password is not None:
        raise Refused("credentials_in_url", "Links with a user name or password cannot be imported: only public "
                                            f"content, without a login. {UPLOAD_INSTEAD}")
    path, query = parts.path or "/", parse_qs(parts.query)
    if port in (None, 443):
        for handler in (_twitch, _kick, _youtube, _gdrive, _dropbox):
            source = handler(host, path, query)
            if source is not None:
                return _checked(source)
    source = _direct(host, port, path, parts.query)
    if source is None:
        raise Refused("unsupported_source", _UNSUPPORTED)
    return _checked(source)


def _checked(source: Source) -> Source:
    if len(source.url) > MAX_URL_LEN or len(source.fetch_url) > MAX_URL_LEN + 40:
        raise Refused("bad_url", f"Send one link of at most {MAX_URL_LEN} characters.")
    return source


def canonical(url: str) -> str | None:
    """The canonical form of a link we import from, or None for anything else (used by takedown to match)."""
    try:
        return classify(url).url
    except Refused:
        return None
