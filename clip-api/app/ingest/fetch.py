"""One https download for direct, Google Drive and Dropbox links.

Every hop (the first URL and each redirect) is checked the same way: https only, no credentials in the URL, the
host must resolve to public addresses only, and the connection is made to the address that was checked, so a
DNS answer cannot change between the check and the use. No cookies are kept between hops, no proxy is used
(`http.client` does not read proxy settings), and the client says honestly what it is. A size cap, a time cap
and a content-type check apply while the body is streamed to disk. The container is checked afterwards, on the
saved file (runner.py, ffprobe with `-protocol_whitelist file,pipe`), never on the URL.
"""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from dataclasses import dataclass
from email.message import Message
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit

from . import UPLOAD_INSTEAD, Refused
from .sources import VIDEO_EXT

USER_AGENT = "ClutchClips-LinkImport/1.0"      # what we are; never a browser's name
MAX_REDIRECTS = 5
CONNECT_TIMEOUT = 15.0     # seconds to connect and for each read: a server that goes quiet ends the import
CHUNK = 256 * 1024
NAT64 = ipaddress.ip_network("64:ff9b::/96")

# Content types a video file is served with. Anything else (a web page, a sign-in form, JSON) is refused.
CONTENT_TYPES = {
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/x-matroska": ".mkv", "video/webm": ".webm",
    "video/x-m4v": ".m4v", "video/x-msvideo": ".avi", "video/avi": ".avi", "video/x-flv": ".flv",
    "video/mp2t": ".ts", "application/mp4": ".mp4",
}
OPAQUE_TYPES = {"application/octet-stream", "binary/octet-stream", "application/x-binary", ""}   # go by the name


@dataclass(frozen=True)
class Limits:
    max_bytes: int
    timeout_sec: float      # the whole download, redirects included


@dataclass
class Fetched:
    path: Path
    size: int
    filename: str           # as the server or the URL named it, with a video extension


def is_public_ip(address: str) -> bool:
    """True only for an address on the public internet. Private, loopback, link-local (cloud metadata), reserved
    and multicast addresses are not, and neither is an IPv6 address that carries one of those inside it."""
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if ip.version == 6:
        inner = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if inner is None and ip in NAT64:
            inner = ipaddress.ip_address(int(ip) & 0xFFFFFFFF)
        if inner is not None:
            ip = inner
    # is_global alone lets multicast through, so every special range is ruled out by name as well.
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local
                                 or ip.is_private or ip.is_unspecified)


def _resolve(host: str, port: int) -> list[str]:
    """The addresses a host name resolves to. A seam for tests (they never use the network)."""
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def _connect(address: str, port: int, timeout: float) -> socket.socket:
    """A TCP connection to one checked address. A seam for tests."""
    return socket.create_connection((address, port), timeout=timeout)


def _tls() -> ssl.SSLContext:
    """Certificates are always verified. A seam for tests (they trust their own test certificate)."""
    return ssl.create_default_context()


def checked_address(host: str, port: int) -> str:
    """The address to connect to for this host: resolved once, and refused unless every answer is public."""
    try:
        addresses = _resolve(host, port)
    except (OSError, UnicodeError):
        raise Refused("unreachable", f"This link's server could not be found. {UPLOAD_INSTEAD}") from None
    if not addresses or not all(is_public_ip(a) for a in addresses):
        raise Refused("private_address", "This link points at a private or local address, which cannot be "
                                         f"imported. {UPLOAD_INSTEAD}")
    v4 = [a for a in addresses if ":" not in a]
    return (v4 or addresses)[0]


def check_hop(url: str) -> tuple[str, int, str, str]:
    """(host, port, checked address, path and query) for one hop, or Refused."""
    try:
        parts = urlsplit(url)
        host, port = (parts.hostname or "").lower().rstrip("."), parts.port or 443
    except ValueError:
        raise Refused("bad_url", "This is not a valid link.") from None
    if parts.scheme.lower() != "https":
        raise Refused("https_only", f"Only https links can be imported (this one led to {parts.scheme or 'no'} "
                                    f"scheme). {UPLOAD_INSTEAD}")
    if not host or parts.username is not None or parts.password is not None:
        raise Refused("bad_url", "This is not a valid link.")
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return host, port, checked_address(host, port), target


class _PinnedConnection(http.client.HTTPSConnection):
    """An HTTPS connection to one already-checked address. The certificate is verified for the host name."""

    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._address, self._tls_context = address, _tls()

    def connect(self) -> None:
        sock = _connect(self._address, self.port, self.timeout)
        try:
            self.sock = self._tls_context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _disposition_name(header: str | None) -> str | None:
    if not header:
        return None
    msg = Message()
    msg["content-disposition"] = header
    name = msg.get_filename()
    return PurePosixPath(name.replace("\\", "/")).name if name else None


