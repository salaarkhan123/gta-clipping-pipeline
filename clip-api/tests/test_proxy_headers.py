"""SEC-003: uvicorn must not trust X-Forwarded-For from every peer (`*` is forbidden)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compose_and_dockerfile_document_proxy_trust():
    dockerfile = (ROOT / "Dockerfile").read_text()
    env_example = (ROOT / ".env.example").read_text()
    assert "forwarded-allow-ips=*" not in dockerfile
    assert "FORWARDED_ALLOW_IPS" in dockerfile
    assert "FORWARDED_ALLOW_IPS" in env_example or "forwarded-allow-ips" in env_example.lower()


def test_client_ip_uses_request_peer(client):
    """App-level client_ip is the ASGI peer; spoofed XFF is only honored when uvicorn trusts the peer."""
    from starlette.requests import Request
    from app.deps import client_ip

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": "/", "raw_path": b"/", "query_string": b"", "root_path": "",
        "headers": [(b"x-forwarded-for", b"203.0.113.9")],
        "client": ("198.51.100.2", 12345), "server": ("127.0.0.1", 8000),
    }
    assert client_ip(Request(scope)) == "198.51.100.2"
