"""Keep secrets in URLs out of the access log.

Uvicorn logs every request line. Two kinds of URL carry a secret: the email verification link
(`/v1/auth/verify?token=...`) and signed file links (`/v1/files/<token>`). The filter rewrites them before the line
is written, so a log file never holds a working link.
"""
import logging
import re

_PATTERNS = (
    (re.compile(r"([?&](?:token|t)=)[^&\s\"']+"), r"\1[redacted]"),
    (re.compile(r"(/v1/files/)[^/?\s\"']+"), r"\1[redacted]"),
)


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = redact(record.msg)
        return True


def install() -> None:
    """Add the filter to uvicorn's access logger (idempotent)."""
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactSecrets) for f in access.filters):
        access.addFilter(RedactSecrets())
