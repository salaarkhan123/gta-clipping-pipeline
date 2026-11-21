"""GPU encode/decode and CUDA Whisper plug-in points (S5 / #99).

Production defaults stay CPU: libx264 encode, software decode, faster-whisper on
`device="cpu"` / `compute_type="int8"`. These helpers exist so a future owner-OK
change can flip Settings flags without hunting call sites. Nothing here turns GPU
on by itself; the bench harness is the only caller that probes hardware today.

NVENC quality knobs are not CRF. Do not invent timings — run scripts/bench_nvenc.py
on an owner-provisioned GPU host.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .ff import SAFE_IN

# Exact status string the A/B harness prints on CPU-only hosts (tests assert this).
SKIPPED_NO_NVENC = "skipped: no NVENC"
SKIPPED_NO_NVDEC = "skipped: no NVDEC"
SKIPPED_NO_CUDA_WHISPER = "skipped: no CUDA Whisper"

# Mirror render.FULL_ENCODE / PREVIEW_ENCODE so this module never imports render
# (avoids a cycle when render later calls video_codec_and_encode).
CPU_FULL_ENCODE = ["-preset", "veryfast", "-crf", "20"]
CPU_PREVIEW_ENCODE = ["-preset", "ultrafast", "-crf", "30"]

# NVENC does not take -crf. These are a starting point for A/B only, not a quality claim.
NVENC_FULL = ["-preset", "p4", "-b:v", "5M", "-maxrate", "8M", "-bufsize", "10M"]
NVENC_PREVIEW = ["-preset", "p1", "-b:v", "2M", "-maxrate", "3M", "-bufsize", "4M"]

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def ffmpeg_lists_encoder(name: str = "h264_nvenc") -> bool:
    """True when this ffmpeg binary names the encoder (driver may still be missing)."""
    try:
        res = subprocess.run(
            [FFMPEG, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return name in (res.stdout or "")


def ffmpeg_lists_hwaccel(name: str = "cuda") -> bool:
    try:
        res = subprocess.run(
            [FFMPEG, "-hide_banner", "-hwaccels"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(line.strip() == name for line in (res.stdout or "").splitlines())


def probe_nvenc(timeout: float = 20.0) -> tuple[bool, str]:
    """Try a 0.2 s lavfi → h264_nvenc encode. Returns (ok, detail).

    On hosts without a loadable CUDA driver the detail is SKIPPED_NO_NVENC.
    """
    if not ffmpeg_lists_encoder("h264_nvenc"):
        return False, SKIPPED_NO_NVENC
    with tempfile.TemporaryDirectory(prefix="nvenc_probe_") as tmp:
        out = Path(tmp) / "probe.mp4"
        cmd = [
            FFMPEG, "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
            "-t", "0.2",
            "-c:v", "h264_nvenc", "-preset", "p1", "-b:v", "1M",
            str(out),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False, SKIPPED_NO_NVENC
        if res.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            return True, "ok"
        return False, SKIPPED_NO_NVENC


def probe_nvdec(timeout: float = 20.0) -> tuple[bool, str]:
    """Smoke-test CUDA hwaccel decode. Not wired into render_clip (CPU filters need frames)."""
    if not ffmpeg_lists_hwaccel("cuda"):
        return False, SKIPPED_NO_NVDEC
    ok, _ = probe_nvenc(timeout=timeout)
    if not ok:
        return False, SKIPPED_NO_NVDEC
    with tempfile.TemporaryDirectory(prefix="nvdec_probe_") as tmp:
        src = Path(tmp) / "src.mp4"
        make = [
            FFMPEG, "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
            "-t", "0.3", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(src),
        ]
        subprocess.run(make, capture_output=True, text=True, timeout=timeout, check=False)
        cmd = [
            FFMPEG, "-loglevel", "error", "-y",
            "-hwaccel", "cuda", *SAFE_IN, "-i", str(src),
            "-f", "null", "-",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False, SKIPPED_NO_NVDEC
        if res.returncode == 0:
            return True, "ok"
        return False, SKIPPED_NO_NVDEC


def video_codec_and_encode(encoder: str, preview: bool) -> tuple[str, list[str]]:
    """Return (-c:v value, trailing encode flags) for the requested encoder name.

    Default and unknown values resolve to libx264 with the existing PREVIEW/FULL presets.
    """
    name = (encoder or "libx264").strip().lower()
    if name == "h264_nvenc":
        return "h264_nvenc", list(NVENC_PREVIEW if preview else NVENC_FULL)
    return "libx264", list(CPU_PREVIEW_ENCODE if preview else CPU_FULL_ENCODE)


def nvdec_input_args(enabled: bool) -> list[str]:
    """Optional `-hwaccel cuda` prefix for an ffmpeg input. Empty when disabled.

    Plug-in point only: production render_clip still omits these because crop/boxblur/ass
    need CPU frames (hwdownload would sit on the critical path). Enable only after a
    measured bench on the real filter graph.
    """
    return ["-hwaccel", "cuda"] if enabled else []


def whisper_model_kwargs(device: str = "cpu") -> dict:
    """Kwargs for `faster_whisper.WhisperModel(...)`.

    CPU (default): device=cpu, compute_type=int8 — today's production path.
    CUDA: device=cuda, compute_type=float16 — stub for an owner-OK GPU worker; not
    selected unless Settings.whisper_device is flipped and a CUDA torch/ctranslate2
    stack is installed on that host.
    """
    name = (device or "cpu").strip().lower()
    if name == "cuda":
        return {"device": "cuda", "compute_type": "float16"}
    return {"device": "cpu", "compute_type": "int8"}


def cuda_whisper_available() -> tuple[bool, str]:
    """Best-effort check that a CUDA Whisper stack could load. Does not download models."""
    try:
        import ctranslate2  # type: ignore
    except ImportError:
        return False, SKIPPED_NO_CUDA_WHISPER
    try:
        n = int(ctranslate2.get_cuda_device_count())  # type: ignore[attr-defined]
    except Exception:
        return False, SKIPPED_NO_CUDA_WHISPER
    if n <= 0:
        return False, SKIPPED_NO_CUDA_WHISPER
    return True, "ok"
