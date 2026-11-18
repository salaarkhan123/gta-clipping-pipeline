"""Transactional email: Resend's HTTPS API (primary), SMTP (optional), or none.

EMAIL_PROVIDER picks one: `resend` (needs RESEND_API_KEY), `smtp` (needs SMTP_HOST), `none`. Empty (the default)
means `smtp` when SMTP_HOST is set and `none` otherwise, as before.

Logs never hold a message body, a link or a token, whatever the provider: only the masked recipient, the subject
and what went wrong. The one exception is local development (ENV=dev with no provider), where the body is
printed so a developer can click the link.

Resend API: https://resend.com/docs/api-reference/emails/send-email (POST /emails, Bearer key, Idempotency-Key
up to 256 characters, kept 24 hours) and https://resend.com/docs/api-reference/introduction (a User-Agent header
is required; 429 = rate limit, 5xx = Resend's error).
"""
import logging
import smtplib
import time
from email.message import EmailMessage

import httpx

from .config import get_settings

log = logging.getLogger("clipapi.email")
RESEND_URL = "https://api.resend.com/emails"
USER_AGENT = "clutchclips-api/1.0"
TIMEOUT_SEC = 10
ATTEMPTS = 3                  # Resend: one try plus two retries on 429, 5xx or a network error
BACKOFF_SEC = (0.5, 2.0)      # wait before retry 1 and retry 2
_sleep = time.sleep           # tests replace it


class EmailError(Exception):
    """Delivery failed. The message says why without the body or any secret."""


def provider(s=None) -> str:
    s = s or get_settings()
    chosen = (s.email_provider or "").strip().lower()
    if not chosen:
        return "smtp" if s.smtp_host else "none"
    return chosen


def mask(address: str) -> str:
    """`s***@example.com`: enough to tell messages apart in a log, not enough to read the address."""
    local, _, domain = (address or "").partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def missing_keys(s=None) -> list[str]:
    """Env var names that must be set before mail can leave (names only, never values)."""
    s = s or get_settings()
    p = provider(s)
    if p == "resend":
        return [] if s.resend_api_key else ["RESEND_API_KEY"]
    if p == "smtp":
        missing = [] if s.smtp_host else ["SMTP_HOST"]
        if s.smtp_user and not s.smtp_password:
            missing.append("SMTP_PASSWORD")
        return missing
    if p == "none":
        return ["EMAIL_PROVIDER=resend with RESEND_API_KEY (or SMTP_HOST)"]
    return [f"EMAIL_PROVIDER (unknown value {p!r}: use resend, smtp or none)"]


missing_smtp_keys = missing_keys        # the older name, still used by callers


def _smtp(to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


def _resend(to: str, subject: str, body: str, idempotency_key: str | None, client: httpx.Client | None) -> str:
    """Returns Resend's message id. Retries 429, 5xx and network errors; other refusals fail at once."""
    s = get_settings()
    headers = {"Authorization": f"Bearer {s.resend_api_key}", "User-Agent": USER_AGENT}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:256]
    payload = {"from": s.email_from, "to": [to], "subject": subject, "text": body}
    http = client or httpx.Client(timeout=TIMEOUT_SEC)
    try:
        for attempt in range(ATTEMPTS):
            if attempt:
                _sleep(BACKOFF_SEC[attempt - 1])
            try:
                r = http.post(RESEND_URL, json=payload, headers=headers, timeout=TIMEOUT_SEC)
            except httpx.HTTPError as e:
                why = f"network error ({type(e).__name__})"
                continue
            if r.status_code < 300:
                return str((r.json() or {}).get("id", ""))
            why = f"Resend answered {r.status_code}"
            if r.status_code != 429 and r.status_code < 500:
                break                                   # bad request, bad key, unverified domain: retrying won't help
        raise EmailError(why)
    finally:
        if client is None:
            http.close()


def deliver(to: str, subject: str, body: str, idempotency_key: str | None = None,
            client: httpx.Client | None = None) -> str:
    """Send one message through the configured provider. Raises EmailError (or the SMTP error) on failure."""
    p = provider()
    if missing_keys():
        raise EmailError(f"email provider {p} is not configured: {', '.join(missing_keys())}")
    if p == "resend":
        return _resend(to, subject, body, idempotency_key, client)
    _smtp(to, subject, body)
    return ""


def send_email(to: str, subject: str, body: str, idempotency_key: str | None = None) -> bool:
    """Send, never raise. False when the mail did not go; the failure is logged without the body."""
    s, p = get_settings(), provider()
    if p == "none":
        if s.env == "dev":
            log.warning("No email provider (ENV=dev): printing instead of sending. To %s. Subject: %s\n%s",
                        to, subject, body)
        else:
            log.error("email_not_sent reason=no_provider to=%s subject=%r", mask(to), subject)
        return False
    try:
        deliver(to, subject, body, idempotency_key)
        log.info("email_sent provider=%s to=%s subject=%r", p, mask(to), subject)
        return True
    except Exception as e:
        # Only the exception's type and our own text: an SMTP or HTTP error can echo the request.
        detail = str(e) if isinstance(e, EmailError) else type(e).__name__
        log.error("email_delivery_failed provider=%s to=%s subject=%r error=%s", p, mask(to), subject, detail)
        return False
