#!/usr/bin/env python3
"""Score clip runs against a labelled moment sheet (the quality eval set), or check a sheet.

Usage:
  python scripts/eval_clips.py <v1-labels.csv> <run.json> [--json]                  # v1 sheet, one run
  python scripts/eval_clips.py <labels-v2.csv> [<vod>=<run.json> ...] [--json] [--show-held-out]
  python scripts/eval_clips.py <labels-v2.csv>                                       # check the sheet only

A run file is what `scripts/label_moments.py select` (ours) or `wayin` (Wayin's clips placed in the source) writes,
or a GET /v1/jobs/<job_id> response: its "clips" have start_sec / end_sec, and a rank (1 = best) or a score;
without either the listed order is the rank. Its "system" (default clutchclips) says whose run it is: give one run
per system and video, and the report compares the systems side by side on the same rated moments.

Matching rule (v1 and v2): a clip matches the rated moment of its own video it overlaps most, if that overlap is at
least 10 s (or a third of the clip, for clips under 30 s); on equal overlap the higher rating wins. A clip matches
at most one moment, and unrated rows take no part.

Among a run's k best clips (k = 20, 40), each clip is one of:
- hit: on a moment rated 2 or 3 that no better-ranked clip of the run is on;
- miss: on a moment rated 1;
- repeat: on a rated moment a better-ranked clip of the run is already on;
- unrated: on no rated moment. Unrated is not a miss: nobody has judged it yet.
Precision is never one number that counts unrated clips as bad. It is printed as: precision over the rated clips
(hits / rated), and a range from unrated-as-misses (hits / clips) to unrated-as-hits ((hits + unrated) / clips).
When a run returned fewer than k clips (n < k), that is flagged and the strict range over k is printed too
(hits / k to (hits + unrated) / k), next to the range over the n clips it did return.
Recall: the share of 3-rated moments some clip of the run is on (all of the run's clips).

Pooled lines (tuning videos, held-out videos, all) add up the counts over videos, so each video weighs the same.
Held-out videos print their totals; --show-held-out also prints their clips and misses. Nobody tunes against them.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

GOOD, GREAT, DUP_GAP = 2, 3, 60.0
TOP_K = (20, 40)
OURS = "clutchclips"
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


def pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.0%}"


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


def load_run(path: Path) -> tuple[str, list[dict]]:
    """(system, clips) of a run file."""
    data = json.loads(Path(path).read_text())
    clips = data.get("clips", data) if isinstance(data, dict) else data
    system = (data.get("system") if isinstance(data, dict) else None) or OURS
    return system, [{"start": float(c["start_sec"] if "start_sec" in c else c["start"]),
                     "end": float(c["end_sec"] if "end_sec" in c else c["end"]),
                     "title": c.get("title") or c.get("file"), "rank": c.get("rank"), "score": c.get("score")}
                    for c in clips]


def load_clips(path: Path) -> list[dict]:
    return load_run(path)[1]


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


def verdicts(rows: list[dict], order: list[dict]) -> list[tuple[str, dict | None]]:
    """(hit | miss | repeat | unrated, matched row) for each clip, best-ranked first."""
    seen: set[int] = set()
    out = []
    for c in order:
        m = match(c, rows)
        if m is None:
            out.append(("unrated", None))
            continue
        out.append(("repeat" if id(m) in seen else "hit" if m["label"] >= GOOD else "miss", m))
        seen.add(id(m))
    return out


def precision(d: dict) -> dict:
    """Adds the precision numbers to counts {k, n, hits, misses, repeats, unrated} (one run, or pooled sums)."""
    k, n, hits, unrated = d["k"], d["n"], d["hits"], d["unrated"]
    rated = n - unrated
    return {**d, "precision_rated": round(hits / rated, 3) if rated else None,
            "precision_low": round(hits / n, 3) if n else None,
            "precision_high": round((hits + unrated) / n, 3) if n else None,
            "short": n < k,
            "strict_low": round(hits / k, 3), "strict_high": round((hits + unrated) / k, 3)}


def counts(kinds: list[str], k: int) -> dict:
    top = kinds[:k]
    return precision({"k": k, "n": len(top), "hits": top.count("hit"), "misses": top.count("miss"),
                      "repeats": top.count("repeat"), "unrated": top.count("unrated")})


def at_k(rows: list[dict], clips: list[dict]) -> dict:
    kinds = [v for v, _m in verdicts(rows, ranked(clips))]
    return {f"@{k}": counts(kinds, k) for k in TOP_K}


def fmt_at(d: dict) -> str:
    """One precision@k, never as a single number that counts unrated clips as misses."""
    line = (f"@{d['k']}: {d['n']} clips · hits {d['hits']} · misses {d['misses']} · repeats {d['repeats']} · "
            f"unrated {d['unrated']} · precision {pct(d['precision_rated'])} of rated, "
            f"{pct(d['precision_low'])} to {pct(d['precision_high'])} (unrated as misses / as hits)")
    if d["short"]:
        line += (f" · run returned only {d['n']} clips: {pct(d['strict_low'])} to {pct(d['strict_high'])} "
                 f"of {d['k']} (strict)")
    return line


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
             *(fmt_at(s[f"@{k}"]) for k in TOP_K)]
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
        counts_ = {k: sum(1 for r in rated if r["label"] == k) for k in (3, 2, 1)}
        lines.append(f"{v} ({mine[0]['game']}{', held out' if mine[0]['held_out'] else ''}): rated {len(rated)} "
                     f"of {len(mine)} · 3s {counts_[3]} · 2s {counts_[2]} · 1s {counts_[1]}")
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
    judged = verdicts(rows, order)
    kinds = [v for v, _m in judged]
    great = [r for r in rows if r["label"] == GREAT]
    found = {id(m) for _v, m in judged if m is not None and m["label"] == GREAT}
    return {
        "clips": len(clips), "moments": len(rows), "great": len(great), "great_found": len(found),
        "recall": round(len(found) / len(great), 3) if great else None,
        **{f"@{k}": counts(kinds, k) for k in TOP_K},
        "per_clip": [{"rank": i + 1, "start": c["start"], "end": c["end"], "title": c.get("title"), "verdict": v,
                      "row": m["id"] if m else None, "rating": m["label"] if m else None}
                     for i, (c, (v, m)) in enumerate(zip(order, judged))],
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
        out[f"@{k}"] = precision({key: sum(s[f"@{k}"][key] for s in per_vod)
                                  for key in ("k", "n", "hits", "misses", "repeats", "unrated")})
    return out


def score_v2(rows: list[dict], runs: dict[str, dict[str, list[dict]]]) -> dict:
    """runs: system -> vod id -> that system's clips on that video. Only rated rows count."""
    vods = {r["vod"]: r["held_out"] for r in rows}
    out: dict = {"systems": {}, "unscored": {}}
    for system, by_vod in runs.items():
        unknown = sorted(set(by_vod) - set(vods))
        if unknown:
            raise ValueError(f"no rows for vod {', '.join(unknown)} in the sheet (vods: {', '.join(sorted(vods))})")
        per = {v: {"held_out": vods[v], **score_vod([r for r in rows if r["vod"] == v and r["label"] is not None], c)}
               for v, c in sorted(by_vod.items())}
        out["systems"][system] = {"per_vod": per,
                                  "tuning": pooled([s for s in per.values() if not s["held_out"]]),
                                  "held_out": pooled([s for s in per.values() if s["held_out"]]),
                                  "all": pooled(list(per.values()))}
        missing = sorted(set(vods) - set(by_vod))
        if missing:
            out["unscored"][system] = missing
    return out


