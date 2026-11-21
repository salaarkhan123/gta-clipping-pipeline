"""scripts/admin.py ops-status: the queue health that ops.sh status and the monitor read."""
import contextlib
import importlib.util
import io
import re
from pathlib import Path

from app.db import init_db

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "admin.py"


def test_prints_integer_key_values_the_monitor_parses():
    init_db()
    spec = importlib.util.spec_from_file_location("admin_script_ops", SCRIPT)
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert admin.ops_status() == 0
    lines = buf.getvalue().splitlines()
    assert [line.split("=")[0] for line in lines] == [
        "jobs_running", "jobs_queued", "oldest_queued_min", "stalest_heartbeat_min", "last_claim_min",
        "email_configured", "stripe_configured", "stripe_webhook_configured"]
    assert all(re.fullmatch(r"[a-z_]+=-?\d+", line) for line in lines)   # the pattern ops.sh status keeps


def test_config_flags_say_whether_a_setting_is_set_never_its_value(monkeypatch):
    from app import config
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_do_not_print")
    config.get_settings.cache_clear()
    try:
        spec = importlib.util.spec_from_file_location("admin_script_ops2", SCRIPT)
        admin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(admin)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            admin.ops_status()
    finally:
        config.get_settings.cache_clear()
    out = buf.getvalue()
    assert "email_configured=0" in out and "stripe_webhook_configured=1" in out
    assert "whsec" not in out
