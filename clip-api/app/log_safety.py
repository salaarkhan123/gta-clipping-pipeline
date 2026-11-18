"""Keep tokens, keys and passwords out of logs and error reports.

- Request logs: download links (`/v1/files/<token>`) and email verification links (`/v1/auth/verify?token=...`)
  carry a signed token in the URL, so uvicorn's access log and httpx's request log would write it down. A filter
  replaces anything token- or key-shaped in those lines with `[redacted]`.
- Sentry: local variables are not sent with errors. A handler's locals include the settings object, whose repr
  holds SECRET_KEY, STRIPE_SECRET_KEY and the database password.

tests/test_secrets_in_logs.py scans every log line of the test run for secret-shaped strings.
"""
import logging
import re

SECRET_SHAPES = re.compile("|".join((
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",     # signed tokens (JWT)
    r"\b[sr]k_(?:live|test)_[A-Za-z0-9]+",                     # Stripe keys
    r"\bwhsec_[A-Za-z0-9]+",                                    # Stripe webhook secrets
    r"\bsk-ant-[A-Za-z0-9_-]+",                                 # Anthropic keys
    r"\bgck_[A-Za-z0-9_-]+",                                    # ClutchClips API keys
)))
REQUEST_LOGGERS = ("uvicorn.access", "uvicorn.error", "httpx", "httpcore")


class RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        clean = SECRET_SHAPES.sub("[redacted]", message)
        if clean != message:
            record.msg, record.args = clean, None
        return True


def install() -> None:
    """Add the filter to the request loggers. Safe to call more than once."""
    for name in REQUEST_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactSecrets) for f in logger.filters):
            logger.addFilter(RedactSecrets())


def init_sentry(dsn: str) -> None:
    import sentry_sdk
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0, include_local_variables=False, send_default_pii=False)
