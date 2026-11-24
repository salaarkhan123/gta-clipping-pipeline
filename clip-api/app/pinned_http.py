"""Outbound HTTPS that connects only to the address checked at resolve time (SEC-001).

Same contract as app.ingest.fetch._PinnedConnection: resolve once, refuse non-public
addresses, then open TLS to that address with SNI for the original host name so a DNS
answer cannot change between the SSRF check and the connect (rebinding).
"""
from __future__ import annotations

import http.client
import socket
import ssl
from urllib.parse import urlsplit

from .ingest.fetch import is_public_ip

CONNECT_TIMEOUT = 15.0


def _resolve(host: str, port: int) -> list[str]:
    """Addresses a host name resolves to. Seam for tests (they never use the network)."""
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def _connect(address: str, port: int, timeout: float) -> socket.socket:
    """TCP connection to one checked address. Seam for tests."""
    return socket.create_connection((address, port), timeout=timeout)


def _tls() -> ssl.SSLContext:
    """Certificates are always verified. Seam for tests (they trust their own test certificate)."""
    return ssl.create_default_context()


def checked_address(host: str, port: int) -> str:
    """Address to connect to: resolved once; refused unless every answer is public."""
    addresses = _resolve(host, port)
    if not addresses or not all(is_public_ip(a) for a in addresses):
        raise OSError("private or non-public address")
    v4 = [a for a in addresses if ":" not in a]
    return (v4 or addresses)[0]


class _PinnedConnection(http.client.HTTPSConnection):
    """HTTPS connection to one already-checked address. Certificate verified for the host name."""

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


def parse_https_url(url: str) -> tuple[str, int, str]:
    """(host, port, path+query) for a public https URL, or raise ValueError/OSError."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme.lower() != "https" or not host:
        raise ValueError("https URL required")
    if parts.username is not None or parts.password is not None:
        raise ValueError("credentials in URL not allowed")
    port = parts.port or 443
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return host, port, target


def is_public_https_url(url: str) -> bool:
    """True when the URL is https and every DNS answer is a public address (SSRF guard)."""
    try:
        host, port, _target = parse_https_url(url)
        checked_address(host, port)
        return True
    except (OSError, ValueError, UnicodeError):
        return False


def pinned_https_request(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> int:
    """Send one HTTPS request pinned to the address checked at resolve time. Returns status code.

    Raises OSError/ValueError when the URL is not a public https target, or on connect/TLS failure.
    Does not follow redirects.
    """
    host, port, target = parse_https_url(url)
    address = checked_address(host, port)
    conn = _PinnedConnection(host, port, address, timeout=min(CONNECT_TIMEOUT, timeout))
    try:
        conn.request(method.upper(), target, body=body, headers=headers or {})
        resp = conn.getresponse()
        resp.read()  # drain so the connection can close cleanly
        return resp.status
    finally:
        conn.close()
