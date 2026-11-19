"""One number that voids every outstanding password-reset and email-verification link at once.

Reset and verify tokens carry the epoch they were issued in (claim `e`; tokens from before this existed count as
0). `python scripts/admin.py bump-token-epoch` adds one, so every link already sent stops working, without
rotating SECRET_KEY (which would also log everyone out). Session tokens are not affected.

The number is kept as a small object in storage (app/storage.py), so the api and every worker see the same value.
"""
import json
import uuid

from .config import get_settings
from .storage import get_storage

KEY = "system/token_epoch.json"


def current() -> int:
    storage = get_storage()
    if not storage.exists(KEY):
        return 0
    tmp = get_settings().work_dir / f"epoch_{uuid.uuid4().hex}.json"
    try:
        storage.fetch(KEY, tmp)
        return int(json.loads(tmp.read_text()).get("epoch", 0))
    finally:
        tmp.unlink(missing_ok=True)


def bump() -> int:
    """Raise the epoch by one and return the new value. Every reset and verify link issued before is void."""
    new = current() + 1
    tmp = get_settings().work_dir / f"epoch_{uuid.uuid4().hex}.json"
    try:
        tmp.write_text(json.dumps({"epoch": new}))
        get_storage().put(KEY, tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return new
