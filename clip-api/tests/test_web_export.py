"""Caddy serves clip-api/web/ from the git checkout (not the API image).

FE changes in web-src/ do not reach production until web/ is rebuilt and committed.
This test fails closed when a source route has no matching static export, so a
deploy of web-src-only PRs cannot look "successful" while the site stays stale.
"""
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parents[1] / "web-src"
WEB = WEB_SRC.parent / "web"


def _app_routes() -> list[Path]:
    root = WEB_SRC / "app"
    routes = []
    for page in root.rglob("page.tsx"):
        rel = page.relative_to(root).parent
        if any(part.startswith("[") for part in rel.parts):
            continue  # dynamic segments are not static-exported as fixed folders
        routes.append(rel)
    return sorted(routes)


def test_static_export_covers_every_app_route():
    missing = []
    for rel in _app_routes():
        target = WEB / "index.html" if str(rel) == "." else WEB / rel / "index.html"
        if not target.is_file():
            missing.append(str(rel) if str(rel) != "." else "/")
    assert not missing, (
        "clip-api/web/ is missing static pages for web-src routes: "
        + ", ".join(missing)
        + ". Rebuild and commit: cd clip-api/web-src && "
        "NEXT_PUBLIC_API_URL=https://api.clutchclips.io npm run build && "
        "rm -rf ../web && cp -r out ../web"
    )


def test_homepage_export_includes_score_labels():
    """Score chip labels from components/ui/Score.tsx must be in the committed export."""
    chunks = list((WEB / "_next" / "static" / "chunks").rglob("*.js"))
    blob = "\n".join(p.read_text(errors="ignore") for p in chunks)
    assert "AI score" in blob, "homepage export missing Score 'AI score' label"
    assert '"Sample"' in blob or "Sample" in blob, "homepage export missing Score 'Sample' label"
    assert "AI quality" in blob, "results export missing Rating 'AI quality' copy"


def test_templates_export_includes_recreate_and_honest_connectors():
    """Producer-parity gallery copy must ship in the committed static export."""
    chunks = list((WEB / "_next" / "static" / "chunks").rglob("*.js"))
    blob = "\n".join(p.read_text(errors="ignore") for p in chunks)
    assert "Recreate" in blob, "templates export missing Recreate CTA"
    assert "Clip with this style" in blob, "templates export missing style composer submit"
    assert "Edit in Claude" in blob, "templates export missing honest Claude disabled state"
    assert "ChatGPT plugin" in blob, "templates export missing honest ChatGPT disabled state"
