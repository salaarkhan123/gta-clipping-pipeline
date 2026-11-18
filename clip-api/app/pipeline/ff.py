"""ffmpeg/ffprobe helpers with timeouts. Inputs are restricted to local files."""
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

# Uploaded files are untrusted: never let ffmpeg follow URLs embedded in a playlist or container.
SAFE_IN = ["-protocol_whitelist", "file,pipe"]


class PipelineError(Exception):
    """An error that is safe to show to the user."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class PipelineTimeout(PipelineError):
    def __init__(self):
        super().__init__("timeout", "Processing took too long and was stopped.")


class Deadline:
    """Overall time budget for a job; every subprocess gets the remaining time as its timeout."""
    def __init__(self, seconds: float | None = None):
        self.at = time.monotonic() + seconds if seconds else None

    def remaining(self, cap: float | None = None) -> float | None:
        if self.at is None:
            return cap
        left = self.at - time.monotonic()
        if left <= 0:
            raise PipelineTimeout()
        return min(left, cap) if cap else left


def run(cmd, deadline: Deadline | None = None, cap: float | None = None, check: bool = True):
    timeout = deadline.remaining(cap) if deadline else cap
    try:
        return subprocess.run([str(c) for c in cmd], check=check, text=True, errors="replace",
                              capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise PipelineTimeout() from None
    except subprocess.CalledProcessError as e:
        tail = ((e.stderr or "").strip().splitlines() or ["unknown error"])[-1][:300]
        raise PipelineError("media_error", f"Could not process this video ({tail}).") from None


def run_bytes(cmd, deadline: Deadline | None = None, cap: float | None = None) -> bytes:
    """Like run(), for commands that write binary data to stdout."""
    return run_binary(cmd, deadline, cap)[0]


def run_binary(cmd, deadline: Deadline | None = None, cap: float | None = None) -> tuple[bytes, str]:
    """Like run_bytes(), and the command's log (stderr) as text too."""
    timeout = deadline.remaining(cap) if deadline else cap
    try:
        res = subprocess.run([str(c) for c in cmd], check=True, capture_output=True, timeout=timeout,
                             stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise PipelineTimeout() from None
    except subprocess.CalledProcessError:
        raise PipelineError("media_error", "Could not read this video.") from None
    return res.stdout, res.stderr.decode("utf-8", "replace")


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    has_audio: bool


def probe(path: Path, deadline: Deadline | None = None) -> MediaInfo:
    try:
        res = run(["ffprobe", "-v", "error", *SAFE_IN, "-show_entries",
                   "format=duration:stream=codec_type,width,height", "-of", "json", path],
                  deadline, cap=120)
        data = json.loads(res.stdout or "{}")
    except (PipelineError, json.JSONDecodeError) as e:
        if isinstance(e, PipelineTimeout):
            raise
        raise PipelineError("unsupported_media", "This file is not a readable video.") from None
    streams = data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video" and s.get("width")]
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    if not video or duration <= 0:
        raise PipelineError("unsupported_media", "This file is not a readable video.")
    return MediaInfo(duration=duration, width=int(video[0]["width"]), height=int(video[0]["height"]),
                     has_audio=any(s.get("codec_type") == "audio" for s in streams))
