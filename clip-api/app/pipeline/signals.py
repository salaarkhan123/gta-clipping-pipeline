"""Per-second highlight signals computed from the uploaded file itself.

Ported from test-tools/auto_clip.py (audio loudness, on-screen chat motion), with a
rolling-baseline z-score added so quiet and loud streams are judged against themselves.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from .ff import SAFE_IN, Deadline, probe, run

CHAT_LAG = 4  # seconds: chat reacts a few seconds after the moment happens
# dense/sparse: historical A3 paths. coarse/lite: Phase-4 CPR-14 (fewer filter frames;
# coarse also halves sample rate and parallelises long spans — see onscreen_chat_motion).
CHAT_MOTION_SAMPLES = ("dense", "sparse", "coarse", "lite")
_SAMPLE_FPS = {"dense": 2.0, "sparse": 1.0, "coarse": 0.5, "lite": 1.0}
_SAMPLE_SCALE = {"dense": 480, "sparse": 480, "coarse": 480, "lite": 240}
# Parallel segment decode only for the new modes (dense/sparse stay serial for back-compat).
_PARALLEL_SAMPLES = frozenset({"coarse", "lite"})
_PARALLEL_MIN_SEC = 120.0
_PARALLEL_WORKERS = 4


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


def _chat_band(chat_region: str) -> tuple[float, float]:
    return (0.0, 0.32) if chat_region.startswith("top") else (0.58, 0.42)


def _yavg_cmd(path: Path, start: float, length: float | None, fps: float, scale: int,
              band_y: float, band_h: float, *, threads: int | None = None) -> list:
    thr = (["-threads", str(threads), "-filter_threads", "1"] if threads is not None else [])
    return [
        "ffmpeg", "-hide_banner", "-nostats", *thr, *_seek(start, length), *SAFE_IN, "-i", path, "-an",
        "-vf", f"fps={fps},crop=iw:ih*{band_h}:0:ih*{band_y},scale={scale}:-2,format=gray,"
               "edgedetect=low=0.15:high=0.4,tblend=all_mode=difference,signalstats,"
               "metadata=print:key=lavfi.signalstats.YAVG:file=-",
        "-f", "null", "-",
    ]


def _yavg_vals(path: Path, start: float, length: float | None, fps: float, scale: int,
               band_y: float, band_h: float, deadline: Deadline | None,
               *, threads: int | None = None) -> list[float]:
    res = run(_yavg_cmd(path, start, length, fps, scale, band_y, band_h, threads=threads), deadline)
    return [float(v) for v in re.findall(r"YAVG=([\d.]+)", res.stdout)]


def _span_seconds(path: Path, start: float, length: float | None,
                  deadline: Deadline | None) -> float | None:
    """How many seconds of media this call will read, or None if unknown."""
    if length is not None:
        return max(0.0, float(length))
    try:
        dur = probe(path, deadline).duration
    except Exception:
        return None
    return max(0.0, dur - max(start, 0.0))


def _yavg_parallel(path: Path, start: float, span: float, fps: float, scale: int,
                   band_y: float, band_h: float, deadline: Deadline | None) -> list[float]:
    """Split [start, start+span) into up to 4 ffmpeg workers (1 decode thread each)."""
    workers = max(1, min(_PARALLEL_WORKERS, os.cpu_count() or 1))
    if span < _PARALLEL_MIN_SEC or workers == 1:
        return _yavg_vals(path, start, span, fps, scale, band_y, band_h, deadline)
    chunk = span / workers
    out: list[list[float] | None] = [None] * workers

    def one(i: int) -> tuple[int, list[float]]:
        return i, _yavg_vals(
            path, start + i * chunk, chunk, fps, scale, band_y, band_h, deadline, threads=1,
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, i) for i in range(workers)]
        for fut in as_completed(futs):
            i, vals = fut.result()
            out[i] = vals
    merged: list[float] = []
    for part in out:
        if part:
            merged.extend(part)
    return merged


def _to_per_second(vals: list[float], sample: str, span: float | None) -> list[float] | None:
    """Map raw YAVG samples to one value per second of content."""
    if sample == "dense":
        if len(vals) < 20:
            return None
        return [sum(vals[i:i + 2]) / len(vals[i:i + 2]) for i in range(0, len(vals), 2)]
    if sample in ("sparse", "lite"):
        return vals if len(vals) >= 10 else None
    # coarse: fps=0.5 → linear interpolate onto integer seconds
    if len(vals) < 5:
        return None
    fps = _SAMPLE_FPS["coarse"]
    n_sec = int(round(span)) if span is not None else int(round(len(vals) / fps))
    n_sec = max(n_sec, 1)
    t = np.arange(len(vals), dtype=float) / fps
    return np.interp(np.arange(n_sec, dtype=float), t, np.asarray(vals, dtype=float)).tolist()


def onscreen_chat_motion(path: Path, chat_region: str, deadline: Deadline | None = None, start: float = 0.0,
                         length: float | None = None, sample: str = "dense") -> list[float] | None:
    """How fast the on-screen chat band is changing each second (scrolling text = many edge changes).
    With `length`, only that part of the file is read (see audio_rms_db).

    `sample`:
    - `dense` (default): decode at 2 fps and average pairs → one value per second (historical behaviour).
    - `sparse`: decode at 1 fps → one value per second with about half the frames (research A3).
    - `coarse`: decode at 0.5 fps, scale 480, linear-interpolate to per-second; parallel segment
      decode on spans ≥ 120 s (preferred for preview latency when chat_region is set).
    - `lite`: decode at 1 fps like sparse but scale 240; same parallel rule as coarse.
    """
    if sample not in CHAT_MOTION_SAMPLES:
        raise ValueError(f"chat motion sample must be one of {CHAT_MOTION_SAMPLES}, not {sample!r}")
    band_y, band_h = _chat_band(chat_region)
    fps = _SAMPLE_FPS[sample]
    scale = _SAMPLE_SCALE[sample]
    span = _span_seconds(path, start, length, deadline)

    if sample in _PARALLEL_SAMPLES and span is not None and span >= _PARALLEL_MIN_SEC:
        vals = _yavg_parallel(path, max(start, 0.0), span, fps, scale, band_y, band_h, deadline)
    else:
        # dense/sparse keep the historical single-process path (no -t when length is None).
        # Whole-number fps stays an int in the vf string (tests and older logs match `fps=1,`).
        fps_arg: float | int = int(fps) if float(fps).is_integer() else fps
        vals = _yavg_vals(path, start, length, fps_arg, scale, band_y, band_h, deadline)

    return _to_per_second(vals, sample, span)


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
