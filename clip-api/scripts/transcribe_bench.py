#!/usr/bin/env python3
"""Compare transcription providers on one recording: speed, cost, accuracy, and what each does to the clips.

  python scripts/transcribe_bench.py --audio <video or audio> --out <dir>
      [--providers local,groq,deepgram,assemblyai]   each may name a model: local:small.en, groq:whisper-large-v3
      [--keys-file <path>]          GROQ_API_KEY, DEEPGRAM_API_KEY, ASSEMBLYAI_API_KEY, ANTHROPIC_API_KEY (judge)
      [--reference <transcript.json>] [--terms scripts/gaming-terms.txt]
      [--select] [--judge auto|off] [--labels eval/labels-v2.csv --vod gta-online-1] [--duration 0-90]
  python scripts/transcribe_bench.py --audio <file> --out <dir> --make-reference large-v3
      Writes <out>/reference.json with the strongest local model: a model reference, not a human one.

The audio is extracted once (16 kHz mono WAV). Each provider transcribes the whole file, and gets:
- wall time, realtime factor (audio seconds per wall second), and an estimate for a 2-hour video;
- cost: billed seconds x the documented pay-as-you-go price (hosted_stt.PRICE_PER_HOUR, cited there);
  local: wall time x --local-usd-per-hour (the machine's price; 0 = not counted);
- reliability: requests, retries, errors;
- with --reference: WER (case and punctuation ignored, numbers not normalised), word timestamp error (median
  and p90 |start difference| over the words both transcripts agree on, aligned by difflib);
- gaming terms (--terms): how often each term is heard, and with a reference the share of its uses found;
- hallucination checks: words inside non-speech stretches of 5 s or more (Silero VAD, bundled with
  faster-whisper) and inside quiet seconds (below -45 dB), and repetition loops (the same 1 to 4 words
  repeated 4 or more times in a row, or the same segment 3 or more times).
With --select (needs a video): the clip pipeline picks moments from each provider's transcript (the same
signals, only the transcript differs; with the judge when ANTHROPIC_API_KEY is in the keys file and --judge is
not off) and each set is compared with the first local provider's: overlap of the top 10 / 20 / all, Spearman
rank correlation over the shared moments, and the eval set's numbers when --labels has rated rows.

Keys: --keys-file is read into this process only (python-dotenv; os.environ is not changed), must not be
readable by other users (chmod 600), and no key is printed or written: only which providers have one.

Writes <out>/results.json and <out>/summary.md (paste both back), and <out>/transcripts/, <out>/moments/.
Exit 0 = ran (a provider may have failed: see its status), 2 = bad input.
"""
import argparse
import difflib
import json
import os
import platform
import re
import statistics
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.pipeline import hosted_stt  # noqa: E402
from app.pipeline.hosted_stt import HostedConfig  # noqa: E402
from app.pipeline.stt import LocalProvider, extract_audio, wav_duration  # noqa: E402
from app.pipeline.transcribe import Transcript  # noqa: E402

KEY_NAMES = {"groq": "GROQ_API_KEY", "deepgram": "DEEPGRAM_API_KEY", "assemblyai": "ASSEMBLYAI_API_KEY",
             "judge": "ANTHROPIC_API_KEY"}
DEFAULT_MODELS = {"groq": "whisper-large-v3-turbo", "deepgram": "nova-3", "assemblyai": "assemblyai-stt-3-7"}
TERMS = Path(__file__).resolve().parent / "gaming-terms.txt"
TWO_HOURS = 7200.0
BUDGET = {"previews": 300.0, "final_render": 120.0}   # owner target: previews < 5 min, final render < 2 more
QUIET_DB, NONSPEECH_MIN_SEC = -45.0, 5.0


# ---------- keys ----------

def load_keys(path: Path | None) -> dict[str, str]:
    """{GROQ_API_KEY: value, ...} for the names this script knows and the file sets. Refuses a file that other
    users can read or write."""
    if path is None:
        return {}
    mode = path.stat().st_mode
    if mode & (stat.S_IROTH | stat.S_IWOTH):
        raise SystemExit(f"{path} can be read or written by other users: run `chmod 600 {path}` first")
    from dotenv import dotenv_values
    found = dotenv_values(path)
    return {name: v for name in KEY_NAMES.values() if (v := (found.get(name) or "").strip())}


