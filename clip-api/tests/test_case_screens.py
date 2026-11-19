"""The website's case screens (/takedown/, /dashboard/cases/, /dashboard/admin/cases/) stay in step with the API:
their form fields are the API models' fields, and the admin page offers exactly the decisions RULES allows."""
import re
import uuid
from pathlib import Path

import pytest

from app import trust_decisions
from app.db import new_session
from app.models import Account
from app.routes_trust import CounterNotice, Report

WEB = Path(__file__).resolve().parents[1] / "web-src"
TAKEDOWN = WEB / "app/takedown/page.tsx"
MY_CASES = WEB / "app/dashboard/cases/page.tsx"
ADMIN = WEB / "app/dashboard/admin/cases/page.tsx"


def names(*files: Path) -> set[str]:
    """Every name="..." in the files: the form fields they send."""
    return {n for f in files for n in re.findall(r'\bname="([a-z_]+)"', f.read_text())}


@pytest.mark.parametrize("page", [TAKEDOWN, MY_CASES, ADMIN], ids=lambda p: str(p.relative_to(WEB)))
def test_each_page_exists(page):
    assert page.is_file()


def test_the_report_form_sends_exactly_the_report_fields():
    assert "TakedownForm" in TAKEDOWN.read_text()
    assert names(TAKEDOWN, WEB / "components/trust/TakedownForm.tsx") == set(Report.model_fields)


def test_the_counter_notice_form_sends_exactly_the_counter_notice_fields():
    assert "CounterNoticeForm" in MY_CASES.read_text()
    assert names(WEB / "components/trust/CounterNoticeForm.tsx") == set(CounterNotice.model_fields)


def test_the_admin_page_offers_exactly_the_decisions_rules_allows():
    src = ADMIN.read_text()
    block = re.search(r"const RULES: Record<Action, string\[\]> = \{\n(.*?)\n\};", src, re.S).group(1)
    page = {m[0]: re.findall(r'"([a-z_]+)"', m[1]) for m in re.findall(r"^\s+([a-z_]+): \[([^\]]*)\],?$", block, re.M)}
    assert list(page) == list(trust_decisions.RULES)
    assert page == {action: list(allowed) for action, (allowed, _after) in trust_decisions.RULES.items()}
    assert "/decisions`" in src and "/v1/admin/trust/cases/" in src


def test_the_admin_page_asks_for_no_case_data_before_it_knows_the_account_is_an_admin():
    src = ADMIN.read_text()
    gate = src.index("if (!me.is_admin)")
    assert "Admins only" in src[gate:gate + 400]
    assert src.index("/v1/admin/") > src.index("function CaseList")      # every admin call is past the gate


def test_me_says_whether_the_account_is_an_admin(client):
    r = client.post("/v1/auth/signup", json={"email": f"a{uuid.uuid4().hex[:10]}@example.org", "password": "correct-horse-9"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert r.json()["account"]["is_admin"] is False
    assert client.get("/v1/me", headers=h).json()["is_admin"] is False
    with new_session() as db:
        db.get(Account, r.json()["account"]["id"]).is_admin = True
        db.commit()
    assert client.get("/v1/me", headers=h).json()["is_admin"] is True
