"""Gaming Intelligence (GI) research hooks — disabled by default.

Integrates candidate timestamps with optional structured features, cache, and
offline re-rank helpers. When `enabled` is false (the default), every public
entry point is a no-op that returns the input candidates unchanged.

Hard rules:
- Does not raise production WEIGHTS or touch HUD_REGIONS.
- Does not emit a virality probability or view forecast.
- Experiments stay off unless the caller sets enabled=True (or GI_ENABLED=1).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Research feature families. All default contributions are 0.0 so enabling the
# module without raising a family weight cannot reorder candidates.
FEATURE_FAMILIES = (
    "audio_named",   # YAMNet-class scores (external adapter; weight 0)
    "hud_ocr",       # HUD text events (external adapter; weight 0)
    "dialogue",      # transcript setup/payoff hints
    "visual",        # CLIP / sparse vision corroboration
    "reaction",      # chat_motion / facecam proxies
)

DEFAULT_FAMILY_WEIGHTS: dict[str, float] = {k: 0.0 for k in FEATURE_FAMILIES}


def env_enabled() -> bool:
    """True only when GI_ENABLED is an explicit truthy string."""
    return os.environ.get("GI_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class GIConfig:
    """Runtime knobs. Defaults keep production selection byte-identical."""
    enabled: bool = False
    family_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_FAMILY_WEIGHTS))
    cache_dir: Path | None = None
    max_candidates: int = 100

    @classmethod
    def from_env(cls, *, cache_dir: Path | None = None) -> "GIConfig":
        return cls(enabled=env_enabled(), cache_dir=cache_dir)


@dataclass
class CandidateFeatures:
    """Structured per-candidate GI payload (research sidecar)."""
    start_sec: float
    end_sec: float
    baseline_rank: int | None = None
    baseline_score: float | None = None
    families: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    gi_score: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GIResult:
    """Output of a GI pass. `candidates` mirrors input order when disabled or all weights 0."""
    enabled: bool
    candidates: list[dict[str, Any]]
    features: list[CandidateFeatures]
    cache_key: str | None
    metrics: dict[str, Any]
    elapsed_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "candidates": self.candidates,
            "features": [f.as_dict() for f in self.features],
            "cache_key": self.cache_key,
            "metrics": self.metrics,
            "elapsed_ms": self.elapsed_ms,
        }


def _interval_key(c: dict[str, Any]) -> tuple[float, float]:
    start = float(c.get("start_sec", c.get("start", 0.0)))
    end = float(c.get("end_sec", c.get("end", start)))
    return round(start, 3), round(end, 3)


def cache_key_for(
    candidates: list[dict[str, Any]],
    *,
    model_id: str = "gi-heuristic-v0",
    family_weights: dict[str, float] | None = None,
) -> str:
    """Stable cache key from candidate PTS + model id + weights."""
    rows = [{"start": s, "end": e} for s, e in (_interval_key(c) for c in candidates)]
    payload = {
        "model_id": model_id,
        "weights": family_weights or DEFAULT_FAMILY_WEIGHTS,
        "intervals": rows,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _read_cache(cache_dir: Path, key: str) -> dict[str, Any] | None:
    path = cache_dir / f"{key}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(cache_dir: Path, key: str, payload: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def extract_family_scores(candidate: dict[str, Any]) -> dict[str, float]:
    """Pull optional research scores from a candidate dict; missing → 0.0.

    Expected optional keys (all research; never required on main path):
      gi_audio_named, gi_hud_ocr, gi_dialogue, gi_visual, gi_reaction
    or nested candidate["gi"][family].
    """
    nested = candidate.get("gi") if isinstance(candidate.get("gi"), dict) else {}
    aliases = {
        "audio_named": ("gi_audio_named", "audio_named"),
        "hud_ocr": ("gi_hud_ocr", "hud_ocr"),
        "dialogue": ("gi_dialogue", "dialogue"),
        "visual": ("gi_visual", "visual"),
        "reaction": ("gi_reaction", "reaction"),
    }
    out: dict[str, float] = {}
    for family, keys in aliases.items():
        val = nested.get(family)
        if val is None:
            for k in keys:
                if k in candidate:
                    val = candidate[k]
                    break
        try:
            out[family] = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            out[family] = 0.0
    return out


def combine_score(
    baseline: float,
    families: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Weighted sum of family scores added to baseline. Zero weights → baseline."""
    bump = sum(float(weights.get(k, 0.0)) * float(families.get(k, 0.0)) for k in FEATURE_FAMILIES)
    return round(baseline + bump, 4)