def redact(text: str, keys: dict[str, str]) -> str:
    for v in keys.values():
        text = text.replace(v, "***")
    return text


# ---------- text ----------

def norm_words(text: str) -> list[str]:
    """Lowercase words without punctuation; hyphens split words; apostrophes inside words stay."""
    text = text.lower().replace("-", " ").replace("’", "'")
    return [w.strip("'") for w in re.sub(r"[^a-z0-9' ]+", " ", text).split() if w.strip("'")]


def norm_timed(words: list[tuple[float, float, str]]) -> list[tuple[float, str]]:
    return [(s, n) for s, _e, w in words for n in norm_words(w)]


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    """Word-level Levenshtein distance, one numpy row at a time (2-hour transcripts fit)."""
    import numpy as np
    if not ref:
        return len(hyp)
    vocab: dict[str, int] = {}
    r = np.array([vocab.setdefault(w, len(vocab)) for w in ref])
    h = [vocab.setdefault(w, len(vocab)) for w in hyp]
    idx = np.arange(len(ref) + 1)
    prev = idx.copy()
    for j, w in enumerate(h, 1):
        cur = np.empty_like(prev)
        cur[0] = j
        cur[1:] = np.minimum(prev[1:] + 1, prev[:-1] + (r != w))
        cur = np.minimum.accumulate(cur - idx) + idx               # deletions along the row
        prev = cur
    return int(prev[-1])


def aligned_starts(ref: list[tuple[float, str]], hyp: list[tuple[float, str]]) -> list[float]:
    """|start difference| of every word the two transcripts agree on (difflib's matching blocks)."""
    sm = difflib.SequenceMatcher(a=[w for _s, w in ref], b=[w for _s, w in hyp], autojunk=False)
    out = []
    for a, b, n in sm.get_matching_blocks():
        out += [abs(ref[a + k][0] - hyp[b + k][0]) for k in range(n)]
    return out


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(q * len(v)))], 3)


# ---------- reference and terms ----------

def load_reference(path: Path) -> dict:
    """A transcript in our shape: words [[start, end, word]] and/or segments ([start, end, text] or
    {start, end, text}), or plain "text". Optional "range": [start, end] (e.g. a hand-corrected 2 minutes):
    then only that part of each provider's transcript is compared."""
    d = json.loads(path.read_text())
    segs = [tuple(s[:3]) if isinstance(s, list) else (s["start"], s["end"], s["text"]) for s in d.get("segments") or []]
    words = [tuple(w[:3]) for w in d.get("words") or []]
    text = d.get("text") or (" ".join(w for _s, _e, w in words) if words else " ".join(x for _s, _e, x in segs))
    return {"words": words, "text": text, "range": d.get("range"), "note": d.get("note", ""),
            "model": d.get("model", "")}


def load_terms(path: Path) -> list[tuple[str, list[list[str]]]]:
    """Lines `Term | alias | alias`; # comments. Each spelling as normalised words."""
    out = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names = [n.strip() for n in line.split("|") if n.strip()]
            out.append((names[0], [norm_words(n) for n in names if norm_words(n)]))
    return out


def term_counts(words: list[str], terms) -> dict[str, int]:
    """How often each term is said: a position counts once even when several spellings start there."""
    return {name: sum(1 for i in range(len(words)) if any(words[i:i + len(sp)] == sp for sp in spellings))
            for name, spellings in terms}


# ---------- hallucination ----------

def nonspeech_stretches(wav: Path) -> list[tuple[float, float]]:
    """Stretches of NONSPEECH_MIN_SEC or more with no speech by Silero VAD, in 10-minute blocks."""
    import wave

    import numpy as np
    from faster_whisper.vad import get_speech_timestamps
    speech = []
    with wave.open(str(wav), "rb") as w:
        rate, n = w.getframerate(), w.getnframes()
        block = 600 * rate
        for i in range(0, n, block):
            w.setpos(i)
            a = np.frombuffer(w.readframes(min(block, n - i)), dtype=np.int16).astype(np.float32) / 32768
            speech += [((i + c["start"]) / rate, (i + c["end"]) / rate) for c in get_speech_timestamps(a)]
    gaps, t = [], 0.0
    for s, e in speech + [(n / rate, n / rate)]:
        if s - t >= NONSPEECH_MIN_SEC:
            gaps.append((round(t, 2), round(s, 2)))
        t = max(t, e)
    return gaps


