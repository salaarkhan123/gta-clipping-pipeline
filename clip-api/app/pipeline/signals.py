"""Per-second highlight signals computed from the uploaded file itself.

Ported from test-tools/auto_clip.py (audio loudness, on-screen chat motion), with a
rolling-baseline z-score added so quiet and loud streams are judged against themselves.
"""
import re
from pathlib import Path

import numpy as np

from .ff import SAFE_IN, Deadline, run

CHAT_LAG = 4  # seconds: chat reacts a few seconds after the moment happens
# How densely the chat band is sampled. dense = historical fps=2 path; sparse = fps=1 (half the frames).
CHAT_MOTION_SAMPLES = ("dense", "sparse")


def _seek(start: float, length: float | None) -> list[str]:
    """ffmpeg input options that read only [start, start + length] of the file. Nothing for the whole file."""
    return [] if length is None else ["-ss", f"{max(start, 0.0):.3f}", "-t", f"{length:.3f}"]


def audio_rms_db(path: Path, deadline: Deadline | None = None, start: float = 0.0,
                 length: float | None = None) -> list[float]:
    """RMS level in dB, one value per second. With `length`, only that part of the file is read and the
    first value is the second starting at `start`."""
    res = run(["ffmpeg", "-hide_banner", "-nostats", *_seek(start, length), *SAFE_IN, "-i", path, "-vn", "-ac", "1",
               "-af", "aresample=8000,asetnsamples=n=8000,astats=metadata=1:reset=1,"
                      "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
               "-f", "null", "-"], deadline)
    vals = re.findall(r"RMS_level=(\S+)", res.stdout)
    return [max(-90.0, -90.0 if v in ("-inf", "inf", "nan") else float(v)) for v in vals]


def onscreen_chat_motion(path: Path, chat_region: str, deadline: Deadline | None = None, start: float = 0.0,
                         length: float | None = None, sample: str = "dense") -> list[float] | None:
    """How fast the on-screen chat band is changing each second (scrolling text = many edge changes).
    With `length`, only that part of the file is read (see audio_rms_db).

    `sample`:
    - `dense` (default): decode at 2 fps and average pairs → one value per second (historical behaviour).
    - `sparse`: decode at 1 fps → one value per second with about half the frames (research A3).
    """
    if sample not in CHAT_MOTION_SAMPLES:
        raise ValueError(f"chat motion sample must be one of {CHAT_MOTION_SAMPLES}, not {sample!r}")
    band_y, band_h = (0.0, 0.32) if chat_region.startswith("top") else (0.58, 0.42)
    fps = 2 if sample == "dense" else 1
    res = run(["ffmpeg", "-hide_banner", "-nostats", *_seek(start, length), *SAFE_IN, "-i", path, "-an",
               "-vf", f"fps={fps},crop=iw:ih*{band_h}:0:ih*{band_y},scale=480:-2,format=gray,"
                      "edgedetect=low=0.15:high=0.4,tblend=all_mode=difference,signalstats,"
                      "metadata=print:key=lavfi.signalstats.YAVG:file=-",
               "-f", "null", "-"], deadline)
    vals = [float(v) for v in re.findall(r"YAVG=([\d.]+)", res.stdout)]
    if sample == "dense":
        if len(vals) < 20:
            return None
        return [sum(vals[i:i + 2]) / len(vals[i:i + 2]) for i in range(0, len(vals), 2)]
    if len(vals) < 10:
        return None
    return vals


def baseline_z(vals: list[float], window: int = 300, floor: float = 1.0) -> np.ndarray:
    """Positive z-score against a rolling median/MAD baseline (default 5 minutes)."""
    x = np.asarray(vals, dtype=float)
    n = len(x)
    if n == 0:
        return x
    half = max(1, min(window // 2, n - 1)) if n > 1 else 0
    if half == 0:
        return np.zeros(1)
    pad = np.pad(x, (half, half), mode="reflect" if n > half else "edge")
    win = np.lib.stride_tricks.sliding_window_view(pad, 2 * half + 1)
    med = np.median(win, axis=1)
    mad = np.median(np.abs(win - med[:, None]), axis=1)
    z = (x - med) / np.maximum(1.4826 * mad, floor)
    return np.clip(z, 0.0, None)


def normalise(per_sec, n: int, shift: int = 0, smooth: int = 5) -> np.ndarray:
    """Shift earlier by `shift` seconds, smooth, and scale so typical peaks are about 1."""
    vals = np.zeros(n)
    src = np.asarray(per_sec, dtype=float)[shift:][:n]
    vals[:len(src)] = src
    if smooth > 1:
        vals = np.convolve(vals, np.ones(smooth) / smooth, mode="same")
    top = np.quantile(vals, 0.98) if n else 0.0
    if top <= 0:
        top = vals.max() if n and vals.max() > 0 else 1.0
    return np.minimum(vals / top, 1.5)
