"""Census existing eval sheets and caption geometry without inventing ratings."""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

CLIP_API = Path(__file__).resolve().parents[2]
EVAL = CLIP_API / "eval"
CAPTION_BOXES = CLIP_API / "scripts" / "caption_eval_boxes.json"
DENYLIST = (
    Path(__file__).resolve().parents[3]
    / "docs/gaming-intelligence-research/phase1/fixtures/denylist-eval-ids.json"
)


@dataclass
class EvalInventory:
    labels_v2_rows: int
    labels_v2_rated: int
    labels_v2_by_rating: dict[str, int]
    labels_v2_vods: list[str]
    held_out_vods: list[str]
    benchmark_2h_rows: int
    benchmark_2h_labelled: int
    wayin_rows: int
    wayin_labelled: int
    caption_geometry_videos: dict[str, int]
    hud_regions_populated: int
    denylist_vod_ids: list[str]
    gaps: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _rating_census(path: Path, field: str = "rating") -> tuple[int, int, dict[str, int], list[str], list[str]]:
    rows = list(csv.DictReader(path.open(newline="")))
    ratings = Counter((r.get(field) or "").strip() for r in rows)
    rated = sum(v for k, v in ratings.items() if k)
    vods = sorted({(r.get("vod") or "").strip() for r in rows if (r.get("vod") or "").strip()})
    held = sorted({
        (r.get("vod") or "").strip()
        for r in rows
        if (r.get("held_out") or "").strip().lower() in {"yes", "true", "1"}
    })
    return len(rows), rated, dict(ratings), vods, held


def inventory_eval_set() -> EvalInventory:
    from app.pipeline.layouts import HUD_REGIONS

    v2_rows, v2_rated, v2_ratings, v2_vods, held = _rating_census(EVAL / "labels-v2.csv", "rating")
    b_rows, b_labelled, _, _, _ = _rating_census(EVAL / "benchmark-2h-labels.csv", "label")
    w_rows, w_labelled, _, _, _ = _rating_census(EVAL / "wayin-zias-iceman.csv", "label")

    boxes = json.loads(CAPTION_BOXES.read_text())
    geometry = {name: len(meta.get("boxes") or []) for name, meta in boxes.get("videos", {}).items()}
    denylist = json.loads(DENYLIST.read_text()).get("evaluation_only_vod_ids", [])

    gaps = []
    if v2_rated == 0:
        gaps.append("labels-v2.csv has zero human ratings; precision/recall/NDCG cannot be computed.")
    if not held:
        gaps.append("No held-out VOD in labels-v2.csv (gta-rp-1 not supplied).")
    if len(v2_vods) < 3:
        gaps.append(f"Only {len(v2_vods)} VOD(s) in v2 sheet; README target is three.")
    if sum(1 for n in geometry.values() if n > 0) < 6:
        gaps.append("Caption geometry exists for some games, but HUD_REGIONS is empty and OCR text labels are absent.")
    if not HUD_REGIONS:
        gaps.append("HUD_REGIONS={} — no production HUD crops; #201 measurements still required.")
    gaps.append(
        "Private multigame sheets (~55 blank ratings) and ~/ClutchClips-eval media are not on this agent host."
    )
    gaps.append(
        "Per-second named-sound sheets for six evaluation VODs are missing (Phase 1C)."
    )

    return EvalInventory(
        labels_v2_rows=v2_rows,
        labels_v2_rated=v2_rated,
        labels_v2_by_rating=v2_ratings,
        labels_v2_vods=v2_vods,
        held_out_vods=held,
        benchmark_2h_rows=b_rows,
        benchmark_2h_labelled=b_labelled,
        wayin_rows=w_rows,
        wayin_labelled=w_labelled,
        caption_geometry_videos=geometry,
        hud_regions_populated=len(HUD_REGIONS),
        denylist_vod_ids=list(denylist),
        gaps=gaps,
    )
