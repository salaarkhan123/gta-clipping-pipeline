#!/usr/bin/env python3
"""CLI for Gaming Intelligence research helpers (offline).

Examples:
  python scripts/gaming_intelligence_cli.py export-sheet --from-labels-v2 eval/labels-v2.csv -o /tmp/gi-sheet.csv
  python scripts/gaming_intelligence_cli.py sheet-stats /tmp/gi-sheet.csv
  python scripts/gaming_intelligence_cli.py cpu-bench -o /tmp/gi-cpu-bench.json
  python scripts/gaming_intelligence_cli.py estimate-gpu --sku l4 --minutes 15
  python scripts/gaming_intelligence_cli.py gpu-plan
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gaming_intelligence.bench import (  # noqa: E402
    estimate_gpu_cost,
    reproducible_gpu_bench_plan,
    write_cpu_bench_stub,
)
from scripts.gaming_intelligence.compare import evaluate_arms  # noqa: E402
from scripts.gaming_intelligence.dataset import (  # noqa: E402
    candidates_from_labels_v2,
    candidates_from_run,
    export_label_sheet,
    load_label_sheet,
    sheet_stats,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export-sheet", help="Export human label sheet from candidates")
    src = e.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-labels-v2", type=Path, help="Reuse eval/labels-v2.csv intervals")
    src.add_argument("--from-run", type=Path, help="Pipeline/job run JSON")
    e.add_argument("--vod", default="gta-online-1")
    e.add_argument("--game", default="gta-online")
    e.add_argument("-o", "--out", type=Path, required=True)

    s = sub.add_parser("sheet-stats", help="Census a label sheet (no invented ratings)")
    s.add_argument("sheet", type=Path)

    b = sub.add_parser("cpu-bench", help="MEASURED hook overhead on synthetic candidates")
    b.add_argument("-o", "--out", type=Path, required=True)
    b.add_argument("--n", type=int, default=40, help="synthetic candidate count")
    b.add_argument("--repeats", type=int, default=50)

    g = sub.add_parser("estimate-gpu", help="ESTIMATE compute $ from list prices")
    g.add_argument("--sku", default="l4", choices=["cpu_c6", "l4", "rtx4090", "l40s", "rtx5090"])
    g.add_argument("--minutes", type=float, default=15.0, help="billed minutes per source hour (assumption)")
    g.add_argument("--hours", type=float, default=1.0)

    sub.add_parser("gpu-plan", help="Print reproducible L4 bench plan (no provision)")

    c = sub.add_parser("compare", help="A/B/C metrics (blocked until human labels exist)")
    c.add_argument("sheet", type=Path)
    c.add_argument("--min-rated", type=int, default=20)

    args = p.parse_args(argv)

    if args.cmd == "export-sheet":
        if args.from_labels_v2:
            rows = candidates_from_labels_v2(args.from_labels_v2)
        else:
            rows = candidates_from_run(args.from_run, vod=args.vod, game=args.game)
        path = export_label_sheet(rows, args.out)
        print(json.dumps({"out": str(path), **sheet_stats(rows)}, indent=2))
        return 0

    if args.cmd == "sheet-stats":
        print(json.dumps(sheet_stats(load_label_sheet(args.sheet)), indent=2))
        return 0

    if args.cmd == "cpu-bench":
        cands = [
            {"start_sec": float(i * 30), "end_sec": float(i * 30 + 25), "score": float(100 - i), "rank": i + 1}
            for i in range(args.n)
        ]
        print(json.dumps(write_cpu_bench_stub(cands, args.out, repeats=args.repeats), indent=2))
        return 0

    if args.cmd == "estimate-gpu":
        print(json.dumps(estimate_gpu_cost(
            sku=args.sku,
            billed_minutes_per_source_hour=args.minutes,
            source_hours=args.hours,
        ), indent=2))
        return 0

    if args.cmd == "gpu-plan":
        print(json.dumps(reproducible_gpu_bench_plan(), indent=2))
        return 0

    if args.cmd == "compare":
        rows = load_label_sheet(args.sheet)
        print(json.dumps(evaluate_arms(rows, min_rated=args.min_rated), indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
