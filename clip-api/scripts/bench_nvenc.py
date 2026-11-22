#!/usr/bin/env python3
"""A/B encode bench: libx264 vs h264_nvenc on identical clip windows (S5 / #99).

Usage:
  python scripts/bench_nvenc.py                     # lavfi synthetic source
  python scripts/bench_nvenc.py path/to/clip.mp4    # real file (first --seconds)
  python scripts/bench_nvenc.py --nvdec-probe       # also probe NVDEC (optional)
  python scripts/bench_nvenc.py --whisper-probe     # also probe CUDA Whisper (optional)

On CPU-only hosts the JSON status is exactly `skipped: no NVENC` and exit code is 0.
Never fabricates GPU timings: when NVENC is unavailable the nvenc field is null.
Does not change production defaults; does not provision cloud GPUs.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.ff import SAFE_IN  # noqa: E402
from app.pipeline.gpu import (  # noqa: E402
    FFMPEG,
    SKIPPED_NO_NVENC,
    cuda_whisper_available,
    probe_nvdec,
    probe_nvenc,
    video_codec_and_encode,
)


def _run(cmd: list[str], timeout: float) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip() or f"exit {res.returncode}"
        raise RuntimeError(err)


def make_synthetic(dest: Path, seconds: float, timeout: float = 60.0) -> None:
    _run([
        FFMPEG, "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(dest),
    ], timeout=timeout)


def time_encode(src: Path, dest: Path, encoder: str, preview: bool, seconds: float,
                timeout: float = 120.0) -> dict:
    codec, flags = video_codec_and_encode(encoder, preview=preview)
    cmd = [
        FFMPEG, "-loglevel", "error", "-y",
        "-ss", "0", "-t", f"{seconds:.3f}",
        *SAFE_IN, "-i", str(src),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
        "-c:v", codec, *flags, "-pix_fmt", "yuv420p",
        "-an", "-movflags", "+faststart", str(dest),
    ]
    start = time.perf_counter()
    _run(cmd, timeout=timeout)
    wall = time.perf_counter() - start
    size = dest.stat().st_size if dest.is_file() else 0
    return {
        "encoder": codec,
        "preview": preview,
        "wall_seconds": round(wall, 3),
        "bytes": size,
        "seconds_encoded": seconds,
    }


def benchmark(src: Path | None, seconds: float, preview: bool, runs: int,
              nvdec_probe: bool, whisper_probe: bool) -> dict:
    nvenc_ok, nvenc_detail = probe_nvenc()
    report: dict = {
        "status": "ok" if nvenc_ok else SKIPPED_NO_NVENC,
        "source_seconds": seconds,
        "preview": preview,
        "runs": runs,
        "libx264": None,
        "nvenc": None,
        "nvdec": None,
        "cuda_whisper": None,
    }
    with tempfile.TemporaryDirectory(prefix="bench_nvenc_") as tmp:
        root = Path(tmp)
        video = root / "src.mp4"
        if src is None:
            make_synthetic(video, max(seconds, 1.0))
        else:
            _run([
                FFMPEG, "-loglevel", "error", "-y",
                "-ss", "0", "-t", f"{seconds:.3f}",
                *SAFE_IN, "-i", str(src),
                "-c", "copy", str(video),
            ], timeout=120.0)

        x264_times = []
        for i in range(runs):
            out = root / f"x264_{i}.mp4"
            x264_times.append(time_encode(video, out, "libx264", preview, seconds))
        report["libx264"] = {
            "runs": x264_times,
            "wall_seconds_mean": round(sum(r["wall_seconds"] for r in x264_times) / len(x264_times), 3),
        }

        if nvenc_ok:
            nv_times = []
            for i in range(runs):
                out = root / f"nvenc_{i}.mp4"
                nv_times.append(time_encode(video, out, "h264_nvenc", preview, seconds))
            mean = sum(r["wall_seconds"] for r in nv_times) / len(nv_times)
            report["nvenc"] = {
                "runs": nv_times,
                "wall_seconds_mean": round(mean, 3),
            }
            x_mean = report["libx264"]["wall_seconds_mean"]
            report["speedup_x264_over_nvenc"] = round(x_mean / mean, 3) if mean > 0 else None
        else:
            report["nvenc"] = None
            report["probe_detail"] = nvenc_detail

        if nvdec_probe:
            ok, detail = probe_nvdec()
            report["nvdec"] = {"ok": ok, "detail": detail}
        if whisper_probe:
            ok, detail = cuda_whisper_available()
            report["cuda_whisper"] = {"ok": ok, "detail": detail}
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", nargs="?", type=Path, default=None,
                    help="optional source video; lavfi synthetic when omitted")
    ap.add_argument("--seconds", type=float, default=3.0, help="window length to encode")
    ap.add_argument("--runs", type=int, default=1, help="repeats per encoder")
    ap.add_argument("--preview", action="store_true", help="use preview encode presets")
    ap.add_argument("--nvdec-probe", action="store_true", help="also probe NVDEC / CUDA hwaccel")
    ap.add_argument("--whisper-probe", action="store_true", help="also probe CUDA Whisper stack")
    args = ap.parse_args(argv)
    if args.video is not None and not args.video.is_file():
        print(f"not a file: {args.video}", file=sys.stderr)
        return 2
    try:
        report = benchmark(args.video, args.seconds, args.preview, max(1, args.runs),
                           args.nvdec_probe, args.whisper_probe)
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        return 1
    print(json.dumps(report))
    # Skip and success both exit 0 so CI / CPU hosts stay green.
    return 0


if __name__ == "__main__":
    sys.exit(main())
