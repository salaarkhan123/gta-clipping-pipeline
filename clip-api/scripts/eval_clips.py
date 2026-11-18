#!/usr/bin/env python3
"""Score clip runs against a labelled moment sheet (the quality eval set), or check a sheet.

Usage:
  python scripts/eval_clips.py <v1-labels.csv> <job.json> [--json]                  # v1 sheet, one run
  python scripts/eval_clips.py <labels-v2.csv> [<vod>=<job.json> ...] [--json] [--show-held-out]
  python scripts/eval_clips.py <labels-v2.csv>                                       # check the sheet only

A job file is the response of GET /v1/jobs/<job_id>, or what `scripts/label_moments.py select` writes: its
"clips" have start_sec / end_sec, and a rank (1 = best) or a score; without either the listed order is the rank.

Matching rule (v1 and v2): a clip matches the rated moment of its own video it overlaps most, if that overlap is at
least 10 s (or a third of the clip, for clips under 30 s); on equal overlap the higher rating wins. A clip matches
at most one moment, and unrated rows take no part.

v1 sheet (id, start, end, label 0-3): good_rate (clips on a 2 or 3), mean label, great_recall (3-rated moments some
clip found, and the ones no clip found), unlabelled clips, duplicates (same moment, or under 60 s apart), clips per
quarter, and precision@20/@40.

v2 sheet (see eval/README.md and V2_FIELDS), per video and pooled over the tuning videos and the held-out ones:
- precision@k: hits among the k best-ranked clips, divided by k (a run with fewer than k clips cannot score 1).
  A hit is a clip on a moment rated 2 or 3 that no better-ranked clip of the run already matched.
- recall: the share of 3-rated moments that some clip of the run matched.
- unrated@k: clips among the k best on no rated moment. Rate them (label_moments.py add --job) and re-run.
Pooled numbers add up hits and moments over videos, so each scored video weighs the same in precision@k.
Held-out videos print their totals only; --show-held-out also prints their clips and misses.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

GOOD, GREAT, DUP_GAP = 2, 3, 60.0
TOP_K = (20, 40)
V2_FIELDS = ["id", "vod", "game", "start", "end", "rating", "reason", "held_out", "source"]
V2_REQUIRED = ["vod", "game", "start", "end", "rating", "reason", "held_out"]
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MIN_LEN, MAX_LEN, REASON_MAX = 5.0, 300.0, 80


def seconds(t: str) -> float:
    parts = [float(p) for p in str(t).strip().split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def hms(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def load_labels(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            label = (r.get("label") or "").strip()
            if label == "":
                continue
            rows.append({"id": r.get("id") or str(len(rows) + 1), "start": seconds(r["start"]),
                         "end": seconds(r["end"]), "label": int(float(label))})
    return rows


def load_clips(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    clips = data.get("clips", data) if isinstance(data, dict) else data
    return [{"start": float(c["start_sec"] if "start_sec" in c else c["start"]),
             "end": float(c["end_sec"] if "end_sec" in c else c["end"]),
             "title": c.get("title"), "rank": c.get("rank"), "score": c.get("score")} for c in clips]


def overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def match(clip: dict, rows: list[dict]) -> dict | None:
    need = min(10.0, (clip["end"] - clip["start"]) / 3)
    best = max(rows, key=lambda r: (overlap(clip["start"], clip["end"], r["start"], r["end"]), r["label"]),
               default=None)
    if best is None or overlap(clip["start"], clip["end"], best["start"], best["end"]) < need:
        return None
    return best


def ranked(clips: list[dict]) -> list[dict]:
    """Best first: by `rank` when every clip has one, else by `score` (high first), else as listed."""
    if clips and all(c.get("rank") is not None for c in clips):
        return sorted(clips, key=lambda c: c["rank"])
    if clips and all(c.get("score") is not None for c in clips):
        return sorted(clips, key=lambda c: -c["score"])         # stable: equal scores keep the listed order
    return list(clips)


def at_k(rows: list[dict], clips: list[dict]) -> dict:
    """precision@k and unrated@k for each k in TOP_K, from one run's clips on one video."""
    seen: set[int] = set()
    hit, unrated = [], []
    for c in ranked(clips):
        m = match(c, rows)
        hit.append(m is not None and m["label"] >= GOOD and id(m) not in seen)
        unrated.append(m is None)
        if m is not None:
            seen.add(id(m))
    out = {}
    for k in TOP_K:
        out[f"hits@{k}"] = sum(hit[:k])
        out[f"precision@{k}"] = round(sum(hit[:k]) / k, 3)
        out[f"unrated@{k}"] = sum(unrated[:k])
    return out


