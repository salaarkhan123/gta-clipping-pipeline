#!/usr/bin/env python3
"""Website media made by the real clipping engine: loops, posters, stills and a manifest.json per site section.

Each step can be rerun. `--work` holds everything in between (audio, segments, scout results). The flow is
scout, then render (which fetches what it needs), then the owner picks in the featured picker, then publish.

  python scripts/make_site_media.py scout  --sources S.json --work W
      For each source, the engine (run_pipeline, no AI judge) ranks the whole video and stops before rendering.
      A link source is scored from its audio only: the audio is downloaded (public content, no cookies or
      logins), scored, then deleted. Writes W/scout/<source>.json: the engine's moments, best first, each with
      its signal-only rating and the display rating the app would show for that video (app/scoring.py).

  python scripts/make_site_media.py fetch  --sources S.json --shots H.json --work W
      Downloads (yt-dlp --download-sections) or cuts only the pieces the shot list uses into W/seg/.

  python scripts/make_site_media.py render --sources S.json --shots H.json --work W --out OUT
                                           [--only a,b] [--featured F]
      Renders every shot through the engine (run_pipeline on the segment with the shot's options) as candidates:
      OUT/<section>/<cid>.mp4 (H.264, muted, faststart), <cid>.webm (VP9), <cid>.webp (poster) or a still, and
      OUT/<section>/candidates.json. A cid is "<source>-m<rank>", or "<variant>--<source>-m<rank>" in the sections
      that show one moment several ways (captions, reframe, templates, setup). With --featured, the picker's
      open requests are served first.

  python scripts/make_site_media.py more --section S --like CID [--count N] ...
      "Find another moment like this": the same shot on the source's next-best scouted moment.
  python scripts/make_site_media.py requests --featured F ...
      Serves every request in F ("find another moment like this", from the picker) that no candidate answers yet.

  python scripts/make_site_media.py publish --sources S.json --work W --out OUT --featured F --public P
      Copies only the featured candidates, in the owner's order, into P/<section>/ under the ids the site reads
      (clip-1.., hook-1.., or the variant name) and writes P/<section>/manifest.json, the shape
      clip-api/web-src/lib/media.ts reads, with the permission and a credit per item.

  python scripts/make_site_media.py clean --work W     Deletes the downloads and segments in W.

Ratings are signal-only (app.ai.signal_meta): this script never calls a paid AI. A shot that needs hook text
gives it in the shot list, and the manifest records that the text came from the shot list, not from the AI.
Use only footage the owner has the rights to publish. Exit 0 = ok, 1 = a step failed, 2 = bad input.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai import signal_meta  # noqa: E402
from app.pipeline import Deadline, PipelineError, PipelineOptions, probe, run_pipeline  # noqa: E402
from app.pipeline.ff import SAFE_IN, run  # noqa: E402
from app.scoring import display_scores  # noqa: E402
from app.templates import TEMPLATES  # noqa: E402

PAD = 2.0                       # seconds fetched either side of a moment
LOOP_SECONDS = 8.0
MAX_BYTES = 1_450_000           # each loop file (mp4, webm) stays under ~1.5 MB
POSTER_BYTES = 120_000
STILL_BYTES = 60_000
VERTICAL, WIDE = (540, 960), (960, 540)
CAP = 900                       # seconds any one ffmpeg or download may take
FORMAT = "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b"
FORMAT_RETRY = "bv*[height<=1080][vcodec^=avc1]+139/bv*[height<=1080]+wa/b"
AUDIO_FORMAT = "ba[abr<=80]/wa/ba"


class Stop(Exception):
    """Raised from on_moments: scouting needs the ranked moments, not the renders."""


def load(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"cannot read {path}: {e}")


def ytdlp(*args: str) -> None:
    # Public content only: no cookies, no logins, no proxies. A refusal is reported and the step fails.
    cmd = ["yt-dlp", "--no-playlist", "--no-cookies", "--no-cookies-from-browser", "-q", "--no-warnings", *args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=CAP * 4)
    if res.returncode:
        raise PipelineError("download_refused", (res.stderr.strip().splitlines() or ["download failed"])[-1][:300])


def ffmpeg(*args, cap: float = CAP) -> None:
    run(["ffmpeg", "-loglevel", "error", "-y", *args], Deadline(cap))


def transcriber(model: str):
    if model == "none":
        return None
    from app.pipeline.transcribe import FasterWhisperTranscriber
    return FasterWhisperTranscriber(model)


# ---------------------------------------------------------------- scout

def scout(sources: dict, work: Path, only: set | None, model: str) -> None:
    (work / "scout").mkdir(parents=True, exist_ok=True)
    stt = transcriber(model)
    for sid, src in sources.items():
        if (only and sid not in only) or (not only and (work / "scout" / f"{sid}.json").exists()):
            continue            # without --only, a source already scouted is kept
        print(f"scout {sid}", flush=True)
        tmp = Path(tempfile.mkdtemp(prefix=f"scout-{sid}-", dir=work))
        try:
            video = Path(src["file"]).expanduser() if src.get("file") else _audio_proxy(src["url"], tmp)
            info = probe(video)
            s = src.get("scout", {})
            options = PipelineOptions(limit=s.get("limit", 12), clip_length=s.get("clip_length", 20), vertical=False,
                                      captions=False, tighten=False, flash_forward=False, hook_overlay=False,
                                      punch_zoom=False, range=s.get("range"))
            found: list = []

            def keep(moments):
                found.extend(moments)
                raise Stop()

            try:
                run_pipeline(video, options, tmp, transcriber=stt, on_moments=keep)
            except Stop:
                pass
            raws = [signal_meta(m.score)["virality"]["score"] for m in found]
            shown = display_scores(raws)
            moments = [{"rank": i + 1, "start": m.start, "end": m.end, "score": m.score, "rating_raw": raw,
                        "rating": dis, "signals": m.signals,
                        "exclamations": m.features.get("exclamation_hits", 0), "words": m.features.get("words")}
                       for i, (m, raw, dis) in enumerate(zip(found, raws, shown))]
            out = {"source": sid, "duration_sec": round(info.duration, 1), "rating_source": "signals",
                   "options": {"limit": options.limit, "clip_length": options.clip_length, "range": options.range},
                   "moments": moments}
            (work / "scout" / f"{sid}.json").write_text(json.dumps(out, indent=1))
            for m in moments:
                print(f"  #{m['rank']:>2} {_hms(m['start'])}-{_hms(m['end'])} rating {m['rating']} "
                      f"(raw {m['rating_raw']}, words {m['words']}, excl {m['exclamations']})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _audio_proxy(url: str, tmp: Path) -> Path:
    """The source's audio under a 1 fps, 64x36 black picture: what run_pipeline needs to score a link without
    downloading its video."""
    ytdlp("-f", AUDIO_FORMAT, "-o", str(tmp / "audio.%(ext)s"), url)
    audio = next(tmp.glob("audio.*"))
    proxy = tmp / "proxy.mkv"
    ffmpeg(*SAFE_IN, "-f", "lavfi", "-i", "color=black:s=64x36:r=1", *SAFE_IN, "-i", audio, "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage", "-c:a", "copy", "-shortest", proxy,
           cap=CAP * 2)
    audio.unlink()
    return proxy


def _hms(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}"


# ---------------------------------------------------------------- fetch

def moment_of(work: Path, sid: str, rank: int) -> dict:
    data = load(work / "scout" / f"{sid}.json")
    for m in data["moments"]:
        if m["rank"] == rank:
            return m
    sys.exit(f"{sid} has no scouted moment #{rank}")


def piece(shot: dict, work: Path) -> tuple[str, float, float]:
    """(name, start, end) of the segment a shot is cut from, in source seconds."""
    sid = shot["source"]
    if "moment" in shot:
        m = moment_of(work, sid, shot["moment"])
        return f"{sid}-m{shot['moment']}", max(0.0, m["start"] - PAD), m["end"] + PAD
    at, seconds = float(shot["at"]), float(shot.get("seconds", 12))
    return f"{sid}-at{int(at)}", at, at + seconds


def fetch(sources: dict, shots: list, work: Path) -> None:
    seg = work / "seg"
    seg.mkdir(parents=True, exist_ok=True)
    wanted = {}
    for shot in shots:
        name, a, b = piece(shot, work)
        wanted[name] = (shot["source"], a, b)
    for name, (sid, a, b) in sorted(wanted.items()):
        out = seg / f"{name}.mp4"
        if (seg / f"{name}.json").exists() and _complete(out, b - a):
            continue
        src = sources[sid]
        print(f"fetch {name} {_hms(a)}-{_hms(b)}", flush=True)
        # Two tries. The second asks for the small AAC audio: on some live-stream VODs ffmpeg cannot open
        # YouTube's other audio stream at a seek point, and a section download now and then drops mid-way.
        for fmt in (FORMAT, FORMAT_RETRY):
            try:
                if src.get("file"):
                    ffmpeg("-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", *SAFE_IN, "-i", Path(src["file"]).expanduser(),
                           "-c", "copy", "-avoid_negative_ts", "make_zero", out)
                else:
                    out.unlink(missing_ok=True)
                    ytdlp("-f", fmt, "--merge-output-format", "mp4", "--download-sections", f"*{a:.2f}-{b:.2f}",
                          "-o", str(out), src["url"])
                if not _complete(out, b - a):
                    raise PipelineError("short_segment", "the downloaded piece is much shorter than asked for")
                (seg / f"{name}.json").write_text(json.dumps({"source": sid, "start": a, "end": b}))
                break
            except PipelineError as e:
                (seg / f"{name}.json").unlink(missing_ok=True)
                if fmt is FORMAT_RETRY:      # the shots that need it fail at render; the rest go on
                    print(f"  FAILED fetch {name}: {e.message}", file=sys.stderr)


def _complete(path: Path, seconds: float) -> bool:
    """The segment exists, has audio, and is at least 70% of the length asked for."""
    try:
        info = probe(path)
    except PipelineError:
        return False
    return info.has_audio and info.duration >= 0.7 * seconds


# ---------------------------------------------------------------- render

def options_for(shot: dict) -> PipelineOptions:
    opts = {"limit": 1, "max_side": 540, "facecam_region": "auto", "caption_style": "impact",
            "flash_forward": False, "hook_overlay": bool(shot.get("hook"))}
    if shot.get("template"):
        t = TEMPLATES[shot["template"]]
        opts.update(t["options"], template=shot["template"])
        panels = t.get("panels") or {}
        if panels.get("camera"):
            opts.update(camera=panels["camera"], split_ratio=panels.get("split_ratio"))
    opts.update(shot.get("options", {}))
    return PipelineOptions(**opts)


def render_shot(shot: dict, seg_file: Path, seg: dict, tmp: Path, stt, budget: float):
    """The engine's render of one shot: (video, clip-relative words, ClipResult or None)."""
    if shot.get("kind", "clip") == "source":
        return seg_file, [], None
    options = options_for(shot)
    length = seg["end"] - seg["start"]
    options.clip_length = int(shot.get("clip_length", max(6, length - 2 * PAD)))
    options.range = None
    judge = None
    if shot.get("hook"):
        # No AI: the shot list supplies the hook. The pipeline only burns a hook the judge's meta carries, so
        # this judge hands over that text and the signal rating, and rates nothing itself.
        def judge(_text, _frame, _ctx, hook=shot["hook"]):
            return {"virality": {"score": 60}, "hook": hook, "source": "shot-list"}
    clips = run_pipeline(seg_file, options, tmp, transcriber=None if shot.get("output") in ("still", "strip") else stt,
                         deadline=Deadline(budget), judge=judge)
    if not clips:
        raise PipelineError("no_clip", "the engine returned no clip")
    clip = clips[0]
    words = []
    if clip.captions_path:
        words = json.loads(Path(clip.captions_path).read_text())["words"]
    return clip.video_path, words, clip


