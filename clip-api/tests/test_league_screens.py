"""The Creators League screens stay in step with the API: the forms send the API models' fields, the admin page
offers exactly the moves the rules allow and asks for nothing before it knows the account is an admin, and no
page writes a domain, a made-up creator or raw HTML."""
import re
from pathlib import Path

import pytest

from app import league
from app.routes_league import EntryBody, ProfileBody

WEB = Path(__file__).resolve().parents[1] / "web-src"
PUBLIC = WEB / "app/league/page.tsx"
CREATOR = WEB / "app/league/creator/page.tsx"
ENTER = WEB / "app/dashboard/league/page.tsx"
ADMIN = WEB / "app/dashboard/admin/league/page.tsx"
HOME = WEB / "components/league/HomeLeagueSection.tsx"
LIB = WEB / "lib/league.ts"
SCREENS = [PUBLIC, CREATOR, ENTER, ADMIN, HOME, LIB, WEB / "components/league/Bits.tsx",
           WEB / "components/league/Leaderboard.tsx"]


def table(name: str) -> dict[str, list[str]]:
    block = re.search(rf"export const {name}: Record<\w+, string\[\]> = \{{\n(.*?)\n\}};", LIB.read_text(), re.S).group(1)
    return {m[0]: re.findall(r'"([a-z_]+)"', m[1]) for m in re.findall(r"^\s+([a-z_]+): \[([^\]]*)\],?$", block, re.M)}


@pytest.mark.parametrize("page", SCREENS, ids=lambda p: str(p.relative_to(WEB)))
def test_each_screen_exists(page):
    assert page.is_file()


def test_the_entry_and_profile_forms_send_exactly_the_api_fields():
    names = set(re.findall(r'\bname="([a-z_]+)"', ENTER.read_text()))
    assert names == set(EntryBody.model_fields) | set(ProfileBody.model_fields)


def test_the_screens_offer_exactly_the_moves_the_rules_allow():
    assert table("ENTRY_RULES") == {a: list(allowed) for a, (allowed, _after, _reason) in league.ENTRY_RULES.items()}
    assert table("COMPETITION_RULES") == {a: list(allowed) for a, (allowed, _after) in league.COMPETITION_RULES.items()}


def test_the_avatars_the_site_draws_are_the_ones_the_api_accepts():
    block = re.search(r"export const AVATAR_COLOR: Record<string, string> = \{\n(.*?)\n\};", LIB.read_text(), re.S).group(1)
    assert tuple(re.findall(r"(\w+): \"#", block)) == league.AVATARS


def test_the_admin_page_asks_for_nothing_before_it_knows_the_account_is_an_admin():
    src = ADMIN.read_text()
    gate = src.index("if (!me.is_admin)")
    assert "Admins only" in src[gate:gate + 400]
    assert src.index("/v1/admin/") > src.index("function Admin()")


def test_the_page_carries_the_title_the_subtitle_and_the_five_steps():
    src = PUBLIC.read_text()
    assert ">Creators League</h1>" in src and "uppercase" in src.split(">Creators League</h1>")[0].rsplit("<h1", 1)[1]
    assert "Create. Compete. Climb." in src
    assert re.findall(r'\["(\w+)", "', src.split("const STEPS")[1].split("];")[0]) == ["Create", "Publish", "Submit", "Compete", "Win"]


def test_cash_amounts_are_drawn_only_when_the_api_says_cash_prizes_are_on():
    for f in (PUBLIC, HOME, WEB / "components/league/Bits.tsx"):
        for line in f.read_text().splitlines():
            if "dollars(" in line and "import" not in line:
                assert "cash_prizes" in line, f"{f.name}: {line.strip()[:120]}"


def test_no_screen_writes_a_domain_a_fixture_or_raw_html():
    for f in SCREENS:
        src = f.read_text()
        assert "dangerouslySetInnerHTML" not in src and "innerHTML" not in src, f.name
        assert "clutchclips.io" not in src and "clutchclips.com" not in src, f.name       # the link comes from the API
    for f in (PUBLIC, HOME, CREATOR):                                                    # no typed-in creators or counts
        assert not re.search(r"username: \"|views: \d|participants: \d", f.read_text()), f.name


def test_submitted_links_open_safely_and_only_for_the_three_platforms():
    lib = LIB.read_text()
    assert 'const HOSTS = ["https://www.tiktok.com/", "https://www.youtube.com/shorts/", "https://www.instagram.com/reel/"];' in lib
    for f in SCREENS:
        src = f.read_text()
        for m in re.finditer(r"<a href=\{url\}[^>]*>", src):
            assert 'rel="noopener noreferrer nofollow"' in m.group(0) and 'target="_blank"' in m.group(0), f.name
        assert "href={row.video_url}" not in src and "href={e.video_url}" not in src and "href={entry.video_url}" not in src, f.name


def test_the_public_site_and_the_app_link_to_the_league():
    chrome = (WEB / "components/Chrome.tsx").read_text()
    assert chrome.count('href="/league/"') == 3                       # desktop nav, phone menu, footer
    assert 'label: "Creators League", icon: "gamepad", href: "/dashboard/league/"' in (WEB / "components/dash/shell/nav.ts").read_text()
    home = (WEB / "app/page.tsx").read_text()
    assert home.count("<HomeLeagueSection />") == 1 and 'href="/league/"' in HOME.read_text()


def test_the_views_are_labelled_unverified_wherever_they_are_listed():
    for f in (WEB / "components/league/Leaderboard.tsx", HOME, CREATOR, ENTER, ADMIN):
        assert "unverified" in f.read_text(), f.name
