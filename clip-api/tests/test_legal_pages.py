"""The website's legal pages show the policy versions the API serves (app/legal.py)."""
import re
from pathlib import Path

from app import legal

WEB = Path(__file__).resolve().parents[1] / "web-src"
ROW = re.compile(r'\{\s*id:\s*"([^"]+)",\s*title:\s*"([^"]+)",\s*version:\s*"([^"]+)",\s*effective:\s*"([^"]+)",'
                 r'\s*path:\s*"([^"]+)",\s*required:\s*(true|false)\s*\}')


def site_policies() -> list[dict]:
    text = (WEB / "lib" / "legal.ts").read_text()
    return [{"id": i, "title": t, "version": v, "effective": e, "path": p, "required": r == "true"}
            for i, t, v, e, p, r in ROW.findall(text)]


def test_site_lists_the_same_policies_as_the_api():
    assert site_policies() == legal.public_list()


def test_every_policy_has_a_page():
    for p in legal.POLICIES.values():
        page = WEB / "app" / p.path.strip("/") / "page.tsx"
        assert page.is_file(), f"{p.id}: missing {page}"
        text = page.read_text()
        assert f'<LegalPage id="{p.id}"' in text, f"{page} does not render LegalPage for {p.id}"


def test_footer_links_every_policy():
    footer = (WEB / "components" / "Chrome.tsx").read_text()
    assert "POLICIES.map" in footer


def test_signup_sends_accept_policies_and_links_the_terms():
    auth = (WEB / "components" / "Auth.tsx").read_text()
    assert "accept_policies: true" in auth
    for path in ("/terms/", "/privacy/", "/acceptable-use/"):
        assert f'href="{path}"' in auth
