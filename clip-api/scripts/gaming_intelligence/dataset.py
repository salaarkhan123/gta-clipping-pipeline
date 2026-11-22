"""Phase 4 — GTA eval dataset from existing pipeline candidates.

Candidates come from run JSON / labels-v2 rows. Human fields start empty.
ClutchClips AI ratings and ranks are **not** ground truth — they are proposals
for a human to rate. Do not fabricate ratings.
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

# Human labels for GI evaluation (owner request 2026-11-21). Empty until filled.
# Scales are 1–5 unless noted. Do not copy clutch_score into these fields.
HUMAN_FIELDS = (
    "quality_1_5",          # highlight quality
    "entertainment_1_5",    # entertainment value
    "context_1_5",          # context / understandability
    "suitable_tiktok",      # yes|no|maybe
    "suitable_shorts",      # yes|no|maybe
    "suitable_reels",       # yes|no|maybe
    "genuine_highlight",    # yes|no|maybe — is this a real gaming highlight?
    "clutch_correct",       # yes|no|maybe — did ClutchClips correctly identify it?
    "event_tags",           # free text: gunfight,crash,dialogue,...
    "notes",
    "rater",
    "rated_at",
)

# Legacy research rubric (0–3) kept for optional side studies; not required for GI v1 eval.
LEGACY_RUBRIC_FIELDS = (
    "hook", "stakes", "payoff", "reaction", "clarity", "novelty", "completeness", "publish",
)

ALL_FIELDS = CANDIDATE_FIELDS + HUMAN_FIELDS

# Fields that must be non-empty for a row to count as "human-rated" for metrics.
REQUIRED_FOR_RATED = (
    "quality_1_5",
    "entertainment_1_5",
    "context_1_5",
    "genuine_highlight",
    "clutch_correct",
)


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
    """Reuse eval/labels-v2.csv intervals as candidates; strip any prior rating as GT."""
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
            rows.append(row)
    return rows


def migrate_sheet_row(old: dict[str, str]) -> dict[str, str]:
    """Map an older GI sheet row onto the current schema without inventing ratings."""
    row = {k: "" for k in ALL_FIELDS}
    for k in CANDIDATE_FIELDS:
        if k in old:
            row[k] = (old.get(k) or "").strip()
    for k in HUMAN_FIELDS:
        if k in old and (old.get(k) or "").strip():
            row[k] = (old.get(k) or "").strip()
    # Do not auto-translate legacy 0–3 rubric into 1–5 — that would invent values.
    return row


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
        raw = list(csv.DictReader(f))
    # Accept legacy headers by migrating each row.
    return [migrate_sheet_row(r) for r in raw]


def is_rated(row: dict[str, str]) -> bool:
    return all((row.get(k) or "").strip() for k in REQUIRED_FOR_RATED)


def sheet_stats(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Census only — never invents ratings."""
    rated = sum(1 for r in rows if is_rated(r))
    partial = sum(
        1 for r in rows
        if not is_rated(r) and any((r.get(k) or "").strip() for k in HUMAN_FIELDS)
    )
    return {
        "rows": len(rows),
        "vods": sorted({(r.get("vod") or "") for r in rows if r.get("vod")}),
        "human_rated_complete": rated,
        "human_partial": partial,
        "unrated": len(rows) - rated - partial,
        "treats_clutch_score_as_gt": False,
        "required_for_rated": list(REQUIRED_FOR_RATED),
        "metrics_ready": rated > 0,
    }
