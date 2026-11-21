"""The production image must ship runtime assets and must not pull the static site into the build context."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
DOCKERIGNORE = (ROOT / ".dockerignore").read_text().splitlines()


def test_dockerfile_copies_template_assets():
    assert "COPY templates ./templates" in DOCKERFILE
    assert "/srv/templates" in DOCKERFILE


def test_dockerignore_excludes_the_static_site():
    """Caddy serves web/ from the checkout; baking it into the API image only bloated the Mac CI context."""
    entries = {line.strip() for line in DOCKERIGNORE if line.strip() and not line.strip().startswith("#")}
    assert "web/" in entries
    assert "web-src/" in entries
    assert "tests/" in entries
