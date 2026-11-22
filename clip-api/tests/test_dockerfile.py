"""The production image must ship runtime assets and must not pull the static site into the build context."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
DOCKERIGNORE = (ROOT / ".dockerignore").read_text().splitlines()


def test_dockerfile_copies_template_assets():
    assert "COPY templates ./templates" in DOCKERFILE
    assert "/srv/templates" in DOCKERFILE


def test_dockerfile_does_not_trust_all_forwarded_ips():
    """SEC-003: --forwarded-allow-ips=* lets any peer spoof client IP for rate limits."""
    assert "forwarded-allow-ips=*" not in DOCKERFILE
    assert "FORWARDED_ALLOW_IPS" in DOCKERFILE
    assert "--forwarded-allow-ips=${FORWARDED_ALLOW_IPS}" in DOCKERFILE


def test_dockerignore_excludes_the_static_site():
    """Caddy serves web/ from the checkout; baking it into the API image only bloated the Mac CI context."""
    entries = {line.strip() for line in DOCKERIGNORE if line.strip() and not line.strip().startswith("#")}
    assert "web/" in entries
    assert "web-src/" in entries
    assert "tests/" in entries