def loops(words: list[str], segments: list[str]) -> list[str]:
    """Repetition loops: 1-4 words repeated 4+ times in a row, or one segment 3+ times in a row."""
    found, i = [], 0
    while i < len(words):
        hit = 0
        for n in range(1, 5):
            gram, reps = words[i:i + n], 1
            while len(gram) == n and words[i + reps * n:i + (reps + 1) * n] == gram:
                reps += 1
            if reps >= 4:
                found.append(f"{' '.join(gram)} x{reps}")
                hit = reps * n
                break
        i += hit or 1
    run = 1
    for a, b in zip(segments, segments[1:]):
        run = run + 1 if a.strip().lower() == b.strip().lower() and a.strip() else 1
        if run == 3:
            found.append(f"segment '{b.strip()[:40]}' x3+")
    return found


def in_spans(t: float, spans: list[tuple[float, float]]) -> bool:
    import bisect
    i = bisect.bisect_right([s for s, _e in spans], t) - 1
    return i >= 0 and spans[i][0] <= t < spans[i][1]


def hallucination(t: Transcript, levels: list[float], gaps: list[tuple[float, float]]) -> dict:
    quiet = [w for w in t.words if 0 <= int((w[0] + w[1]) / 2) < len(levels) and levels[int((w[0] + w[1]) / 2)] < QUIET_DB]
    inside = [w for w in t.words if in_spans((w[0] + w[1]) / 2, gaps)]
    lp = loops([n for _s, n in norm_timed(t.words)], [x for _s, _e, x in t.segments])
    return {"words_in_nonspeech": len(inside), "nonspeech_sec": round(sum(e - s for s, e in gaps), 1),
            "examples_in_nonspeech": [f"{w[0]:.1f}s {w[2]}" for w in inside[:5]],
            "words_in_quiet_seconds": len(quiet), "loops": len(lp), "loop_examples": lp[:3]}


# ---------- providers ----------

def parse_providers(spec: str, local_default: str) -> list[tuple[str, str]]:
    out = []
    for item in [x.strip() for x in spec.split(",") if x.strip()]:
        name, _, model = item.partition(":")
        if name not in ("local", *hosted_stt.HOSTED):
            raise SystemExit(f"unknown provider '{name}' (local, {', '.join(hosted_stt.HOSTED)})")
        out.append((name, model or (local_default if name == "local" else DEFAULT_MODELS[name])))
    return out


def training_block(name: str, args) -> str | None:
    """Why the audio may not go to this provider, or None. Audio goes only where it is not used for training
    (docs read 2026-11-18, see docs/transcription/provider-comparison.md): Groq does not train on inputs;
    Deepgram is called with mip_opt_out=true; AssemblyAI trains on some files unless the account opted out or
    the files go to its EU servers."""
    if name == "assemblyai" and args.assemblyai_region != "eu" and not args.assemblyai_opted_out:
        return ("AssemblyAI may train on files sent to its US servers: use --assemblyai-region eu, or opt out in "
                "its dashboard (Data Controls) and pass --assemblyai-opted-out")
    return None


