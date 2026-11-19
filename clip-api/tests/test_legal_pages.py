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


def test_the_deployed_site_shows_no_owner_placeholder():
    """clip-api/web/ is what production serves: no page in it may show an [OWNER …] placeholder."""
    web = WEB.parent / "web"
    for p in legal.POLICIES.values():
        html = (web / p.path.strip("/") / "index.html").read_text()
        assert "data-owner-placeholder" not in html and "[OWNER" not in html, f"{p.path} shows a placeholder"
    pkg = (WEB / "package.json").read_text()
    assert '"build": "next build && node scripts/check-legal.mjs out"' in pkg


def test_footer_has_one_legal_list_and_links_the_report_form():
    footer = (WEB / "components" / "Chrome.tsx").read_text()
    assert footer.count("POLICIES.map") == 1, "the footer lists the policies once (a merge had left an unstyled copy)"
    assert 'href="/takedown/"' in footer


def test_a_stub_names_the_contact_for_its_subject_and_the_copyright_stub_links_the_form():
    page = (WEB / "components" / "LegalPage.tsx").read_text()
    assert "copyright: CONTACT.copyright" in page and "terms: CONTACT.support" in page
    assert 'href="/takedown/"' in page


def test_the_terms_name_the_tools_as_the_product_does():
    tools = (WEB / "lib" / "tools.ts").read_text()
    terms = (WEB / "app" / "terms" / "page.tsx").read_text()
    for name in re.findall(r"\(such as ([^)]+)\)", terms):
        for tool in re.split(r" and |, ", name):
            assert f'name: "{tool}"' in tools, f"the Terms name a tool that does not exist: {tool}"
