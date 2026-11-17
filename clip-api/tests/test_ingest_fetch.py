"""The direct downloader against a local HTTPS server: https only, public addresses only on every hop, the checked
address is the one connected to, size and time caps, content type. No test here uses the network."""
import ssl
import time

import pytest

from app.ingest import Refused, fetch
from app.ingest.fetch import Limits, is_public_ip
from tests.ingest_support import PUBLIC_IP, web  # noqa: F401

ROOMY = Limits(max_bytes=50 * 1024 ** 2, timeout_sec=30)


def refused(url, tmp_path, limits=ROOMY) -> Refused:
    with pytest.raises(Refused) as e:
        fetch.fetch(url, tmp_path, limits)
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("download")], "a refused download left a file"
    return e.value


@pytest.mark.parametrize("address, public", [
    ("93.184.216.34", True), ("2606:4700:4700::1111", True),
    ("10.0.0.5", False), ("172.16.3.4", False), ("192.168.1.1", False), ("127.0.0.1", False), ("0.0.0.0", False),
    ("169.254.169.254", False),            # cloud metadata
    ("100.64.0.1", False),                 # carrier-grade NAT
    ("224.0.0.1", False), ("255.255.255.255", False),
    ("::1", False), ("fd00::1", False), ("fe80::1", False), ("::", False),
    ("::ffff:10.0.0.5", False), ("::ffff:127.0.0.1", False),       # a private IPv4 address inside an IPv6 one
    ("64:ff9b::a00:5", False), ("2002:a00:5::1", False),
    ("::ffff:93.184.216.34", True),
    ("not an address", False), ("", False),
])
def test_only_public_addresses_count_as_public(address, public):
    assert is_public_ip(address) is public


def test_downloads_a_public_video(web, tmp_path, video):
    seen = []
    got = fetch.fetch("https://cdn.test/video.mp4", tmp_path, ROOMY, lambda done, total: seen.append((done, total)))
    assert got.path.read_bytes() == video.read_bytes() and got.size == video.stat().st_size
    assert got.filename == "video.mp4" and got.path.suffix == ".mp4"
    assert seen[-1] == (got.size, got.size)
    assert web.connected == [PUBLIC_IP]


def test_says_honestly_what_it_is_and_sends_no_identity(web, tmp_path, monkeypatch):
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://proxy.invalid:3128")       # a proxy setting changes nothing
    fetch.fetch("https://cdn.test/video.mp4", tmp_path, ROOMY)
    host, _path, headers = web.hits[0]
    sent = {k.lower(): v for k, v in headers.items()}
    assert host == "cdn.test"
    assert sent["user-agent"] == "ClutchClips-LinkImport/1.0"
    assert "mozilla" not in sent["user-agent"].lower() and "chrome" not in sent["user-agent"].lower()
    assert set(sent) == {"host", "user-agent", "accept", "accept-encoding"}     # no cookie, no authorization
    assert web.connected == [PUBLIC_IP]                                         # straight to the checked address


def test_name_comes_from_the_server_then_the_url_then_the_type(web, tmp_path):
    assert fetch.fetch("https://cdn.test/download", tmp_path, ROOMY).filename == "Shared Recording.mp4"
    assert fetch.fetch("https://cdn.test/dir/My%20Stream.mp4", tmp_path, ROOMY).filename == "My Stream.mp4"
    assert fetch.fetch("https://cdn.test/typed", tmp_path, ROOMY).filename == "typed.mp4"
    assert fetch.fetch("https://cdn.test/octet.mp4", tmp_path, ROOMY).filename == "octet.mp4"


def test_follows_a_redirect_and_checks_each_hop(web, tmp_path, video):
    got = fetch.fetch("https://cdn.test/redirect-ok.mp4", tmp_path, ROOMY)
    assert got.size == video.stat().st_size
    assert web.paths() == ["/redirect-ok.mp4", "/video.mp4"]
    assert web.resolved == ["cdn.test", "cdn.test"]                 # resolved, and checked, once per hop
    web.hits.clear()
    fetch.fetch("https://cdn.test/redirect-other.mp4", tmp_path, ROOMY)
    assert [host for host, _p, _h in web.hits] == ["cdn.test", "other.test"]
    assert web.connected[-1] == "93.184.216.35"