def encode_loop(src: Path, out: Path, start: float, seconds: float, size: tuple[int, int]) -> dict:
    """<out>.mp4 + <out>.webm (muted) under MAX_BYTES each, and <out>.webp poster. Returns the file names."""
    w, h = size
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps=30,"
          f"format=yuv420p")
    files = {}
    for ext, codec in (("mp4", ["-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-movflags", "+faststart"]),
                       ("webm", ["-c:v", "libvpx-vp9", "-b:v", "0", "-row-mt", "1", "-cpu-used", "2"])):
        path = out.with_suffix(f".{ext}")
        crf = 26 if ext == "mp4" else 36
        while True:
            ffmpeg("-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", *SAFE_IN, "-i", src, "-an", "-vf", vf, *codec,
                   "-crf", str(crf), path)
            if path.stat().st_size <= MAX_BYTES or crf >= 44:
                break
            crf += 3
        if path.stat().st_size > MAX_BYTES:
            raise PipelineError("too_big", f"{path.name} is over {MAX_BYTES} bytes even at crf {crf}")
        files["src" if ext == "mp4" else "webm"] = path.name
    poster = out.with_suffix(".webp")
    still(src, poster, start + min(1.0, seconds / 2), size, POSTER_BYTES)
    files["poster"] = poster.name
    return files


