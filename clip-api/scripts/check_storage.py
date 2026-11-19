#!/usr/bin/env python3
"""Check the S3/R2 bucket end to end through app/storage.py.

Needs STORAGE_BACKEND=s3 and the S3_* settings (DEPLOY.md, "Moving files to Cloudflare R2"). Writes and deletes
a few small objects under healthcheck/<id>/. Prints `ok <step>` or `FAIL <step>: <error>` per step:
put, get, signed-url (bytes, content type, download name), cors (the site at PUBLIC_WEB_URL may read the
signed URL), private (the object is not readable without a signature), delete, delete-prefix.
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
    s = get_settings()
    if s.storage_backend != "s3":
        print("check_storage only checks S3: set STORAGE_BACKEND=s3 and the S3_* settings")
        return 2
    store = storage.get_storage()
    folder = f"healthcheck/{uuid.uuid4()}/"
    key = folder + "probe.json"
    payload = os.urandom(1024)
    origin = s.public_web_url.rstrip("/")
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

    def write(k: str, data: bytes) -> None:
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.bin"
            src.write_bytes(data)
            store.put(k, src)

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
        if r.headers.get("content-type") != "application/json":
            raise ValueError(f"content-type is {r.headers.get('content-type')!r}, expected 'application/json'")
        if 'filename="probe.json"' not in r.headers.get("content-disposition", ""):
            raise ValueError(f"content-disposition is {r.headers.get('content-disposition')!r}")

    def cors() -> None:
        r = httpx.get(store.url(key), headers={"Origin": origin}, timeout=30)
        allowed = r.headers.get("access-control-allow-origin")
        if allowed not in (origin, "*"):
            raise ValueError(f"the bucket does not let {origin} read files (Access-Control-Allow-Origin: {allowed}). "
                             "Paste the CORS rules from DEPLOY.md")

    def private() -> None:
        status = httpx.get(store.url(key).split("?")[0], timeout=30).status_code
        if status < 400:
            raise ValueError(f"the object is readable without a signature (HTTP {status}): turn public access off")

    def delete() -> None:
        store.delete(key)
        if store.exists(key):
            raise ValueError("object still exists after delete")

    def delete_prefix() -> None:
        for name in ("a.txt", "sub/b.txt"):
            write(folder + name, b"x")
        removed = store.delete_prefix(folder)
        left = store.keys(folder)
        if left:
            raise ValueError(f"{len(left)} objects left after deleting {removed}")

    try:
        if step("put", lambda: write(key, payload)) and step("get", get) and step("signed-url", signed_url):
            step("cors", cors)
            step("private", private)
    finally:
        step("delete", delete)
        step("delete-prefix", delete_prefix)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
