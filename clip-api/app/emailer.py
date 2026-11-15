import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("clipapi.email")


def send_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not s.smtp_host:
        log.warning("SMTP not configured; email to %s not sent. Subject: %s\n%s", to, subject, body)
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception("Failed to send email to %s", to)
        return False