def still(src: Path, out: Path, at: float, size: tuple[int, int], limit: int, vf_extra: str = "") -> None:
    w, h = size
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}" + vf_extra
    for q in (82, 72, 62, 52, 42, 32):
        ffmpeg("-ss", f"{at:.3f}", *SAFE_IN, "-i", src, "-frames:v", "1", "-vf", vf, "-c:v", "libwebp",
               "-quality", str(q), out)
        if out.stat().st_size <= limit:
            return
    raise PipelineError("too_big", f"{out.name} is over {limit} bytes")


def strip(frames: list[tuple[Path, float]], out: Path, size: tuple[int, int], limit: int) -> None:
    """One row of frames, each `size`, from (file, second) pairs."""
    w, h = size
    tmp = Path(tempfile.mkdtemp(prefix="strip"))
    try:
        parts = []
        for i, (f, at) in enumerate(frames):
            p = tmp / f"{i:02d}.png"
            ffmpeg("-ss", f"{at:.3f}", *SAFE_IN, "-i", f, "-frames:v", "1", "-vf",
                   f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", p)
            parts.append(p)
        inputs = [a for p in parts for a in (*SAFE_IN, "-i", p)]
        for q in (80, 65, 50, 35):
            ffmpeg(*inputs, "-filter_complex", f"hstack=inputs={len(parts)}", "-c:v", "libwebp", "-quality", str(q), out)
            if out.stat().st_size <= limit:
                return
        raise PipelineError("too_big", f"{out.name} is over {limit} bytes")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Candidates: every rendered shot is a candidate with an id (cid) the owner's picker (featured.json) refers to.
# A section of variants shows one moment several ways (cid "<variant>--<source>-m<rank>"); the other sections show
# one clip per moment (cid "<source>-m<rank>"). `publish` renames them to the ids the site reads.
VARIANT_SECTIONS = ("captions", "reframe", "templates", "setup")
ORDINAL = {"hero-long-video": "vod", "hero-vertical-clips": "clip", "hook": "hook", "editor": "editor",
           "clip-finding": "find"}


def cid_of(shot: dict) -> str:
    where = f"{shot['source']}-m{shot['moment']}" if "moment" in shot else f"{shot['source']}-at{int(shot['at'])}"
    return f"{shot['variant']}--{where}" if shot.get("variant") else where


def expand(shots: list) -> list:
    """One concrete shot per candidate: a shot whose `moment` is a list becomes one shot per moment."""
    out = []
    for shot in shots:
        if shot["section"] in VARIANT_SECTIONS and not shot.get("variant"):
            sys.exit(f"a {shot['section']} shot needs a variant")
        for m in (shot["moment"] if isinstance(shot.get("moment"), list) else [shot.get("moment")]):
            one = {**shot, **({"moment": m} if m is not None else {})}
            if not one.get("moment"):
                one.pop("moment", None)
            one["cid"] = cid_of(one)
            if one.get("words_from"):
                one["words_from"] = cid_of({**one, "variant": one["words_from"]})
            out.append(one)
    return out


def read_candidates(path: Path, section: str) -> dict:
    data = load(path) if path.exists() else {"section": section, "version": 1, "candidates": []}
    return {c["cid"]: c for c in data["candidates"]}


CONFIRMED = "owner-confirmed"


def write_candidates(path: Path, section: str, by_cid: dict, permission: str, sources: dict) -> None:
    """Several runs (each with its own sources file) share one candidates.json, so permission is per candidate
    (`commercial_permission`, stamped from the run that rendered it). The file-level `permission`, which the
    picker warns on, is a confirmed one only when every candidate is confirmed."""
    for c in by_cid.values():
        if "commercial_permission" not in c and c.get("source", {}).get("id") in sources:
            c["commercial_permission"] = sources[c["source"]["id"]].get("permission", permission)
    unconfirmed = [cid for cid, c in by_cid.items() if not str(c.get("commercial_permission", "")).startswith(CONFIRMED)]
    level = f"NOT CONFIRMED for: {', '.join(unconfirmed)}" if unconfirmed else permission
    path.write_text(json.dumps({"section": section, "version": 1, "permission": level,
                                "candidates": list(by_cid.values())}, indent=1) + "\n")


def render(sources: dict, shots: list, work: Path, out: Path, only: set | None, model: str, permission: str) -> int:
    stt = transcriber(model)
    failed = 0
    scouts = {sid: load(work / "scout" / f"{sid}.json") for sid in sources if (work / "scout" / f"{sid}.json").exists()}
    for shot in shots:
        section, sid, cid = shot["section"], shot["source"], shot["cid"]
        if only and not only & {section, cid, shot.get("variant"), sid}:
            continue
        src = sources[sid]
        name, a, b = piece(shot, work)
        seg_file = work / "seg" / f"{name}.mp4"
        if not (work / "seg" / f"{name}.json").exists():
            failed += 1
            print(f"  FAILED {section}/{cid}: segment {name} was not fetched", file=sys.stderr)
            continue
        seg = load(work / "seg" / f"{name}.json")
        dest = out / section
        dest.mkdir(parents=True, exist_ok=True)
        print(f"render {section}/{cid}", flush=True)
        tmp = Path(tempfile.mkdtemp(prefix="shot-", dir=work))
        try:
            video, words, clip = render_shot(shot, seg_file, seg, tmp, stt, budget=CAP)
            info = probe(video)
            outputs = shot.get("output", "loop")
            item = {"cid": cid, "label": shot.get("label", cid), "kind": "image" if outputs in ("still", "strip") else "video"}
            loop_start = float(shot.get("loop_start", 0.0))
            if clip is None:            # a 16:9 cut straight from the source: skip the fetch padding
                loop_start += float(shot.get("offset", PAD if "moment" in shot else 0.0))
            seconds = 0.0
            if outputs == "loop":
                seconds = min(float(shot.get("seconds", LOOP_SECONDS)), info.duration - loop_start)
                size = VERTICAL if info.height > info.width else WIDE
                item.update(encode_loop(video, dest / cid, loop_start, seconds, size))
                item.update(width=size[0], height=size[1], duration_sec=round(seconds, 2))
            elif outputs == "still":
                size = tuple(shot["size"])
                path = dest / f"{cid}.webp"
                still(video, path, loop_start + float(shot.get("still_at", 1.0)), size,
                      int(shot.get("max_bytes", STILL_BYTES)), shot.get("vf", ""))
                item.update(src=path.name, width=size[0], height=size[1])
            elif outputs == "strip":
                n, size = int(shot.get("frames", 10)), tuple(shot["size"])
                segs = sorted((work / "seg").glob(f"{sid}-*.mp4"), key=lambda p: load(p.with_suffix(".json"))["start"])
                per = -(-n // len(segs))          # frames per segment, spread evenly over the strip
                pool = [(f, 1.0 + 2.5 * r) for f in segs for r in range(per)]
                path = dest / f"{cid}.webp"
                strip([pool[i * len(pool) // n] for i in range(n)], path, size, int(shot.get("max_bytes", STILL_BYTES)))
                item.update(src=path.name, width=size[0] * n, height=size[1])
            else:
                sys.exit(f"unknown output {outputs!r}")
            if shot.get("words") and words:
                end = loop_start + seconds
                kept = [{"start": round(w["start"] - loop_start, 3), "end": round(w["end"] - loop_start, 3),
                         "text": w["text"]} for w in words if loop_start <= w["start"] < end]
                (dest / f"{cid}.words.json").write_text(json.dumps({"words": kept}))
                item["words"] = f"{cid}.words.json"
            if shot.get("words_from"):         # the same moment and cut, rendered with captions: its words fit here
                item["words"] = f"{shot['words_from']}.words.json"
            inner = (clip.start if clip else 0.0) + loop_start      # seconds into the segment
            scouted = moment_of(work, sid, shot["moment"]) if "moment" in shot else None
            opts = options_for(shot)
            item.update({k: v for k, v in {
                "like": shot.get("like"), "request": shot.get("request"),
                "game": shot.get("game", src.get("game")),
                "aspect": "9:16" if item.get("height", 0) > item.get("width", 0) else "16:9",
                "layout": opts.layout if clip else "original",
                "caption_style": opts.caption_style if clip and opts.captions else None,
                "template": shot.get("template"),
                "hook": shot.get("hook"), "hook_source": "shot-list" if shot.get("hook") else None,
                "rank": scouted["rank"] if scouted else None,
                "rating": scouted["rating"] if scouted else None,
                "rating_source": scouts.get(sid, {}).get("rating_source") if scouted else None,
                "credit": src["credit"],
                "commercial_permission": src.get("permission", permission),
                "source": {"id": sid, "creator": src["creator"], "title": src.get("title"), "url": src.get("url"),
                           "start_sec": round(seg["start"] + inner, 2),
                           "end_sec": round(seg["start"] + inner + seconds, 2)},
            }.items() if v is not None})
            if shot.get("duration") == "source":
                item["duration_sec"] = scouts.get(sid, {}).get("duration_sec") or src.get("duration_sec")
                item["loop_sec"] = round(seconds, 2)
            path = dest / "candidates.json"
            by_cid = read_candidates(path, section)
            by_cid[cid] = item
            write_candidates(path, section, by_cid, permission, sources)
        except PipelineError as e:
            failed += 1
            print(f"  FAILED {section}/{cid}: {e.message}", file=sys.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


def more_like(sources: dict, raw_shots: list, work: Path, out: Path, section: str, like: str, count: int,
              model: str, permission: str, moment: int | None = None, request: str | None = None) -> int:
    """"Find another moment like this": the shot behind candidate `like`, on scouted moment `moment`, or on the
    source's next-best scouted moments this section has no candidate for yet. The new candidates carry `like`
    and the picker's `request` id, which is how the picker sees the request is done."""
    variant, _, where = like.rpartition("--")
    sid = where.rsplit("-m", 1)[0]
    base = next((s for s in raw_shots if s["section"] == section and s["source"] == sid
                 and (s.get("variant") or "") == variant), None)
    if base is None:
        print(f"no shot in the shot list makes {section}/{like}", file=sys.stderr)
        return 1
    have = read_candidates(out / section / "candidates.json", section)
    taken = {c.get("rank") for c in have.values() if c.get("source", {}).get("id") == sid
             and c["cid"].rpartition("--")[0] == variant}
    ranks = [m["rank"] for m in load(work / "scout" / f"{sid}.json")["moments"]]
    free = [moment] if moment else [r for r in ranks if r not in taken][:count]
    if not free or free[0] not in ranks:
        print(f"{sid} has no scouted moment left for {section}", file=sys.stderr)
        return 1
    shots = expand([{**base, "moment": free, "like": like, **({"request": request} if request else {})}])
    fetch(sources, shots, work)
    code = render(sources, shots, work, out, None, model, permission)
    print("new: " + ", ".join(s["cid"] for s in shots))
    return code


def requests(sources: dict, raw_shots: list, work: Path, out: Path, featured: Path, model: str, permission: str) -> int:
    """The picker's open "find another moment like this" requests (featured.json `requests`): each one that no
    candidate answers yet is rendered."""
    if not featured.exists():
        return 0
    code = 0
    for req in load(featured).get("requests", []):
        if req["cid"].rpartition("--")[2].rsplit("-m", 1)[0] not in sources:
            continue          # another sources file (another media run) serves this one
        answered = read_candidates(out / req["section"] / "candidates.json", req["section"])
        if any(c.get("request") == req["id"] for c in answered.values()):
            continue
        print(f"request {req['id']}: {req['section']} like {req['cid']}", flush=True)
        code |= more_like(sources, raw_shots, work, out, req["section"], req["cid"], 1, model, permission,
                          moment=req.get("moment"), request=req["id"])
    return code


def publish(featured: Path, out: Path, public: Path) -> int:
    """Copy only the featured candidates (each section's `clips[:show]`, in the owner's order) into
    public/<section>/ under the ids the site reads, and write that section's manifest.json. A section the picker
    left out is not touched; a featured cid with no candidate is skipped with a warning. Nothing is written when
    any featured candidate lacks the owner's confirmed permission to publish its footage."""
    plan = {}
    for section, pick in load(featured).get("sections", {}).items():
        have = read_candidates(out / section / "candidates.json", section)
        cids = pick.get("clips", [])
        for c in cids:
            if c not in have:
                print(f"warning: {section}/{c} is featured but not rendered; skipped", file=sys.stderr)
        cids = [c for c in cids if c in have]          # a missing pick does not use up one of the `show` slots
        plan[section] = (have, cids[:pick["show"]] if pick.get("show") is not None else cids)
    refused = [f"{s}/{c}" for s, (have, cids) in plan.items() for c in cids
               if not str(have[c].get("commercial_permission", "")).startswith(CONFIRMED)]
    if refused:
        print(f"refused, nothing published: no confirmed permission for {', '.join(refused)}", file=sys.stderr)
        return 1
    for section, (have, cids) in plan.items():
        dest = public / section
        if dest.exists():
            shutil.rmtree(dest)       # the folder is this step's output: what is not featured any more goes
        dest.mkdir(parents=True)
        items, used = [], set()
        for n, cid in enumerate(cids, 1):
            c = dict(have[cid])
            if section in VARIANT_SECTIONS:
                pid = base = cid.rpartition("--")[0]
                k = 2
                while pid in used:          # two featured candidates of one variant: impact, impact-2
                    pid, k = f"{base}-{k}", k + 1
            elif section == "hero-long-video":
                pid = "vod" if n == 1 else f"vod-{n}"
            else:
                pid = f"{ORDINAL[section]}-{n}"
            used.add(pid)
            for key, ext in (("src", None), ("webm", None), ("poster", None), ("words", ".words.json")):
                if c.get(key):        # a words file may belong to another candidate (captions "plain")
                    name = f"{pid}{ext or Path(c[key]).suffix}"
                    shutil.copy2(out / section / c[key], dest / name)
                    c[key] = name
            c.pop("request", None)
            c.pop("like", None)
            items.append({"id": pid, "candidate": c.pop("cid"), **c})
        credits = {}
        for i in items:
            credits.setdefault(i["source"]["creator"], i["source"].get("url"))
        (dest / "manifest.json").write_text(json.dumps(
            {"section": section, "version": 1,
             "permission": sorted({i["commercial_permission"] for i in items})[0] if items else CONFIRMED,
             "credits": [{"creator": k, "url": v} for k, v in credits.items()], "items": items}, indent=1) + "\n")
        print(f"published {section}: {', '.join(i['id'] for i in items)}")
    return 0


def clean(work: Path) -> None:
    for sub in ("seg", "raw"):
        shutil.rmtree(work / sub, ignore_errors=True)
    for tmp in work.glob("scout-*"):
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("scout", "fetch", "render", "more", "requests", "publish", "clean"))
    p.add_argument("--sources", type=Path)
    p.add_argument("--shots", type=Path)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--out", type=Path, help="where candidates go, one folder per section")
    p.add_argument("--only", help="comma-separated source ids (scout), or sections, variants or cids (render)")
    p.add_argument("--whisper", default="small.en", help="faster-whisper model for captions, or none")
    p.add_argument("--section", help="more: the section")
    p.add_argument("--like", help="more: the candidate id to find another moment like")
    p.add_argument("--count", type=int, default=1, help="more: how many new moments")
    p.add_argument("--featured", type=Path, help="publish: the owner's featured.json")
    p.add_argument("--public", type=Path, help="publish: clip-api/web-src/public/media")
    a = p.parse_args(argv)
    only = set(a.only.split(",")) if a.only else None
    work = a.work.expanduser()
    if a.step == "clean":
        clean(work)
        return 0
    if not a.sources:
        p.error("--sources is required")
    conf = load(a.sources)
    sources, permission = conf["sources"], conf.get("permission", "unconfirmed")
    if a.step == "scout":
        scout(sources, work, only, "base.en" if a.whisper != "none" else "none")
        return 0
    if a.step != "publish" and not a.shots:
        p.error("--shots is required")
    if a.step == "requests" and not a.featured:
        p.error("requests needs --featured")
    if a.step != "fetch" and not a.out:
        p.error("--out is required")
    out = a.out.expanduser() if a.out else None
    if a.step == "publish":
        if not (a.featured and a.public):
            p.error("publish needs --featured and --public")
        return publish(a.featured.expanduser(), out, a.public.expanduser())
    raw = load(a.shots)["shots"]
    if a.step == "more":
        if not (a.section and a.like):
            p.error("more needs --section and --like")
        return more_like(sources, raw, work, out, a.section, a.like, a.count, a.whisper, permission)
    code = 0
    if a.featured and a.step in ("render", "requests"):      # the picker's open requests go first
        code = requests(sources, raw, work, out, a.featured.expanduser(), a.whisper, permission)
    if a.step == "requests":
        return code
    shots = expand(raw)
    fetch(sources, shots, work)
    if a.step == "fetch":
        return 0
    return render(sources, shots, work, out, only, a.whisper, permission) | code

if __name__ == "__main__":
    sys.exit(main())
