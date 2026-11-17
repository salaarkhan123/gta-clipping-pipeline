"""The clipping pipeline as one importable function. No web, database or path assumptions.

    run_pipeline(input_path, options, out_dir, progress_cb=None, transcriber=None, deadline=None) -> [ClipResult]

Flow: probe -> cheap signals (audio loudness, optional on-screen chat motion) -> fused per-second
score -> candidate windows -> Whisper on candidates only -> re-rank -> snap edges to speech ->
render with captions.

With a `judge` (the AI), the signals only nominate ~3x more candidates than asked for; the judge rates each
one from its transcript and a frame, and the best-rated are rendered. Loud is not the same as good: the
judge throws out intro cards, menus and dead air that happen to be loud.
"""
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np

from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout, probe, run  # noqa: F401 (re-exported)
from .render import CHAT_REGIONS, FACECAM_REGIONS, render_clip, render_thumb, resolve_layout
from .censor import mask, mask_words
from .facecam import resolve_facecam
from .timing import Timer
from .stt import SourceAudio, slice_wav, window as transcript_window
from .signals import CHAT_LAG, audio_rms_db, baseline_z, normalise, onscreen_chat_motion
from .transcribe import Transcriber, Transcript, exclamation_hits, extract_wav, snap_to_speech
from .edit import KEEP_PAUSE, avoid_words, cut, duration as kept_duration, filler_spans, remap_words, silences, speech_gaps, select_cuts, with_flash_forward, zoom_expr, zoom_peaks
from .variety import min_gap_for, pick_distinct
from .windows import pick_spread, pick_windows

WEIGHTS = {"chat_motion": 1.0, "audio": 0.7}   # hand-set; the learned ranker replaces these later
TRANSCRIPT_BONUS = 0.15                        # max re-rank bonus from exclamation phrases
PAD = 4.0                                      # seconds of audio transcribed either side of a candidate
JUDGE_PAD = 8.0                                # ... when a judge chooses the cut: room to grow a 30 s window to 45 s
JUDGE_MIN_LEN, JUDGE_MAX_LEN = 15.0, 45.0      # the clip lengths a judge may choose
MIN_CLIP = 10.0
MIN_RELATIVE_SCORE = 0.2                      # candidates below 20% of the best window are dropped
MAX_CANDIDATES = 30                           # how many moments the judge may look at per video
JUDGE_WEIGHT = 0.75                           # final rank = 0.75 * judge score + 0.25 * signal strength
JUDGE_FLOOR = 20                              # judge scores below this are junk (menus, intro cards, dead air)
JUDGE_THREADS = 4

# judge(transcript_text, frame_path, context) -> {"virality": {"score": 0-100, ...}, ...} or None
Judge = Callable[[str, Path | None, dict], dict | None]


@dataclass
class PipelineOptions:
    max_clips: int = 3
    clip_length: int = 30
    vertical: bool = True         # False keeps the source framing
    aspect: str = "9:16"          # 9:16 | 4:5 | 1:1 | 16:9 (used when vertical/reframing is on)
    max_side: int | None = None   # plan resolution cap: short side in pixels
    chat_region: str = "none"     # "none" or a key of CHAT_REGIONS
    zoom: float = 1.0
    captions: bool = True
    caption_font: str = "DejaVu Sans"
    caption_style: str = "pop"            # impact | pop | bold | neon | boxed | clean
    caption_position: str = "auto"        # impact only: auto | seam | lower | center
    caption_accent: str | None = None     # impact only: the keyword's colour, #RRGGBB; None = the brand lime
    camera: str | None = None             # two-panel layouts: "top" | "bottom"; None = the layout's own
    split_ratio: float | None = None      # two-panel layouts: the top panel's share of the height, 0.25 to 0.75
    censor: bool = False                  # mask swears in captions (burned and captions.json)
    layout: str = "auto"                  # a name from layouts.LAYOUTS, or split | fill | classic from before them
    resolution: str | None = None         # 480 | 720 | 1080 | 2k | 4k: the short side, never above the source or max_side
    facecam_region: str | None = None     # "auto" (detect), or a preset key of FACECAM_REGIONS
    facecam_box: list | None = None       # [x, y, w, h] fractions; overrides the preset
    tighten: bool = True                  # cut silences over 0.6 s and filler words out of each clip
    punch_zoom: bool = True               # subtle punch-in zooms (max 1.15x) on the gameplay at loudness spikes
    flash_forward: bool = True            # open on 1.5 s of the peak when the judge names one, then cut back
    hook_overlay: bool = True             # burn the judge's on-screen hook text over the first 2.5 s
    template: str | None = None           # the template these options came from (recorded, not interpreted here)
    weights: dict | None = None           # per-signal weights overriding WEIGHTS, e.g. {"audio": 1.0}
    transcript_bonus: float | None = None # overrides TRANSCRIPT_BONUS
    judge_focus: str | None = None        # what kind of moment the judge should favour


