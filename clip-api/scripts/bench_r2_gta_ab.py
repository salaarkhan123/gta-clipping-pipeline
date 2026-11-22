#!/usr/bin/env python3
"""Fetch the private GTA 2h R2 bench object (SigV4) and run controlled before/after timings.

Credentials come **only** from the environment — never argv, never files committed to git:

    R2_ENDPOINT_URL   https://<account_id>.r2.cloudflarestorage.com
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_BUCKET         default: clutchclips-benchmarks
    R2_OBJECT_KEY     default: GTA_Benchmark_2Hours.mkv

Optional aliases: S3_ENDPOINT_URL / S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY / S3_BUCKET
(same values; do **not** point a media-scoped token at this bucket and expect it to work).

Subcommands:
  check   HEAD the object (size + exists). No download.
  fetch   download to --out (skips if size already matches).
  probe   ffprobe duration / codecs / resolution / fps (needs local file).
  run     one local run_pipeline pass; writes JSONL metrics.
  ab      check+fetch+probe, then run on --before-tree and --after-tree with identical options.

Defaults keep RENDER_WORKERS=1 and experimental weights at 0. Exit 0 = ok, 1 = run failed,
2 = bad input / missing credentials / access denied, 3 = probe tools missing.

Never prints secret values. Never enables public bucket access.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_BUCKET = "clutchclips-benchmarks"
DEFAULT_KEY = "GTA_Benchmark_2Hours.mkv"


def _env(*names: str, default: str = "") -> str:
    for name in names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return default


def creds() -> dict:
    endpoint = _env("R2_ENDPOINT_URL", "S3_ENDPOINT_URL")
    key_id = _env("R2_ACCESS_KEY_ID", "S3_ACCESS_KEY_ID")
    secret = _env("R2_SECRET_ACCESS_KEY", "S3_SECRET_ACCESS_KEY")
    bucket = _env("R2_BUCKET", "S3_BUCKET", default=DEFAULT_BUCKET)
    object_key = _env("R2_OBJECT_KEY", default=DEFAULT_KEY)
    missing = [n for n, v in (("R2_ENDPOINT_URL|S3_ENDPOINT_URL", endpoint),
                              ("R2_ACCESS_KEY_ID|S3_ACCESS_KEY_ID", key_id),
                              ("R2_SECRET_ACCESS_KEY|S3_SECRET_ACCESS_KEY", secret)) if not v]
    return {"endpoint": endpoint, "key_id": key_id, "secret": secret, "bucket": bucket,
            "object_key": object_key, "missing": missing}


def client(c: dict):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=c["endpoint"], region_name=_env("R2_REGION", "S3_REGION", default="auto"),
        aws_access_key_id=c["key_id"], aws_secret_access_key=c["secret"],
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required"))


def peak_rss_mb() -> float:
    peak = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def cmd_check(args: argparse.Namespace) -> int:
    c = creds()
    if c["missing"]:
        print(json.dumps({"ok": False, "error": "missing_credentials", "missing": c["missing"],
                          "bucket": c["bucket"], "key": c["object_key"],
                          "note": "Scoped Object Read token for clutchclips-benchmarks only. "
                                  "Do not reuse a clutchclips-media-only token."}))
        return 2
    try:
        head = client(c).head_object(Bucket=c["bucket"], Key=c["object_key"])
    except Exception as e:
        # Never include request headers / signed URLs that could leak credentials.
        err = getattr(e, "response", {}).get("Error", {}) if hasattr(e, "response") else {}
        print(json.dumps({"ok": False, "error": "access_denied_or_missing",
                          "code": err.get("Code") or type(e).__name__,
                          "bucket": c["bucket"], "key": c["object_key"],
                          "message": str(e)[:200]}))
        return 2
    size = int(head.get("ContentLength") or 0)
    print(json.dumps({"ok": True, "bucket": c["bucket"], "key": c["object_key"], "size_bytes": size,
                      "size_gb": round(size / (1024 ** 3), 3),
                      "etag": head.get("ETag", "").strip('"'),
                      "content_type": head.get("ContentType"),
                      "last_modified": head.get("LastModified").isoformat() if head.get("LastModified") else None,
                      "public_access": "private_via_sigv4_only"}))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    c = creds()
    if c["missing"]:
        print(json.dumps({"ok": False, "error": "missing_credentials", "missing": c["missing"]}))
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cl = client(c)
    try:
        head = cl.head_object(Bucket=c["bucket"], Key=c["object_key"])
    except Exception as e:
        print(json.dumps({"ok": False, "error": "access_denied_or_missing", "message": str(e)[:200]}))
        return 2
    size = int(head["ContentLength"])
    if out.is_file() and out.stat().st_size == size and not args.force:
        print(json.dumps({"ok": True, "action": "skipped_existing", "path": str(out), "size_bytes": size}))
        return 0
    t0 = time.perf_counter()
    cl.download_file(c["bucket"], c["object_key"], str(out))
    wall = round(time.perf_counter() - t0, 1)
    got = out.stat().st_size
    print(json.dumps({"ok": got == size, "action": "downloaded", "path": str(out),
                      "size_bytes": got, "expected_bytes": size, "wall_seconds": wall}))
    return 0 if got == size else 1


def ffprobe(path: Path) -> dict:
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ], text=True)
    data = json.loads(raw)
    video = next((s for s in data.get("streams") or [] if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams") or [] if s.get("codec_type") == "audio"), {})
    fps = None
    for key in ("avg_frame_rate", "r_frame_rate"):
        rate = video.get(key) or ""
        if rate and rate != "0/0" and "/" in rate:
            num, den = rate.split("/", 1)
            if float(den):
                fps = round(float(num) / float(den), 3)
                break
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "duration_sec": float(data.get("format", {}).get("duration") or 0),
        "format_name": data.get("format", {}).get("format_name"),
        "video_codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": fps,
        "pix_fmt": video.get("pix_fmt"),
        "audio_codec": audio.get("codec_name"),
        "audio_channels": audio.get("channels"),
        "bit_rate": int(data.get("format", {}).get("bit_rate") or 0) or None,
    }


def cmd_probe(args: argparse.Namespace) -> int:
    path = Path(args.video)
    if not path.is_file():
        print(json.dumps({"ok": False, "error": "missing_file", "path": str(path)}))
        return 2
    try:
        meta = ffprobe(path)
    except FileNotFoundError:
        print(json.dumps({"ok": False, "error": "ffprobe_missing"}))
        return 3
    except subprocess.CalledProcessError as e:
        print(json.dumps({"ok": False, "error": "ffprobe_failed", "message": str(e)[:200]}))
        return 1
    print(json.dumps({"ok": True, "label": "measured", **meta}))
    return 0


def _highlight_sec(stages: dict) -> float:
    """Sum of stages that select / score moments before encode (not ASR, not render)."""
    keys = ("chat_motion", "audio_signal", "scene", "sound_events", "hud_ocr", "standby",
            "llm_pass", "judge_frames", "judge_ai", "moment_scene", "dead_air", "facecam_detect")
    return round(sum(float(stages.get(k) or 0.0) for k in keys), 2)


def _asr_sec(stages: dict) -> float:
    return round(sum(float(stages.get(k) or 0.0) for k in (
        "transcribe_rough", "transcribe_final", "transcribe_whole", "audio")), 2)


def run_once(video: Path, out_json: Path, *, max_clips: int, clip_length: int, render: str,
             chat_region: str, chat_motion_sample: str | None, render_workers: int,
             transcriber_mode: str, label: str, sha: str) -> dict:
    from app.config import get_settings
    from app.pipeline import PipelineError, PipelineOptions, Timer, probe, run_pipeline
    from app.pipeline.transcribe import FasterWhisperTranscriber

    # Hard safety: never raise workers above 1 unless caller explicitly set env already measured.
    os.environ.setdefault("RENDER_WORKERS", "1")
    settings = get_settings()
    model = settings.whisper_model
    transcriber = None
    if transcriber_mode == "whisper" and model.lower() != "none":
        transcriber = FasterWhisperTranscriber(model)

    duration = probe(video).duration
    timer = Timer()
    failure = None
    clips = []
    first_clip = None
    t0 = time.perf_counter()
    try:
        opts_kwargs = dict(
            chat_region=chat_region, max_clips=max_clips, clip_length=clip_length,
            facecam_region="auto", render=render,
        )
        names = getattr(PipelineOptions, "model_fields", None) or getattr(PipelineOptions, "__fields__", {})
        if chat_motion_sample and "chat_motion_sample" in names:
            opts_kwargs["chat_motion_sample"] = chat_motion_sample or None
        opts = PipelineOptions(**opts_kwargs)
        if hasattr(opts, "render_workers"):
            opts.render_workers = int(render_workers)
        with tempfile.TemporaryDirectory(prefix=f"gta-ab-{label}-") as tmp:
            def on_clip(r):
                nonlocal first_clip
                if first_clip is None:
                    first_clip = time.perf_counter() - t0

            clips = run_pipeline(video, opts, Path(tmp), transcriber=transcriber, timer=timer, on_clip=on_clip)
    except PipelineError as e:
        failure = {"type": "PipelineError", "code": getattr(e, "code", None), "message": str(e)[:300]}
    except Exception as e:
        failure = {"type": type(e).__name__, "message": str(e)[:300], "trace": traceback.format_exc()[-800:]}
    wall = time.perf_counter() - t0
    stages = (timer.as_dict() or {}).get("stages") or {}
    counts = (timer.as_dict() or {}).get("counts") or {}
    result = {
        "ok": failure is None,
        "label": "measured",
        "arm": label,
        "git_sha": sha,
        "video": str(video),
        "source_sec": round(duration, 1),
        "settings": {
            "max_clips": max_clips, "clip_length": clip_length, "render": render,
            "chat_region": chat_region, "chat_motion_sample": chat_motion_sample,
            "render_workers": render_workers, "transcriber": transcriber_mode,
            "whisper_model": model, "yamnet_hud_weights": 0.0,
        },
        "wall_seconds": round(wall, 2),
        "first_clip_sec": None if first_clip is None else round(first_clip, 2),
        "transcription_sec": _asr_sec(stages),
        "highlight_detection_sec": _highlight_sec(stages),
        "rendering_sec": round(float(stages.get("render") or 0.0) + float(stages.get("thumbnail") or 0.0), 2),
        "peak_rss_mb": peak_rss_mb(),
        "clips": len(clips),
        "stages": stages,
        "counts": counts,
        "failure": failure,
        "host": {
            "nproc": os.cpu_count(),
            "content": "gaming",
            "claim_2h_north_star": "measured" if duration >= 7000 else "partial_source",
        },
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result) + "\n")
    print(json.dumps({k: result[k] for k in (
        "ok", "arm", "git_sha", "wall_seconds", "first_clip_sec", "transcription_sec",
        "highlight_detection_sec", "rendering_sec", "peak_rss_mb", "clips", "failure")}))
    return result


def cmd_run(args: argparse.Namespace) -> int:
    video = Path(args.video)
    if not video.is_file():
        print(json.dumps({"ok": False, "error": "missing_file", "path": str(video)}))
        return 2
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    result = run_once(
        video, Path(args.out), max_clips=args.max_clips, clip_length=args.clip_length,
        render=args.render, chat_region=args.chat_region, chat_motion_sample=args.chat_motion_sample,
        render_workers=args.render_workers, transcriber_mode=args.transcriber,
        label=args.label, sha=sha)
    return 0 if result["ok"] else 1


def cmd_ab(args: argparse.Namespace) -> int:
    """Fetch once, then instruct identical runs. Actual tree switches are done by the caller via
    --before-tree / --after-tree Python paths, or by invoking `run` twice from a shell recipe."""
    c = creds()
    status = {"phase": "access", "credentials_present": not bool(c["missing"]), "missing": c["missing"]}
    if c["missing"]:
        print(json.dumps({"ok": False, "error": "missing_credentials", **status,
                          "unlock": "Create an R2 API token with Object Read on bucket "
                                    "clutchclips-benchmarks only; set R2_ENDPOINT_URL, "
                                    "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY in the bench env "
                                    "(Cursor dashboard / cloud-agent environment). "
                                    "Do not paste secrets into chat."}))
        return 2
    rc = cmd_check(args)
    if rc != 0:
        return rc
    out_video = Path(args.out)
    args.force = False
    rc = cmd_fetch(args)
    if rc != 0:
        return rc
    args.video = out_video
    rc = cmd_probe(args)
    if rc != 0:
        return rc
    recipe = {
        "ok": True,
        "label": "recipe",
        "video": str(out_video),
        "identical_settings": {
            "max_clips": args.max_clips, "clip_length": args.clip_length, "render": args.render,
            "chat_region": args.chat_region, "chat_motion_sample": args.chat_motion_sample,
            "render_workers": 1, "transcriber": args.transcriber,
            "WORKER_CONCURRENCY": 1, "YAMNet_HUD_weights": 0.0, "NVENC": "off",
        },
        "commands": [
            f"python scripts/bench_r2_gta_ab.py run {out_video} --label before "
            f"--out {args.results_dir}/before.jsonl --max-clips {args.max_clips} "
            f"--clip-length {args.clip_length} --render {args.render} "
            f"--chat-region {args.chat_region} --render-workers 1 "
            f"--transcriber {args.transcriber}"
            + (f" --chat-motion-sample {args.chat_motion_sample}" if args.chat_motion_sample else ""),
            f"python scripts/bench_r2_gta_ab.py run {out_video} --label after "
            f"--out {args.results_dir}/after.jsonl --max-clips {args.max_clips} "
            f"--clip-length {args.clip_length} --render {args.render} "
            f"--chat-region {args.chat_region} --render-workers 1 "
            f"--transcriber {args.transcriber}"
            + (f" --chat-motion-sample {args.chat_motion_sample}" if args.chat_motion_sample else ""),
            f"python scripts/job_timings.py {args.results_dir}/after.job.json "
            f"--baseline {args.results_dir}/before.job.json --md",
        ],
        "note": "Run `before` on origin/main (or prod SHA) worktree and `after` on the perf tip "
                "with the same machine, same env, RENDER_WORKERS=1. Do not invent numbers.",
    }
    Path(args.results_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.results_dir) / "recipe.json").write_text(json.dumps(recipe, indent=2) + "\n")
    print(json.dumps(recipe))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="HEAD object with SigV4")
    p_check.set_defaults(func=cmd_check)

    p_fetch = sub.add_parser("fetch", help="download private object")
    p_fetch.add_argument("--out", type=Path, default=Path("/tmp/clutchclips-bench/GTA_Benchmark_2Hours.mkv"))
    p_fetch.add_argument("--force", action="store_true")
    p_fetch.set_defaults(func=cmd_fetch)

    p_probe = sub.add_parser("probe", help="ffprobe local file")
    p_probe.add_argument("video", type=Path, nargs="?", default=Path("/tmp/clutchclips-bench/GTA_Benchmark_2Hours.mkv"))
    p_probe.set_defaults(func=cmd_probe)

    def add_run_flags(p):
        p.add_argument("--max-clips", type=int, default=40)
        p.add_argument("--clip-length", type=int, default=30)
        p.add_argument("--render", default="preview", choices=["preview", "full", "none"])
        p.add_argument("--chat-region", default="none")
        p.add_argument("--chat-motion-sample", default="",
                       choices=["", "dense", "sparse", "coarse", "lite"],
                       help="empty = omit (main) or pipeline default (dense on perf tip)")
        p.add_argument("--render-workers", type=int, default=1)
        p.add_argument("--transcriber", default="whisper", choices=["whisper", "none"])

    p_run = sub.add_parser("run", help="one controlled local pipeline pass")
    p_run.add_argument("video", type=Path)
    p_run.add_argument("--out", type=Path, required=True)
    p_run.add_argument("--label", default="run")
    add_run_flags(p_run)
    p_run.set_defaults(func=cmd_run)

    p_ab = sub.add_parser("ab", help="check+fetch+probe and write identical A/B recipe")
    p_ab.add_argument("--out", type=Path, default=Path("/tmp/clutchclips-bench/GTA_Benchmark_2Hours.mkv"))
    p_ab.add_argument("--results-dir", type=Path, default=Path("/tmp/clutchclips-bench/results"))
    add_run_flags(p_ab)
    p_ab.set_defaults(func=cmd_ab)

    args = ap.parse_args(argv)
    if getattr(args, "render_workers", 1) != 1:
        print(json.dumps({"ok": False, "error": "render_workers_must_be_1",
                          "note": "8GB prod OOM history; raise only after measured soak on a larger host."}),
              file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
