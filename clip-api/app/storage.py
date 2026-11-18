"""Object storage behind one interface: local disk (dev/tests) or S3-compatible (DigitalOcean Spaces, R2)."""
import mimetypes
import shutil
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from .config import get_settings
from .security import make_token


def _checked_prefix(prefix: str) -> str:
    """A prefix inside one top-level folder (`clips/<job>/`, `transcripts/<upload>`): never a whole folder, never
    the whole store, so a missing id cannot turn a delete into a wipe."""
    top, _, rest = prefix.partition("/")
    if not top or not rest or rest.startswith("/") or ".." in prefix.split("/") or prefix.startswith("/"):
        raise ValueError(f"bad storage prefix: {prefix!r}")
    return prefix


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
        """Every stored key that starts with `prefix`, sorted."""
        root = self.root.resolve()
        folder = (root / prefix.rpartition("/")[0]).resolve()
        if folder != root and root not in folder.parents:
            raise ValueError("bad storage prefix")
        if not folder.is_dir():
            return []
        found = (p.relative_to(root).as_posix() for p in folder.rglob("*") if p.is_file())
        return sorted(k for k in found if k.startswith(prefix))

    def delete_prefix(self, prefix: str) -> int:
        """Delete every key under `prefix` (see _checked_prefix). Returns how many were deleted."""
        keys = self.keys(_checked_prefix(prefix))
        for key in keys:
            self.delete(key)
        for key in keys:                       # empty folders left behind
            folder = self.path(key).parent
            while folder != self.root.resolve() and folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
                folder = folder.parent
        return len(keys)


class S3Storage:
    """Private bucket; downloads are presigned URLs straight from the bucket (no bytes through the api)."""

    def __init__(self):
        import boto3
        from botocore.config import Config
        s = get_settings()
        self.bucket = s.s3_bucket
        # Checksums only when the API requires them: boto3's newer default (a CRC on every upload) is
        # rejected by some S3-compatible services.
        self.client = boto3.client(
            "s3", endpoint_url=s.s3_endpoint_url or None, region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key_id, aws_secret_access_key=s.s3_secret_access_key,
            config=Config(signature_version="s3v4", request_checksum_calculation="when_required",
                          response_checksum_validation="when_required"))

    def put(self, key: str, src: Path) -> None:
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        self.client.upload_file(str(src), self.bucket, key, ExtraArgs={"ContentType": content_type})

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
        name = Path(key).name.replace('"', "")
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key,
                                  "ResponseContentDisposition": f'attachment; filename="{name}"'},
            ExpiresIn=get_settings().signed_url_ttl_sec)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def keys(self, prefix: str) -> list[str]:
        """Every stored key that starts with `prefix`, sorted (all pages of list_objects_v2)."""
        pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
        return sorted(o["Key"] for page in pages for o in page.get("Contents", []))

    def delete_prefix(self, prefix: str) -> int:
        """Delete every key under `prefix` (see _checked_prefix), one request each: DeleteObjects needs a
        checksum some S3-compatible services refuse. Returns how many were deleted."""
        keys = self.keys(_checked_prefix(prefix))
        for key in keys:
            self.delete(key)
        return len(keys)


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
