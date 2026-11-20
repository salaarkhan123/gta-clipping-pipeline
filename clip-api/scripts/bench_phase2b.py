#!/usr/bin/env python3
"""Phase 2B performance bench: synthetic stress video + A/B JSON lines.

Reproducible recipe for comparing RC baseline configs (render=preview vs full)
and optional Wave flags when present on the checkout (render_workers, chat_motion_sample).

IMPORTANT
---------
There is usually no real 2h gaming VOD on agent VMs. This harness generates a
**synthetic** lavfi stress clip (testsrc2 + modulated sine). Every result is
labeled ``synthetic`` / ``not gaming``. Any 2h extrapolation is ``inferred``,
never claimed as a measured 2h gaming VOD. GPU / NVENC benches stay pending
when ``nvidia-smi`` is missing.

Usage
-----
  # Generate 10-minute synthetic MP4, then run preview + full (RC baseline):
  python scripts/bench_phase2b.py --generate --minutes 10 --out-dir /tmp/p2b \\
      --configs preview-serial,full-serial --max-clips 8 --transcriber none

  # B1 parallel encode comparison (needs render_workers on this checkout):
  python scripts/bench_phase2b.py --video /tmp/p2b/synthetic_10m.mp4 \\
      --configs preview-w1,preview-w2 --max-clips 8 --transcriber none

  # Dry-run recipe only (no encode, no pipeline):
  python scripts/bench_phase2b.py --dry-run

Each successful run prints one JSON object per line (and appends to --jsonl).
Exit 0 = all configs ok, 1 = a pipeline failed, 2 = bad input / missing feature.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import fields
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.pipeline import PipelineError, PipelineOptions, Timer, probe, run_pipeline  # noqa: E402
from app.pipeline.render import CHAT_REGIONS  # noqa: E402
from app.pipeline.transcribe import FasterWhisperTranscriber, Transcriber  # noqa: E402
from app.routes_media import credits_for  # noqa: E402

HARNESS = "bench_phase2b"
NOT_MEASURED = "not measured"
CLAIM_SYNTHETIC = "synthetic"
CLAIM_NOT_GAMING = "not gaming"
CLAIM_INFERRED = "inferred"


# Named recipes the CLI accepts. Features that this checkout lacks are skipped
# with a clear JSON error line rather than inventing numbers.
CONFIGS: dict[str, dict[str, Any]] = {
    "preview-serial": {"render": "preview", "render_workers": 1, "chat_motion_sample": None},
    "full-serial": {"render": "full", "render_workers": 1, "chat_motion_sample": None},
    "preview-w1": {"render": "preview", "render_workers": 1, "chat_motion_sample": None},
    "preview-w2": {"render": "preview", "render_workers": 2, "chat_motion_sample": None},
    "preview-w4": {"render": "preview", "render_workers": 4, "chat_motion_sample": None},
    "preview-chat-dense": {
        "render": "preview", "render_workers": 1, "chat_motion_sample": "dense",
        "chat_region": "top-right",
    },
    "preview-chat-sparse": {
        "render": "preview", "render_workers": 1, "chat_motion_sample": "sparse",
        "chat_region": "top-right",
    },
}


def peak_rss_mb() -> float:
    """Peak RSS of this process or its largest child (ffmpeg), not the sum."""
    peak = max(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def nproc() -> int:
    return os.cpu_count() or 1


def has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None


def option_field_names() -> set[str]:
    return {f.name for f in fields(PipelineOptions)}


def generate_synthetic(path: Path, *, minutes: float, width: int = 1280, height: int = 720,
                       fps: int = 30) -> dict[str, Any]:
    """Write a lavfi stress MP4. Cheap on disk (veryfast + CRF 28), varies audio for peaks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(1.0, float(minutes) * 60.0)
    # testsrc2 changes every frame; sine frequency + amplitude modulate so audio_rms sees peaks.
    video = f"testsrc2=size={width}x{height}:rate={fps}:duration={duration:g}"
    audio = (
        f"sine=frequency=440:sample_rate=44100:duration={duration:g},"
        f"volume='0.2+0.8*(0.5+0.5*sin(2*PI*t/7))':eval=frame"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", video,
        "-f", "lavfi", "-i", audio,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-shortest",
        str(path),
    ]
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True)
    wall = time.perf_counter() - t0
    size_mb = round(path.stat().st_size / (1024 * 1024), 2)
    return {
        "path": str(path),
        "minutes": round(duration / 60.0, 3),
        "width": width,
        "height": height,
        "fps": fps,
        "size_mb": size_mb,
        "generate_wall_sec": round(wall, 2),
        "source": "ffmpeg lavfi testsrc2+sine",
        "label": CLAIM_SYNTHETIC,
        "content": CLAIM_NOT_GAMING,
    }


