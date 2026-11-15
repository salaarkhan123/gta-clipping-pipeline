#!/usr/bin/env python3
"""Check the S3/R2 bucket end to end through app/storage.py.

Needs STORAGE_BACKEND=s3 and the S3_* settings from .env.example. Writes and deletes one small
object under healthcheck/. Prints `ok <step>` or `FAIL <step>: <error>` per step.
Exit 0 = all ok, 1 = a step failed, 2 = not running against S3.
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import storage  # noqa: E402
from app.config import get_settings  # noqa: E402


def main() -> int:
    if get_settings().storage_backend != "s3":
        print("check_storage only checks S3: set STORAGE_BACKEND=s3 and the S3_* settings")
        return 2
    store = storage.get_storage()
    key = f"healthcheck/{uuid.uuid4()}"
    payload = os.urandom(1024)
    failed = False

    def step(name: str, fn) -> bool:
        nonlocal failed
        try:
            fn()
        except Exception as e:  # report any failure, keep going to cleanup
            print(f"FAIL {name}: {e}")
            failed = True
            return False
        print(f"ok {name}")
        return True

    def put() -> None:
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.bin"
            src.write_bytes(payload)
            store.put(key, src)

    def get() -> None:
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "out.bin"
            store.fetch(key, dest)
            if dest.read_bytes() != payload:
                raise ValueError("downloaded bytes differ from uploaded bytes")

    def signed_url() -> None:
        r = httpx.get(store.url(key), timeout=30)
        if r.status_code != 200:
            raise ValueError(f"signed URL returned HTTP {r.status_code}")
        if r.content != payload:
            raise ValueError("signed URL bytes differ from uploaded bytes")

    def delete() -> None:
        store.delete(key)
        if store.exists(key):
            raise ValueError("object still exists after delete")

    try:
        if step("put", put) and step("get", get):
            step("signed-url", signed_url)
    finally:
        step("delete", delete)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
