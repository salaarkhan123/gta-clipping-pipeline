#!/usr/bin/env python3
"""CLI for Gaming Intelligence research helpers (offline).

Examples:
  python scripts/gaming_intelligence_cli.py export-sheet --from-labels-v2 eval/labels-v2.csv -o /tmp/gi-sheet.csv
  python scripts/gaming_intelligence_cli.py sheet-stats /tmp/gi-sheet.csv
  python scripts/gaming_intelligence_cli.py compare eval/gi-gta-label-sheet.csv
  python scripts/gaming_intelligence_cli.py audit
  python scripts/gaming_intelligence_cli.py init-dataset-a -o eval/datasets/dataset-a-template.csv
  python scripts/gaming_intelligence_cli.py init-dataset-b -o eval/datasets/dataset-b-template.csv
  python scripts/gaming_intelligence_cli.py agreement --primary a.csv --secondary b.csv
  python scripts/gaming_intelligence_cli.py decide
  python scripts/gaming_intelligence_cli.py cpu-bench -o /tmp/gi-cpu-bench.json
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
from scripts.gaming_intelligence.datasets_ab import (  # noqa: E402
    census_dataset_a,
    census_dataset_b,
    init_dataset_a_template,
    init_dataset_b_template,
    load_csv,
    validate_split_isolation,
    write_dataset_manifest,
)
from scripts.gaming_intelligence.report import (  # noqa: E402
    experiment_envelope,
    write_human_report,
    write_json_report,
)
from scripts.gaming_intelligence.stats import (  # noqa: E402
    agreement_report,
    decision_gates,
    pair_dual_rater_sheets,
)


def _audit_snapshot() -> dict:
    """Honest census of measured vs estimated vs blocked — no invented labels."""
    sheet = ROOT / "eval" / "gi-gta-label-sheet.csv"
    labels_v2 = ROOT / "eval" / "labels-v2.csv"
    bench2h = ROOT / "eval" / "benchmark-2h-labels.csv"
    wayin = ROOT / "eval" / "wayin-zias-iceman.csv"

    gi_stats = sheet_stats(load_label_sheet(sheet)) if sheet.is_file() else {"missing": True}
    v2_rated = 0
    if labels_v2.is_file():
        import csv
        with labels_v2.open(newline="") as f:
            for r in csv.DictReader(f):
                if (r.get("rating") or "").strip():
                    v2_rated += 1

    compare = evaluate_arms(load_label_sheet(sheet), min_rated=20) if sheet.is_file() else {
        "status": "blocked_no_sheet"
    }

    return {
        "kind": "research_audit_snapshot",
        "invented_results": False,
        "measured": {
            "gi_sheet_census": gi_stats,
            "labels_v2_rows_with_rating_field": v2_rated,
            "wayin_proxy_rows": sum(1 for _ in open(wayin)) - 1 if wayin.is_file() else 0,
            "benchmark_2h_exists": bench2h.is_file(),
            "compare_status": compare.get("status"),
            "gi_weights_default_zero": True,
            "gi_disabled_by_default": True,
        },
        "estimated_not_measured": [
            "GPU $/source-hour (list-price × assumed billed minutes)",
            "Full-VOD GI quality lift (no human labels)",
            "End-to-end detection recall on exhaustively annotated timelines",
        ],
        "blocked_metrics": [
            "Precision@5/@10 with human GT",
            "Recall vs independently annotated gameplay",
            "Ranking correlation with human ratings (claim-ready)",
            "Inter-rater agreement",
            "Paired source-level CI for A vs B",
        ],
        "human_labels_sufficient": False,
        "selection_bias_risks": [
            "gi-gta-label-sheet candidates come from ClutchClips proposals → proposal-biased precision",
            "Wayin sheet is competitor-overlap proxy, not gaming-quality GT",
            "YouNiverse pilot is reach-matched metadata; popularity ≠ highlight quality",
            "Single VOD (gta-online-1) → clips not independent for CI",
        ],
        "leakage_risks": [
            "Eval denylist VODs must stay out of training/calibration",
            "Do not tune GI weights on held-out labels",
            "Do not treat blank ratings as negatives",
        ],
        "decision_gates": compare.get("decision_gates") or decision_gates(
            agreement=None,
            baseline_measured=False,
            improvement=None,
            cost=None,
            generalization=None,
        ),
    }


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
    c.add_argument("--seed", type=int, default=42)
    c.add_argument("--json-out", type=Path, help="Write full machine-readable report")
    c.add_argument("--md-out", type=Path, help="Write concise human report")

    sub.add_parser("audit", help="Statistical audit snapshot (measured vs estimated vs blocked)")

    da = sub.add_parser("init-dataset-a", help="Write Dataset A template (blank; no invented engagement)")
    da.add_argument("-o", "--out", type=Path, required=True)
    da.add_argument("--manifest", type=Path, help="Optional manifest JSON path")

    db = sub.add_parser("init-dataset-b", help="Write Dataset B template (blank human fields)")
    db.add_argument("-o", "--out", type=Path, required=True)
    db.add_argument("--split", default="development", choices=["development", "held_out_eval"])
    db.add_argument("--manifest", type=Path, help="Optional manifest JSON path")

    dc = sub.add_parser("dataset-census", help="Census Dataset A or B CSV")
    dc.add_argument("which", choices=["A", "B"])
    dc.add_argument("sheet", type=Path)

    dv = sub.add_parser("validate-splits", help="Check Dataset B recording/streamer isolation")
    dv.add_argument("sheet", type=Path)

    ag = sub.add_parser("agreement", help="Dual-rater agreement (never fabricates)")
    ag.add_argument("--primary", type=Path, required=True)
    ag.add_argument("--secondary", type=Path, required=True)

    sub.add_parser("decide", help="Print decision gates (fail-closed without evidence)")

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
        report = evaluate_arms(rows, min_rated=args.min_rated, seed=args.seed)
        print(json.dumps(report, indent=2))
        if args.json_out or args.md_out:
            env = experiment_envelope(
                experiment_id="gi-abc-compare",
                dataset_version=str(args.sheet),
                source_recording_ids=sorted({(r.get("vod") or "") for r in rows if r.get("vod")}),
                model_id="gi-heuristic-v0",
                feature_config={"family_weights": "default_zero"},
                evaluation_methodology="fixed_pool_A_B_C_source_clustered",
                sample_size={
                    "n_rows": report.get("n_rows"),
                    "n_rated": report.get("n_rated"),
                    "n_independent_source_videos": report.get("n_independent_source_videos"),
                },
                metrics=report,
                random_seed=args.seed,
                known_limitations=report.get("notes") or [],
                code_version=None,
            )
            if args.json_out:
                write_json_report(env, args.json_out)
            if args.md_out:
                write_human_report(env, args.md_out)
        return 0

    if args.cmd == "audit":
        print(json.dumps(_audit_snapshot(), indent=2))
        return 0

    if args.cmd == "init-dataset-a":
        path = init_dataset_a_template(args.out)
        if args.manifest:
            write_dataset_manifest(
                args.manifest,
                dataset="A",
                version="v0-template",
                rows_path=str(path),
            )
        print(json.dumps({"out": str(path), **census_dataset_a(load_csv(path))}, indent=2))
        return 0

    if args.cmd == "init-dataset-b":
        path = init_dataset_b_template(args.out, default_split=args.split)
        if args.manifest:
            write_dataset_manifest(
                args.manifest,
                dataset="B",
                version="v0-template",
                rows_path=str(path),
            )
        print(json.dumps({"out": str(path), **census_dataset_b(load_csv(path))}, indent=2))
        return 0

    if args.cmd == "dataset-census":
        rows = load_csv(args.sheet)
        if args.which == "A":
            print(json.dumps(census_dataset_a(rows), indent=2))
        else:
            print(json.dumps(census_dataset_b(rows), indent=2))
        return 0

    if args.cmd == "validate-splits":
        print(json.dumps(validate_split_isolation(load_csv(args.sheet)), indent=2))
        return 0

    if args.cmd == "agreement":
        primary = load_label_sheet(args.primary)
        secondary = load_label_sheet(args.secondary)
        pairs = pair_dual_rater_sheets(primary, secondary)
        print(json.dumps(agreement_report(pairs), indent=2))
        return 0

    if args.cmd == "decide":
        snap = _audit_snapshot()
        print(json.dumps(snap["decision_gates"], indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