def _video_name(final_url: str, content_type: str, disposition: str | None) -> str:
    """A file name with a video extension, from the server's own name for the file, else the URL, else the
    content type. Refused when none of them says this is a video."""
    url_name = PurePosixPath(unquote(urlsplit(final_url).path)).name
    for name in (_disposition_name(disposition), url_name):
        if name and PurePosixPath(name).suffix.lower() in VIDEO_EXT:
            return name
    if content_type in CONTENT_TYPES:
        stem = PurePosixPath(url_name).stem or "import"
        return f"{stem}{CONTENT_TYPES[content_type]}"
    raise Refused("unsupported_type", f"This link is not a video file ({', '.join(sorted(VIDEO_EXT))}). "
                                      f"{UPLOAD_INSTEAD}")


def fetch(url: str, dest_dir: Path, limits: Limits, on_progress: Callable[[int, int | None], None] | None = None,
          ) -> Fetched:
    """Download one video file to dest_dir. Raises Refused for anything that is not a public https video file
    within the limits; whatever was written is removed."""
    deadline = time.monotonic() + limits.timeout_sec
    too_slow = Refused("import_timeout", f"The download took longer than {int(limits.timeout_sec // 60)} minutes "
                                         f"and was stopped. {UPLOAD_INSTEAD}")
    too_big = Refused("file_too_large", f"Maximum import size is {limits.max_bytes // 1024 ** 2} MB.")
    unreachable = Refused("unreachable", f"This link's server did not answer. {UPLOAD_INSTEAD}")
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        host, port, address, target = check_hop(current)
        left = deadline - time.monotonic()
        if left <= 0:
            raise too_slow
        conn = _PinnedConnection(host, port, address, timeout=min(CONNECT_TIMEOUT, left))
        try:
            try:
                conn.request("GET", target, headers={"User-Agent": USER_AGENT, "Accept": "*/*",
                                                     "Accept-Encoding": "identity"})
                resp = conn.getresponse()
            except ssl.SSLError:
                raise Refused("bad_certificate", "This link's server has no valid https certificate. "
                                                 f"{UPLOAD_INSTEAD}") from None
            except (OSError, http.client.HTTPException):
                raise unreachable from None
            if resp.status in (301, 302, 303, 307, 308):
                location = resp.getheader("location")
                if not location:
                    raise unreachable
                current = urljoin(current, location)
                continue
            if resp.status in (401, 403, 407, 429, 451):
                raise Refused("source_refused", f"The site refused this download (HTTP {resp.status}). The link "
                                                f"may be private or blocked. {UPLOAD_INSTEAD}")
            if resp.status != 200:
                raise Refused("source_error", f"The site answered HTTP {resp.status} for this link. "
                                              f"{UPLOAD_INSTEAD}")
            content_type = (resp.getheader("content-type") or "").split(";")[0].strip().lower()
            if content_type not in CONTENT_TYPES and content_type not in OPAQUE_TYPES:
                raise Refused("not_a_video", f"This link returned {content_type}, not a video file. It may be a "
                                             f"web page, or need a login. {UPLOAD_INSTEAD}")
            filename = _video_name(current, content_type, resp.getheader("content-disposition"))
            declared = resp.getheader("content-length")
            total = int(declared) if declared and declared.isdigit() else None
            if total is not None and total > limits.max_bytes:
                raise too_big
            dest = dest_dir / f"download{PurePosixPath(filename).suffix.lower()}"
            size = 0
            try:
                with open(dest, "wb") as fh:
                    while True:
                        if time.monotonic() > deadline:
                            raise too_slow
                        try:
                            chunk = resp.read1(CHUNK)
                        except (OSError, http.client.HTTPException):
                            raise unreachable from None
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > limits.max_bytes:
                            raise too_big
                        fh.write(chunk)
                        if on_progress:
                            on_progress(size, total)
                if total is not None and size != total:
                    raise unreachable
                if size == 0:
                    raise Refused("empty_file", f"This link returned an empty file. {UPLOAD_INSTEAD}")
            except BaseException:
                dest.unlink(missing_ok=True)
                raise
            return Fetched(dest, size, re.sub(r"[^\w.\- ]+", "_", filename)[:255])
        finally:
            conn.close()
    raise Refused("too_many_redirects", f"This link redirects too many times. {UPLOAD_INSTEAD}")
