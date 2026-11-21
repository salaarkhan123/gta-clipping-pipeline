"""Gaming Intelligence offline eval helpers (research). Experiments off by default."""
from .bench import estimate_gpu_cost, write_cpu_bench_stub
from .compare import evaluate_arms
from .dataset import (
    CANDIDATE_FIELDS,
    HUMAN_FIELDS,
    candidates_from_run,
    export_label_sheet,
    load_label_sheet,
    sheet_stats,
)

__all__ = [
    "CANDIDATE_FIELDS",
    "HUMAN_FIELDS",
    "candidates_from_run",
    "export_label_sheet",
    "load_label_sheet",
    "sheet_stats",
    "estimate_gpu_cost",
    "write_cpu_bench_stub",
    "evaluate_arms",
]
