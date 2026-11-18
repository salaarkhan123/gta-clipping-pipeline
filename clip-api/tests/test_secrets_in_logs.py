"""No secret reaches a log line: every record logged during the test run is scanned for secret-shaped strings
(Stripe, Anthropic and ClutchClips keys, webhook secrets, signed tokens, passwords in URLs, password hashes) and
for the exact secrets this run is configured with. tests/conftest.py runs this test last."""
from app.config import get_settings
from tests.secret_scan import RECORDER, find
from tests.test_stripe_events import fresh_ids, i, send  # noqa: F401

PASSWORD = "correct-horse-9"          # the password tests/conftest.py signs every user up with


def literals() -> dict[str, str]:
    s = get_settings()
    found = {name: getattr(s, name) for name in ("secret_key", "secret_key_previous", "stripe_secret_key",
                                                 "stripe_webhook_secret", "smtp_password", "s3_secret_access_key",
                                                 "anthropic_api_key")}
    return {**{k: v for k, v in found.items() if v and len(v) >= 8}, "test password": PASSWORD}


def test_the_scan_recognises_each_kind_of_secret():
    planted = {                                                     # built here so no key-shaped literal is committed
        "Stripe secret or restricted key": "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc",
        "Stripe webhook secret": "whsec_" + "a1B2c3D4e5F6",
        "Anthropic API key": "sk-" + "ant-api03-" + "x" * 20,
        "ClutchClips API key": "gck_" + "Q" * 40,
        "signed token (JWT)": "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiJhY2N0In0" + "." + "s" * 30,
        "password in a URL": "postgresql+psycopg://clip:" + "hunter2hunter2" + "@db:5432/clip",
        "password hash": "$argon2" + "id$v=19$m=65536",
    }
    for name, value in planted.items():
        assert find(f"something went wrong with {value} here") == [name], name
    assert find("GET /v1/jobs/job_123 200 stripe event evt_1 invoice in_1 pi_1 cus_1 sub_1") == []
    assert find(f"login {PASSWORD}", {"test password": PASSWORD}) == ["test password"]


def test_request_logs_hide_the_tokens_in_download_and_verification_links():
    import logging
    from app import log_redact
    log_redact.install()
    token = "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiJhY2N0In0" + "." + "s" * 30
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4:5", "GET", f"/v1/auth/verify?token={token}", "1.1", 200), None)
    assert logging.getLogger("uvicorn.access").filter(record)
    assert record.getMessage() == '1.2.3.4:5 - "GET /v1/auth/verify?token=[redacted] HTTP/1.1" 200'
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, "HTTP Request: GET %s", (f"/v1/files/{token}",), None)
    logging.getLogger("httpx").filter(record)
    assert record.getMessage() == "HTTP Request: GET /v1/files/[redacted]"


def test_keys_and_bare_tokens_are_hidden_in_every_request_logger():
    """Beyond the two URL shapes: Stripe, Anthropic and API keys, webhook secrets and signed tokens anywhere in the
    line, on uvicorn's error log and httpx's outgoing-request log too."""
    import logging
    from app import log_redact
    log_redact.install()
    planted = ["sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc", "rk_" + "test_" + "abcdef123456", "whsec_" + "a1B2c3D4e5F6",
               "sk-" + "ant-api03-" + "x" * 20, "gck_" + "Q" * 40,
               "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiJhY2N0In0" + "." + "s" * 30]
    for name in ("uvicorn.error", "httpx", "httpcore", "uvicorn.access"):
        for value in planted:
            record = logging.LogRecord(name, logging.INFO, __file__, 1, "call %s failed: %s",
                                       ("https://example.invalid/hook", f"Authorization: Bearer {value}"), None)
            logging.getLogger(name).filter(record)
            assert value not in record.getMessage() and "Bearer [redacted]" in record.getMessage(), (name, value[:6])
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, "plain message with " + planted[2], None, None)
    logging.getLogger("httpx").filter(record)
    assert record.getMessage() == "plain message with [redacted]"


def test_sentry_never_gets_local_variables(monkeypatch):
    """A handler's locals hold the settings object, whose repr has SECRET_KEY and STRIPE_SECRET_KEY in it."""
    import sentry_sdk
    from app import log_redact
    seen = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    log_redact.init_sentry("https://public@example.invalid/1")
    assert seen["include_local_variables"] is False and seen["send_default_pii"] is False


def test_no_log_line_in_this_run_holds_a_secret(client, user):
    headers, account = user
    # Paths that log on purpose, so the scan has something to look at even when this file runs alone.
    send(client, "checkout.session.completed", {"id": i("cs_x"), "mode": "payment", "payment_status": "paid",
                                                 "metadata": {"account_id": "acct_nobody", "pack_id": "pack_300"}})
    send(client, "charge.refunded", {"id": i("ch_x"), "payment_intent": "pi_nobody", "amount": 1, "amount_refunded": 1})
    client.post("/v1/auth/login", json={"email": account["email"], "password": "wrong-password-1"})
    client.get("/v1/me", headers={"Authorization": "Bearer gck_" + "z" * 40})
    assert RECORDER.lines, "the recorder saw no log lines: is it attached to the root logger?"
    secrets = literals()
    leaks = [(logger, find(line, secrets)) for logger, line in RECORDER.lines if find(line, secrets)]
    # Only the logger and the kind of secret are reported, never the line itself.
    assert not leaks, f"{len(leaks)} log line(s) hold a secret: {sorted(set((lg, tuple(k)) for lg, k in leaks))}"
