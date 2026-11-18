#!/usr/bin/env python3
"""Time run_pipeline on one local video and print one JSON line.

Usage: python scripts/bench_pipeline.py <video> [--chat-region top-right] [--transcriber whisper|none]
                                       [--max-clips 3] [--clip-length 30]

Keys: source_minutes, wall_seconds, realtime_factor (source seconds per wall second), peak_rss_mb,
clips, credits (what Clip Maker would charge for this length), chat_region, stages (seconds per pipeline
stage) and counts (candidates, clips, seconds transcribed and rendered). No AI judge is used here.
peak_rss_mb is the larger of this process and its biggest child (ffmpeg); the two peaks are not summed.
Exit 0 = ok, 1 = pipeline failed, 2 = bad input. Clips are rendered to a temp dir and deleted.
"""
import argparse
import json
import resource
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.pipeline import PipelineError, PipelineOptions, Timer, probe, run_pipeline  # noqa: E402
from app.pipeline.render import CHAT_REGIONS  # noqa: E402
from app.pipeline.transcribe import FasterWhisperTranscriber, Transcriber  # noqa: E402
from app.routes_media import credits_for  # noqa: E402


def peak_rss_mb() -> float:
    peak = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)   # bytes on macOS, KiB on Linux


def benchmark(video: Path, chat_region: str = "none", transcriber: Transcriber | None = None,
              max_clips: int = 3, clip_length: int = 30) -> dict:
    duration = probe(video).duration
    timer = Timer()
    with tempfile.TemporaryDirectory(prefix="bench_") as out:
        start = time.perf_counter()
        # facecam_region="auto" is what the API sends by default: detect the camera, split layout when there is one.
        clips = run_pipeline(video, PipelineOptions(chat_region=chat_region, max_clips=max_clips, clip_length=clip_length,
                                                    facecam_region="auto"),
                             Path(out), transcriber=transcriber, timer=timer)
        wall = time.perf_counter() - start
    return {"source_minutes": round(duration / 60, 2), "wall_seconds": round(wall, 2),
            "realtime_factor": round(duration / wall, 2), "peak_rss_mb": peak_rss_mb(),
            "clips": len(clips), "credits": credits_for(duration), "chat_region": chat_region, **timer.as_dict()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--chat-region", default="none", choices=["none", *CHAT_REGIONS])
    ap.add_argument("--max-clips", type=int, default=3)
    ap.add_argument("--clip-length", type=int, default=30)
    ap.add_argument("--transcriber", default="whisper", choices=["whisper", "none"],
                    help="whisper uses WHISPER_MODEL from the environment (as the worker does)")
    args = ap.parse_args(argv)
    if not args.video.is_file():
        print(f"not a file: {args.video}", file=sys.stderr)
        return 2
    model = get_settings().whisper_model
    transcriber = FasterWhisperTranscriber(model) if args.transcriber == "whisper" and model.lower() != "none" else None
    try:
        print(json.dumps(benchmark(args.video, args.chat_region, transcriber, args.max_clips, args.clip_length)))
    except PipelineError as e:
        print(f"pipeline failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
