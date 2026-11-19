"""The shared frame pass: the key frames of the analysed part are decoded once, and every picture signal of the
timeline (timeline.py) is measured from that one decode. It runs next to the audio decode, not after it.

Key frames come every 2 s (OBS and Twitch defaults) to 5 s (YouTube AV1). That is enough to tell what stays the
same (standby, repeated screens) and how much changes between key frames; it is too sparse for anything shorter
than a few seconds, which is why there is no frame-by-frame event detector here.
"""
import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout
from .timeline import KEY_ONLY, STILL, _seek

log = logging.getLogger("clipapi.frames")

FRAME_W, FRAME_H = 320, 180     # the size key frames are read at
PRINT_W, PRINT_H = 32, 18       # a frame's fingerprint, for "this screen was shown before"
REPEAT_GAP = 120.0              # seconds: a frame only repeats one at least this much earlier
REPEAT_SIM = 0.99               # fingerprint correlation at which two key frames show the same screen


def _box(cam, w: int, h: int) -> tuple[slice, slice] | None:
    """A camera box [x, y, w, h] in fractions of the frame (facecam.CamBox) as pixel slices, or None."""
    if not (isinstance(cam, (list, tuple)) and len(cam) == 4):
        return None
    x, y, bw, bh = (float(v) for v in cam)
    x0, y0 = int(max(0.0, x) * w), int(max(0.0, y) * h)
    x1, y1 = int(min(1.0, x + bw) * w), int(min(1.0, y + bh) * h)
    return (slice(y0, y1), slice(x0, x1)) if x1 - x0 >= 4 and y1 - y0 >= 4 else None


