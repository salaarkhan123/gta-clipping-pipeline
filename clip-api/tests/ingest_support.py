"""Shared fixtures for the link-import tests. Nothing here touches the network.

`web`: a local HTTPS server with its own certificate. Host names resolve through a fake DNS table (so "public"
and "private" hosts exist without the internet), and a connection to a checked public address is delivered to
the local server. A connection to anything that is not a public address fails the test: the import code must
refuse before it connects.
`fake_ydl`: yt-dlp's YoutubeDL with its three network seams replaced; it records what it was given.
"""
import datetime
import http.server
import io
import shutil
import socket
import ssl
import threading
import time
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import update
from yt_dlp import YoutubeDL as RealYoutubeDL

from app.db import new_session
from app.ingest import fetch, platforms
from app.models import Job, utcnow

PUBLIC_IP = "93.184.216.34"
DNS = {
    "cdn.test": [PUBLIC_IP],
    "other.test": ["93.184.216.35"],
    "internal.test": ["10.0.0.5"],
    "mixed.test": [PUBLIC_IP, "192.168.1.9"],          # one public answer, one private: refused
    "metadata.test": ["169.254.169.254"],
    "localhost.test": ["127.0.0.1"],
    "v6private.test": ["fd00::1"],
    "mapped.test": ["::ffff:10.0.0.5"],
}
HOSTS = ["cdn.test", "other.test", "internal.test", "untrusted.test"]


def make_cert(folder: Path) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ingest tests")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in HOSTS]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = folder / "cert.pem", folder / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_path, key_path