def infer_2h(wall_seconds: float, source_minutes: float) -> dict[str, Any]:
    """Linear scale wall time to 120 source minutes. Always labeled inferred, never measured."""
    if source_minutes <= 0:
        return {"label": CLAIM_INFERRED, "wall_seconds_2h": None, "note": "no source duration"}
    scale = 120.0 / source_minutes
    return {
        "label": CLAIM_INFERRED,
        "method": "linear_scale_source_minutes",
        "scale_factor": round(scale, 3),
        "wall_seconds_2h": round(wall_seconds * scale, 1),
        "note": "Not a measured 2h gaming VOD. Synthetic stress only; encode/ASR do not scale linearly.",
    }


def build_options(
    *,
    render: str,
    max_clips: int,
    clip_length: int,
    chat_region: str,
    render_workers: int | None,
    chat_motion_sample: str | None,
) -> tuple[PipelineOptions, dict[str, Any]]:
    """Build PipelineOptions, recording which optional Wave flags were applied or skipped."""
    names = option_field_names()
    applied: dict[str, Any] = {"render": render}
    skipped: dict[str, str] = {}
    kwargs: dict[str, Any] = {
        "max_clips": max_clips,
        "clip_length": clip_length,
        "chat_region": chat_region,
        "facecam_region": "auto",
        "render": render,
    }
    if render_workers is not None:
        if "render_workers" in names:
            kwargs["render_workers"] = int(render_workers)
            applied["render_workers"] = int(render_workers)
        else:
            skipped["render_workers"] = "PipelineOptions has no render_workers (B1 not on this checkout)"
    if chat_motion_sample is not None:
        # A3 wires sample via Settings / kwargs into onscreen_chat_motion; options field may vary.
        if "chat_motion_sample" in names:
            kwargs["chat_motion_sample"] = chat_motion_sample
            applied["chat_motion_sample"] = chat_motion_sample
        else:
            skipped["chat_motion_sample"] = (
                "PipelineOptions has no chat_motion_sample (A3 not on this checkout); "
                f"requested={chat_motion_sample}"
            )
    return PipelineOptions(**kwargs), {"applied": applied, "skipped": skipped}


