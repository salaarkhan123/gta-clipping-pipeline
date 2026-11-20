#!/usr/bin/env python3
"""Check the judge's five sub-scores against the owner's labels, and fit per-game ranking weights from them.

Usage: python scripts/fit_score_weights.py <labels-v2.csv> <vod>=<job.json> [...] [--k 20] [--min-rated 30]
                                           [--out weights.json]

<job.json> is a GET /v1/jobs/<job_id> response of a run with the AI judge: its clips carry `scores` (hook, payoff,
clarity, emotion, pacing). Clips are matched to rated moments exactly as scripts/eval_clips.py does.

What it prints, for the tuning videos pooled and for each game:
- per sub-score: how many rated clips, its rank correlation with the owner's rating (Spearman), and precision@k when
  clips are ranked by that sub-score alone (hits / rated clips in the top k, with the counts);
- equal weights against the fitted weights: precision@k over rated clips, with the counts.
Weights are fitted on tuning videos only, by trying every split of the weight in tenths, and only for a game (or
"default", all games) with at least --min-rated rated clips; with fewer, equal weights stay. A fit that does not
beat equal weights on the tuning videos is not written. Held-out videos get totals only, with the fitted weights
already fixed: nothing is fitted on them and their clips are never listed.

--out writes {"<game>": {...}, "default": {...}} for the SCORE_WEIGHTS setting. The numbers are an AI rating and
ranking weights, never a probability of views.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_clips import GOOD, match, parse_v2  # noqa: E402

from app.pipeline.ranking import SCORES, clean, rank_score  # noqa: E402

STEP = 10          # weights are tried in tenths


def load_scored(path: Path) -> list[dict]:
    """The clips of a job that the judge gave all five sub-scores."""
    data = json.loads(Path(path).read_text())
    out = []
    for c in data.get("clips", []):
        scores = c.get("scores") or (c.get("meta") or {}).get("scores")
        if rank_score(scores, None) is None:
            continue
        out.append({"start": float(c.get("start_sec", c.get("start"))), "end": float(c.get("end_sec", c.get("end"))),
                    "scores": {k: float(scores[k]) for k in SCORES}})
    return out


def rated_clips(rows: list[dict], clips: list[dict]) -> list[dict]:
    """Each clip on a rated moment, with that moment's rating and id."""
    rated = [r for r in rows if r["label"] is not None]
    out = []
    for c in clips:
        m = match(c, rated)
        if m is not None:
            out.append({**c, "label": m["label"], "moment": m["id"]})
    return out


def precision_at(videos: list[list[dict]], key, k: int) -> tuple[int, int]:
    """(hits, rated) over the videos: each video's rated clips ranked by `key` (high first), the top k taken; a hit
    is a clip on a moment rated 2 or 3 that no better-ranked clip of that video is on."""
    hits = rated = 0
    for clips in videos:
        seen: set = set()
        for c in sorted(clips, key=key, reverse=True)[:k]:
            rated += 1
            if c["label"] >= GOOD and c["moment"] not in seen:
                hits += 1
            seen.add(c["moment"])
    return hits, rated


def _ranks(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for m in range(i, j + 1):
            ranks[order[m]] = (i + j) / 2 + 1          # tied values share the mean rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation, or None with fewer than 3 points or no variation."""
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    if not sx or not sy:
        return None
    return round(sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy), 3)


def grid():
    """Every way to split the weight over the five sub-scores in tenths."""
    for parts in itertools.product(range(STEP + 1), repeat=len(SCORES) - 1):
        if sum(parts) <= STEP:
            yield dict(zip(SCORES, (*[p / STEP for p in parts], (STEP - sum(parts)) / STEP)))


def fit(videos: list[list[dict]], k: int) -> tuple[dict | None, tuple[int, int], tuple[int, int]]:
    """(weights or None, equal (hits, rated), fitted (hits, rated)): the split with the most hits in the top k, the
    one nearest to equal weights among ties. None when nothing beats equal weights."""
    equal = precision_at(videos, lambda c: rank_score(c["scores"], None), k)
    best, best_key = None, (equal[0], 0.0)
    for w in grid():
        hits, _rated = precision_at(videos, lambda c, w=w: rank_score(c["scores"], w), k)
        key = (hits, -sum(abs(v - 1 / len(SCORES)) for v in w.values()))
        if key > best_key and hits > equal[0]:
            best, best_key = w, key
    fitted = precision_at(videos, lambda c: rank_score(c["scores"], best), k) if best else equal
    return (clean(best) if best else None), equal, fitted