@pytest.mark.parametrize("path", ["/redirect-private.mp4", "/redirect-metadata.mp4", "/redirect-loopback.mp4"])
def test_a_redirect_to_a_private_address_is_refused_before_connecting(web, tmp_path, path):
    e = refused(f"https://cdn.test{path}", tmp_path)
    assert e.code == "private_address" and "Upload the file instead." in e.message
    assert web.paths() == [path]                    # only the first hop was requested
    assert web.connected == [PUBLIC_IP]             # and nothing was ever opened to the private address


@pytest.mark.parametrize("host", ["internal.test", "metadata.test", "localhost.test", "v6private.test",
                                  "mapped.test", "mixed.test", "10.0.0.5", "127.0.0.1", "169.254.169.254"])
def test_a_first_url_on_a_private_address_is_refused_before_connecting(web, tmp_path, host):
    e = refused(f"https://{host}/video.mp4", tmp_path)
    assert e.code == "private_address"
    assert web.connected == [] and web.hits == []


def test_connects_to_the_address_it_checked_even_if_dns_changes(web, tmp_path):
    """DNS rebinding: the name answers with a public address when checked and a private one afterwards. The
    download uses the checked answer and never asks again."""
    web.dns_script["cdn.test"] = [[PUBLIC_IP], ["10.0.0.5"], ["10.0.0.5"]]
    fetch.fetch("https://cdn.test/video.mp4", tmp_path, ROOMY)
    assert web.resolved == ["cdn.test"]             # one lookup for the one hop
    assert web.connected == [PUBLIC_IP]


def test_other_refused_hops(web, tmp_path):
    assert refused("https://cdn.test/redirect-http.mp4", tmp_path).code == "https_only"
    assert refused("https://cdn.test/redirect-login.mp4", tmp_path).code == "bad_url"
    assert refused("https://cdn.test/loop.mp4", tmp_path).code == "too_many_redirects"
    assert len([p for p in web.paths() if p == "/loop.mp4"]) == fetch.MAX_REDIRECTS + 1
    assert refused("http://cdn.test/video.mp4", tmp_path).code == "https_only"
    assert refused("https://nowhere.test/video.mp4", tmp_path).code == "unreachable"


def test_an_oversized_file_is_refused_declared_or_not(web, tmp_path):
    small = Limits(max_bytes=200_000, timeout_sec=30)
    e = refused("https://cdn.test/huge-declared.mp4", tmp_path, small)
    assert e.code == "file_too_large"
    started = time.monotonic()
    e = refused("https://cdn.test/huge-streamed.mp4", tmp_path, small)      # no length: stopped at the cap
    assert e.code == "file_too_large" and time.monotonic() - started < 10
    e = refused("https://cdn.test/video.mp4", tmp_path, Limits(max_bytes=1000, timeout_sec=30))
    assert e.code == "file_too_large"


def test_a_slow_body_is_stopped_at_the_time_cap(web, tmp_path):
    started = time.monotonic()
    e = refused("https://cdn.test/slow.mp4", tmp_path, Limits(max_bytes=50 * 1024 ** 2, timeout_sec=1.0))
    assert e.code == "import_timeout" and "Upload the file instead." in e.message
    assert time.monotonic() - started < 6


def test_wrong_content_and_site_refusals(web, tmp_path):
    e = refused("https://cdn.test/page.mp4", tmp_path)
    assert e.code == "not_a_video" and "text/html" in e.message
    assert refused("https://cdn.test/forbidden.mp4", tmp_path).code == "source_refused"
    assert refused("https://cdn.test/missing.mp4", tmp_path).code == "source_error"
    assert refused("https://cdn.test/empty.mp4", tmp_path).code == "empty_file"
    assert refused("https://cdn.test/truncated.mp4", tmp_path).code == "unreachable"


def test_a_server_without_a_valid_certificate_is_refused(web, tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "_tls", ssl.create_default_context)      # the real thing: the test CA is unknown
    assert refused("https://cdn.test/video.mp4", tmp_path).code == "bad_certificate"
    assert web.hits == []
    monkeypatch.setattr(fetch, "_tls", web.tls)
    web.dns["wrongname.test"] = [PUBLIC_IP]                             # a name the certificate does not cover
    assert refused("https://wrongname.test/video.mp4", tmp_path).code == "bad_certificate"