def run_one(name: str, model: str, wav: Path, work: Path, keys: dict, args) -> tuple[dict, Transcript | None]:
    row = {"provider": name, "model": model, "label": f"{name}:{model}"}
    usage, load_sec = None, 0.0
    if name == "local":
        from app.pipeline.transcribe import FasterWhisperTranscriber
        tr = FasterWhisperTranscriber(model, words=True)
        t0 = time.monotonic()
        tr._load()
        load_sec = time.monotonic() - t0
        provider = LocalProvider(tr, chunk_sec=args.chunk_sec)
        row["usd_per_hour"] = None
    else:
        key = keys.get(KEY_NAMES[name])
        if not key:
            row.update(status="skipped", error=f"{KEY_NAMES[name]} not in the keys file")
            return row, None
        if blocked := training_block(name, args):
            row.update(status="skipped", error=blocked)
            return row, None
        provider = hosted_stt.HOSTED[name](HostedConfig(api_key=key, model=model, timeout_sec=args.timeout,
                                                        diarize=True, region=args.assemblyai_region))
        usage = provider.usage
        row["usd_per_hour"] = provider.price_per_hour()
    duration = wav_duration(wav)
    t0 = time.monotonic()
    transcript = None
    try:
        transcript = provider.transcribe_file(wav, work)
        row["status"] = "ok"
    except Exception as e:      # noqa: BLE001 -- a failed provider is a result, not the end of the benchmark
        row.update(status="failed", error=redact(f"{getattr(e, 'code', type(e).__name__)}: {e}", keys)[:300])
    wall = time.monotonic() - t0
    row.update(wall_sec=round(wall, 1), model_load_sec=round(load_sec, 1), audio_sec=round(duration, 1),
               realtime_factor=round(duration / wall, 1) if wall > 0 else None,
               est_2h_sec=round(wall * TWO_HOURS / duration, 0) if name == "local" else None)
    if usage is not None:
        row.update(billed_sec=round(usage.billed_sec, 1), requests=usage.requests, retries=usage.retries,
                   errors=[redact(x, keys) for x in usage.errors][:10])
        price = row["usd_per_hour"]
        row["cost_usd"] = round(usage.billed_sec / 3600 * price, 4) if price is not None else None
        row["usd_per_2h_vod"] = round(2 * price, 3) if price is not None else None
        row["est_2h_sec"] = None      # not linear in length: run a 2-hour file to know
    else:
        row["cost_usd"] = round(wall / 3600 * args.local_usd_per_hour, 4)
        row["usd_per_2h_vod"] = round(row["est_2h_sec"] / 3600 * args.local_usd_per_hour, 3)
    return row, transcript


def accuracy(t: Transcript, ref: dict | None, terms, base_counts: dict | None) -> dict:
    words = t.words
    if ref and ref["range"]:
        a, b = ref["range"]
        words = [w for w in words if a <= w[0] < b]
    hyp = norm_timed(words)
    hyp_words = [w for _s, w in hyp]
    out: dict = {"words": len(hyp_words), "speaker_turns": None if t.turns is None else len(t.turns)}
    counts = term_counts(hyp_words, terms)
    out["terms_heard"] = sum(counts.values())
    if ref:
        rw = norm_words(ref["text"])
        out["wer"] = round(edit_distance(rw, hyp_words) / max(1, len(rw)), 4)
        out["ref_words"] = len(rw)
        if ref["words"]:
            deltas = aligned_starts(norm_timed(ref["words"]), hyp)
            out.update(ts_aligned_words=len(deltas), ts_median_sec=pct(deltas, 0.5), ts_p90_sec=pct(deltas, 0.9))
        rc = term_counts(rw, terms)
        used = {k: v for k, v in rc.items() if v}
        out["term_recall"] = round(sum(min(counts[k], v) for k, v in used.items()) / sum(used.values()), 3) if used else None
        out["terms_missed"] = sorted(k for k, v in used.items() if counts[k] < v)[:15]
    elif base_counts is not None:
        out["terms_vs_baseline"] = {k: [counts[k], base_counts[k]] for k in counts if counts[k] or base_counts[k]}
    out["_counts"] = counts
    return out


def as_doc(t: Transcript, duration: float, model: str) -> dict:
    return {"duration": round(duration, 3), "model": model,
            "segments": [{"start": s, "end": e, "text": x} for s, e, x in t.segments],
            "words": [[s, e, w] for s, e, w in t.words], "turns": t.turns}


# ---------- highlight impact ----------

def window(t: Transcript, a: float, b: float) -> Transcript:
    return Transcript(words=[(s - a, e - a, w) for s, e, w in t.words if a <= s < b],
                      segments=[(s - a, e - a, x) for s, e, x in t.segments if a <= s < b])


