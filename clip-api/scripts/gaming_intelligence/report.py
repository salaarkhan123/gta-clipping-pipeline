"""Reproducible experiment reports (machine-readable + concise human text).

Never invents metrics. Marks measured vs estimated vs blocked explicitly.
"""
from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _git_rev(cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd or Path.cwd(),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def experiment_envelope(
    *,
    experiment_id: str,
    dataset_version: str,
    source_recording_ids: list[str],
    model_id: str,
    feature_config: dict[str, Any],
    evaluation_methodology: str,
    sample_size: dict[str, Any],
    metrics: dict[str, Any],
    runtime: dict[str, Any] | None = None,
    hardware: dict[str, Any] | None = None,
    known_limitations: list[str] | None = None,
    random_seed: int | None = None,
    code_version: str | None = None,
) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset_version,
        "source_recording_ids": source_recording_ids,
        "model_id": model_id,
        "code_version": code_version or _git_rev(),
        "feature_config": feature_config,
        "random_seed": random_seed,
        "evaluation_methodology": evaluation_methodology,
        "sample_size": sample_size,
        "metrics": metrics,
        "runtime": runtime or {"status": "not_recorded"},
        "hardware": hardware or {
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "python": platform.python_version(),
        },
        "known_limitations": known_limitations or [],
        "invented_results": False,
    }


def write_json_report(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def human_summary(payload: dict[str, Any]) -> str:
    """Concise human-readable report. Does not invent missing metrics."""
    lines = [
        f"# Experiment {payload.get('experiment_id', '?')}",
        "",
        f"- Dataset version: `{payload.get('dataset_version')}`",
        f"- Code version: `{payload.get('code_version')}`",
        f"- Model: `{payload.get('model_id')}`",
        f"- Methodology: {payload.get('evaluation_methodology')}",
        f"- Sample: {json.dumps(payload.get('sample_size'))}",
        f"- Seed: {payload.get('random_seed')}",
        "",
        "## Metrics",
    ]
    metrics = payload.get("metrics") or {}
    status = metrics.get("status")
    if status and status.startswith("blocked"):
        lines.append(f"- **Blocked:** {metrics.get('message') or status}")
    else:
        lines.append("```json")
        lines.append(json.dumps(metrics, indent=2)[:4000])
        lines.append("```")
    lines.append("")
    lines.append("## Limitations")
    for lim in payload.get("known_limitations") or ["None recorded."]:
        lines.append(f"- {lim}")
    lines.append("")
    lines.append("## Runtime / hardware")
    lines.append(f"- Runtime: {json.dumps(payload.get('runtime'))}")
    lines.append(f"- Hardware: {json.dumps(payload.get('hardware'))}")
    lines.append("")
    lines.append("_No results were invented to complete this report._")
    return "\n".join(lines) + "\n"


def write_human_report(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(human_summary(payload))
    return path
