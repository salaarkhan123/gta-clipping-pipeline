"""Freeze and replay the production highlight selector (B0)."""
from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PIN = ROOT / "docs/gaming-intelligence-research/phase1/baseline-pin.json"


@dataclass(frozen=True)
class BaselinePin:
    name: str
    selector_merge_sha: str
    production_weights: dict[str, float]
    experimental_weights_remain_zero: list[str]
    hud_regions: dict
    entry_point: str

    def assert_matches_runtime(self, weights: dict[str, float], hud_regions: dict) -> None:
        if dict(weights) != dict(self.production_weights):
            raise AssertionError(
                f"runtime WEIGHTS {weights} != pinned {self.production_weights}"
            )
        if dict(hud_regions) != dict(self.hud_regions):
            raise AssertionError("HUD_REGIONS changed since baseline pin; re-pin intentionally")


def load_pin(path: Path | None = None) -> BaselinePin:
    data = json.loads((path or DEFAULT_PIN).read_text())
    return BaselinePin(
        name=data["name"],
        selector_merge_sha=data["selector_merge_sha"],
        production_weights=dict(data["production_weights"]),
        experimental_weights_remain_zero=list(data["experimental_weights_remain_zero"]),
        hud_regions=dict(data.get("hud_regions") or {}),
        entry_point=data["entry_point"],
    )


def candidate_fingerprint(clips: list[dict]) -> str:
    """Stable hash of ranked candidate intervals and scores for determinism checks."""
    rows = []
    for c in clips:
        rows.append({
            "rank": c.get("rank"),
            "start": round(float(c["start_sec"] if "start_sec" in c else c["start"]), 3),
            "end": round(float(c["end_sec"] if "end_sec" in c else c["end"]), 3),
            "score": round(float(c.get("score") or 0.0), 4),
            "kind": c.get("kind"),
        })
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def select_b0(
    video: Path,
    *,
    max_clips: int = 5,
    clip_length: int = 10,
    range_sec: dict | None = None,
    duration: str | None = None,
) -> dict:
    """Run production selection without judge or render; return a run JSON dict."""
    from app.pipeline import PipelineOptions, WEIGHTS, run_pipeline
    from app.pipeline.layouts import HUD_REGIONS

    pin = load_pin()
    pin.assert_matches_runtime(WEIGHTS, HUD_REGIONS)

    chosen: list = []

    class Stop(Exception):
        pass

    def on_moments(moments):
        chosen.extend(moments)
        raise Stop

    opts = PipelineOptions(
        max_clips=max_clips,
        clip_length=clip_length,
        vertical=False,
        captions=False,
        tighten=False,
        punch_zoom=False,
        flash_forward=False,
        hook_overlay=False,
        thumbnail_text=False,
        chat_region="none",
        range=range_sec,
        duration=duration,
        render="none",
    )
    with tempfile.TemporaryDirectory(prefix="gaming_b0_") as tmp:
        try:
            run_pipeline(Path(video), opts, Path(tmp), on_moments=on_moments)
        except Stop:
            pass

    clips = [
        {
            "rank": i,
            "start_sec": float(m.start),
            "end_sec": float(m.end),
            "score": round(float(m.score), 4),
            "kind": getattr(m, "kind", None),
            "signals": getattr(m, "signals", None),
        }
        for i, m in enumerate(chosen, 1)
    ]
    return {
        "system": "clutchclips",
        "arm": "B0",
        "baseline": asdict(pin),
        "source": Path(video).name,
        "options": {
            "max_clips": max_clips,
            "clip_length": clip_length,
            "range": range_sec,
            "duration": duration,
            "chat_region": "none",
            "render": "none",
        },
        "clips": clips,
        "fingerprint": candidate_fingerprint(clips),
        "paid_model_calls": 0,
    }