@dataclass
class ClipResult:
    start: float
    end: float
    score: float
    signals: dict                 # share of the score from each signal (user-facing "why this clip")
    features: dict                # raw features (training data for the future ranker)
    video_path: Path
    thumb_path: Path | None = None
    captions_path: Path | None = None
    meta: dict | None = None      # the judge's title, hashtags and virality for this clip
    index: int = 0                # the clip's number within the job, in the order the moments happen (1 = earliest)


@dataclass
class _Candidate:
    start: float
    end: float
    base: float
    signals: dict
    features: dict
    transcript: Transcript = field(default_factory=Transcript)
    offset: float = 0.0           # absolute time of transcript t=0
    final: float = 0.0
    meta: dict | None = None
    peak: float | None = None     # source time of the most striking second, when the judge named one


def _frame(src: Path, t: float, out: Path, deadline: Deadline | None) -> Path | None:
    try:
        run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", *SAFE_IN, "-i", src, "-frames:v", "1",
             "-vf", "scale=640:-2", "-q:v", "4", out], deadline, cap=60)
        return out if out.exists() else None
    except PipelineTimeout:
        raise
    except PipelineError:
        return None


def _transcribe(c: "_Candidate", i: int, transcriber, src: Path, duration: float, out_dir: Path, deadline,
                pad: float = PAD, audio: Path | None = None) -> None:
    """Whisper over the candidate plus `pad` either side. `audio` is the job's extracted WAV: with it the piece
    is cut straight out of that file; without it ffmpeg seeks into the source."""
    c.offset = max(0.0, c.start - pad)
    length = min(duration, c.end + pad) - c.offset
    wav = out_dir / f"cand{i}.wav"
    if audio is not None:
        slice_wav(audio, c.offset, length, wav)
    else:
        extract_wav(src, c.offset, length, wav, deadline)
    try:
        c.transcript = transcriber.transcribe(wav)
    finally:
        wav.unlink(missing_ok=True)


