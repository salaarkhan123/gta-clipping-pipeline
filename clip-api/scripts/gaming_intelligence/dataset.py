"""Phase 4 — GTA eval dataset from existing pipeline candidates.

Candidates come from run JSON / labels-v2 rows. Human fields start empty.
ClutchClips AI ratings and ranks are **not** ground truth — they are proposals
for a human to rate with the entertainment rubric.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

# Machine-proposed interval (from pipeline / prior run). Never treat as GT.
CANDIDATE_FIELDS = (
    "id",
    "vod",
    "game",
    "start",
    "end",
    "source",           # e.g. clutchclips:<run>#rank
    "clutch_rank",      # proposal only
    "clutch_score",     # proposal only — not ground truth
)

# Human labels (entertainment rubric). Empty until an owner/editor fills them.
HUMAN_FIELDS = (
    "hook",             # 0-3
    "stakes",           # 0-3
    "payoff",           # 0-3
    "reaction",         # 0-3
    "clarity",          # 0-3
    "novelty",          # 0-3
    "completeness",     # 0-3
    "publish",          # yes|no|maybe
    "event_tags",       # free text: gunfight,crash,dialogue,...
    "notes",
    "rater",
    "rated_at",
)

ALL_FIELDS = CANDIDATE_FIELDS + HUMAN_FIELDS


def _hms(seconds: float) -> str:
    t = int(round(float(seconds)))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def candidates_from_run(
    run: dict[str, Any] | Path,
    *,
    vod: str,
    game: str = "gta-online",
) -> list[dict[str, str]]:
    """Build label-sheet rows from a pipeline/job run. Human fields left blank."""
    data = json.loads(Path(run).read_text()) if isinstance(run, Path) else run
    clips = data.get("clips", data) if isinstance(data, dict) else data
    system = (data.get("system") if isinstance(data, dict) else None) or "clutchclips"
    rows: list[dict[str, str]] = []
    for i, c in enumerate(clips, 1):
        start = float(c.get("start_sec", c.get("start", 0.0)))
        end = float(c.get("end_sec", c.get("end", start)))
        rank = c.get("rank", i)
        score = c.get("score", c.get("rank_score", ""))
        cid = f"{vod}-{rank}"
        row = {k: "" for k in ALL_FIELDS}
        row.update({
            "id": cid,
            "vod": vod,
            "game": game,
            "start": _hms(start),
            "end": _hms(end),
            "source": f"{system}:{vod}#{rank}",
            "clutch_rank": str(rank),
            "clutch_score": "" if score == "" else str(score),
        })
        rows.append(row)
    return rows


def candidates_from_labels_v2(path: Path) -> list[dict[str, str]]:
    """Reuse eval/labels-v2.csv intervals as candidates; strip any prior rating as GT.

    Existing `rating`/`reason` columns are ignored for ground truth. They may be
    copied into notes only when already human-filled — we leave human fields blank
    so raters start clean.
    """
    rows: list[dict[str, str]] = []
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            row = {k: "" for k in ALL_FIELDS}
            row.update({
                "id": (r.get("id") or "").strip(),
                "vod": (r.get("vod") or "").strip(),
                "game": (r.get("game") or "").strip(),
                "start": (r.get("start") or "").strip(),
                "end": (r.get("end") or "").strip(),
                "source": (r.get("source") or "").strip(),
                "clutch_rank": "",
                "clutch_score": "",
            })
            # Do not copy rating into human rubric fields — that would launder Clutch scores as GT.
            rows.append(row)
    return rows


def export_label_sheet(rows: list[dict[str, str]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ALL_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in ALL_FIELDS})
    return path


def load_label_sheet(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def sheet_stats(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Census only — never invents ratings."""
    rubric_keys = ("hook", "stakes", "payoff", "reaction", "clarity", "novelty", "completeness")
    rated = sum(1 for r in rows if any((r.get(k) or "").strip() for k in rubric_keys))
    publish_filled = sum(1 for r in rows if (r.get("publish") or "").strip())
    return {
        "rows": len(rows),
        "vods": sorted({(r.get("vod") or "") for r in rows if r.get("vod")}),
        "human_rubric_partial_or_complete": rated,
        "publish_filled": publish_filled,
        "unrated": len(rows) - rated,
        "treats_clutch_score_as_gt": False,
    }
