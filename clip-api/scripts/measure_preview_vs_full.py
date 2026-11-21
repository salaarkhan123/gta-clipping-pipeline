#!/usr/bin/env python3
"""PR-A1 (S2 measure): preview-first vs full render timing harness.

Runs (or dry-runs) two comparable Clip Maker paths with render=preview and render=full,
then prints one JSON object whose per-mode blocks are job_timings-compatible so staging
can report TTFC / render / total with scripts/job_timings.py.

Modes
-----
  --dry-run
      Print the staging recipe (curl + job_timings) and a JSON stub. No jobs are started.
      2h VOD results are always labeled "not measured" until staging fills them in.

  --preview-job PATH --full-job PATH
      Compare two finished GET /v1/jobs/<id> responses (or synthetic job-shaped JSON from
      --local). Emits the same comparison fields ops looks at.

  --local VIDEO
      Run run_pipeline twice on one local file (preview then full). Writes job-shaped JSON
      under --out-dir and prints the comparison. Use a short fixture on this VM; do not
      invent 2h numbers.

Usage
-----
  python scripts/measure_preview_vs_full.py --dry-run
  python scripts/measure_preview_vs_full.py --preview-job preview.json --full-job full.json
  python scripts/measure_preview_vs_full.py --local fixture.mp4 --transcriber none --max-clips 2

Exit 0 = ok, 2 = bad input / unfinished job JSON.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

COMPARE_FIELDS = ("first_clip_sec", "stages.render", "total_sec")
NOT_MEASURED = "not measured"


def _load_job_timings():
    spec = importlib.util.spec_from_file_location("job_timings", SCRIPT_DIR / "job_timings.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def stage_render_sec(compared: dict) -> float | None:
    """Fine `render` stage seconds from a job_timings.compare() result, else None."""
    for row in compared.get("stages") or []:
        if row.get("stage") == "render":
            return float(row["sec"])
    return None


def pick_metrics(compared: dict) -> dict[str, Any]:
    """The three fields Wave A1 asks ops to compare, plus ids for the PR table."""
    return {
        "job_id": compared.get("job_id"),
        "first_clip_sec": compared.get("first_clip_sec"),
        "render_sec": stage_render_sec(compared),
        "total_sec": compared.get("total_sec"),
        "run_sec": compared.get("run_sec"),
        "queue_sec": compared.get("queue_sec"),
        "clips": compared.get("clips"),
        "source_min": compared.get("source_min"),
        "meets_target": compared.get("meets_target"),
        "detail": compared.get("detail"),
        "job_timings": compared,
    }


def delta_metrics(preview: dict, full: dict) -> dict[str, Any]:
    """Signed change (preview − full). Negative means preview was faster."""
    out: dict[str, Any] = {}
    for key in ("first_clip_sec", "render_sec", "total_sec", "run_sec"):
        a, b = preview.get(key), full.get(key)
        if a is None or b is None:
            out[key] = None
        else:
            out[key] = round(float(a) - float(b), 1)
    return out


def compare_job_files(preview_path: Path, full_path: Path) -> dict[str, Any]:
    jt = _load_job_timings()
    preview = pick_metrics(jt.compare(jt.load(preview_path)))
    full = pick_metrics(jt.compare(jt.load(full_path)))
    source_min = preview.get("source_min") or full.get("source_min") or 0.0
    two_hour = source_min is not None and float(source_min) >= 110.0  # ~2h with slack
    return {
        "harness": "measure_preview_vs_full",
        "compare_fields": list(COMPARE_FIELDS),
        "claim": {
            "2h_vod": "measured" if two_hour else NOT_MEASURED,
            "pair": "measured",
        },
        "preview": preview,
        "full": full,
        "delta_preview_minus_full": delta_metrics(preview, full),
        "notes": [
            "first_clip_sec includes queue (what the customer waits).",
            "stages.render is the fine render stage from job_timings --json.",
            "total_sec is queue + run.",
            f"2h VOD end-to-end on staging: {NOT_MEASURED} until a real ~7200s source is run.",
        ],
    }


def local_run_to_job_shape(
    *,
    job_id: str,
    render: str,
    wall_sec: float,
    timer_dict: dict,
    first_clip_sec: float | None,
) -> dict:
    """Shape a local pipeline timing dict like GET /v1/jobs so job_timings.load can read it."""
    stages = dict(timer_dict.get("stages") or {})
    counts = dict(timer_dict.get("counts") or {})
    source = float(counts.get("source_sec") or 0.0)
    elapsed = round(wall_sec, 3)
    speed = round(source / elapsed, 3) if elapsed > 0 and source > 0 else 0.0
    result: dict[str, Any] = {
        "elapsed_sec": elapsed,
        "speed_x": speed,
        "queue_sec": 0.0,
        "total_sec": elapsed,
        "stages": stages,
        "timings": {},
        "counts": counts,
        "render": render,
    }
    if first_clip_sec is not None:
        result["first_clip_sec"] = round(first_clip_sec, 3)
    return {
        "job_id": job_id,
        "status": "SUCCEEDED",
        "clips": [{}] * int(counts.get("clips") or 0),
        "result": result,
    }


def run_local_pair(
    video: Path,
    *,
    max_clips: int,
    clip_length: int,
    transcriber_name: str,
    out_dir: Path,
) -> dict[str, Any]:
    from app.config import get_settings
    from app.pipeline import PipelineError, PipelineOptions, Timer, run_pipeline
    from app.pipeline.transcribe import FasterWhisperTranscriber

    model = get_settings().whisper_model
    if transcriber_name == "whisper" and model.lower() != "none":
        transcriber = FasterWhisperTranscriber(model)
    else:
        transcriber = None

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for render in ("preview", "full"):
        timer = Timer()
        first_clip: list[float] = []
        t0 = time.perf_counter()

        def on_clip(_clip, started=t0, bucket=first_clip):
            if not bucket:
                bucket.append(time.perf_counter() - started)

        work = Path(tempfile.mkdtemp(prefix=f"preview_vs_full_{render}_", dir=out_dir))
        try:
            run_pipeline(
                video,
                PipelineOptions(
                    max_clips=max_clips,
                    clip_length=clip_length,
                    facecam_region="auto",
                    render=render,
                ),
                work,
                transcriber=transcriber,
                timer=timer,
                on_clip=on_clip,
            )
        except PipelineError as e:
            raise SystemExit(f"pipeline failed ({render}): {e}") from e
        wall = time.perf_counter() - t0
        shaped = local_run_to_job_shape(
            job_id=f"local-{render}",
            render=render,
            wall_sec=wall,
            timer_dict=timer.as_dict(),
            first_clip_sec=first_clip[0] if first_clip else None,
        )
        path = out_dir / f"local-{render}.json"
        path.write_text(json.dumps(shaped, indent=2) + "\n")
        paths[render] = path

    report = compare_job_files(paths["preview"], paths["full"])
    report["claim"]["pair"] = "measured"
    report["claim"]["2h_vod"] = NOT_MEASURED
    report["local"] = {
        "video": str(video),
        "preview_job": str(paths["preview"]),
        "full_job": str(paths["full"]),
        "max_clips": max_clips,
        "clip_length": clip_length,
        "transcriber": transcriber_name,
    }
    return report


def staging_recipe(*, api: str, upload_id: str | None, max_clips: int, clip_length: int) -> dict[str, Any]:
    """Documented curl recipe for staging. Does not call the network."""
    api = api.rstrip("/")
    uid = upload_id or "<UPLOAD_ID>"
    body_preview = {
        "upload_id": uid,
        "options": {"max_clips": max_clips, "clip_length": clip_length, "render": "preview"},
    }
    body_full = {
        "upload_id": uid,
        "options": {"max_clips": max_clips, "clip_length": clip_length, "render": "full"},
    }
    steps = [
        "# 1. Same upload for both jobs (2h VOD on staging, or a short fixture for a smoke). "
        "Confirm ownership/consent for any link import.",
        f'export API={api!r} KEY=<API_KEY>',
        f"curl -sS -X POST \"$API/v1/clips\" -H \"authorization: Bearer $KEY\" "
        f"-H 'content-type: application/json' -d '{json.dumps(body_preview)}' | tee preview-start.json",
        f"curl -sS -X POST \"$API/v1/clips\" -H \"authorization: Bearer $KEY\" "
        f"-H 'content-type: application/json' -d '{json.dumps(body_full)}' | tee full-start.json",
        "# 2. Poll until SUCCEEDED, then save the full job payloads:",
        'PREVIEW_ID=$(python -c "import json;print(json.load(open(\'preview-start.json\'))[\'job_id\'])")',
        'FULL_ID=$(python -c "import json;print(json.load(open(\'full-start.json\'))[\'job_id\'])")',
        'curl -sS "$API/v1/jobs/$PREVIEW_ID" -H "authorization: Bearer $KEY" > preview.json',
        'curl -sS "$API/v1/jobs/$FULL_ID" -H "authorization: Bearer $KEY" > full.json',
        "# 3. Per-mode tables (paste into the PR):",
        "python scripts/job_timings.py preview.json --json",
        "python scripts/job_timings.py full.json --json",
        "python scripts/job_timings.py preview.json --baseline full.json --md",
        "# 4. Side-by-side TTFC / render / total:",
        "python scripts/measure_preview_vs_full.py --preview-job preview.json --full-job full.json",
    ]
    return {
        "harness": "measure_preview_vs_full",
        "mode": "dry-run",
        "compare_fields": list(COMPARE_FIELDS),
        "claim": {"2h_vod": NOT_MEASURED, "pair": "dry-run"},
        "api": api,
        "upload_id": upload_id,
        "options": {"max_clips": max_clips, "clip_length": clip_length},
        "recipe": steps,
        "fields": {
            "first_clip_sec": "queue_sec + result.first_clip_sec (job_timings --json)",
            "stages.render": "fine stage seconds for encode (job_timings stages row 'render')",
            "total_sec": "queue + run end-to-end",
        },
        "notes": [
            f"Real 2h preview-vs-full numbers: {NOT_MEASURED} on this agent VM (no 2h VOD).",
            "Run the recipe on staging with a ~7200s source before claiming a win.",
            "Keep max_clips / clip_length / template / weights identical across the pair.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print staging recipe JSON; start no jobs")
    ap.add_argument("--api", default="https://staging.example.com", help="API base for the dry-run recipe")
    ap.add_argument("--upload-id", default=None, help="upload id to embed in the dry-run recipe")
    ap.add_argument("--preview-job", type=Path, help="finished GET /v1/jobs JSON for render=preview")
    ap.add_argument("--full-job", type=Path, help="finished GET /v1/jobs JSON for render=full")
    ap.add_argument("--local", type=Path, help="local video for a dual run_pipeline measurement")
    ap.add_argument("--out-dir", type=Path, default=Path("preview-vs-full-out"))
    ap.add_argument("--max-clips", type=int, default=3)
    ap.add_argument("--clip-length", type=int, default=30)
    ap.add_argument("--transcriber", choices=("whisper", "none"), default="none")
    args = ap.parse_args(argv)

    try:
        if args.dry_run:
            report = staging_recipe(
                api=args.api, upload_id=args.upload_id,
                max_clips=args.max_clips, clip_length=args.clip_length,
            )
        elif args.preview_job and args.full_job:
            report = compare_job_files(args.preview_job, args.full_job)
        elif args.local:
            if not args.local.is_file():
                print(f"not a file: {args.local}", file=sys.stderr)
                return 2
            report = run_local_pair(
                args.local,
                max_clips=args.max_clips,
                clip_length=args.clip_length,
                transcriber_name=args.transcriber,
                out_dir=args.out_dir,
            )
        else:
            ap.print_help(sys.stderr)
            print("\nNeed --dry-run, or --preview-job + --full-job, or --local VIDEO.", file=sys.stderr)
            return 2
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
