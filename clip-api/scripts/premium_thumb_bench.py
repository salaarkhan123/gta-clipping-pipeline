#!/usr/bin/env python3
"""Benchmark premium AI thumbnails (#140) on moments of local videos: real provider calls, real money.

Usage:
  python scripts/premium_thumb_bench.py <out_dir> --video <file> <moments.csv> [--video <file> <moments.csv> ...]
         [--per-video 14 6] [--env-file <path to the settings file with GEMINI_API_KEY / BFL_API_KEY>]
         [--max-usd 3.0] [--max-calls 40]

For each picked moment (rows of the CSV spread evenly, the first rows of a stream skipped as they are often a
"be right back" screen) it makes the free thumbnail exactly as the pipeline does (thumbs.make_thumbnail), then
the premium one through imagegen.generate, the code the worker runs: Gemini first, one retry on BFL. Styles cycle
through the four presets; every third moment also gets a custom instruction.

Writes, in <out_dir>: NN/free.jpg, NN/premium.jpg, NN/premium.clean.jpg, results.json (every attempt: provider,
model, outcome, seconds, dollars and how they were worked out), summary.md, and sheet-N.jpg contact sheets (free
left, premium right). Keys are read by Settings from the environment or --env-file and are never printed.

Spending guard: no call is started once the estimated spend reaches --max-usd or --max-calls calls were made. A
fallback that answers it has no balance is marked unavailable and not called again.
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.config import Settings  # noqa: E402
from app.imagegen import GenerationFailed, editors_from, generate, style_look  # noqa: E402
from app.imagegen.base import ProviderFailed  # noqa: E402
from app.imagegen.prompts import clean_instruction  # noqa: E402
from app.pipeline import PipelineOptions, probe  # noqa: E402
from app.pipeline.captions import FONT_DIR, IMPACT_FILE  # noqa: E402
from app.pipeline.facecam import resolve_facecam  # noqa: E402
from app.pipeline.signals import audio_rms_db  # noqa: E402
from app.pipeline.thumbs import canvas_of, make_thumbnail  # noqa: E402

STYLES = ["cinematic", "high_energy", "clean", "dramatic"]
INSTRUCTIONS = ["warm golden-hour sunset tones", "neon purple and blue night lighting",
                "make the colors pop more but keep it realistic"]
HOOKS = ["He did NOT see that coming", "Worst getaway driver in Los Santos", "Cops gave up", "This went wrong fast",
         "Clean escape", "How did that work", "Never trust the bridge", "Full send off the pier", "Wrong car bro",
         "Chat called it", "He really thought", "One in a million crash", "Drake really said that",
         "They were NOT ready", "Chat lost it"]
GEMINI_MODELS = "https://generativelanguage.googleapis.com/v1beta/models/"
FALLBACK_MODEL_IDS = ["gemini-3.1-flash-image"]       # what Nano Banana 2.1 updates, if the stable id is not served
CELL = 300
STOP_AFTER_FAILURES = 3      # a wrong request format or a dead key should not burn the budget


def seconds(value: str) -> float:
    total = 0.0
    for p in str(value).strip().split(":"):
        total = total * 60 + float(p)
    return total


class Guard:
    """Wraps an editor: counts calls and dollars, refuses calls past the caps, and stops calling a fallback that
    has no balance."""
    def __init__(self, editor, budget: dict):
        self.editor, self.budget, self.name, self.model = editor, budget, editor.name, editor.model
        self.unavailable: str | None = None

    def edit(self, request, timeout):
        b = self.budget
        if self.unavailable:
            raise ProviderFailed("fallback_unavailable", self.unavailable)
        if b["calls"] >= b["max_calls"] or b["usd"] >= b["max_usd"]:
            b["capped"] = True
            raise ProviderFailed("bench_cap", "Benchmark spending cap reached; call not made.")
        b["calls"] += 1
        b["by_provider"][self.name] = b["by_provider"].get(self.name, 0) + 1
        try:
            result = self.editor.edit(request, timeout)
        except ProviderFailed as e:
            b["usd"] += e.cost_usd or 0
            low = e.message.lower()
            if self.name == "bfl" and (" 402" in e.message or "credit" in low or "balance" in low or "insufficient" in low):
                self.unavailable = f"BFL has no balance ({e.message[:120]})"
                raise ProviderFailed("fallback_unavailable", self.unavailable) from None
            raise
        b["usd"] += result.cost_usd or 0
        return result


def pick_model(settings: Settings) -> str:
    """The Gemini model id to use: the configured one when the API serves it (a free metadata call), else the
    first fallback id it serves."""
    for model in [settings.gemini_image_model, *FALLBACK_MODEL_IDS]:
        r = httpx.get(GEMINI_MODELS + model, headers={"x-goog-api-key": settings.gemini_api_key}, timeout=20)
        print(f"model check {model}: HTTP {r.status_code}", flush=True)
        if r.status_code == 200:
            return model
    raise SystemExit("No Gemini image model id is served to this key.")


def moments(csv_path: Path, n: int) -> list[dict]:
    rows = list(csv.DictReader(csv_path.open()))
    if len(rows) > 3 * n:
        rows = rows[len(rows) // 8:]
    step = max(1, len(rows) // n)
    return rows[::step][:n]


def sheet(items: list[dict], out: Path) -> None:
    font = ImageFont.truetype(str(FONT_DIR / IMPACT_FILE), 18)
    tiles = []
    for it in items:
        ims = [Image.open(p).convert("RGB") for p in (it["free"], it.get("premium") or it["free"])]
        ims = [im.resize((CELL, round(CELL * im.height / im.width))) for im in ims]
        tile = Image.new("RGB", (2 * CELL + 10, max(i.height for i in ims) + 54), (24, 24, 24))
        d = ImageDraw.Draw(tile)
        d.text((4, 2), f"#{it['n']:02d} {it['source']} · {it['style']}" + (" + notes" if it["instruction"] else ""),
               font=font, fill=(230, 230, 230))
        status = (f"{it['provider']} {it['seconds']:.1f}s ${it['cost_usd']:.4f}" if it.get("premium")
                  else f"FAILED {it.get('error')}")
        for k, (im, name) in enumerate(zip(ims, ("FREE", "PREMIUM " + status))):
            tile.paste(im, (k * (CELL + 10), 52))
            d.text((k * (CELL + 10) + 4, 26), name, font=font, fill=(200, 230, 120) if k else (200, 200, 200))
        tiles.append(tile)
    per_row, per_sheet = 2, 6
    for s, start in enumerate(range(0, len(tiles), per_sheet), 1):
        group = tiles[start:start + per_sheet]
        rows = [group[i:i + per_row] for i in range(0, len(group), per_row)]
        width = per_row * (2 * CELL + 10) + 30
        canvas = Image.new("RGB", (width, sum(max(t.height for t in r) + 20 for r in rows)), (10, 10, 10))
        y = 0
        for r in rows:
            for k, t in enumerate(r):
                canvas.paste(t, (k * (2 * CELL + 40), y))
            y += max(t.height for t in r) + 20
        canvas.save(out / f"sheet-{s}.jpg", "JPEG", quality=86)


def pct(values: list[float], q: float) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, max(0, round(q * (len(v) - 1))))] if v else 0.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--video", nargs=2, action="append", metavar=("FILE", "MOMENTS_CSV"), required=True)
    ap.add_argument("--per-video", type=int, nargs="+", default=[20])
    ap.add_argument("--env-file", type=Path)
    ap.add_argument("--max-usd", type=float, default=3.0)
    ap.add_argument("--max-calls", type=int, default=40)
    ap.add_argument("--aspect", default="9:16")
    args = ap.parse_args(argv)
    settings = Settings(_env_file=str(args.env_file)) if args.env_file else Settings()
    if not settings.gemini_api_key and not settings.bfl_api_key:
        raise SystemExit("Set GEMINI_API_KEY (and BFL_API_KEY for the fallback) first.")
    if settings.gemini_api_key:
        settings.gemini_image_model = pick_model(settings)
    budget = {"calls": 0, "usd": 0.0, "max_calls": args.max_calls, "max_usd": args.max_usd, "capped": False,
              "by_provider": {}}
    editors = [Guard(e, budget) for e in editors_from(settings)]
    print("providers:", [(e.name, e.model) for e in editors], flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    items, n, failed_in_a_row = [], 0, 0
    for v, (video, csv_path) in enumerate(args.video):
        video = Path(video)
        count = args.per_video[min(v, len(args.per_video) - 1)]
        info = probe(video)
        opts = PipelineOptions(facecam_region="auto", layout="auto", aspect=args.aspect)
        layout, facecam = resolve_facecam(video, info, opts)
        for row in moments(Path(csv_path), count):
            n += 1
            folder = args.out / f"{n:02d}"
            folder.mkdir(exist_ok=True)
            start, end = seconds(row["start"]), seconds(row["end"])
            hook = HOOKS[(n - 1) % len(HOOKS)]
            levels = audio_rms_db(video, start=int(start), length=end - int(start) + 1) if info.has_audio else []
            made = make_thumbnail(video, info, start, end, folder / "free.jpg", options=opts, layout=layout,
                                  facecam=facecam, text=hook, loudness=[-90.0] * int(start) + levels)
            style = STYLES[(n - 1) % len(STYLES)]
            instruction = clean_instruction(INSTRUCTIONS[(n // 3 - 1) % len(INSTRUCTIONS)]) if n % 3 == 0 else None
            item = {"n": n, "source": video.stem[:28], "at": made.record["at"], "hook": hook, "style": style,
                    "instruction": instruction, "free": str(folder / "free.jpg"), "frame": str(made.frame)}
            t0 = time.monotonic()
            try:
                got = generate(made.frame, folder, look=style_look(settings, style), instruction=instruction, text=hook,
                               canvas=canvas_of(made.record), accent=None, editors=editors,
                               timeout=settings.premium_thumb_timeout_sec)
                item.update(premium=str(got.image), clean=str(got.clean), text_drawn=got.text_drawn, **got.info())
            except GenerationFailed as e:
                item.update(error=e.code, message=e.message, attempts=[a.__dict__ for a in e.attempts],
                            cost_usd=round(sum(a.cost_usd or 0 for a in e.attempts), 6))
            item["seconds"] = round(time.monotonic() - t0, 2)
            items.append(item)
            print(json.dumps({k: item.get(k) for k in ("n", "style", "provider", "seconds", "cost_usd", "error",
                                                        "face_check")}), flush=True)
            failed_in_a_row = 0 if item.get("premium") else failed_in_a_row + 1
            if budget["capped"]:
                print("spending cap reached: stopping", flush=True)
                break
            if failed_in_a_row >= STOP_AFTER_FAILURES:
                budget["capped"] = True
                print(f"{failed_in_a_row} generations failed in a row: stopping (see results.json)", flush=True)
                break
        if budget["capped"]:
            break
    (args.out / "results.json").write_text(json.dumps({"budget": budget, "items": items}, indent=1))
    sheet(items, args.out)
    ok = [i for i in items if i.get("premium")]
    lat = [i["seconds"] for i in ok]
    retried = [i for i in items if i.get("attempts") and not i["attempts"][0]["ok"]]
    lines = [f"# Premium thumbnail benchmark ({time.strftime('%Y-%m-%d')})", "",
             f"- Generations: {len(items)}; succeeded {len(ok)}; failed {len(items) - len(ok)}",
             f"- First attempt failed (a retry was needed): {len(retried)}",
             f"- Provider calls: {budget['calls']} {budget['by_provider']}; estimated spend ${budget['usd']:.4f}",
             f"- Latency of successful generations (s): median {statistics.median(lat) if lat else 0:.1f}, "
             f"mean {statistics.mean(lat) if lat else 0:.1f}, p90 {pct(lat, 0.9):.1f}, p95 {pct(lat, 0.95):.1f}, "
             f"max {max(lat) if lat else 0:.1f}",
             f"- Cost per successful generation: ${(sum(i['cost_usd'] for i in ok) / len(ok)) if ok else 0:.4f}", "",
             "| # | source | style | notes | provider | seconds | cost $ | face check | attempts |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i in items:
        attempts = "; ".join(f"{a['provider']} {'ok' if a['ok'] else a['code']}" for a in i.get("attempts", []))
        lines.append(f"| {i['n']} | {i['source']} | {i['style']} | {i['instruction'] or ''} | {i.get('provider', '-')} "
                     f"| {i['seconds']} | {i.get('cost_usd', 0):.4f} | {i.get('face_check', '-')} | {attempts} |")
    (args.out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
