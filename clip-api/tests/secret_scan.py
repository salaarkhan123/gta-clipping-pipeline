"""Records every log line the test run writes and finds secret-shaped strings in them (tests/test_secrets_in_logs.py).

Kept apart from app/log_redact.py on purpose: this is the independent check that the redaction works."""
import logging
import re

PATTERNS = {
    "Stripe secret or restricted key": re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{6,}"),
    "Stripe webhook secret": re.compile(r"\bwhsec_[A-Za-z0-9]{4,}"),
    "Anthropic API key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}"),
    "ClutchClips API key": re.compile(r"\bgck_[A-Za-z0-9_-]{20,}"),
    "signed token (JWT)": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "password in a URL": re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "password hash": re.compile(r"\$argon2(?:id|i|d)\$"),
}


def find(text: str, literals: dict[str, str] | None = None) -> list[str]:
    """Names of the secret kinds in `text`: the patterns above plus exact `literals` ({name: value})."""
    hits = [name for name, rx in PATTERNS.items() if rx.search(text)]
    return hits + [name for name, value in (literals or {}).items() if value and value in text]


class Recorder(logging.Handler):
    """Keeps (logger, level, formatted line with any traceback) for every record that reaches the root logger."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
        self.lines: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append((record.name, self.format(record)))
        except Exception:                      # a record that cannot be formatted is not ours to fail on
            pass


RECORDER = Recorder()
