"""Email: Resend over HTTPS (mocked), logs that never hold a link or a token, safe failure on password reset,
the token epoch that voids every reset and verify link, and the production check."""
import importlib.util
import json
import logging
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app import emailer, token_epoch
from app.config import Settings, get_settings
from app.security import make_token

KEY = "re_test_key_never_printed"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "admin.py"


@pytest.fixture(autouse=True)
def keep_epoch(tmp_path):
    """The epoch is shared by the whole test run: put it back, so tokens other tests mint stay valid."""
    from app.storage import get_storage
    before = token_epoch.current()
    yield
    saved = tmp_path / "epoch.json"
    saved.write_text(json.dumps({"epoch": before}))
    get_storage().put(token_epoch.KEY, saved)


@pytest.fixture
def resend(monkeypatch):
    """Configure Resend and capture every request; `answers` is the list of status codes to give, in order."""
    s = get_settings()
    monkeypatch.setattr(s, "email_provider", "resend")
    monkeypatch.setattr(s, "resend_api_key", KEY)
    monkeypatch.setattr(emailer, "_sleep", lambda _s: None)
    seen, answers = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        code = answers.pop(0) if answers else 200
        if code == -1:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(code, json={"id": "msg_123"} if code < 300 else {"message": "no"})

    real = httpx.Client
    monkeypatch.setattr(emailer.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen, answers


@pytest.fixture
def prod_logs(monkeypatch, caplog):
    """Production-like logging: ENV is not dev."""
    monkeypatch.setattr(get_settings(), "env", "prod")
    caplog.set_level(logging.DEBUG, logger="clipapi.email")
    return caplog


def test_mask_keeps_one_letter_and_the_domain():
    assert emailer.mask("salaar@example.com") == "s***@example.com"
    assert emailer.mask("not-an-address") == "***"


def test_resend_request_has_key_user_agent_idempotency_and_text(resend):
    seen, _ = resend
    assert emailer.deliver("to@example.org", "Subject", "Body text", idempotency_key="reset:abc") == "msg_123"
    (r,) = seen
    assert str(r.url) == "https://api.resend.com/emails" and r.method == "POST"
    assert r.headers["authorization"] == f"Bearer {KEY}"
    assert r.headers["user-agent"].startswith("clutchclips-api/")
    assert r.headers["idempotency-key"] == "reset:abc"
    assert json.loads(r.content) == {"from": get_settings().email_from, "to": ["to@example.org"],
                                     "subject": "Subject", "text": "Body text"}


@pytest.mark.parametrize("first", [429, 500, 503, -1])
def test_resend_retries_rate_limits_server_errors_and_timeouts(resend, first):
    seen, answers = resend
    answers += [first, first]
    assert emailer.deliver("to@example.org", "s", "b", idempotency_key="k") == "msg_123"
    assert len(seen) == 3
    assert {r.headers["idempotency-key"] for r in seen} == {"k"}        # the same key: Resend sends once


def test_resend_gives_up_after_three_tries(resend):
    seen, answers = resend
    answers += [503, 503, 503, 503]
    with pytest.raises(emailer.EmailError, match="503"):
        emailer.deliver("to@example.org", "s", "b")
    assert len(seen) == 3


@pytest.mark.parametrize("code", [400, 401, 403, 422])
def test_resend_refusals_are_not_retried(resend, code):
    seen, answers = resend
    answers.append(code)
    with pytest.raises(emailer.EmailError, match=str(code)):
        emailer.deliver("to@example.org", "s", "b")
    assert len(seen) == 1


def test_a_failed_send_logs_no_body_link_or_key(resend, prod_logs):
    _, answers = resend
    answers += [500, 500, 500]
    body = "Reset here: https://clutchclips.io/reset-password?token=SECRET.TOKEN.VALUE"
    assert emailer.send_email("victim@example.org", "Reset your password", body) is False
    text = prod_logs.text
    assert "email_delivery_failed" in text and "v***@example.org" in text
    for leak in ("SECRET.TOKEN.VALUE", "reset-password", "victim@", KEY):
        assert leak not in text


def test_a_sent_message_logs_no_body(resend, prod_logs):
    assert emailer.send_email("victim@example.org", "Confirm", "link https://x.test/?token=TOK") is True
    assert "email_sent" in prod_logs.text and "TOK" not in prod_logs.text


def test_no_provider_outside_dev_logs_no_body(monkeypatch, prod_logs):
    monkeypatch.setattr(get_settings(), "email_provider", "none")
    assert emailer.send_email("victim@example.org", "Reset", "https://x.test/?token=TOK") is False
    assert "no_provider" in prod_logs.text and "TOK" not in prod_logs.text and "victim@" not in prod_logs.text


def test_no_provider_in_dev_prints_the_link(monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "email_provider", "none")
    caplog.set_level(logging.DEBUG, logger="clipapi.email")
    assert get_settings().env == "dev"
    assert emailer.send_email("dev@example.org", "Reset", "https://x.test/?token=TOK") is False
    assert "TOK" in caplog.text


def account(client):
    email = f"m{uuid.uuid4().hex[:10]}@example.org"
    r = client.post("/v1/auth/signup", json={"email": email, "password": "correct-horse-9"})
    return email, r.json()["account"]["id"]


def test_forgot_answers_the_same_when_delivery_fails_and_logs_no_token(client, resend, prod_logs):
    _, answers = resend
    answers += [500, 500, 500]
    email, _ = account(client)
    r = client.post("/v1/auth/forgot", json={"email": email})
    assert r.status_code == 200 and r.json() == {"sent": True}
    assert "email_delivery_failed" in prod_logs.text
    assert "token=" not in prod_logs.text and email not in prod_logs.text
    assert client.post("/v1/auth/forgot", json={"email": "nobody-" + email}).json() == {"sent": True}


def test_forgot_sends_the_reset_link_through_resend(client, resend):
    seen, _ = resend
    email, _ = account(client)
    client.post("/v1/auth/forgot", json={"email": email})
    (r,) = seen
    payload = json.loads(r.content)
    assert payload["to"] == [email] and "/reset-password?token=" in payload["text"]
    assert r.headers["idempotency-key"].startswith("reset:")


def test_bumping_the_epoch_voids_reset_and_verify_links(client):
    email, acct = account(client)
    from app.db import new_session
    from app.models import Account
    from app.routes_auth import _pw_version
    with new_session() as db:
        version = _pw_version(db.get(Account, acct))
    epoch = token_epoch.current()
    reset = make_token(acct, "reset", timedelta(hours=1), v=version, e=epoch)
    verify = make_token(acct, "verify", timedelta(hours=48), e=epoch)
    token_epoch.bump()
    assert token_epoch.current() == epoch + 1
    r = client.post("/v1/auth/reset", json={"token": reset, "password": "another-horse-9"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_token"
    assert client.get("/v1/auth/verify", params={"token": verify}).status_code == 400
    fresh = make_token(acct, "reset", timedelta(hours=1), v=version, e=token_epoch.current())
    assert client.post("/v1/auth/reset", json={"token": fresh, "password": "another-horse-9"}).status_code == 200


def test_tokens_from_before_the_epoch_existed_die_on_the_first_bump(client):
    _, acct = account(client)
    old = make_token(acct, "verify", timedelta(hours=48))            # no `e` claim: issued by the old code
    if token_epoch.current() == 0:
        assert client.get("/v1/auth/verify", params={"token": old}).status_code == 200
    token_epoch.bump()
    assert client.get("/v1/auth/verify", params={"token": old}).status_code == 400


def prod(**over) -> Settings:
    # Explicit empty Stripe pair so conftest's webhook env does not trip SEC-016 coherence check.
    base = dict(env="prod", secret_key="x" * 40, database_url="postgresql+psycopg://u:p@db/clip",
                auto_verify_email=False, email_provider="resend", resend_api_key=KEY, smtp_host="",
                admin_mfa_required=True, storage_backend="s3",
                s3_endpoint_url="https://example.r2.cloudflarestorage.com", s3_bucket="clips",
                s3_access_key_id="id", s3_secret_access_key="secret",
                stripe_secret_key="", stripe_webhook_secret="")
    return Settings(**{**base, **over})


def test_production_accepts_resend_with_a_key():
    prod().check_production()


@pytest.mark.parametrize("over, problem", [
    ({"resend_api_key": ""}, "email delivery must be configured"),
    ({"email_provider": "none"}, "email delivery must be configured"),
    ({"email_provider": ""}, "email delivery must be configured"),          # no SMTP_HOST either
    ({"auto_verify_email": True}, "AUTO_VERIFY_EMAIL must be false"),
    ({"admin_mfa_required": False}, "ADMIN_MFA_REQUIRED must be true"),
    ({"storage_backend": "local"}, "STORAGE_BACKEND must be s3"),
    ({"stripe_secret_key": "only-one-side-set", "stripe_webhook_secret": ""},
     "STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET"),
])
def test_production_refuses_without_working_email(over, problem):
    with pytest.raises(RuntimeError, match=problem):
        prod(**over).check_production()


def test_production_still_accepts_smtp():
    prod(email_provider="smtp", resend_api_key="", smtp_host="smtp.example.org").check_production()


def run_admin(monkeypatch, *args):
    spec = importlib.util.spec_from_file_location("admin_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "argv", ["admin.py", *args])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    return exc.value.code


def test_admin_send_test_email_through_resend(resend, monkeypatch, capsys):
    seen, _ = resend
    assert run_admin(monkeypatch, "send-test-email", "--to", "me@example.org") == 0
    assert len(seen) == 1 and json.loads(seen[0].content)["to"] == ["me@example.org"]
    out = capsys.readouterr()
    assert "Resend API" in out.out and "msg_123" in out.out and KEY not in out.out + out.err


def test_admin_send_test_email_reports_a_bad_key_without_printing_it(resend, monkeypatch, capsys):
    _, answers = resend
    answers.append(401)
    assert run_admin(monkeypatch, "send-test-email", "--to", "me@example.org") == 1
    out = capsys.readouterr()
    assert "401" in out.err and KEY not in out.out + out.err


def test_admin_bump_token_epoch(monkeypatch, capsys):
    before = token_epoch.current()
    assert run_admin(monkeypatch, "bump-token-epoch") == 0
    assert token_epoch.current() == before + 1
    assert f"token epoch is now {before + 1}" in capsys.readouterr().out


def test_the_access_log_never_holds_a_verify_or_file_token():
    from app.log_redact import RedactSecrets, install
    install()
    assert any(isinstance(f, RedactSecrets) for f in logging.getLogger("uvicorn.access").filters)
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4:5", "GET", "/v1/auth/verify?token=eyJ.SECRET.sig&x=1", "1.1", 303), None)
    RedactSecrets().filter(record)
    line = record.getMessage()
    assert "SECRET" not in line and "/v1/auth/verify?token=[redacted]&x=1" in line
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4:5", "GET", "/v1/files/eyJ.FILETOKEN.sig", "1.1", 200), None)
    RedactSecrets().filter(record)
    assert "FILETOKEN" not in record.getMessage() and "/v1/files/[redacted]" in record.getMessage()
