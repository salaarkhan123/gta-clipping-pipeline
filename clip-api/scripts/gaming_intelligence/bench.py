"""CPU-feasible GI bench helpers + GPU cost *estimates* (clearly labeled).

No GPU is purchased or provisioned here. `estimate_gpu_cost` uses public list
prices and caller-supplied billed minutes — outputs are ESTIMATES.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.pipeline.gaming_intelligence import GIConfig, apply_gi

# Public list prices cited in GPU-REQUIREMENTS.md / #237 (USD/hour, 2026-11-19).
# ESTIMATE inputs only — not ClutchClips measured throughput.
LIST_USD_PER_HOUR = {
    "cpu_c6": 0.16,
    "l4": 0.69,
    "rtx4090": 0.89,
    "l40s": 1.09,
    "rtx5090": 1.39,
}


def write_cpu_bench_stub(
    candidates: list[dict[str, Any]],
    out: Path,
    *,
    repeats: int = 50,
) -> dict[str, Any]:
    """MEASURED on this host: identity vs enabled-zero-weight GI overhead (no models)."""
    t_off = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        apply_gi(candidates, config=GIConfig(enabled=False))
        t_off.append((time.perf_counter() - t0) * 1000)
    t_on = []
    cfg = GIConfig(enabled=True, family_weights={k: 0.0 for k in ("audio_named", "hud_ocr", "dialogue", "visual", "reaction")})
    for _ in range(repeats):
        t0 = time.perf_counter()
        apply_gi(candidates, config=cfg)
        t_on.append((time.perf_counter() - t0) * 1000)

    def stats(xs: list[float]) -> dict[str, float]:
        xs = sorted(xs)
        return {
            "n": len(xs),
            "median_ms": xs[len(xs) // 2],
            "p95_ms": xs[int(len(xs) * 0.95) - 1] if len(xs) >= 2 else xs[0],
            "max_ms": xs[-1],
        }

    report = {
        "kind": "measured_cpu_gi_hook_overhead",
        "candidates": len(candidates),
        "disabled": stats(t_off),
        "enabled_zero_weights": stats(t_on),
        "gpu": "not_run",
        "note": "No model inference; measures Python hook + annotate/rerank only.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    return report


def estimate_gpu_cost(
    *,
    sku: str,
    billed_minutes_per_source_hour: float,
    source_hours: float = 1.0,
) -> dict[str, Any]:
    """ESTIMATE: list_price × billed time. Not a ClutchClips measurement."""
    rate = LIST_USD_PER_HOUR.get(sku)
    if rate is None:
        raise KeyError(f"unknown sku {sku}; known={sorted(LIST_USD_PER_HOUR)}")
    hours = (billed_minutes_per_source_hour / 60.0) * source_hours
    return {
        "kind": "estimate",
        "sku": sku,
        "list_usd_per_hour": rate,
        "billed_minutes_per_source_hour": billed_minutes_per_source_hour,
        "source_hours": source_hours,
        "estimated_compute_usd": round(rate * hours, 4),
        "includes_cold_start": False,
        "includes_storage_egress": False,
        "clutchclips_gpu_throughput": "not_measured",
    }


def reproducible_gpu_bench_plan() -> dict[str, Any]:
    """Checklist for an owner-approved L4 rental — do not execute without OK."""
    return {
        "status": "plan_only",
        "sku_first": "l4",
        "host_ram_floor_gb": 32,
        "scale": "0→1→0",
        "arms": [
            "cpu_worker_control_same_vod",
            "ffmpeg_nvdec_optional",
            "faster_whisper_cuda",
            "embed_onnx_or_cuda",
            "tier2_qwen3vl_capped_shortlist_only",
        ],
        "metrics": [
            "cold_start_s",
            "e2e_wall_s",
            "ttf_preview_s",
            "peak_host_rss_gb",
            "peak_vram_gb",
            "usd_per_successful_source_hour",
        ],
        "forbidden_without_owner_ok": ["purchase", "provision", "always_on_droplet"],
        "refs": [
            "docs/gaming-intelligence-research/GPU-REQUIREMENTS.md",
            "docs/gaming-intelligence-research/phases/gaming-intelligence-gpu-cost-report.md",
            "PR #258 serverless GPU pipeline",
        ],
    }
