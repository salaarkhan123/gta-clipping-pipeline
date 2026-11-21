"""Dataset A (online reference) and Dataset B (ClutchClips evaluation) specs.

Templates and validators only — never invent engagement, ratings, or media.
Permissioned content only. Popularity ≠ ground-truth highlight quality.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

TARGET_GAMES = (
    "gta",
    "warzone",
    "fortnite",
    "valorant",
    "counter-strike-2",
)

CLIPS_PER_GAME_TARGET = 30

# Dataset A — successful published reference clips (characteristic study only).
DATASET_A_FIELDS = (
    "clip_id",
    "game",
    "platform",              # twitch|youtube|tiktok|kick|other
    "source_url_or_id",      # opaque id preferred in git; full URL private
    "permission_record_id",  # consent / license pointer (never fabricate)
    "publisher_date",
    "creator_pseudonym",
    "creator_audience_size_at_post",  # if known; blank if unknown — never invent
    "views",
    "likes",
    "engagement_age_days",   # age at which engagement was recorded
    "duration_sec",
    "editing_characteristics",  # captions|cuts|music|facecam|montage|raw|unknown
    "confounders",           # free text: thumbnail, title clickbait, collab, …
    "notes",
    "split",                 # not used for training GT; optional exploratory strata
)

# Dataset B — ClutchClips candidates from permitted raw gameplay.
DATASET_B_FIELDS = (
    "clip_id",
    "game",
    "source_recording_id",
    "streamer_id",           # pseudonym; used for separation
    "start_sec",
    "end_sec",
    "model_version",
    "code_version",
    "detector_scores_json",  # serialized baseline / GI family scores
    "candidate_source",      # baseline|gi|grid|gap_hunt|ordinary_draw
    "is_ordinary_or_weak",   # yes|no — deliberately include non-highlights
    "split",                 # development|held_out_eval
    "permission_record_id",
    # Human ratings (blank until labelled; never auto-filled)
    "entertainment_1_5",
    "gameplay_significance_1_5",
    "opening_hook_1_5",
    "context_1_5",
    "editing_suitability_1_5",
    "genuine_highlight",     # yes|no|maybe
    "rater",
    "rated_at",
    "notes",
)

SPLIT_VALUES = ("development", "held_out_eval")


def empty_row(fields: tuple[str, ...]) -> dict[str, str]:
    return {k: "" for k in fields}


def init_dataset_a_template(path: Path, *, games: tuple[str, ...] = TARGET_GAMES) -> Path:
    """Write header + placeholder rows (blank). Does not invent engagement values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for game in games:
        for i in range(1, CLIPS_PER_GAME_TARGET + 1):
            row = empty_row(DATASET_A_FIELDS)
            row["clip_id"] = f"A-{game}-{i:02d}"
            row["game"] = game
            rows.append(row)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DATASET_A_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def init_dataset_b_template(
    path: Path,
    *,
    games: tuple[str, ...] = TARGET_GAMES,
    default_split: str = "development",
) -> Path:
    if default_split not in SPLIT_VALUES:
        raise ValueError(f"split must be one of {SPLIT_VALUES}")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for game in games:
        for i in range(1, CLIPS_PER_GAME_TARGET + 1):
            row = empty_row(DATASET_B_FIELDS)
            row["clip_id"] = f"B-{game}-{i:02d}"
            row["game"] = game
            row["split"] = default_split
            row["is_ordinary_or_weak"] = ""  # must be set when candidates are generated
            rows.append(row)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DATASET_B_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def census_dataset_a(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_game: dict[str, int] = {}
    with_permission = 0
    with_engagement = 0
    filled = 0
    for r in rows:
        g = (r.get("game") or "").strip() or "_none"
        by_game[g] = by_game.get(g, 0) + 1
        if (r.get("permission_record_id") or "").strip():
            with_permission += 1
        if (r.get("views") or "").strip() or (r.get("likes") or "").strip():
            with_engagement += 1
        # A row is "ingested" when permission + source + game present
        if all((r.get(k) or "").strip() for k in ("permission_record_id", "source_url_or_id", "game")):
            filled += 1
    return {
        "dataset": "A",
        "purpose": "online_reference_characteristics_only",
        "not_ground_truth_highlight_quality": True,
        "rows": len(rows),
        "ingested_with_permission": filled,
        "with_engagement_fields": with_engagement,
        "with_permission_record": with_permission,
        "by_game": by_game,
        "target_per_game": CLIPS_PER_GAME_TARGET,
        "target_games": list(TARGET_GAMES),
        "pilot_complete": all(by_game.get(g, 0) >= CLIPS_PER_GAME_TARGET for g in TARGET_GAMES) and filled >= CLIPS_PER_GAME_TARGET * len(TARGET_GAMES),
    }


def census_dataset_b(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_game: dict[str, int] = {}
    by_split: dict[str, int] = {}
    recordings: set[str] = set()
    streamers: set[str] = set()
    rated = 0
    ordinary = 0
    for r in rows:
        g = (r.get("game") or "").strip() or "_none"
        by_game[g] = by_game.get(g, 0) + 1
        sp = (r.get("split") or "").strip() or "_unset"
        by_split[sp] = by_split.get(sp, 0) + 1
        if (r.get("source_recording_id") or "").strip():
            recordings.add(r["source_recording_id"].strip())
        if (r.get("streamer_id") or "").strip():
            streamers.add(r["streamer_id"].strip())
        if (r.get("is_ordinary_or_weak") or "").strip().lower() == "yes":
            ordinary += 1
        if _b_rated(r):
            rated += 1
    return {
        "dataset": "B",
        "purpose": "clutchclips_highlight_evaluation",
        "rows": len(rows),
        "human_rated_complete": rated,
        "ordinary_or_weak_marked": ordinary,
        "unique_source_recordings": len(recordings),
        "unique_streamers": len(streamers),
        "by_game": by_game,
        "by_split": by_split,
        "target_per_game": CLIPS_PER_GAME_TARGET,
        "target_games": list(TARGET_GAMES),
        "held_out_must_not_train": True,
    }


def _b_rated(r: dict[str, str]) -> bool:
    need = (
        "entertainment_1_5",
        "gameplay_significance_1_5",
        "opening_hook_1_5",
        "context_1_5",
        "editing_suitability_1_5",
        "genuine_highlight",
    )
    return all((r.get(k) or "").strip() for k in need)


def validate_split_isolation(
    rows: list[dict[str, str]],
    *,
    recording_key: str = "source_recording_id",
    streamer_key: str = "streamer_id",
) -> dict[str, Any]:
    """Ensure no source recording (and preferably streamer) appears in both splits."""
    rec_splits: dict[str, set[str]] = {}
    streamer_splits: dict[str, set[str]] = {}
    for r in rows:
        sp = (r.get("split") or "").strip()
        if sp not in SPLIT_VALUES:
            continue
        rid = (r.get(recording_key) or "").strip()
        sid = (r.get(streamer_key) or "").strip()
        if rid:
            rec_splits.setdefault(rid, set()).add(sp)
        if sid:
            streamer_splits.setdefault(sid, set()).add(sp)
    leaked_recordings = sorted(k for k, v in rec_splits.items() if len(v) > 1)
    leaked_streamers = sorted(k for k, v in streamer_splits.items() if len(v) > 1)
    return {
        "recording_leakage": leaked_recordings,
        "streamer_leakage": leaked_streamers,
        "ok": len(leaked_recordings) == 0,
        "streamer_separation_ok": len(leaked_streamers) == 0,
        "message": (
            "Splits isolated by source recording."
            if not leaked_recordings
            else f"LEAKAGE: recordings in both splits: {leaked_recordings}"
        ),
    }


def assign_held_out_by_recording(
    rows: list[dict[str, str]],
    *,
    held_out_recording_ids: set[str],
) -> list[dict[str, str]]:
    """Return copies with split set from recording membership. No random invent."""
    out = []
    for r in rows:
        row = dict(r)
        rid = (row.get("source_recording_id") or "").strip()
        if rid and rid in held_out_recording_ids:
            row["split"] = "held_out_eval"
        elif rid:
            row["split"] = "development"
        out.append(row)
    return out


def write_dataset_manifest(
    path: Path,
    *,
    dataset: str,
    version: str,
    rows_path: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    payload = {
        "dataset": dataset,
        "version": version,
        "rows_path": rows_path,
        "games": list(TARGET_GAMES),
        "clips_per_game_target": CLIPS_PER_GAME_TARGET,
        "popularity_is_not_gt": dataset == "A",
        "held_out_labels_must_not_train": dataset == "B",
        **(extra or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path
