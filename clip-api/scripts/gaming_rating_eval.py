#!/usr/bin/env python3
"""AS-1 offline helpers for gaming highlight-quality scores.

  sheet-stats  — census eval/gi-gta-label-sheet.csv (never invents ratings)
  ablate       — leave-one-out / zero-out composites for nine components

Honesty: composites are AI-quality math only. No NDCG / virality-% without human labels.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.gaming_rating import (  # noqa: E402
    GAMING_COMPONENTS,
    GAMING_LABELS,
    HONESTY,
    ablation_table,
    clean_components,
    composite,
)

# Human fields that must be filled before metrics (same spirit as GI sheet).
REQUIRED_FOR_RATED = (
    "quality_1_5",
    "entertainment_1_5",
    "context_1_5",
    "genuine_highlight",
    "clutch_correct",
)


def sheet_stats(path: Path) -> dict:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    rated = sum(1 for r in rows if all((r.get(k) or "").strip() for k in REQUIRED_FOR_RATED))
    partial = sum(
        1 for r in rows
        if not all((r.get(k) or "").strip() for k in REQUIRED_FOR_RATED)
        and any((r.get(k) or "").strip() for k in REQUIRED_FOR_RATED)
    )
    return {
        "sheet": str(path),
        "rows": len(rows),
        "human_rated_complete": rated,
        "human_partial": partial,
        "unrated": len(rows) - rated - partial,
        "treats_clutch_score_as_gt": False,
        "metrics_ready": rated > 0,
        "ndcg_claimed": False,
        "virality_percent_claimed": False,
        "honesty": HONESTY,
        "gaming_components": list(GAMING_COMPONENTS),
        "required_for_rated": list(REQUIRED_FOR_RATED),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sheet-stats", help="Census a GI / gaming label sheet")
    s.add_argument("sheet", type=Path)

    a = sub.add_parser("ablate", help="Print ablation table for one component vector")
    for k in GAMING_COMPONENTS:
        a.add_argument(f"--{k}", type=float, required=True, help=GAMING_LABELS[k])

    args = p.parse_args(argv)

    if args.cmd == "sheet-stats":
        print(json.dumps(sheet_stats(args.sheet), indent=2))
        return 0

    if args.cmd == "ablate":
        comps = {k: getattr(args, k) for k in GAMING_COMPONENTS}
        cleaned = clean_components(comps)
        out = {
            "components": cleaned,
            "composite": composite(cleaned),
            "ablation": ablation_table(cleaned or {}),
            "honesty": HONESTY,
        }
        print(json.dumps(out, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