def run_one(
    video: Path,
    *,
    config_name: str,
    cfg: dict[str, Any],
    max_clips: int,
    clip_length: int,
    chat_region: str,
    transcriber: Transcriber | None,
    keep_dir: Path | None,
) -> dict[str, Any]:
    duration = probe(video).duration
    source_minutes = round(duration / 60.0, 3)
    opts, feature_note = build_options(
        render=cfg["render"],
        max_clips=max_clips,
        clip_length=clip_length,
        chat_region=cfg.get("chat_region") or chat_region,
        render_workers=cfg.get("render_workers"),
        chat_motion_sample=cfg.get("chat_motion_sample"),
    )
    # Hard-fail configs that need a missing Wave flag so we never silently compare apples to oranges.
    # render_workers=1 is the serial default; missing field is OK for serial configs.
    if "render_workers" in feature_note["skipped"] and int(cfg.get("render_workers") or 1) > 1:
        return {
            "harness": HARNESS,
            "ok": False,
            "config": config_name,
            "error": feature_note["skipped"]["render_workers"],
            "features": feature_note,
            "label": CLAIM_SYNTHETIC,
            "content": CLAIM_NOT_GAMING,
            "gpu": "pending" if not has_nvidia() else "available",
        }
    if "chat_motion_sample" in feature_note["skipped"] and cfg.get("chat_motion_sample"):
        return {
            "harness": HARNESS,
            "ok": False,
            "config": config_name,
            "error": feature_note["skipped"]["chat_motion_sample"],
            "features": feature_note,
            "label": CLAIM_SYNTHETIC,
            "content": CLAIM_NOT_GAMING,
            "gpu": "pending" if not has_nvidia() else "available",
        }

    timer = Timer()
    first_clip: list[float] = []
    out_ctx: Any
    if keep_dir is not None:
        work = keep_dir / config_name
        work.mkdir(parents=True, exist_ok=True)
        out_ctx = nullcontext(work)
    else:
        out_ctx = tempfile.TemporaryDirectory(prefix=f"p2b_{config_name}_")

    t_begin = time.perf_counter()
    with out_ctx as out:
        out_path = Path(out)

        def on_clip(_clip, started=t_begin, bucket=first_clip):
            if not bucket:
                bucket.append(time.perf_counter() - started)

        clips = run_pipeline(
            video, opts, out_path, transcriber=transcriber, timer=timer, on_clip=on_clip,
        )
        wall = time.perf_counter() - t_begin
        timed = timer.as_dict()
        counts = dict(timed.get("counts") or {})
        first_from_timer = counts.get("first_clip_sec")
        first_sec = first_from_timer if first_from_timer is not None else (
            round(first_clip[0], 3) if first_clip else None
        )
        result = {
            "harness": HARNESS,
            "ok": True,
            "config": config_name,
            "label": CLAIM_SYNTHETIC,
            "content": CLAIM_NOT_GAMING,
            "claim_2h_gaming_vod": NOT_MEASURED,
            "video": str(video),
            "source_minutes": source_minutes,
            "wall_seconds": round(wall, 2),
            "realtime_factor": round(duration / wall, 3) if wall > 0 else None,
            "peak_rss_mb": peak_rss_mb(),
            "clips": len(clips),
            "credits": credits_for(duration),
            "nproc": nproc(),
            "gpu": "pending_no_nvidia_smi" if not has_nvidia() else "nvidia_smi_present",
            "render": cfg["render"],
            "render_workers": feature_note["applied"].get("render_workers", 1),
            "chat_region": opts.chat_region,
            "chat_motion_sample": feature_note["applied"].get("chat_motion_sample"),
            "max_clips": max_clips,
            "clip_length": clip_length,
            "first_clip_sec": first_sec,
            "stages": timed.get("stages") or {},
            "counts": counts,
            "features": feature_note,
            "extrapolate_2h": infer_2h(wall, source_minutes),
        }
    return result


class nullcontext:
    """Minimal stand-in so we need no contextlib import dance on keep_dir paths."""

    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *exc):
        return False


