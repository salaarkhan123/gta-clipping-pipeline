"""CLI: python -m scripts.gaming_phase1 <command> ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python -m scripts.gaming_phase1` from clip-api/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _print(data) -> int:
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def cmd_pin(_args) -> int:
    from scripts.gaming_phase1.baseline import load_pin
    from app.pipeline import WEIGHTS
    from app.pipeline.layouts import HUD_REGIONS

    pin = load_pin()
    pin.assert_matches_runtime(WEIGHTS, HUD_REGIONS)
    return _print({
        "ok": True,
        "pin": {
            "name": pin.name,
            "selector_merge_sha": pin.selector_merge_sha,
            "production_weights": pin.production_weights,
            "experimental_weights_remain_zero": pin.experimental_weights_remain_zero,
            "hud_regions_empty": pin.hud_regions == {},
        },
    })


def cmd_inventory(_args) -> int:
    from scripts.gaming_phase1.inventory import inventory_eval_set

    return _print(inventory_eval_set().as_dict())


def cmd_baseline(args) -> int:
    from scripts.gaming_phase1.baseline import candidate_fingerprint, select_b0

    video = Path(args.video)
    range_sec = None
    if args.start is not None or args.end is not None:
        if args.start is None or args.end is None:
            raise SystemExit("--start and --end are required together")
        range_sec = {"start": float(args.start), "end": float(args.end)}

    first = select_b0(
        video,
        max_clips=args.max_clips,
        clip_length=args.clip_length,
        range_sec=range_sec,
    )
    second = None
    if args.repeat:
        second = select_b0(
            video,
            max_clips=args.max_clips,
            clip_length=args.clip_length,
            range_sec=range_sec,
        )
        if first["fingerprint"] != second["fingerprint"]:
            raise SystemExit("B0 fingerprint mismatch across repeated runs")

    if args.out:
        Path(args.out).write_text(json.dumps(first, indent=2) + "\n")

    return _print({
        "ok": True,
        "fingerprint": first["fingerprint"],
        "n_clips": len(first["clips"]),
        "clips": first["clips"],
        "deterministic": True if second is None else first["fingerprint"] == second["fingerprint"],
        "paid_model_calls": first["paid_model_calls"],
        "out": args.out,
    })


def cmd_signals(args) -> int:
    from scripts.gaming_phase1.signals import measure_signals

    report = measure_signals(
        Path(args.video),
        start=float(args.start),
        length=float(args.length),
        chat_region=args.chat_region,
    )
    return _print(report.as_dict())


def cmd_metrics_demo(_args) -> int:
    from scripts.gaming_phase1.metrics import boundary_errors, event_confusion, ndcg_at_k

    # Synthetic only: proves metric wiring; not a quality claim.
    labels = [(20, {"gunshot"}), (21, {"gunshot"}), (30, {"ordinary"})]
    preds = [(20, "gunshot"), (40, "gunshot")]
    return _print({
        "event_gunshot": event_confusion(preds, labels, positive_class="gunshot"),
        "ndcg_at_5_example": ndcg_at_k([3, 0, 1], [3, 1], k=5),
        "boundaries": boundary_errors([(19.0, 24.0)], [(20.0, 23.0)]),
        "note": "Synthetic demo only; do not treat as gaming quality evidence.",
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gaming_phase1", description="Phase 1 gaming research harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pin", help="Verify runtime WEIGHTS match the frozen baseline pin")
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("inventory", help="Census eval sheets and geometry without fabricating ratings")
    p.set_defaults(func=cmd_inventory)

    p = sub.add_parser("baseline", help="Run B0 production selection and optionally check determinism")
    p.add_argument("video", type=Path)
    p.add_argument("--max-clips", type=int, default=5)
    p.add_argument("--clip-length", type=int, default=10)
    p.add_argument("--start", type=float, default=None)
    p.add_argument("--end", type=float, default=None)
    p.add_argument("--repeat", action="store_true")
    p.add_argument("--out", type=str, default=None)
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("signals", help="Shadow-measure audio/flux/bursts and keyframe decode cost")
    p.add_argument("video", type=Path)
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--length", type=float, default=40.0)
    p.add_argument("--chat-region", default="none")
    p.set_defaults(func=cmd_signals)

    p = sub.add_parser("metrics-demo", help="Run synthetic metric checks")
    p.set_defaults(func=cmd_metrics_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
