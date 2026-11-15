#!/usr/bin/env python3
"""Thin Clip API client (standard library only): upload a video, wait for clips, download them."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def call(method: str, url: str, key: str, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())["error"]
            sys.exit(f"Error {e.code} {err['code']}: {err['message']}")
        except (ValueError, KeyError):
            sys.exit(f"Error {e.code}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video")
    p.add_argument("--clips", type=int, default=3)
    p.add_argument("--length", type=int, default=30)
    p.add_argument("--horizontal", action="store_true")
    p.add_argument("--chat-region", default="none")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--layout", default="auto", choices=["auto", "split", "fill", "classic"])
    p.add_argument("--facecam", default="auto", choices=["auto", "none", "top-left", "top-right", "bottom-left", "bottom-right"],
                   help="where the facecam is in the source; gives the split layout (cam on top, gameplay below)")
    p.add_argument("--out", default="./clips")
    args = p.parse_args()

    key, base = os.environ.get("CLIPAPI_KEY"), os.environ.get("CLIPAPI_URL", "").rstrip("/")
    if not key or not base:
        sys.exit("Set CLIPAPI_KEY and CLIPAPI_URL first.")
    video = Path(args.video)
    if not video.is_file():
        sys.exit(f"No such file: {video}")

    print(f"Uploading {video.name} ({video.stat().st_size / 1e6:.0f} MB)...")
    with open(video, "rb") as fh:   # streamed from disk, not loaded into memory
        up = call("POST", f"{base}/v1/uploads?filename={urllib.parse.quote(video.name)}", key, data=fh,
                  headers={"Content-Type": "application/octet-stream", "Content-Length": str(video.stat().st_size)},
                  timeout=3600)
    print(f"Uploaded: {up['duration_sec'] / 60:.1f} min, needs {up['credits_required']} credits.")

    body = {"upload_id": up["upload_id"], "options": {
        "max_clips": args.clips, "clip_length": args.length, "vertical": not args.horizontal,
        "chat_region": args.chat_region, "captions": not args.no_captions,
        "layout": args.layout, "facecam_region": None if args.facecam == "none" else args.facecam}}
    job = call("POST", f"{base}/v1/clips", key, data=json.dumps(body).encode(),
               headers={"Content-Type": "application/json", "Idempotency-Key": uuid.uuid4().hex})
    job_id = job["job_id"]
    print(f"Job {job_id} started.")

    while True:
        job = call("GET", f"{base}/v1/jobs/{job_id}", key)
        if job["status"] in ("SUCCEEDED", "FAILED", "CANCELED"):
            break
        print(f"  {job['status']} {job.get('stage') or ''} {job['progress']}%")
        time.sleep(5)

    if job["status"] != "SUCCEEDED":
        err = job.get("error") or {}
        sys.exit(f"Job {job['status']}: {err.get('message', 'no details')} (credits refunded)")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for clip in job["clips"]:
        dest = out / f"clip-{clip['index']}-{int(clip['start_sec'])}s.mp4"
        urllib.request.urlretrieve(clip["video_url"], dest)
        why = ", ".join(f"{k} {v:.0%}" for k, v in clip["signals"].items())
        print(f"Saved {dest}  [{clip['start_sec']:.0f}s-{clip['end_sec']:.0f}s, score {clip['score']:.2f}; {why}]")
    print(f"Done. Credits charged: {job['credits_charged']}")


if __name__ == "__main__":
    main()