def dry_run_recipe() -> dict[str, Any]:
    return {
        "harness": HARNESS,
        "mode": "dry-run",
        "machine_assumed": {"vcpus": 4, "ram_gi": 15, "gpu": "none / nvidia-smi missing"},
        "primary_length_minutes": 10,
        "configs": list(CONFIGS),
        "labels": {
            "synthetic": CLAIM_SYNTHETIC,
            "content": CLAIM_NOT_GAMING,
            "2h_extrapolation": CLAIM_INFERRED,
            "2h_gaming_vod": NOT_MEASURED,
            "gpu_bench": "pending",
        },
        "recipe": [
            "cd clip-api",
            "python scripts/bench_phase2b.py --generate --minutes 10 --out-dir /tmp/p2b "
            "--configs preview-serial,full-serial --max-clips 8 --transcriber none "
            "--jsonl /tmp/p2b/rc-baseline.jsonl",
            "# On a B1 checkout (render_workers present):",
            "python scripts/bench_phase2b.py --video /tmp/p2b/synthetic_10m.mp4 "
            "--configs preview-w1,preview-w2 --max-clips 8 --transcriber none "
            "--jsonl /tmp/p2b/b1-workers.jsonl",
            "# Optional A3 chat_motion (needs chat_motion_sample on checkout):",
            "python scripts/bench_phase2b.py --video /tmp/p2b/synthetic_10m.mp4 "
            "--configs preview-chat-dense,preview-chat-sparse --max-clips 5 --transcriber none "
            "--jsonl /tmp/p2b/a3-chat.jsonl",
        ],
        "claims": {
            "2h_gaming_vod": NOT_MEASURED,
            "gpu_nvenc": "pending" if not has_nvidia() else "hardware_present",
        },
        "notes": [
            "Do not fabricate timings. Missing features return ok=false JSON lines.",
            "extrapolate_2h is linear and labeled inferred — staging must remeasure on a real VOD.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--generate", action="store_true", help="write synthetic lavfi MP4 under --out-dir")
    ap.add_argument("--minutes", type=float, default=10.0, help="synthetic length (default 10)")
    ap.add_argument("--video", type=Path, help="existing local video (skips --generate)")
    ap.add_argument("--out-dir", type=Path, default=Path("/tmp/phase-2b-bench"))
    ap.add_argument("--keep-renders", action="store_true", help="keep clip files under --out-dir/renders")
    ap.add_argument("--configs", default="preview-serial,full-serial",
                    help="comma-separated keys from CONFIGS")
    ap.add_argument("--max-clips", type=int, default=8)
    ap.add_argument("--clip-length", type=int, default=30)
    ap.add_argument("--chat-region", default="none", choices=["none", *CHAT_REGIONS])
    ap.add_argument("--transcriber", choices=("whisper", "none"), default="none")
    ap.add_argument("--jsonl", type=Path, help="append one JSON object per config")
    args = ap.parse_args(argv)

    if args.dry_run:
        print(json.dumps(dry_run_recipe(), indent=2))
        return 0

    names = [c.strip() for c in args.configs.split(",") if c.strip()]
    unknown = [n for n in names if n not in CONFIGS]
    if unknown:
        print(f"unknown configs: {unknown}; choose from {sorted(CONFIGS)}", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    video = args.video
    meta_path = args.out_dir / "synthetic_meta.json"
    if args.generate or video is None:
        minutes_tag = int(args.minutes) if float(args.minutes).is_integer() else args.minutes
        video = args.out_dir / f"synthetic_{minutes_tag}m.mp4"
        if not video.is_file() or args.generate:
            print(f"# generating synthetic {args.minutes}m → {video}", file=sys.stderr)
            meta = generate_synthetic(video, minutes=args.minutes)
            meta_path.write_text(json.dumps(meta, indent=2) + "\n")
            print(json.dumps({"event": "generated", **meta}))
        else:
            print(f"# reusing {video}", file=sys.stderr)
    if not video.is_file():
        print(f"not a file: {video}", file=sys.stderr)
        return 2

    model = get_settings().whisper_model
    if args.transcriber == "whisper" and model.lower() != "none":
        transcriber: Transcriber | None = FasterWhisperTranscriber(model)
    else:
        transcriber = None

    keep_dir = (args.out_dir / "renders") if args.keep_renders else None
    rc = 0
    for name in names:
        try:
            row = run_one(
                video,
                config_name=name,
                cfg=CONFIGS[name],
                max_clips=args.max_clips,
                clip_length=args.clip_length,
                chat_region=args.chat_region,
                transcriber=transcriber,
                keep_dir=keep_dir,
            )
        except PipelineError as e:
            row = {
                "harness": HARNESS,
                "ok": False,
                "config": name,
                "error": str(e),
                "label": CLAIM_SYNTHETIC,
                "content": CLAIM_NOT_GAMING,
                "gpu": "pending_no_nvidia_smi" if not has_nvidia() else "nvidia_smi_present",
            }
            rc = 1
        if not row.get("ok", False) and "error" in row:
            rc = max(rc, 1 if "PipelineOptions" not in row.get("error", "") else 2)
        line = json.dumps(row, sort_keys=True)
        print(line)
        if args.jsonl:
            args.jsonl.parent.mkdir(parents=True, exist_ok=True)
            with args.jsonl.open("a") as fh:
                fh.write(line + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