def annotate_candidates(
    candidates: list[dict[str, Any]],
    *,
    weights: dict[str, float] | None = None,
) -> list[CandidateFeatures]:
    """Build structured features for each candidate (does not reorder)."""
    w = {**DEFAULT_FAMILY_WEIGHTS, **(weights or {})}
    features: list[CandidateFeatures] = []
    for i, c in enumerate(candidates):
        start, end = _interval_key(c)
        baseline = float(c.get("score") or c.get("rank_score") or 0.0)
        families = extract_family_scores(c)
        features.append(CandidateFeatures(
            start_sec=start,
            end_sec=end,
            baseline_rank=c.get("rank") if c.get("rank") is not None else i + 1,
            baseline_score=baseline,
            families=families,
            evidence={"source_keys": sorted(k for k in c if k.startswith("gi") or k == "gi")},
            gi_score=combine_score(baseline, families, w),
        ))
    return features


def rerank(
    candidates: list[dict[str, Any]],
    features: list[CandidateFeatures],
    *,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return candidates reordered by gi_score when any family weight > 0.

    When all weights are 0, returns a shallow copy in the original order.
    """
    w = {**DEFAULT_FAMILY_WEIGHTS, **(weights or {})}
    if not any(v > 0 for v in w.values()):
        return [dict(c) for c in candidates]
    scored = []
    for c, f in zip(candidates, features):
        row = dict(c)
        row["gi_score"] = f.gi_score
        row["gi_families"] = dict(f.families)
        scored.append(row)
    scored.sort(key=lambda r: (-float(r.get("gi_score") or 0.0), float(r.get("start_sec", r.get("start", 0.0)))))
    for i, row in enumerate(scored, 1):
        row["gi_rank"] = i
    return scored


def apply_gi(
    candidates: list[dict[str, Any]],
    *,
    config: GIConfig | None = None,
    model_id: str = "gi-heuristic-v0",
) -> GIResult:
    """Main hook. Disabled → identity pass with empty metrics."""
    cfg = config or GIConfig()
    t0 = time.perf_counter()
    capped = list(candidates[: cfg.max_candidates])

    if not cfg.enabled:
        return GIResult(
            enabled=False,
            candidates=[dict(c) for c in capped],
            features=[],
            cache_key=None,
            metrics={"skipped": True, "reason": "gi_disabled"},
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
        )

    key = cache_key_for(capped, model_id=model_id, family_weights=cfg.family_weights)
    if cfg.cache_dir is not None:
        hit = _read_cache(cfg.cache_dir, key)
        if hit is not None:
            feats = [CandidateFeatures(**f) for f in hit.get("features", [])]
            return GIResult(
                enabled=True,
                candidates=hit.get("candidates", capped),
                features=feats,
                cache_key=key,
                metrics={"cache_hit": True, "n": len(capped)},
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )

    features = annotate_candidates(capped, weights=cfg.family_weights)
    ordered = rerank(capped, features, weights=cfg.family_weights)
    metrics = {
        "cache_hit": False,
        "n": len(capped),
        "nonzero_family_weights": sorted(k for k, v in cfg.family_weights.items() if v > 0),
        "order_changed": [ _interval_key(a) for a in ordered ] != [ _interval_key(b) for b in capped ],
    }
    result = GIResult(
        enabled=True,
        candidates=ordered,
        features=features,
        cache_key=key,
        metrics=metrics,
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
    )
    if cfg.cache_dir is not None:
        _write_cache(cfg.cache_dir, key, result.as_dict())
    return result


def maybe_rerank_moments(
    moments: list[Any],
    *,
    enabled: bool | None = None,
    family_weights: dict[str, float] | None = None,
    cache_dir: Path | None = None,
) -> list[Any]:
    """Optional pipeline seam: convert Moment-like objects ↔ dicts for apply_gi.

    When disabled (default), returns `moments` unchanged (same list object).
    """
    on = env_enabled() if enabled is None else enabled
    if not on:
        return moments
    rows = []
    for i, m in enumerate(moments):
        if isinstance(m, dict):
            rows.append(dict(m))
            continue
        rows.append({
            "start_sec": float(getattr(m, "start", 0.0)),
            "end_sec": float(getattr(m, "end", getattr(m, "start", 0.0))),
            "score": float(getattr(m, "score", 0.0) or 0.0),
            "rank": i + 1,
            "kind": getattr(m, "kind", None),
            "gi": getattr(m, "gi", None) or {},
        })
    cfg = GIConfig(enabled=True, family_weights={**DEFAULT_FAMILY_WEIGHTS, **(family_weights or {})}, cache_dir=cache_dir)
    result = apply_gi(rows, config=cfg)
    # Research-only: when moments are plain dicts, return reordered dicts.
    if moments and isinstance(moments[0], dict):
        return result.candidates
    # Object moments: reorder by matching intervals; leave objects intact.
    by_key = {(_interval_key(c)): c for c in result.candidates}
    ordered = []
    used = set()
    for c in result.candidates:
        k = _interval_key(c)
        for m in moments:
            mk = (round(float(getattr(m, "start", 0.0)), 3), round(float(getattr(m, "end", 0.0)), 3))
            if mk == k and id(m) not in used:
                ordered.append(m)
                used.add(id(m))
                break
        _ = by_key  # silence lint for unused in object path
    # Append any unmatched originals to preserve length.
    for m in moments:
        if id(m) not in used:
            ordered.append(m)
    return ordered