def select_moments(video: Path, t: Transcript, audio, judge, duration_bucket: str) -> list[dict]:
    """The pipeline's moments when every candidate's speech is read from `t` instead of being transcribed."""
    import app.pipeline as pipeline
    from app.pipeline import PipelineOptions, run_pipeline

    class Chosen(Exception):
        pass
    chosen = []

    def on_moments(moments):
        chosen.extend(moments)
        raise Chosen

    def reading(c, i, transcriber, src, duration, out_dir, deadline, pad=pipeline.PAD, audio=None, floor=0.0):
        c.offset = max(floor, c.start - pad)
        c.transcript = window(t, c.offset, min(duration, c.end + pad))

    class Stub:     # never asked to transcribe: `reading` answers instead
        def transcribe(self, wav):
            raise AssertionError("not used")
    with tempfile.TemporaryDirectory(prefix="tbench_select_") as tmp, mock.patch.object(pipeline, "_transcribe", reading):
        try:
            run_pipeline(video, PipelineOptions(duration=duration_bucket), Path(tmp), transcriber=Stub(),
                         judge=judge, fast_transcriber=Stub() if judge else None, source_audio=audio,
                         on_moments=on_moments)
        except Chosen:
            pass
    return [{"rank": i, "start_sec": round(m.start, 2), "end_sec": round(m.end, 2), "score": round(m.score, 4)}
            for i, m in enumerate(chosen, 1)]


def same_moment(a: dict, b: dict) -> bool:
    inter = min(a["end_sec"], b["end_sec"]) - max(a["start_sec"], b["start_sec"])
    return inter >= 0.5 * min(a["end_sec"] - a["start_sec"], b["end_sec"] - b["start_sec"])


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for k, i in enumerate(order):
            r[i] = float(k)
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def compare_sets(mine: list[dict], base: list[dict]) -> dict:
    out = {"moments": len(mine)}
    for k in (10, 20, None):
        a, b = mine[:k] if k else mine, base[:k] if k else base
        shared = sum(1 for m in a if any(same_moment(m, x) for x in b))
        out[f"overlap@{k or 'all'}"] = round(shared / len(a), 3) if a else None
    pairs = [(m["rank"], next(x["rank"] for x in base if same_moment(m, x)))
             for m in mine if any(same_moment(m, x) for x in base)]
    out["spearman_shared"] = spearman([p[0] for p in pairs], [p[1] for p in pairs])
    return out


def eval_numbers(labels: Path, vod: str | None, label: str, run_file: Path, duration: float) -> dict | None:
    import eval_clips
    clips = eval_clips.load_clips(run_file)
    if eval_clips.is_v2(labels):
        if not vod:
            return {"error": "--vod is needed with a v2 sheet"}
        rows = [r for r in eval_clips.parse_v2(labels)[0] if r["label"] is not None]
        if not rows:
            return {"error": "no rated rows in the sheet yet"}
        s = eval_clips.score_v2(rows, {label: {vod: clips}})["systems"][label]["per_vod"][vod]
    else:
        rows = [r for r in eval_clips.load_labels(labels) if r.get("label") is not None]
        if not rows:
            return {"error": "no rated rows in the sheet yet"}
        s = eval_clips.score(rows, clips, duration)
    return {k: v for k, v in s.items() if k not in ("per_clip", "missed")}


def machine() -> dict:
    quota = None
    try:
        q, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        quota = None if q == "max" else round(int(q) / int(period), 2)
    except (OSError, ValueError):
        pass
    return {"platform": platform.platform(), "processor": platform.processor() or platform.machine(),
            "cpu_count": os.cpu_count(), "cpu_quota": quota, "omp_num_threads": os.environ.get("OMP_NUM_THREADS")}


# ---------- report ----------

def fmt(v, unit="", digits=None):
    if v is None:
        return "–"
    if digits is not None:
        v = round(v, digits)
    return f"{v}{unit}"