def _table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows]


def report_v2(s: dict, show_held_out: bool = False) -> str:
    systems = sorted(s["systems"], key=lambda x: (x != OURS, x))
    head = ["", "system", "recall of 3s", "@k", "clips", "hits", "misses", "repeats", "unrated",
            "precision of rated", "range (unrated as miss / hit)", "fewer than k clips: strict range of k"]
    table = [head]
    some = s["systems"][systems[0]]
    vods = list(some["per_vod"])
    for sys_ in systems[1:]:
        vods += [v for v in s["systems"][sys_]["per_vod"] if v not in vods]
    scopes = [(name, lambda d, n=name: d[n]) for name in ("tuning", "held_out", "all")]
    scopes += [(v, lambda d, v=v: d["per_vod"].get(v)) for v in vods]
    for name, get in scopes:
        first = True
        for sys_ in systems:
            d = get(s["systems"][sys_])
            if not d:
                continue
            if name in ("tuning", "held_out", "all"):
                label = f"{name} ({d['vods']} vod{'s' * (d['vods'] != 1)})"
            else:
                label = f"{name}{' (held out)' if d['held_out'] else ''}"
            for k in TOP_K:
                a = d[f"@{k}"]
                rec = f"{d['great_found']} of {d['great']} ({pct(d['recall'])})" if k == TOP_K[0] else ""
                short = (f"only {a['n']} of {a['k']}: {pct(a['strict_low'])} to {pct(a['strict_high'])}"
                         if a["short"] else "")
                table.append([label if first else "", sys_ if k == TOP_K[0] else "", rec, str(k), str(a["n"]),
                              str(a["hits"]), str(a["misses"]), str(a["repeats"]), str(a["unrated"]),
                              pct(a["precision_rated"]), f"{pct(a['precision_low'])} to {pct(a['precision_high'])}",
                              short])
                first = False
    lines = _table(table)
    for sys_ in systems:
        for v, p in s["systems"][sys_]["per_vod"].items():
            if p["held_out"] and not show_held_out:
                lines.append(f"{sys_} on {v}: held out, clips and misses hidden (--show-held-out)")
                continue
            lines.append(f"{sys_} on {v}, {p['clips']} clips:")
            for c in p["per_clip"]:
                lines.append(f"  #{c['rank']:<3} {hms(c['start'])}  {c['verdict']:<8} rating {c['rating'] or '-'}  "
                             f"row {c['row'] or '-'}  {c['title'] or ''}".rstrip())
            for m in p["missed"]:
                lines.append(f"  missed 3 {m['id']}  {hms(m['start'])} to {hms(m['end'])}  {m['reason']}")
    for sys_, missing in s["unscored"].items():
        lines.append(f"no {sys_} run given for: {', '.join(missing)}")
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
    runs: dict[str, dict[str, list[dict]]] = {}
    for spec in args.runs:
        vod, sep, path = spec.partition("=")
        if not sep:
            print(f"{spec!r}: give each run as <vod>=<run.json>", file=sys.stderr)
            return 2
        system, clips = load_run(Path(path))
        if vod in runs.setdefault(system, {}):
            print(f"two {system} runs for {vod}: give one per system and video", file=sys.stderr)
            return 2
        runs[system][vod] = clips
    if not any(r["label"] is not None for r in rows if any(r["vod"] in by_vod for by_vod in runs.values())):
        print("no rated rows for these videos yet: rate them first", file=sys.stderr)
        return 2
    try:
        s = score_v2(rows, runs)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.json and not args.show_held_out:
        for d in s["systems"].values():
            for p in d["per_vod"].values():
                if p["held_out"]:
                    p["per_clip"], p["missed"] = [], []
    print(json.dumps(s) if args.json else report_v2(s, args.show_held_out))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("labels", type=Path)
    ap.add_argument("runs", nargs="*", help="v1: one run.json · v2: <vod>=<run.json> per system and video")
    ap.add_argument("--duration", type=float, default=None, help="v1: video length in seconds (default: from the data)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-held-out", action="store_true", help="v2: also print the held-out video's clips and misses")
    args = ap.parse_args(argv)
    if is_v2(args.labels):
        return _main_v2(args)
    if len(args.runs) != 1:
        print("a v1 sheet is scored against exactly one run.json", file=sys.stderr)
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