class Web:
    """The local server plus what it saw and what the import code did."""

    def __init__(self, video: Path, folder: Path):
        self.video_bytes = video.read_bytes()
        self.hits: list[tuple[str, str, dict]] = []     # (Host header, path, request headers)
        self.resolved: list[str] = []
        self.connected: list[str] = []
        self.dns = {k: list(v) for k, v in DNS.items()}
        self.dns_script: dict[str, list[list[str]]] = {}   # host -> successive answers (DNS rebinding)
        self.cert, key = make_cert(folder)
        web = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def send(self, status, headers, body=b""):
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                if "Content-Length" not in headers and "Transfer-Encoding" not in headers:
                    self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?")[0]
                web.hits.append((self.headers.get("Host", ""), self.path, dict(self.headers.items())))
                data = web.video_bytes
                if path in ("/video.mp4", "/dir/My%20Stream.mp4"):
                    self.send(200, {"Content-Type": "video/mp4"}, data)
                elif path == "/octet.mp4":
                    self.send(200, {"Content-Type": "application/octet-stream"}, data)
                elif path == "/download":                 # Drive and Dropbox style: the name is in a header
                    self.send(200, {"Content-Type": "application/octet-stream",
                                    "Content-Disposition": 'attachment; filename="Shared Recording.mp4"'}, data)
                elif path == "/typed":                    # no name anywhere: the content type decides
                    self.send(200, {"Content-Type": "video/mp4"}, data)
                elif path == "/redirect-ok.mp4":
                    self.send(302, {"Location": "/video.mp4"})
                elif path == "/redirect-other.mp4":
                    self.send(302, {"Location": "https://other.test/video.mp4"})
                elif path == "/redirect-private.mp4":
                    self.send(302, {"Location": "https://internal.test/video.mp4"})
                elif path == "/redirect-metadata.mp4":
                    self.send(302, {"Location": "https://169.254.169.254/latest/meta-data/x.mp4"})
                elif path == "/redirect-loopback.mp4":
                    self.send(307, {"Location": "https://127.0.0.1/video.mp4"})
                elif path == "/redirect-http.mp4":
                    self.send(301, {"Location": "http://cdn.test/video.mp4"})
                elif path == "/redirect-login.mp4":
                    self.send(302, {"Location": "https://user:secret@cdn.test/video.mp4"})
                elif path == "/loop.mp4":
                    self.send(302, {"Location": "/loop.mp4"})
                elif path == "/page.mp4":
                    self.send(200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>Sign in</html>")
                elif path == "/garbage.mp4":
                    self.send(200, {"Content-Type": "video/mp4"}, b"this is not a video at all " * 4000)
                elif path == "/empty.mp4":
                    self.send(200, {"Content-Type": "video/mp4"}, b"")
                elif path == "/forbidden.mp4":
                    self.send(403, {"Content-Type": "text/plain"}, b"no")
                elif path == "/missing.mp4":
                    self.send(404, {"Content-Type": "text/plain"}, b"gone")
                elif path == "/huge-declared.mp4":        # says it is 50 GB, sends nothing
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(50 * 1024 ** 3))
                    self.send_header("Connection", "close")
                    self.end_headers()
                elif path in ("/huge-streamed.mp4", "/slow.mp4"):   # no length; a body that never ends
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    try:
                        for _ in range(100_000):
                            if path == "/slow.mp4":
                                self.wfile.write(b"x" * 16)
                                self.wfile.flush()
                                time.sleep(0.05)
                            else:
                                self.wfile.write(b"x" * 65536)
                    except OSError:
                        pass                               # the client hung up, as it should
                elif path == "/truncated.mp4":             # declares more than it sends
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(len(data) + 1000))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send(404, {"Content-Type": "text/plain"}, b"not found")

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.handle_error = lambda *args: None      # a client that hangs up mid-body is expected here
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.cert, key)
        self.server.socket = ctx.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    # The three seams of app/ingest/fetch.py
    def resolve(self, host: str, port: int) -> list[str]:
        self.resolved.append(host)
        if self.dns_script.get(host):
            return self.dns_script[host].pop(0)
        if host in self.dns:
            return self.dns[host]
        try:
            socket.inet_pton(socket.AF_INET, host)        # an address written out is its own answer
            return [host]
        except OSError:
            raise socket.gaierror(f"no such test host: {host}") from None

    def connect(self, address: str, port: int, timeout: float) -> socket.socket:
        self.connected.append(address)
        assert fetch.is_public_ip(address), f"the import code tried to connect to {address}"
        return socket.create_connection(("127.0.0.1", self.port), timeout=timeout)

    def tls(self) -> ssl.SSLContext:
        return ssl.create_default_context(cafile=str(self.cert))

    def paths(self) -> list[str]:
        return [path for _host, path, _headers in self.hits]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def web(video, tmp_path, monkeypatch):
    server = Web(video, tmp_path)
    monkeypatch.setattr(fetch, "_resolve", server.resolve)
    monkeypatch.setattr(fetch, "_connect", server.connect)
    monkeypatch.setattr(fetch, "_tls", server.tls)
    yield server
    server.close()


ONE_FILE = {"format_id": "source", "url": "https://media.test/source.mp4", "ext": "mp4", "height": 360,
            "vcodec": "avc1.4D401E", "acodec": "mp4a.40.2", "protocol": "https"}


class Answer(io.BytesIO):
    """What urlopen hands back: the bytes, and the HTTP status (206 for a byte range that was served)."""
    def __init__(self, data: bytes, status: int = 200):
        super().__init__(data)
        self.status = status