def summary_md(res: dict) -> str:
    a = res["audio"]
    lines = [f"# Transcription benchmark: {a['source']} ({a['duration_sec'] / 60:.1f} min)", "",
             f"{res['created']} · {res['machine']['platform']} · {res['machine']['cpu_count']} CPUs"
             f" (quota {res['machine']['cpu_quota']}) · reference: {res['reference'] or 'none'}", "",
             "| Provider | Status | Wall | RTF | Est. 2 h | $ this file | $ / 2 h VOD | WER | ts median / p90 | "
             "Term recall | Words in non-speech | Loops | Retries / errors |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in res["providers"]:
        acc = p.get("accuracy") or {}
        hal = p.get("hallucination") or {}
        lines.append(" | ".join([
            f"| {p['label']}", p["status"], fmt(p.get("wall_sec"), " s"), fmt(p.get("realtime_factor"), "x"),
            fmt(p.get("est_2h_sec"), " s"), fmt(p.get("cost_usd"), "", 4), fmt(p.get("usd_per_2h_vod")),
            fmt(acc.get("wer")), f"{fmt(acc.get('ts_median_sec'))} / {fmt(acc.get('ts_p90_sec'))} s",
            fmt(acc.get("term_recall")), fmt(hal.get("words_in_nonspeech")), fmt(hal.get("loops")),
            f"{p.get('retries', 0)} / {len(p.get('errors') or [])}"]) + " |")
    lines += ["", "Budget for a 2-hour video: previews in 300 s, final render in 120 s more. Transcription share:", ""]
    for p in res["providers"]:
        est = p.get("est_2h_sec") or p.get("measured_2h_sec")
        if est:
            lines.append(f"- {p['label']}: about {est:.0f} s of the 300 s ({est / 300:.0%})")
    if res.get("selection"):
        lines += ["", "## Clips from each transcript (vs " + res["selection"]["baseline"] + ")", "",
                  "| Provider | Moments | Overlap top 10 | top 20 | all | Spearman (shared) | Eval |", "|---|---|---|---|---|---|---|"]
        for label, s in res["selection"]["providers"].items():
            ev = s.get("eval")
            evs = "–" if not ev else ev.get("error") or json.dumps({k: ev[k] for k in ("recall", "@20", "@40") if k in ev})
            lines.append(f"| {label} | {s.get('moments', '–')} | {fmt(s.get('overlap@10'))} | {fmt(s.get('overlap@20'))} | "
                         f"{fmt(s.get('overlap@all'))} | {fmt(s.get('spearman_shared'))} | {evs} |")
        lines.append(f"\nJudge: {res['selection']['judge']}.")
    for p in res["providers"]:
        if p.get("error"):
            lines.append(f"\n{p['label']}: {p['error']}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--audio", type=Path, required=True, help="audio or video file")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--providers", default="local")
    ap.add_argument("--keys-file", type=Path)
    ap.add_argument("--reference", type=Path)
    ap.add_argument("--make-reference", metavar="MODEL")
    ap.add_argument("--terms", type=Path, default=TERMS)
    ap.add_argument("--select", action="store_true", help="also pick moments from each transcript (video input)")
    ap.add_argument("--judge", choices=("auto", "off"), default="auto")
    ap.add_argument("--labels", type=Path)
    ap.add_argument("--vod")
    ap.add_argument("--duration", default="0-90", help="clip length bucket for --select")
    ap.add_argument("--chunk-sec", type=float, default=300.0, help="local: chunk length (TRANSCRIBE_CHUNK_SEC)")
    ap.add_argument("--timeout", type=float, default=1800.0, help="hosted: seconds per attempt at the whole file")
    ap.add_argument("--assemblyai-region", choices=("us", "eu"), default="eu",
                    help="eu (default): AssemblyAI's EU servers, whose files are excluded from model training")
    ap.add_argument("--assemblyai-opted-out", action="store_true",
                    help="the account has opted out of AssemblyAI's model improvement program (needed for us)")
    ap.add_argument("--local-usd-per-hour", type=float, default=0.0714,
                    help="machine price for local runs: $48/month 4 vCPU / 8 GB droplet = 0.0714; 0 = not counted")
    ap.add_argument("--keep-audio", action="store_true")
    args = ap.parse_args(argv)
    if not args.audio.is_file():
        print(f"no such file: {args.audio}", file=sys.stderr)
        return 2
    keys = load_keys(args.keys_file)
    print("keys:", ", ".join(f"{p} {'yes' if KEY_NAMES[p] in keys else 'no'}" for p in KEY_NAMES))
    from app.config import get_settings
    local_default = get_settings().whisper_index_model if get_settings().whisper_index_model != "none" else "base.en"
    specs = parse_providers(args.providers, local_default)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "transcripts").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="tbench_", dir=args.out))
    wav = work / "audio.wav"
    t0 = time.monotonic()
    audio = extract_audio(args.audio, wav)
    extract_sec = time.monotonic() - t0
    duration = wav_duration(wav)
    print(f"audio: {duration / 60:.1f} min, extracted in {extract_sec:.1f} s")
    try:
        if args.make_reference:
            return make_reference(args, wav, work, duration)
        ref = load_reference(args.reference) if args.reference else None
        terms = load_terms(args.terms) if args.terms and args.terms.is_file() else []
        gaps = nonspeech_stretches(wav)
        res = {"bench_version": 1, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "machine": machine(), "audio": {"source": args.audio.name, "duration_sec": round(duration, 1),
                                               "extract_sec": round(extract_sec, 1)},
               "reference": (f"{args.reference.name} ({ref['model'] or 'unknown model'}; {ref['note'] or 'no note'})"
                             if ref else None),
               "prices": {f"{k[0]}:{k[1]}": v for k, v in hosted_stt.PRICE_PER_HOUR.items()},
               "providers": []}
        transcripts, base_counts = {}, None
        for name, model in specs:
            print(f"{name}:{model} ...", flush=True)
            row, t = run_one(name, model, wav, work, keys, args)
            if t is not None:
                acc = accuracy(t, ref, terms, base_counts)
                counts = acc.pop("_counts")
                if base_counts is None and name == "local":
                    base_counts = counts
                row["accuracy"] = acc
                row["hallucination"] = hallucination(t, audio.levels, gaps)
                transcripts[row["label"]] = t
                (args.out / "transcripts" / f"{row['label'].replace(':', '_')}.json").write_text(
                    json.dumps(as_doc(t, duration, row["label"])))
            res["providers"].append(row)
            print(f"  {row['status']} {row.get('wall_sec')} s", flush=True)
        if args.select:
            res["selection"] = selection(args, transcripts, audio, keys, duration)
        (args.out / "results.json").write_text(json.dumps(res, indent=1))
        (args.out / "summary.md").write_text(summary_md(res))
        print(summary_md(res))
        print(f"wrote {args.out / 'results.json'} and {args.out / 'summary.md'}")
        return 0
    finally:
        if not args.keep_audio:
            wav.unlink(missing_ok=True)
        for f in work.glob("*"):
            f.unlink(missing_ok=True)
        work.rmdir()