def score(rows: list[dict], clips: list[dict], duration: float | None = None) -> dict:
    duration = duration or max([r["end"] for r in rows] + [c["end"] for c in clips] + [1.0])
    matched = [match(c, rows) for c in clips]
    labels = [m["label"] for m in matched if m]
    great = [r for r in rows if r["label"] >= GREAT]
    found_great = {m["id"] for m in matched if m and m["label"] >= GREAT}
    dup = 0
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            same_row = matched[i] is not None and matched[i] is matched[j]
            gap = max(0.0, max(clips[i]["start"], clips[j]["start"]) - min(clips[i]["end"], clips[j]["end"]))
            if same_row or gap < DUP_GAP:
                dup += 1
    quarters = [0, 0, 0, 0]
    for c in clips:
        quarters[min(3, int(4 * c["start"] / duration))] += 1
    return {
        "clips": len(clips),
        "good_rate": round(sum(1 for x in labels if x >= GOOD) / len(clips), 3) if clips else 0.0,
        "mean_label": round(sum(labels) / len(labels), 2) if labels else None,
        "great_recall": round(len(found_great) / len(great), 3) if great else None,
        "great_found": f"{len(found_great)} of {len(great)}",
        "great_missed": [{"id": r["id"], "start": r["start"], "end": r["end"]} for r in great if r["id"] not in found_great],
        "unlabelled": sum(1 for m in matched if m is None),
        "duplicate_pairs": dup,
        "per_quarter": quarters,
        "per_clip": [{"start": c["start"], "end": c["end"], "title": c["title"],
                      "row": m["id"] if m else None, "label": m["label"] if m else None}
                     for c, m in zip(clips, matched)],
        **at_k(rows, clips),
    }


def report(s: dict) -> str:
    lines = [f"clips {s['clips']} · good rate {s['good_rate']:.0%} · mean label {s['mean_label']} · "
             f"great moments found {s['great_found']}",
             f"unlabelled {s['unlabelled']} · duplicate pairs {s['duplicate_pairs']} · per quarter {s['per_quarter']}",
             " · ".join(f"precision@{k} {s[f'precision@{k}']:.0%}" for k in TOP_K)]
    for c in s["per_clip"]:
        t = int(c["start"])
        lines.append(f"  {t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}  label {c['label'] if c['label'] is not None else '-'}"
                     f"  row {c['row'] or '-'}  {c['title'] or ''}")
    for r in s.get("great_missed", []):
        a, b = int(r["start"]), int(r["end"])
        lines.append(f"  missed row {r['id']}  {a // 3600}:{a % 3600 // 60:02d}:{a % 60:02d} to "
                     f"{b // 3600}:{b % 3600 // 60:02d}:{b % 60:02d}")
    return "\n".join(lines)


# ---- v2: several videos, ratings 1-3, one video held out ----

def is_v2(path: Path) -> bool:
    with open(path, newline="") as f:
        header = next(csv.reader(f), [])
    return "vod" in header and "rating" in header


def parse_v2(path: Path) -> tuple[list[dict], list[str]]:
    """Every row of a v2 sheet (rated or not) and the reasons it is invalid, as 'line N: ...'. Rows that fail a
    check are left out. An empty error list means the sheet can be scored."""
    rows: list[dict] = []
    errors: list[str] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in V2_REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            return [], [f"header: missing column(s) {', '.join(missing)} (expected {', '.join(V2_FIELDS)})"]
        for line, r in enumerate(reader, 2):
            bad = []
            vod, game = (r.get("vod") or "").strip(), (r.get("game") or "").strip()
            if not SLUG.match(vod):
                bad.append(f"vod {vod!r} is not a short id (a-z, 0-9, dashes)")
            if not SLUG.match(game):
                bad.append(f"game {game!r} is not a short id (gta-rp, gta-online, or the game, e.g. valorant)")
            try:
                start, end = seconds(r["start"]), seconds(r["end"])
            except (ValueError, TypeError):
                start = end = 0.0
                bad.append(f"start/end {r.get('start')!r}/{r.get('end')!r} are not times (h:mm:ss)")
            else:
                if not MIN_LEN <= end - start <= MAX_LEN:
                    bad.append(f"moment is {end - start:g} s long ({r['start']} to {r['end']}): "
                               f"must be {MIN_LEN:g} to {MAX_LEN:g} s")
            rating = (r.get("rating") or "").strip()
            if rating not in ("", "1", "2", "3"):
                bad.append(f"rating {rating!r} must be 1, 2, 3 or empty (not rated yet)")
            reason = (r.get("reason") or "").strip()
            if len(reason) > REASON_MAX:
                bad.append(f"reason is {len(reason)} characters: keep it under {REASON_MAX}")
            if rating == "3" and not reason:
                bad.append("a 3 needs a reason (a few words on why it is great)")
            held = (r.get("held_out") or "").strip().lower()
            if held not in ("yes", "no"):
                bad.append(f"held_out {held!r} must be yes or no")
            if bad:
                errors += [f"line {line}: {b}" for b in bad]
                continue
            rows.append({"id": (r.get("id") or "").strip() or f"line{line}", "line": line, "vod": vod, "game": game,
                         "start": start, "end": end, "label": int(rating) if rating else None, "reason": reason,
                         "held_out": held == "yes", "source": (r.get("source") or "").strip()})
    errors += _sheet_errors(rows)
    return rows, errors


