"""Cloudflare R2's documented differences from S3, checked on every request the app's S3 client sends, and one
pass over every storage call the app makes. Used against moto (test_r2_storage.py) and a real R2 bucket
(test_r2_live.py).

R2 rules (developers.cloudflare.com/r2, read 2026-11-17):
- region "auto" (api/s3/api/)
- no full-object CRC32/CRC32C/SHA checksums on PutObject, no checksum headers on CopyObject or PutBucketCors
  (api/s3/api/, "Checksum Types")
- multipart: every part but the last the same size, at least 5 MiB, at most 10,000 parts (objects/multipart-objects/)
- DeleteObjects: at most 1,000 keys (platform/release-notes/, 2022-07-01)
- presigned URLs: 1 second to 7 days (api/s3/presigned-urls/)
"""
import os
import re
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

MiB = 1024 ** 2


class R2Rules:
    """Records each request of one boto3 S3 client and lists the ones R2 would refuse."""

    def __init__(self, client):
        self.violations: list[str] = []
        self.calls: list[str] = []
        self.parts: dict[str, list[tuple[int, int]]] = defaultdict(list)
        client.meta.events.register("before-send.s3", self._check)

    def _check(self, request, **kwargs):
        url, headers = urlsplit(request.url), {k.lower(): v for k, v in request.headers.items()}
        query = parse_qs(url.query, keep_blank_values=True)
        name = self._name(request.method, query, headers)
        self.calls.append(name)
        auth = headers.get("authorization", b"")
        auth = auth.decode() if isinstance(auth, bytes) else auth
        m = re.search(r"Credential=[^/]+/\d{8}/([^/]+)/s3/", auth)
        if m and m.group(1) != "auto":
            self.violations.append(f"{name}: signed for region {m.group(1)!r}, R2 uses 'auto'")
        checksums = [h for h in headers if h.startswith("x-amz-checksum-") or h == "x-amz-sdk-checksum-algorithm"]
        if checksums and name != "DeleteObjects":
            self.violations.append(f"{name}: sends {', '.join(sorted(checksums))}")
        if name == "UploadPart":
            body = request.body
            size = len(body) if isinstance(body, (bytes, bytearray)) else int(headers.get("content-length", 0))
            self.parts[query["uploadId"][0]].append((int(query["partNumber"][0]), size))
        if name == "CompleteMultipartUpload":
            self._check_parts(query["uploadId"][0])
        if name == "DeleteObjects":
            body = request.body if isinstance(request.body, (bytes, bytearray)) else b""
            if body.count(b"<Key>") > 1000:
                self.violations.append(f"DeleteObjects: {body.count(b'<Key>')} keys, R2 takes 1000")

    @staticmethod
    def _name(method: str, query: dict, headers: dict) -> str:
        if "uploadId" in query:
            return {"PUT": "UploadPart", "POST": "CompleteMultipartUpload", "DELETE": "AbortMultipartUpload",
                    "GET": "ListParts"}[method]
        if "uploads" in query:
            return "CreateMultipartUpload"
        if "delete" in query:
            return "DeleteObjects"
        if "cors" in query:
            return f"{method}BucketCors"
        if method == "PUT":
            return "CopyObject" if "x-amz-copy-source" in headers else "PutObject"
        if method == "GET":
            return "ListObjectsV2" if "list-type" in query else "GetObject"
        return {"HEAD": "HeadObject", "DELETE": "DeleteObject"}.get(method, method)

    def _check_parts(self, upload_id: str) -> None:
        parts = sorted(self.parts.get(upload_id, []))
        sizes = [s for _, s in parts]
        if len(sizes) > 10_000:
            self.violations.append(f"multipart {upload_id}: {len(sizes)} parts, R2 takes 10,000")
        if len(set(sizes[:-1])) > 1:
            self.violations.append(f"multipart {upload_id}: part sizes differ {sorted(set(sizes[:-1]))}")
        if sizes[:-1] and sizes[0] < 5 * MiB:
            self.violations.append(f"multipart {upload_id}: parts of {sizes[0]} bytes, R2 needs 5 MiB")


def signed_url_checks(url: str, endpoint: str, name: str, content_type: str) -> list[str]:
    """What R2 needs of a presigned download link the site shows."""
    problems = []
    u, e = urlsplit(url), urlsplit(endpoint)
    if (u.scheme, u.netloc) != (e.scheme, e.netloc):
        problems.append(f"link is on {u.scheme}://{u.netloc}, not the endpoint {e.scheme}://{e.netloc} the CSP allows")
    expires = int(parse_qs(u.query)["X-Amz-Expires"][0])
    if not 1 <= expires <= 604_800:
        problems.append(f"X-Amz-Expires={expires}, R2 takes 1 to 604800")
    r = httpx.get(url, timeout=60)
    if r.status_code != 200:
        return problems + [f"signed GET returned HTTP {r.status_code}"]
    if r.headers.get("content-type") != content_type:
        problems.append(f"content-type {r.headers.get('content-type')!r}, expected {content_type!r}")
    if f'attachment; filename="{name}"' != r.headers.get("content-disposition"):
        problems.append(f"content-disposition {r.headers.get('content-disposition')!r}")
    if httpx.get(url.split("?")[0], timeout=60).status_code < 400:
        problems.append(f"{name} is readable without a signature")
    return problems


def exercise(store, prefix: str, big_mib: int = 20, many: int = 1001) -> dict:
    """Every storage call the app makes, under prefix; leaves nothing behind. Returns what it saw."""
    seen: dict = {}
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        small, big = d / "captions.json", d / "upload.mp4"
        small.write_bytes(b'{"words": []}')
        big.write_bytes(os.urandom(big_mib * MiB))               # above 8 MiB: upload_file goes multipart
        store.put(prefix + "clips/c1.captions.json", small)
        store.put(prefix + "uploads/u1.mp4", big)
        assert store.size(prefix + "uploads/u1.mp4") == big.stat().st_size
        assert store.exists(prefix + "clips/c1.captions.json") and not store.exists(prefix + "missing.json")
        store.fetch(prefix + "uploads/u1.mp4", d / "back.mp4")
        assert (d / "back.mp4").read_bytes() == big.read_bytes()
        seen["url_problems"] = (
            signed_url_checks(store.url(prefix + "uploads/u1.mp4"), store.client.meta.endpoint_url, "u1.mp4", "video/mp4")
            + signed_url_checks(store.url(prefix + "clips/c1.captions.json"), store.client.meta.endpoint_url,
                                "c1.captions.json", "application/json"))
        store.delete(prefix + "clips/c1.captions.json")
        assert not store.exists(prefix + "clips/c1.captions.json")
        with ThreadPoolExecutor(16) as pool:                      # more than one DeleteObjects batch
            list(pool.map(lambda i: store.client.put_object(Bucket=store.bucket, Key=f"{prefix}many/{i:05d}", Body=b"x"),
                          range(many)))
        assert len(store.keys(prefix + "many/")) == many
        seen["deleted"] = store.delete_prefix(prefix)
        seen["left"] = store.keys(prefix)
    return seen
