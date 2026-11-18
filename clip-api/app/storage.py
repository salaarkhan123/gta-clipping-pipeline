"""Object storage behind one interface: local disk (dev/tests) or S3-compatible (Cloudflare R2, DigitalOcean Spaces)."""
import mimetypes
import shutil
from contextlib import contextmanager
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from .config import get_settings
from .security import make_token

# Longest life of a SigV4 presigned URL on S3, R2 and Spaces (R2: 1 second to 7 days).
MAX_SIGNED_URL_SEC = 7 * 24 * 3600
# Most keys one DeleteObjects call takes (S3 and R2); ListObjectsV2 pages are the same size.
DELETE_BATCH = 1000


def check_prefix(prefix: str) -> None:
    """A prefix names a folder ("clips/job_1/"): without the slash "uploads/acct_1" would also match acct_10."""
    if not prefix.endswith("/") or prefix.strip("/") == "":
        raise ValueError(f"storage prefix must be a non-empty folder ending in '/': {prefix!r}")


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("bad storage key")
        return p

    def put(self, key: str, src: Path) -> None:
        dest = self.path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)

    def fetch(self, key: str, dest: Path) -> None:
        shutil.copyfile(self.path(key), dest)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def url(self, key: str) -> str:
        s = get_settings()
        token = make_token("file", "file", timedelta(seconds=s.signed_url_ttl_sec), k=key)
        return f"{s.public_api_url}/v1/files/{token}"

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def keys(self, prefix: str) -> list[str]:
        check_prefix(prefix)
        folder = self.path(prefix.rstrip("/"))
        return sorted(p.relative_to(self.root.resolve()).as_posix() for p in folder.rglob("*") if p.is_file())

    def delete_prefix(self, prefix: str) -> int:
        """Delete every file under prefix; returns how many."""
        found = self.keys(prefix)
        for key in found:
            self.delete(key)
        return len(found)


class S3Storage:
    """Private bucket; downloads are presigned URLs straight from the bucket (no bytes through the api)."""

    def __init__(self):
        import boto3
        from botocore.config import Config
        s = get_settings()
        self.bucket = s.s3_bucket
        # Checksums only when the API requires them: boto3's newer default (a CRC on every upload) is
        # rejected by some S3-compatible services (R2 has no full-object CRC32, and none on CopyObject).
        # Path-style URLs: every signed link is on S3_ENDPOINT_URL's host, the one origin the site's CSP allows
        # (Caddyfile, MEDIA_ORIGIN).
        self.client = boto3.client(
            "s3", endpoint_url=s.s3_endpoint_url or None, region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key_id, aws_secret_access_key=s.s3_secret_access_key,
            config=Config(signature_version="s3v4", request_checksum_calculation="when_required",
                          response_checksum_validation="when_required", s3={"addressing_style": "path"}))

    def put(self, key: str, src: Path) -> None:
        # upload_file switches to multipart above 8 MiB with equal-size parts, which R2 requires.
        # Content-Disposition is stored too: R2 documents it on PutObject, not the response-* override in url().
        self.client.upload_file(str(src), self.bucket, key, ExtraArgs=object_headers(key))

    def fetch(self, key: str, dest: Path) -> None:
        self.client.download_file(self.bucket, key, str(dest))

    def size(self, key: str) -> int | None:
        """Bytes stored under key, or None if there is no such object."""
        from botocore.exceptions import ClientError
        try:
            return int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def url(self, key: str) -> str:
        # attachment: the site's Download link is cross-origin, where the browser ignores <a download>.
        # <video> and <img> ignore this header, so previews still play from the same URL.
        # Also asked for per URL, so objects stored before put() set the header download the same way.
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key,
                                  "ResponseContentDisposition": object_headers(key)["ContentDisposition"]},
            ExpiresIn=min(get_settings().signed_url_ttl_sec, MAX_SIGNED_URL_SEC))

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def keys(self, prefix: str) -> list[str]:
        check_prefix(prefix)
        pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
        return [o["Key"] for page in pages for o in page.get("Contents", [])]

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under prefix, 1000 keys per DeleteObjects call; returns how many.
        Raises if the bucket refused any key (DeleteObjects reports those in the body, not the status)."""
        found = self.keys(prefix)
        for i in range(0, len(found), DELETE_BATCH):
            batch = [{"Key": k} for k in found[i:i + DELETE_BATCH]]
            r = self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch, "Quiet": True})
            if r.get("Errors"):
                e = r["Errors"][0]
                raise RuntimeError(f"{len(r['Errors'])} objects under {prefix} not deleted, "
                                   f"first {e.get('Key')}: {e.get('Code')} {e.get('Message')}")
        return len(found)

    # Direct uploads (app/routes_direct_upload.py): the browser PUTs parts to signed URLs; the api starts,
    # checks and completes the multipart upload.
    def start_multipart(self, key: str) -> str:
        return self.client.create_multipart_upload(Bucket=self.bucket, Key=key, **object_headers(key))["UploadId"]

    def part_url(self, key: str, upload_id: str, part_number: int, size: int, ttl_sec: int) -> str:
        """Signed PUT for one part. Content-Length is signed: a body of any other size is refused by the bucket."""
        return self.client.generate_presigned_url(
            "upload_part", Params={"Bucket": self.bucket, "Key": key, "UploadId": upload_id,
                                   "PartNumber": part_number, "ContentLength": size},
            ExpiresIn=min(ttl_sec, MAX_SIGNED_URL_SEC))

    def parts(self, key: str, upload_id: str) -> dict[int, tuple[int, str]]:
        """Uploaded parts: part number -> (bytes, ETag). LookupError once the upload is completed or aborted."""
        with upload_gone():
            pages = self.client.get_paginator("list_parts").paginate(Bucket=self.bucket, Key=key, UploadId=upload_id)
            return {p["PartNumber"]: (p["Size"], p["ETag"]) for page in pages for p in page.get("Parts", [])}

    def complete_multipart(self, key: str, upload_id: str, etags: dict[int, str]) -> None:
        with upload_gone():
            self.client.complete_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=upload_id,
                MultipartUpload={"Parts": [{"PartNumber": n, "ETag": etags[n]} for n in sorted(etags)]})

    def abort_multipart(self, key: str, upload_id: str) -> None:
        """Discard the parts; nothing to do if the upload is already completed or aborted."""
        try:
            with upload_gone():
                self.client.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
        except LookupError:
            pass


@contextmanager
def upload_gone():
    """A multipart upload the bucket no longer knows (completed, aborted, expired) as LookupError."""
    from botocore.exceptions import ClientError
    try:
        yield
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchUpload", "404"):
            raise LookupError("no such multipart upload") from None
        raise


def object_headers(key: str) -> dict:
    """Content-Type from the extension, and attachment with the file's name (see S3Storage.url)."""
    name = Path(key).name.replace('"', "")
    return {"ContentType": mimetypes.guess_type(key)[0] or "application/octet-stream",
            "ContentDisposition": f'attachment; filename="{name}"'}


def transcript_key(upload_id: str) -> str:
    return f"transcripts/{upload_id}.json"


def vindex_key(upload_id: str) -> str:
    return f"index/{upload_id}.npz"


@lru_cache
def get_storage():
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(s.storage_dir)
