#!/usr/bin/env python3
"""AS-1 eval scaffolding for gaming highlight quality — not a second scorer.

Reads `eval/gi-gta-label-sheet.csv` (and optionally joins editorial sub-scores from a run JSON).
Reports whether labelled metrics are ready. Refuses NDCG / precision claims when human ratings
are empty. The product score path stays `app/ai.py` + `pipeline/ranking.py`.

Usage (from clip-api/):
  python scripts/gaming_rating_eval.py sheet-stats
  python scripts/gaming_rating_eval.py sheet-stats eval/gi-gta-label-sheet.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHEET = ROOT / "eval" / "gi-gta-label-sheet.csv"

# Columns that mean a human finished a row (any one filled counts as rated for readiness).
HUMAN_FIELDS = (
    "quality_1_5",
    "entertainment_1_5",
    "context_1_5",
    "genuine_highlight",
    "clutch_correct",
)


def _filled(row: dict, key: str) -> bool:
    return bool(str(row.get(key) or "").strip())


def sheet_stats(path: Path) -> dict:
    if not path.is_file():
        return {"ok": False, "error": f"missing sheet: {path}", "metrics_ready": False}
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rated = [r for r in rows if any(_filled(r, k) for k in HUMAN_FIELDS)]
    games = sorted({(r.get("game") or "").strip() for r in rows if (r.get("game") or "").strip()})
    ready = len(rated) > 0
    out = {
        "ok": True,
        "sheet": str(path),
        "rows": len(rows),
        "rated_rows": len(rated),
        "unrated_rows": len(rows) - len(rated),
        "games": games,
        "metrics_ready": ready,
        "ndcg_claimed": False,
        "precision_claimed": False,
        "note": (
            "Human ratings present — run labelled compare offline; do not invent virality %."
            if ready
            else "No human ratings yet. metrics_ready=false; do not claim NDCG, precision@k, or virality %."
        ),
        "score_path": "app.ai + app.pipeline.ranking (five editorial sub-scores); no parallel scorer",
    }
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    stats = sub.add_parser("sheet-stats", help="Count labelled rows; refuse metric claims when empty")
    stats.add_argument("sheet", nargs="?", type=Path, default=DEFAULT_SHEET)
    args = p.parse_args(argv)
    if args.cmd == "sheet-stats":
        result = sheet_stats(args.sheet)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