class FakeYDL(RealYoutubeDL):
    """Stands in for yt_dlp.YoutubeDL at its three network seams: the metadata request (extract_info), a segment
    list (urlopen) and a stream download (dl). Everything else is yt-dlp's own code: the options it is built from
    and the format selector that picks the streams. It records what it was given and "downloads" the test video."""
    instances: list["FakeYDL"] = []
    video: Path | None = None
    info: dict = {}
    formats: list[dict] | None = None       # the streams the site lists; default: one file with picture and sound
    files: dict[str, Path] = {}             # format_id -> the file its download produces (default: the test video)
    playlists: dict[str, str] = {}          # address -> the text of that segment list
    bodies: dict[str, Path] = {}            # address -> the file served there, by byte range (a stream as one file)
    serve_ranges: bool = True               # False: the server ignores Range and answers 200 with everything
    refuse_range_after: int | None = None   # byte-range requests answered before the server starts refusing (403)
    refuse_extract: str | None = None       # yt-dlp's error text when the site refuses the metadata request
    refuse_download: str | None = None
    report_bytes: int | None = None         # what the progress hook is told has been downloaded

    def __init__(self, params: dict):
        self.given = dict(params)           # yt-dlp normalises some of its options in place
        super().__init__(params)
        self.urls, self.opened, self.fetched, self.ranges = [], [], [], []
        FakeYDL.instances.append(self)

    def extract_info(self, url, download=True, process=True, **kwargs):
        assert download is False and process is False      # metadata only, and no format is chosen
        self.urls.append(url)
        if FakeYDL.refuse_extract:
            raise platforms.DownloadError(FakeYDL.refuse_extract)
        return {"id": "v1", "title": "Ranked grind: part 3 / finale!", "duration": 40.0, "extractor": "twitch:vod",
                "extractor_key": "TwitchVod", "webpage_url": url,
                "formats": [dict(f) for f in (FakeYDL.formats or [ONE_FILE])], **FakeYDL.info}

    def urlopen(self, req):
        url = getattr(req, "url", req)
        asked = dict(getattr(req, "headers", None) or {}).get("Range")
        self.opened.append(url)
        if url in FakeYDL.bodies:
            data = FakeYDL.bodies[url].read_bytes()
            if not asked or not FakeYDL.serve_ranges:
                return Answer(data)
            if FakeYDL.refuse_range_after is not None and len(self.ranges) >= FakeYDL.refuse_range_after:
                raise OSError("HTTP Error 403: Forbidden")
            first, last = (int(n) for n in asked.removeprefix("bytes=").split("-"))
            self.ranges.append((url, first, last))
            return Answer(data[first:last + 1], 206)
        if url not in FakeYDL.playlists:
            raise OSError(f"nothing is served at this test address: {url}")
        return Answer(FakeYDL.playlists[url].encode())

    def dl(self, name, info, subtitle=False, test=False):
        self.fetched.append((Path(name).name, info))
        if FakeYDL.refuse_download:
            raise platforms.DownloadError(FakeYDL.refuse_download)
        shutil.copyfile(FakeYDL.files.get(info["format_id"], FakeYDL.video), name)
        size = Path(name).stat().st_size
        for hook in self.params.get("progress_hooks", []):
            hook({"status": "downloading", "downloaded_bytes": FakeYDL.report_bytes or size, "total_bytes": None})
            hook({"status": "finished", "downloaded_bytes": FakeYDL.report_bytes or size, "total_bytes": size})
        return True, True


@pytest.fixture
def fake_ydl(video, monkeypatch):
    FakeYDL.instances, FakeYDL.video, FakeYDL.info = [], video, {}
    FakeYDL.formats, FakeYDL.files, FakeYDL.playlists, FakeYDL.bodies = None, {}, {}, {}
    FakeYDL.serve_ranges, FakeYDL.refuse_range_after = True, None
    FakeYDL.refuse_extract = FakeYDL.refuse_download = FakeYDL.report_bytes = None
    monkeypatch.setattr(platforms, "YoutubeDL", FakeYDL)
    return FakeYDL


@pytest.fixture(autouse=True)
def no_stray_imports():
    """Imports a test left waiting are cancelled, so a later test's worker run claims its own job."""
    yield
    with new_session() as db:
        db.execute(update(Job).where(Job.id.like("imp\\_%", escape="\\"), Job.status.in_(("QUEUED", "RUNNING")))
                   .values(status="CANCELED", finished_at=utcnow()))
        db.commit()
