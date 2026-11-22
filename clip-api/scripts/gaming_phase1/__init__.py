"""Phase 1 gaming-intelligence research harness (offline only).

Freezes the production selector as B0, inventories existing signals, and scores
research metrics without changing production ranking weights.
"""

from .baseline import BaselinePin, candidate_fingerprint, load_pin, select_b0
from .inventory import EvalInventory, inventory_eval_set
from .metrics import (
    boundary_errors,
    event_confusion,
    ndcg_at_k,
    precision_recall_f1,
)
from .signals import SignalReport, measure_signals

__all__ = [
    "BaselinePin",
    "EvalInventory",
    "SignalReport",
    "boundary_errors",
    "candidate_fingerprint",
    "event_confusion",
    "inventory_eval_set",
    "load_pin",
    "measure_signals",
    "ndcg_at_k",
    "precision_recall_f1",
    "select_b0",
]