def run_pipeline(input_path: Path, options: PipelineOptions, out_dir: Path,
                 progress_cb: Callable[[str, int], None] | None = None,
                 transcriber: Transcriber | None = None,
                 deadline: Deadline | None = None,
                 judge: Judge | None = None,
                 fast_transcriber: Transcriber | None = None, timer: Timer | None = None,
                 transcript: Transcript | None = None, source_audio: SourceAudio | None = None,
                 on_clip: Callable[[ClipResult], None] | None = None) -> list[ClipResult]:
    """`timer`, when given, receives how long each stage took and how much work it did (see timing.py).
    `transcript` is an existing transcript of the whole recording (absolute seconds), if there is one.
    `source_audio` is the recording's audio already decoded by the caller (stt.extract_audio): candidates are
    then cut from it. Without it nothing is extracted up front, which is faster when only candidates are read.
    `on_clip` is called with each clip as soon as it is rendered (best first); the return value is every clip in
    the order of the video."""
    progress = progress_cb or (lambda stage, pct: None)
    timer = timer or Timer()
    t_begin = time.monotonic()
    input_path, out_dir = Path(input_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if options.chat_region != "none" and options.chat_region not in CHAT_REGIONS:
        raise PipelineError("bad_options", "Unknown chat_region.")

    progress("probing", 2)
    with timer.stage("probe"):
        info = probe(input_path, deadline)
    n = int(info.duration) + 1
    timer.count("source_sec", round(info.duration, 1))
    with timer.stage("facecam_detect"):
        layout, facecam = resolve_facecam(input_path, info, options, deadline)

    # 1. Cheap signals over the whole source.
    series: dict[str, np.ndarray] = {}
    if options.chat_region != "none":
        progress("chat_motion", 5)
        with timer.stage("chat_motion"):
            motion = onscreen_chat_motion(input_path, options.chat_region, deadline)
        if motion:
            floor = max(float(np.std(motion)) * 0.1, 1e-6)
            series["chat_motion"] = normalise(baseline_z(motion, floor=floor), n, shift=CHAT_LAG)
    db: list[float] = []
    audio: Path | None = source_audio.path if source_audio is not None else None
    if info.has_audio:
        progress("audio", 30)
        with timer.stage("audio_signal"):
            # A caller that already decoded the audio measured its levels in that pass; otherwise measure now.
            db = (source_audio.levels if source_audio is not None else audio_rms_db(input_path, deadline)) or []
        if db:
            series["audio"] = normalise(baseline_z(db, floor=1.0), n)
    if not series:
        raise PipelineError("no_signal", "This video has no audio track and no chat region was set, "
                                         "so there is nothing to score moments with.")

    weights = {**WEIGHTS, **(options.weights or {})}
    total = np.zeros(n)
    for name, vals in series.items():
        total += weights[name] * vals

    # 2. Candidate windows. Over-generate when we can re-rank with the transcript.
    use_asr = transcriber is not None and info.has_audio
    if judge is not None:
        count = min(MAX_CANDIDATES, max(options.max_clips * 3, options.max_clips + 5))
    else:
        count = min(10, options.max_clips * 2) if use_asr else options.max_clips
    # Candidates the judge will mostly reject only need a rough transcript: use the fast model for them,
    # then the caption model for the ones that make the cut.
    rough = fast_transcriber if (judge is not None and fast_transcriber is not None) else transcriber
    # A transcript of the whole recording (made by the fast model, e.g. for Video Finder) stands in for the rough
    # pass. Only then: the clips that make the cut are still transcribed by the caption model below, so caption
    # quality does not depend on where the rough text came from.
    reuse = transcript is not None and use_asr and rough is not transcriber
    # With a judge, nominate from every quarter of a long video so it sees the whole thing; it still decides.
    picks = (pick_spread if judge is not None else pick_windows)(total, options.clip_length, count, info.duration)
    if not picks:
        raise PipelineError("no_moments", "No stand-out moments were found in this video.")
    top = max(p[2] for p in picks) or 1.0
    # Don't pad the result with filler: drop windows far weaker than the best one.
    picks = [p for p in picks if p[2] / top >= MIN_RELATIVE_SCORE]
    candidates: list[_Candidate] = []
    for start, end, mean in picks:
        a, b = int(start), max(int(start) + 1, int(end))
        parts = {name: float(weights[name] * vals[a:b].mean()) for name, vals in series.items()}
        denom = sum(parts.values()) or 1.0
        candidates.append(_Candidate(
            start=start, end=end, base=mean / top,
            signals={k: round(v / denom, 3) for k, v in parts.items()},
            features={"window_mean": round(mean, 4), **{f"{k}_mean": round(v, 4) for k, v in parts.items()},
                      **{f"{k}_peak": round(float(vals[a:b].max()), 4) for k, vals in series.items()}}))

    # 3. Whisper on candidates only: features, re-rank bonus, edge snapping, captions.
    for i, c in enumerate(candidates):
        c.final = c.base
        if not use_asr:
            continue
        progress("transcribing", 45 + int((15 if judge else 25) * i / len(candidates)))
        pad = JUDGE_PAD if judge is not None else PAD
        if reuse:      # the recording already has a transcript: read the candidate out of it
            lo = max(0.0, c.start - pad)
            c.transcript, c.offset = transcript_window(transcript, lo, min(info.duration, c.end + pad))
            timer.count("transcript_reused")
        else:
            with timer.stage("transcribe_rough"):
                _transcribe(c, i, rough, input_path, info.duration, out_dir, deadline, pad=pad, audio=audio)
            timer.count("transcribed_rough_sec", round(c.end - c.start + 2 * pad, 1))
        text = " ".join(s[2] for s in c.transcript.segments)
        hits = exclamation_hits(text)
        inside = [w for w in c.transcript.words if c.start <= w[0] + c.offset < c.end]
        c.features.update(exclamation_hits=hits, words=len(inside),
                          words_per_sec=round(len(inside) / max(c.end - c.start, 1), 3))
        bonus = (TRANSCRIPT_BONUS if options.transcript_bonus is None else options.transcript_bonus) * min(hits, 3) / 3
        if bonus:
            c.signals["transcript"] = round(bonus / (c.base + bonus), 3)
            scale = 1 - c.signals["transcript"]
            for k in list(c.signals):
                if k != "transcript":
                    c.signals[k] = round(c.signals[k] * scale, 3)
        c.final = c.base + bonus
        if judge is None:
            _snap(c, info.duration)

    timer.count("candidates", len(candidates))
    if judge is None:
        ranked = sorted(candidates, key=lambda c: c.final, reverse=True)
    else:
        ranked = _judge(candidates, judge, input_path, out_dir, progress, deadline, info.duration, options.judge_focus,
                        timer)
    distinct, _skipped = pick_distinct(
        ranked, options.max_clips, window=lambda c: (c.start, c.end), meta=lambda c: c.meta,
        speech=lambda c: " ".join(s[2] for s in c.transcript.segments),
        min_gap=min_gap_for(info.duration, options.max_clips))
    chosen = sorted(distinct, key=lambda c: c.start)
    if judge is not None:
        for i, c in enumerate(chosen):
            progress("transcribing", 62 + int(8 * i / len(chosen)))
            if use_asr and rough is not transcriber:
                with timer.stage("transcribe_final"):
                    _transcribe(c, 100 + i, transcriber, input_path, info.duration, out_dir, deadline, audio=audio)
                timer.count("transcribed_final_sec", round(c.end - c.start + 2 * PAD, 1))
            _snap(c, info.duration)

    # 4. Render, best first: with `on_clip` each clip is handed over the moment it is done, so the strongest
    #    ones can be watched while the rest are still rendering. Clip numbers stay in the order of the video.
    results: list[ClipResult] = []
    for done, (i, c) in enumerate(sorted(enumerate(chosen, 1), key=lambda ic: -ic[1].final)):
        progress("rendering", 70 + int(28 * done / len(chosen)))
        spoken = [(s + c.offset, e + c.offset, w) for s, e, w in c.transcript.words
                  if c.start <= s + c.offset < c.end]                     # source seconds
        segments = [(round(c.start, 3), round(c.end, 3))]
        if options.tighten and info.has_audio:
            with timer.stage("dead_air"):
                dead = (avoid_words(silences(audio or input_path, c.start, c.end, deadline), spoken)
                        + speech_gaps(spoken, db, c.start, c.end))
            quiet = [(s + KEEP_PAUSE / 2, e - KEEP_PAUSE / 2) for s, e in dead]      # leave a short pause behind
            segments = cut(c.start, c.end, select_cuts(quiet + filler_spans(spoken), c.start, c.end))
        body = segments
        if options.flash_forward:
            segments = with_flash_forward(body, c.peak, c.end)
        flash = len(segments) > len(body)
        zooms = []
        if options.punch_zoom and options.vertical and layout != "classic" and info.has_audio:
            zooms = zoom_peaks(db, segments, flash)
        words = []
        if options.captions:
            words = remap_words(spoken, segments)
            if options.censor:
                words = mask_words(words)
        hook = (c.meta or {}).get("hook") if options.hook_overlay else None
        if hook and options.censor:
            hook = " ".join(mask(w) for w in hook.split())
        c.features["edit"] = {"segments": segments, "flash_forward": flash, "zoom_at": zooms, "hook": hook,
                              "removed_sec": round((c.end - c.start) - kept_duration(body), 2)}
        video = out_dir / f"clip-{i}.mp4"
        t0 = time.monotonic()
        with timer.stage("render"):
            render_clip(input_path, c.start, c.end, video, src_w=info.width, src_h=info.height,
                        vertical=options.vertical, zoom=options.zoom, chat=options.chat_region,
                        words=words, font=options.caption_font, layout=layout, facecam=facecam,
                        style=options.caption_style, aspect=options.aspect, max_side=options.max_side,
                        deadline=deadline, segments=segments, punch=zoom_expr(zooms), has_audio=info.has_audio,
                        hook=hook, flash=flash, resolution=options.resolution, position=options.caption_position,
                        accent=options.caption_accent, camera=options.camera, split_ratio=options.split_ratio)
        c.features["edit"]["render_sec"] = round(time.monotonic() - t0, 2)
        timer.count("clips")
        timer.count("rendered_sec", round(kept_duration(segments), 1))
        thumb = out_dir / f"clip-{i}.jpg"
        try:
            with timer.stage("thumbnail"):
                render_thumb(video, thumb, deadline)
        except PipelineTimeout:
            raise
        except PipelineError:
            thumb = None
        caps = None
        if words:
            caps = out_dir / f"clip-{i}.captions.json"
            caps.write_text(json.dumps({"words": [{"start": s, "end": e, "text": t} for s, e, t in words]}))
        results.append(ClipResult(start=round(c.start, 3), end=round(c.end, 3), score=round(c.final, 4),
                                  signals=c.signals, features=c.features, video_path=video,
                                  thumb_path=thumb, captions_path=caps, meta=c.meta, index=i))
        if done == 0:
            timer.count("first_clip_sec", round(time.monotonic() - t_begin, 1))
        if on_clip is not None:
            on_clip(results[-1])
    progress("done", 100)
    return sorted(results, key=lambda r: r.index)


def _snap(c: _Candidate, duration: float) -> None:
    segs = [(s + c.offset, e + c.offset, t) for s, e, t in c.transcript.segments]
    c.start, c.end = snap_to_speech(c.start, c.end, segs, lo=0.0, hi=duration, min_len=MIN_CLIP, max_len=60.0)


def _apply_trim(c: _Candidate, trim: dict | None, duration: float) -> None:
    """Take the judge's cut (seconds on the candidate's transcript timeline) when it is a sane clip of the same
    moment: 15-45 s, inside what was transcribed, and still covering at least half of the nominated window."""
    if not isinstance(trim, dict):
        return
    try:
        start, end = c.offset + float(trim["start"]), c.offset + float(trim["end"])
    except (KeyError, TypeError, ValueError):
        return
    start, end = max(0.0, start), min(duration, end)
    covered = min(end, c.end) - max(start, c.start)
    if not (JUDGE_MIN_LEN <= end - start <= JUDGE_MAX_LEN) or covered < 0.5 * min(end - start, c.end - c.start):
        return
    c.features["nominated"] = [round(c.start, 2), round(c.end, 2)]
    c.start, c.end = start, end
    try:
        peak = c.offset + float(trim["peak"])
    except (KeyError, TypeError, ValueError):
        return
    if c.start <= peak < c.end - 0.5:
        c.peak = peak


def _judge(candidates: list[_Candidate], judge: Judge, src: Path, out_dir: Path, progress, deadline,
           duration: float = float("inf"), focus: str | None = None, timer: Timer | None = None) -> list[_Candidate]:
    """Rate every candidate, drop the junk, and return them best first. The judge may also choose each clip's cut."""
    timer = timer or Timer()
    progress("judging", 60)
    with timer.stage("judge_frames"):
        frames = [_frame(src, (c.start + c.end) / 2, out_dir / f"cand{i}.jpg", deadline) for i, c in enumerate(candidates)]

    def rate(i: int):
        c = candidates[i]
        text = " ".join(s[2] for s in c.transcript.segments)
        # Timed lines let the judge pick where the clip starts, ends and peaks (seconds from the transcript's start).
        return judge(text, frames[i], {"length": c.end - c.start, "signals": c.signals,
                                       "lines": [(round(s, 1), t) for s, _e, t in c.transcript.segments],
                                       "window": (round(c.start - c.offset, 1), round(c.end - c.offset, 1)),
                                       **({"focus": focus} if focus else {})})

    with timer.stage("judge_ai"), ThreadPoolExecutor(JUDGE_THREADS) as pool:
        metas = list(pool.map(rate, range(len(candidates))))
    timer.count("judged", sum(1 for m in metas if m))
    for f in frames:
        if f:
            f.unlink(missing_ok=True)
    top = max((c.final for c in candidates), default=1.0) or 1.0
    rated, unrated = [], []
    for c, meta in zip(candidates, metas):
        c.meta = meta
        if isinstance(meta, dict):
            _apply_trim(c, meta.pop("trim", None), duration)
        score = (meta or {}).get("virality", {}).get("score") if isinstance(meta, dict) else None
        if score is None:
            unrated.append(c)
            continue
        c.features["judge_score"] = score
        c.final = JUDGE_WEIGHT * score / 100 + (1 - JUDGE_WEIGHT) * min(1.0, c.final / top)
        rated.append(c)
    rated.sort(key=lambda c: c.final, reverse=True)
    keep = [c for c in rated if c.features["judge_score"] >= JUDGE_FLOOR]
    junk = [c for c in rated if c.features["judge_score"] < JUDGE_FLOOR]
    # If the judge failed for some, rank them by signals after the good ones; junk only fills an otherwise empty result.
    unrated.sort(key=lambda c: c.final, reverse=True)
    out = keep + unrated
    return out if out else junk[:1]


__all__ = ["run_pipeline", "PipelineOptions", "ClipResult", "PipelineError", "PipelineTimeout", "Timer",
           "Deadline", "probe", "asdict"]
