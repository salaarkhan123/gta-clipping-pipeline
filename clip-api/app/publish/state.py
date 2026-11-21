"""Scheduled post status machine. Illegal transitions raise; callers map to ApiError."""
from . import ACTIVE_UPLOAD, EDITABLE, TERMINAL

# from_status -> allowed next statuses
TRANSITIONS: dict[str, frozenset[str]] = {
    "SCHEDULED": frozenset({"QUEUED", "CANCELED", "FAILED"}),  # FAILED = missed_schedule / reconnect
    "QUEUED": frozenset({"UPLOADING", "FAILED", "CANCELED"}),
    "UPLOADING": frozenset({"PROCESSING", "PUBLISHED", "FAILED", "QUEUED"}),  # QUEUED = retry transfer
    "PROCESSING": frozenset({"PUBLISHED", "FAILED"}),
    "PUBLISHED": frozenset(),
    "FAILED": frozenset({"QUEUED"}),  # explicit customer retry
    "CANCELED": frozenset(),
}


def can_transition(current: str, nxt: str) -> bool:
    return nxt in TRANSITIONS.get(current, frozenset())


def advance(current: str, nxt: str) -> str:
    if not can_transition(current, nxt):
        raise ValueError(f"illegal post transition {current} -> {nxt}")
    return nxt


def can_edit(status: str) -> bool:
    return status in EDITABLE


def can_cancel(status: str) -> bool:
    return status in EDITABLE or status == "QUEUED"


def can_retry(status: str, error_code: str | None) -> bool:
    if status != "FAILED":
        return False
    # Never auto-retry final-call ambiguity or validation failures.
    return error_code not in (
        "outcome_unknown", "validation_rejected", "permission_denied", "quota_exhausted",
        "clip_unfit", "export_required", "rights_required",
    )


def is_terminal(status: str) -> bool:
    return status in TERMINAL


def is_in_flight(status: str) -> bool:
    return status in ACTIVE_UPLOAD