def frame_pass(path: Path, deadline: Deadline | None = None, start: float = 0.0, length: float | None = None,
               cam=None, on_frame=None) -> dict[str, np.ndarray]:
    """Decode the key frames of [start, start + length] once. For each: `t` (source second), `change` (mean grey
    change of the whole picture from the previous key frame, 0-255), `cam_change` (the same inside the camera box
    `cam`; 0 without one) and `print` (a normalised 32 x 18 grey thumbnail). `on_frame(t, rgb)` is called with
    every FRAME_W x FRAME_H RGB key frame, for a detector that needs the picture itself."""
    box = _box(cam, FRAME_W, FRAME_H)
    for key_only in KEY_ONLY:
        cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "info", "-nostdin", *key_only,
               *_seek(start, length), *SAFE_IN, "-i", str(path), "-an",
               "-vf", f"scale={FRAME_W}:{FRAME_H},showinfo", "-fps_mode", "passthrough",
               "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        log: list[bytes] = []
        reader = threading.Thread(target=lambda p=proc: log.append(p.stderr.read()), daemon=True)
        reader.start()
        killer = None
        if deadline is not None and deadline.at is not None:
            killer = threading.Timer(max(1.0, deadline.remaining()), proc.kill)     # never past the job's deadline
            killer.start()
        out = {"change": [], "cam_change": [], "print": []}
        frames, prev, size = [], None, FRAME_W * FRAME_H * 3
        try:
            while True:
                buf = proc.stdout.read(size)
                if len(buf) < size:
                    break
                rgb = np.frombuffer(buf, np.uint8).reshape(FRAME_H, FRAME_W, 3)
                g = rgb.astype(np.float32).mean(axis=2)
                d = np.abs(g - prev) if prev is not None else np.zeros_like(g)
                out["change"].append(float(d.mean()))
                out["cam_change"].append(float(d[box].mean()) if box is not None else 0.0)
                small = g.reshape(PRINT_H, FRAME_H // PRINT_H, PRINT_W, FRAME_W // PRINT_W).mean(axis=(1, 3)).ravel()
                small -= small.mean()
                out["print"].append(small / max(float(np.linalg.norm(small)), 1e-6))
                if on_frame is not None:
                    frames.append(rgb)
                prev = g
            proc.wait()
        finally:
            if killer is not None:
                killer.cancel()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        reader.join()
        if deadline is not None:
            deadline.remaining()                       # raises when the time ran out (the kill above)
        if proc.returncode != 0:
            continue                                   # an ffmpeg without input bitstream filters: the fallback
        times = [start + float(t) for t in re.findall(rb"pts_time:\s*(-?[\d.]+)", log[0] if log else b"")]
        n = min(len(times), len(out["change"]))
        if on_frame is not None:
            for t, rgb in zip(times[:n], frames[:n]):
                on_frame(t, rgb)
        return {"t": np.asarray(times[:n]), **{k: np.asarray(v[:n]) for k, v in out.items()}}
    return {"t": np.zeros(0), "change": np.zeros(0), "cam_change": np.zeros(0), "print": np.zeros((0, PRINT_W * PRINT_H))}


def per_second(times: np.ndarray, values, start: float, n: int) -> np.ndarray:
    """Values measured at key frames (each about the stretch since the key frame before it) as one value per
    second: second i takes the value of the first key frame at or after start + i + 0.5."""
    if len(times) == 0:
        return np.zeros(n)
    idx = np.clip(np.searchsorted(times, start + np.arange(n) + 0.5), 0, len(times) - 1)
    return np.asarray(values, float)[idx]


def still(change: np.ndarray) -> np.ndarray:
    """1 for each key frame where the picture did not change since the one before (timeline.STILL)."""
    return (np.asarray(change) < STILL).astype(float)


def repeats(times: np.ndarray, prints: np.ndarray) -> np.ndarray:
    """1 for each key frame whose screen (fingerprint correlation REPEAT_SIM or more) was already shown at least
    REPEAT_GAP seconds before: lobbies, menus, respawn and loading screens coming back again and again."""
    out = np.zeros(len(times))
    if len(times) < 2:
        return out
    sims = prints @ prints.T
    for i in range(len(times)):
        early = times < times[i] - REPEAT_GAP
        if early.any() and float(sims[i, early].max()) >= REPEAT_SIM:
            out[i] = 1.0
    return out


def runs(flags: np.ndarray, min_len: int) -> np.ndarray:
    """The same 0/1 series with only the runs of 1 that last at least `min_len` values."""
    out = np.zeros(len(flags), bool)
    i = 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j < len(flags) and flags[j]:
                j += 1
            if j - i >= min_len:
                out[i:j] = True
            i = j
        else:
            i += 1
    return out


def spans(flags: np.ndarray, start: float) -> list[list[float]]:
    """The runs of 1 in a per-second series as [[start, end], ...] in seconds, second 0 being `start`."""
    out, i = [], 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j < len(flags) and flags[j]:
                j += 1
            out.append([round(start + i, 3), round(start + j, 3)])
            i = j
        else:
            i += 1
    return out


@dataclass
class Picture:
    """What the key frames say, one value per analysed second (value i is source second base + i)."""
    change: np.ndarray        # how much the whole picture changed (mean grey level, 0-255)
    reaction: np.ndarray      # how much the camera box changed; zeros without a camera
    still: np.ndarray         # 1: the picture did not change
    repeat: np.ndarray        # 1: this screen was already shown at least REPEAT_GAP seconds earlier
    keyframes: int = 0        # key frames read; 0: the pass gave nothing, and every series is zeros
    seconds: float = 0.0      # how long the pass took


def picture(path: Path, n: int, base: int, deadline: Deadline | None = None, start: float = 0.0,
            length: float | None = None, cam=None, on_frame=None) -> Picture:
    """The picture signals of the analysed part from one key-frame decode. A file whose key frames cannot be read
    gives zeros: the picture signals are an addition, never a reason for a job to fail (a timeout still is)."""
    began = time.monotonic()
    try:
        f = frame_pass(path, deadline, start, length, cam, on_frame)
    except PipelineTimeout:
        raise
    except (PipelineError, OSError):
        log.exception("key frames could not be read; continuing without picture signals")
        f = {"t": np.zeros(0)}
    k = len(f["t"])
    if k < 2:
        z = np.zeros(n)
        return Picture(z, z.copy(), z.copy(), z.copy(), 0, time.monotonic() - began)
    t = f["t"]
    for name in ("change", "cam_change"):          # the first key frame has nothing before it: take the next one's
        f[name][0] = f[name][1]
    return Picture(change=per_second(t, f["change"], base, n), reaction=per_second(t, f["cam_change"], base, n),
                   still=per_second(t, still(f["change"]), base, n),
                   repeat=per_second(t, repeats(t, f["print"]), base, n), keyframes=k,
                   seconds=time.monotonic() - began)
