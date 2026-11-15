import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("clipapi.email")


def missing_smtp_keys() -> list[str]:
    """Env var names that must be set before mail can leave (names only, never values)."""
    s = get_settings()
    missing = [] if s.smtp_host else ["SMTP_HOST"]
    if s.smtp_user and not s.smtp_password:
        missing.append("SMTP_PASSWORD")
    return missing


def deliver(to: str, subject: str, body: str) -> None:
    """Send one message. Raises on any SMTP or network error; the caller decides what to do."""
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


def send_email(to: str, subject: str, body: str) -> bool:
    if not get_settings().smtp_host:
        log.warning("SMTP not configured; email to %s not sent. Subject: %s\n%s", to, subject, body)
        return False
    try:
        deliver(to, subject, body)
        return True
    except Exception:
        log.exception("Failed to send email to %s", to)
        return False
