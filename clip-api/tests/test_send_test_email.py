"""scripts/admin.py send-test-email against a local fake SMTP server."""
import importlib.util
import smtplib
import socketserver
import sys
import threading
from email import message_from_string
from pathlib import Path

import pytest

from app import config

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "admin.py"
PASSWORD = "example_password_do_not_print"


def load_admin():
    spec = importlib.util.spec_from_file_location("admin_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeSmtp(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.messages: list[str] = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return self.server_address[1]


class _Handler(socketserver.StreamRequestHandler):
    def reply(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self) -> None:
        self.reply("220 fake ESMTP")
        for raw in self.rfile:
            verb = raw.decode().strip().split(" ")[0].upper()
            if verb == "EHLO":
                self.wfile.write(b"250-fake\r\n250 AUTH PLAIN\r\n")
            elif verb == "AUTH":
                self.reply("535 5.7.8 authentication failed")
            elif verb in ("MAIL", "RCPT", "RSET", "NOOP"):
                self.reply("250 ok")
            elif verb == "DATA":
                self.reply("354 go")
                lines = []
                for part in self.rfile:
                    if part == b".\r\n":
                        break
                    lines.append(part.decode())
                self.server.messages.append("".join(lines))
                self.reply("250 queued")
            elif verb == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("500 unknown")


@pytest.fixture
def smtp_env(monkeypatch):
    # The fake server has no TLS; STARTTLS itself is stdlib behaviour, not ours.
    monkeypatch.setattr(smtplib.SMTP, "starttls", lambda self, *a, **k: (220, b"ok"))

    def configure(**values):
        for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"):
            monkeypatch.delenv(name, raising=False)
        for name, value in values.items():
            monkeypatch.setenv(name, str(value))
        config.get_settings.cache_clear()

    yield configure
    config.get_settings.cache_clear()


def run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["admin.py", "send-test-email", *args])
    with pytest.raises(SystemExit) as exc:
        load_admin().main()
    return exc.value.code


def test_no_smtp_host_exits_2_and_names_missing_keys(smtp_env, monkeypatch, capsys):
    smtp_env()
    assert run(monkeypatch, "--to", "me@example.org") == 2
    out = capsys.readouterr()
    assert "SMTP_HOST" in out.out + out.err


def test_sends_exactly_one_message_and_exits_0(smtp_env, monkeypatch, capsys):
    server = FakeSmtp()
    try:
        smtp_env(SMTP_HOST="127.0.0.1", SMTP_PORT=server.port, EMAIL_FROM="hello@clips.test")
        assert run(monkeypatch, "--to", "me@example.org") == 0
        assert len(server.messages) == 1
        msg = message_from_string(server.messages[0])
        assert msg["To"] == "me@example.org"
        assert msg["From"] == "hello@clips.test"
    finally:
        server.shutdown()
    assert "me@example.org" in capsys.readouterr().out


def test_refused_connection_exits_1(smtp_env, monkeypatch, capsys):
    server = FakeSmtp()
    port = server.port
    server.shutdown()
    server.server_close()
    smtp_env(SMTP_HOST="127.0.0.1", SMTP_PORT=port, SMTP_USER="u", SMTP_PASSWORD=PASSWORD)
    assert run(monkeypatch, "--to", "me@example.org") == 1
    out = capsys.readouterr()
    assert out.err.strip() and PASSWORD not in out.out + out.err


def test_auth_failure_exits_1_without_password(smtp_env, monkeypatch, capsys):
    server = FakeSmtp()
    try:
        smtp_env(SMTP_HOST="127.0.0.1", SMTP_PORT=server.port, SMTP_USER="u", SMTP_PASSWORD=PASSWORD)
        assert run(monkeypatch, "--to", "me@example.org") == 1
    finally:
        server.shutdown()
    out = capsys.readouterr()
    assert "535" in out.out + out.err
    assert PASSWORD not in out.out + out.err
    assert server.messages == []


def test_send_email_still_returns_false_on_failure(smtp_env):
    smtp_env()
    from app.emailer import send_email
    assert send_email("a@example.org", "s", "b") is False
