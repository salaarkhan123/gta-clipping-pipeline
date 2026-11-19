"""Keep secrets out of logs and error reports.

Uvicorn logs every request line. Two kinds of URL carry a secret: the email verification link
(`/v1/auth/verify?token=...`) and signed file links (`/v1/files/<token>`). The filter rewrites them before the line
is written, so a log file never holds a working link. It also hides anything shaped like a signed token or an API
key wherever it appears (Stripe keys and webhook secrets, Anthropic keys, ClutchClips API keys), and it runs on the
httpx request log too, which writes the URL of every outgoing call.

Sentry gets no local variables: a handler's locals hold the settings object, whose repr has SECRET_KEY,
STRIPE_SECRET_KEY and the database password in it.

tests/test_secrets_in_logs.py scans every log line of the test run for secret-shaped strings.
"""
import logging
import re

_PATTERNS = (
    (re.compile(r"([?&](?:token|t)=)[^&\s\"']+"), r"\1[redacted]"),
    (re.compile(r"(/v1/files/)[^/?\s\"']+"), r"\1[redacted]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[redacted]"),   # signed tokens (JWT)
    (re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]+"), "[redacted]"),                    # Stripe keys
    (re.compile(r"\bwhsec_[A-Za-z0-9]+"), "[redacted]"),                                   # Stripe webhook secrets
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]+"), "[redacted]"),                                # Anthropic keys
    (re.compile(r"\bgck_[A-Za-z0-9_-]+"), "[redacted]"),                                   # ClutchClips API keys
)
LOGGERS = ("uvicorn.access", "uvicorn.error", "httpx", "httpcore")


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # The formatted line, not the args one by one: httpx passes the URL as an httpx.URL object, not a str.
        try:
            message = record.getMessage()
        except Exception:
            return True
        clean = redact(message)
        if clean != message:
            record.msg, record.args = clean, None
        return True


def install() -> None:
    """Add the filter to uvicorn's access and error loggers and to httpx (idempotent)."""
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactSecrets) for f in logger.filters):
            logger.addFilter(RedactSecrets())


def init_sentry(dsn: str) -> None:
    import sentry_sdk
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0, include_local_variables=False, send_default_pii=False)