def selection(args, transcripts: dict, audio, keys: dict, duration: float) -> dict:
    judge, judged = None, "off"
    if args.judge == "auto" and KEY_NAMES["judge"] in keys:
        from app.ai import ClaudeAI
        from app.config import get_settings
        ai = ClaudeAI(keys[KEY_NAMES["judge"]], get_settings().ai_model)
        judge = lambda text, frame, ctx: ai.clip_meta(text, ctx, frame)  # noqa: E731
        judged = f"on ({get_settings().ai_model}; costs tokens per candidate)"
    (args.out / "moments").mkdir(exist_ok=True)
    out = {"judge": judged, "baseline": None, "providers": {}}
    sets = {}
    for label, t in transcripts.items():
        print(f"selecting moments from {label} ...", flush=True)
        try:
            sets[label] = select_moments(args.audio, t, audio, judge, args.duration)
        except Exception as e:      # noqa: BLE001
            out["providers"][label] = {"error": redact(f"{getattr(e, 'code', type(e).__name__)}: {e}", keys)[:300]}
            continue
        run_file = args.out / "moments" / f"{label.replace(':', '_')}.json"
        run_file.write_text(json.dumps({"system": label, "source": args.audio.name, "clips": sets[label]}, indent=1))
        out["providers"][label] = {"moments": len(sets[label])}
        if args.labels:
            out["providers"][label]["eval"] = eval_numbers(args.labels, args.vod, label, run_file, duration)
    base = next((label for label in sets if label.startswith("local:")), None)
    out["baseline"] = base
    if base:
        for label, moments in sets.items():
            out["providers"][label].update(compare_sets(moments, sets[base]))
    return out


def make_reference(args, wav: Path, work: Path, duration: float) -> int:
    from app.pipeline.transcribe import FasterWhisperTranscriber
    tr = FasterWhisperTranscriber(args.make_reference, words=True)
    t0 = time.monotonic()
    t = LocalProvider(tr, chunk_sec=args.chunk_sec).transcribe_file(wav, work)
    doc = as_doc(t, duration, args.make_reference)
    doc["note"] = f"model reference ({args.make_reference}, CPU int8, beam 5), not human"
    doc["wall_sec"] = round(time.monotonic() - t0, 1)
    (args.out / "reference.json").write_text(json.dumps(doc))
    print(f"wrote {args.out / 'reference.json'} ({len(t.words)} words, {doc['wall_sec']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
