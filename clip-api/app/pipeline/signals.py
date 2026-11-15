"""Per-second highlight signals computed from the uploaded file itself.

Ported from test-tools/auto_clip.py (audio loudness, on-screen chat motion), with a
rolling-baseline z-score added so quiet and loud streams are judged against themselves.
"""
import re
from pathlib import Path

import numpy as np

from .ff import SAFE_IN, Deadline, run

CHAT_LAG = 4  # seconds: chat reacts a few seconds after the moment happens


def audio_rms_db(path: Path, deadline: Deadline | None = None) -> list[float]:
    """RMS level in dB, one value per second."""
    res = run(["ffmpeg", "-hide_banner", "-nostats", *SAFE_IN, "-i", path, "-vn", "-ac", "1",
               "-af", "aresample=8000,asetnsamples=n=8000,astats=metadata=1:reset=1,"
                      "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
               "-f", "null", "-"], deadline)
    vals = re.findall(r"RMS_level=(\S+)", res.stdout)
    return [max(-90.0, -90.0 if v in ("-inf", "inf", "nan") else float(v)) for v in vals]


def onscreen_chat_motion(path: Path, chat_region: str, deadline: Deadline | None = None) -> list[float] | None:
    """How fast the on-screen chat band is changing each second (scrolling text = many edge changes)."""
    band_y, band_h = (0.0, 0.32) if chat_region.startswith("top") else (0.58, 0.42)
    res = run(["ffmpeg", "-hide_banner", "-nostats", *SAFE_IN, "-i", path, "-an",
               "-vf", f"fps=2,crop=iw:ih*{band_h}:0:ih*{band_y},scale=480:-2,format=gray,"
                      "edgedetect=low=0.15:high=0.4,tblend=all_mode=difference,signalstats,"
                      "metadata=print:key=lavfi.signalstats.YAVG:file=-",
               "-f", "null", "-"], deadline)
    vals = [float(v) for v in re.findall(r"YAVG=([\d.]+)", res.stdout)]
    if len(vals) < 20:
        return None
    return [sum(vals[i:i + 2]) / len(vals[i:i + 2]) for i in range(0, len(vals), 2)]


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