def _sheet_errors(rows: list[dict]) -> list[str]:
    errors = []
    ids: dict[str, int] = {}
    for r in rows:
        if r["id"] in ids:
            errors.append(f"line {r['line']}: id {r['id']} is already used on line {ids[r['id']]}")
        ids.setdefault(r["id"], r["line"])
    first: dict[str, dict] = {}
    for r in rows:
        f = first.setdefault(r["vod"], r)
        for key in ("game", "held_out"):
            if r[key] != f[key]:
                errors.append(f"line {r['line']}: {key} differs from line {f['line']} for vod {r['vod']} "
                              f"(one value per video)")
    rated = sorted((r for r in rows if r["label"] is not None), key=lambda r: (r["vod"], r["start"]))
    for i, a in enumerate(rated):
        for b in rated[i + 1:]:
            if b["vod"] != a["vod"] or b["start"] >= a["end"]:
                break
            if overlap(a["start"], a["end"], b["start"], b["end"]) > min(a["end"] - a["start"], b["end"] - b["start"]) / 2:
                errors.append(f"line {b['line']}: overlaps line {a['line']} by more than half: one moment rated "
                              f"twice (merge them, or trim one)")
    return errors


def sheet_summary(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Lines describing each video's progress, and warnings about the set as a whole."""
    lines, warnings = [], []
    vods = sorted({r["vod"] for r in rows})
    for v in vods:
        mine = [r for r in rows if r["vod"] == v]
        rated = [r for r in mine if r["label"] is not None]
        counts = {k: sum(1 for r in rated if r["label"] == k) for k in (3, 2, 1)}
        lines.append(f"{v} ({mine[0]['game']}{', held out' if mine[0]['held_out'] else ''}): rated {len(rated)} "
                     f"of {len(mine)} · 3s {counts[3]} · 2s {counts[2]} · 1s {counts[1]}")
    held = {r["vod"] for r in rows if r["held_out"]}
    rated_total = sum(1 for r in rows if r["label"] is not None)
    if len(held) != 1:
        warnings.append(f"{len(held)} held-out videos: the set needs exactly one")
    if len(vods) < 3:
        warnings.append(f"{len(vods)} of 3 videos so far")
    if rated_total < 90:
        warnings.append(f"{rated_total} rated moments: the set aims at about 100")
    for v in vods:
        if not any(r["vod"] == v and r["label"] == GREAT for r in rows):
            warnings.append(f"{v} has no 3-rated moment yet: its recall cannot be measured")
    return lines, warnings


def score_vod(rows: list[dict], clips: list[dict]) -> dict:
    """One run on one video: rows are that video's rated moments."""
    order = ranked(clips)
    matched = [match(c, rows) for c in order]
    great = [r for r in rows if r["label"] == GREAT]
    found = {id(m) for m in matched if m is not None and m["label"] == GREAT}
    return {
        "clips": len(clips), "moments": len(rows), "great": len(great), "great_found": len(found),
        "recall": round(len(found) / len(great), 3) if great else None,
        **at_k(rows, clips),
        "per_clip": [{"rank": i + 1, "start": c["start"], "end": c["end"], "title": c.get("title"),
                      "row": m["id"] if m else None, "rating": m["label"] if m else None}
                     for i, (c, m) in enumerate(zip(order, matched))],
        "missed": [{"id": r["id"], "start": r["start"], "end": r["end"], "reason": r.get("reason", "")}
                   for r in great if id(r) not in found],
    }


def pooled(per_vod: list[dict]) -> dict | None:
    if not per_vod:
        return None
    great = sum(s["great"] for s in per_vod)
    found = sum(s["great_found"] for s in per_vod)
    out = {"vods": len(per_vod), "great": great, "great_found": found,
           "recall": round(found / great, 3) if great else None}
    for k in TOP_K:
        hits = sum(s[f"hits@{k}"] for s in per_vod)
        out[f"hits@{k}"] = hits
        out[f"precision@{k}"] = round(hits / (k * len(per_vod)), 3)
        out[f"unrated@{k}"] = sum(s[f"unrated@{k}"] for s in per_vod)
    return out


def score_v2(rows: list[dict], runs: dict[str, list[dict]]) -> dict:
    """runs: vod id -> that video's clips. Only rated rows count; videos without a run are listed as unscored."""
    vods = {r["vod"]: r["held_out"] for r in rows}
    unknown = sorted(set(runs) - set(vods))
    if unknown:
        raise ValueError(f"no rows for vod {', '.join(unknown)} in the sheet (vods: {', '.join(sorted(vods))})")
    per = {v: {"held_out": vods[v], **score_vod([r for r in rows if r["vod"] == v and r["label"] is not None], c)}
           for v, c in sorted(runs.items())}
    return {"per_vod": per,
            "tuning": pooled([s for s in per.values() if not s["held_out"]]),
            "held_out": pooled([s for s in per.values() if s["held_out"]]),
            "all": pooled(list(per.values())),
            "unscored": sorted(set(vods) - set(runs))}


def _line(name: str, s: dict) -> str:
    rec = f"{s['recall']:.0%}" if s["recall"] is not None else "-"
    return (f"{name}: " + " · ".join(f"precision@{k} {s[f'precision@{k}']:.0%}" for k in TOP_K)
            + f" · recall {rec} ({s['great_found']} of {s['great']} 3s)"
            + " · " + " · ".join(f"unrated@{k} {s[f'unrated@{k}']}" for k in TOP_K))


def report_v2(s: dict, show_held_out: bool = False) -> str:
    lines = []
    for name in ("tuning", "held_out", "all"):
        if s[name]:
            lines.append(_line(f"{name} ({s[name]['vods']} vod{'s' * (s[name]['vods'] != 1)})", s[name]))
    for v, p in s["per_vod"].items():
        lines.append(_line(f"{v}{' (held out)' if p['held_out'] else ''}, {p['clips']} clips", p))
        if p["held_out"] and not show_held_out:
            continue
        for c in p["per_clip"]:
            lines.append(f"  #{c['rank']:<3} {hms(c['start'])}  rating {c['rating'] or '-'}  row {c['row'] or '-'}"
                         f"  {c['title'] or ''}".rstrip())
        for m in p["missed"]:
            lines.append(f"  missed {m['id']}  {hms(m['start'])} to {hms(m['end'])}  {m['reason']}")
    if s["unscored"]:
        lines.append(f"no run given for: {', '.join(s['unscored'])}")
    return "\n".join(lines)


def _main_v2(args) -> int:
    rows, errors = parse_v2(args.labels)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(f"{len(errors)} problem(s) in {args.labels}: fix them and run again", file=sys.stderr)
        return 1
    if not args.runs:
        lines, warnings = sheet_summary(rows)
        print("\n".join([f"{args.labels}: {len(rows)} rows, valid", *lines, *(f"warning: {w}" for w in warnings)]))
        return 0
    runs = {}
    for spec in args.runs:
        vod, sep, path = spec.partition("=")
        if not sep:
            print(f"{spec!r}: give each run as <vod>=<job.json>", file=sys.stderr)
            return 2
        runs[vod] = load_clips(Path(path))
    if not any(r["label"] is not None for r in rows if r["vod"] in runs):
        print("no rated rows for these videos yet: rate them first", file=sys.stderr)
        return 2
    try:
        s = score_v2(rows, runs)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.json and not args.show_held_out:
        for p in s["per_vod"].values():
            if p["held_out"]:
                p["per_clip"], p["missed"] = [], []
    print(json.dumps(s) if args.json else report_v2(s, args.show_held_out))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("labels", type=Path)
    ap.add_argument("runs", nargs="*", help="v1: one job.json · v2: <vod>=<job.json> for each video scored")
    ap.add_argument("--duration", type=float, default=None, help="v1: video length in seconds (default: from the data)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-held-out", action="store_true", help="v2: also print the held-out video's clips and misses")
    args = ap.parse_args(argv)
    if is_v2(args.labels):
        return _main_v2(args)
    if len(args.runs) != 1:
        print("a v1 sheet is scored against exactly one job.json", file=sys.stderr)
        return 2
    rows, clips = load_labels(args.labels), load_clips(Path(args.runs[0]))
    if not rows:
        print("no labelled rows yet: fill in the label column first", file=sys.stderr)
        return 2
    s = score(rows, clips, args.duration)
    print(json.dumps(s) if args.json else report(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
