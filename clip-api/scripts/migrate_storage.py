#!/usr/bin/env python3
"""Copy every file from local-disk storage into the S3 bucket (DigitalOcean Spaces), keeping the same keys.

Usage: python scripts/migrate_storage.py [--dry-run]

Reads DATA_DIR/storage and the S3_* settings; STORAGE_BACKEND may still be "local", so files can be copied
before the switch. Safe to run again: a file already in the bucket with the same size is skipped, so a second
run only copies what is new or was interrupted. Nothing local is changed or deleted. Each upload is checked by
size afterwards. Exit 0 = everything is in the bucket, 1 = something failed, 2 = S3 settings missing.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.storage import S3Storage  # noqa: E402


def local_files(root: Path) -> list[tuple[str, Path]]:
    return sorted((p.relative_to(root).as_posix(), p) for p in root.rglob("*") if p.is_file())


def migrate(root: Path, bucket: S3Storage, dry_run: bool = False, out=print) -> dict:
    stats = {"copied": 0, "skipped": 0, "failed": 0, "bytes": 0}
    for key, path in local_files(root):
        size = path.stat().st_size
        try:
            if bucket.size(key) == size:
                stats["skipped"] += 1
                continue
            if dry_run:
                out(f"would copy {key} ({size} bytes)")
            else:
                bucket.put(key, path)
                stored = bucket.size(key)
                if stored != size:
                    raise RuntimeError(f"stored {stored} bytes, expected {size}")
            stats["copied"] += 1
            stats["bytes"] += size
        except Exception as e:  # noqa: BLE001  (keep going: report every file that failed)
            stats["failed"] += 1
            out(f"FAIL {key}: {type(e).__name__}: {e}")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="list what would be copied; copy nothing")
    args = ap.parse_args(argv)
    s = get_settings()
    missing = [n for n in ("s3_endpoint_url", "s3_bucket", "s3_access_key_id", "s3_secret_access_key") if not getattr(s, n)]
    if missing:
        print(f"S3 is not configured. Missing: {', '.join(n.upper() for n in missing)}", file=sys.stderr)
        return 2
    stats = migrate(s.storage_dir, S3Storage(), args.dry_run)
    verb = "would copy" if args.dry_run else "copied"
    print(f"{verb} {stats['copied']} files ({stats['bytes'] / 1e9:.2f} GB), already in the bucket {stats['skipped']}, "
          f"failed {stats['failed']} -> bucket {s.s3_bucket}")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