def frac(hits_rated: tuple[int, int]) -> str:
    hits, rated = hits_rated
    return f"{hits}/{rated}" + (f" = {100 * hits / rated:.0f}%" if rated else "")


def analyse(rows: list[dict], runs: dict[str, list[dict]], k: int, min_rated: int) -> dict:
    vods = {}
    for vod in sorted({r["vod"] for r in rows}):
        mine = [r for r in rows if r["vod"] == vod]
        if vod in runs:
            vods[vod] = {"game": mine[0]["game"], "held_out": mine[0]["held_out"], "clips": rated_clips(mine, runs[vod])}
    tuning = {v: d for v, d in vods.items() if not d["held_out"]}
    held = {v: d for v, d in vods.items() if d["held_out"]}
    groups = {"default": list(tuning)}
    for v, d in tuning.items():
        groups.setdefault(d["game"], []).append(v)
    out = {"k": k, "groups": {}, "weights": {}, "held_out": {}}
    for name, members in groups.items():
        videos = [tuning[v]["clips"] for v in members]
        flat = [c for clips in videos for c in clips]
        per_score = {s: {"spearman": spearman([c["scores"][s] for c in flat], [float(c["label"]) for c in flat]),
                         "precision": precision_at(videos, lambda c, s=s: c["scores"][s], k)} for s in SCORES}
        entry = {"videos": members, "rated": len(flat), "per_score": per_score}
        if len(flat) >= min_rated:
            weights, equal, fitted = fit(videos, k)
            entry.update(equal=equal, fitted=fitted, weights=weights)
            if weights:
                out["weights"][name] = weights
        else:
            entry["equal"] = precision_at(videos, lambda c: rank_score(c["scores"], None), k)
            entry["note"] = f"{len(flat)} rated clips, under {min_rated}: equal weights stay"
        out["groups"][name] = entry
    for v, d in held.items():          # totals only, with weights already fixed
        w = out["weights"].get(d["game"]) or out["weights"].get("default")
        out["held_out"][v] = {"game": d["game"], "rated": len(d["clips"]),
                              "equal": precision_at([d["clips"]], lambda c: rank_score(c["scores"], None), k),
                              "fitted": precision_at([d["clips"]], lambda c: rank_score(c["scores"], w), k)}
    return out


def report(a: dict) -> str:
    k, lines = a["k"], []
    for name, g in a["groups"].items():
        lines.append(f"{name}: {len(g['videos'])} tuning video(s), {g['rated']} rated clips")
        for s, d in g["per_score"].items():
            rho = "n/a" if d["spearman"] is None else f"{d['spearman']:+.3f}"
            lines.append(f"  {s:8s} rank correlation with the rating {rho} · precision@{k} by it alone {frac(d['precision'])}")
        if "note" in g:
            lines.append(f"  equal weights precision@{k} {frac(g['equal'])} · {g['note']}")
        else:
            got = json.dumps(g["weights"]) if g["weights"] else "no split beats equal weights: equal weights stay"
            lines.append(f"  equal weights precision@{k} {frac(g['equal'])} · fitted {frac(g['fitted'])} · {got}")
    for v, h in a["held_out"].items():
        lines.append(f"held-out {v} ({h['game']}): {h['rated']} rated clips · equal precision@{k} {frac(h['equal'])} · "
                     f"fitted {frac(h['fitted'])} (totals only; nothing is fitted here)")
    if not a["groups"]:
        lines.append("no tuning video has a run with sub-scores and rated moments yet")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels", type=Path)
    ap.add_argument("runs", nargs="*", help="<vod>=<job.json>")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--min-rated", type=int, default=30)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    rows, errors = parse_v2(args.labels)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    runs = {}
    for item in args.runs:
        vod, _, path = item.partition("=")
        if not path:
            print(f"{item}: give runs as <vod>=<job.json>", file=sys.stderr)
            return 2
        runs[vod] = load_scored(Path(path))
    a = analyse(rows, runs, args.k, args.min_rated)
    print(report(a))
    if args.out:
        args.out.write_text(json.dumps(a["weights"], indent=1))
        print(f"weights for SCORE_WEIGHTS -> {args.out}" if a["weights"] else f"no weights fitted: {args.out} is empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
