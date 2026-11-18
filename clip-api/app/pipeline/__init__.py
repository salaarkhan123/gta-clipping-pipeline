"""The clipping pipeline as one importable function. No web, database or path assumptions.

    run_pipeline(input_path, options, out_dir, progress_cb=None, transcriber=None, deadline=None) -> [ClipResult]

Flow: probe -> cheap signals (audio loudness, optional on-screen chat motion) -> fused per-second
score -> candidate windows -> Whisper on candidates only -> re-rank -> snap edges to speech ->
render with captions.

With a `judge` (the AI), the signals only nominate ~3x more candidates than asked for; the judge rates each
one from its transcript and a frame, and the best-rated are rendered. Loud is not the same as good: the
judge throws out intro cards, menus and dead air that happen to be loud.

With a `proposer` too and a whole transcript of the analysed part (U3, llm_pass.py), an LLM first reads the
transcript in overlapping 5-minute chunks and proposes moments; the judge then rates those mixed with the
strongest signal windows instead of windows from every quarter. Without either, or when the pass fails, the
candidates are nominated exactly as before.

Three options change what is selected (all optional; without them nothing changes):
- `duration`, a clip-length bucket (moments.BUCKETS): every clip's length, in the source and as rendered, is
  inside it. Windows are nominated at the bucket's nominal length, the judge gets enough transcript to cut
  anywhere in the bucket, and its cut is accepted only inside it.
- `limit`: how many clips to return, best first. With `duration` and no limit: every moment that passes the
  judge's floor, up to moments.MAX_CLIPS.
- `range`: only this part of the source is measured, transcribed and clipped. Clip times stay source times.
"""
import json
import math
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np

from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout, probe, run  # noqa: F401 (re-exported)
from .render import CHAT_REGIONS, FACECAM_REGIONS, render_clip, render_thumb, resolve_layout
from .censor import mask, mask_words
from .facecam import moment_facecam, resolve_facecam
from .timing import Timer
from .stt import SourceAudio, slice_wav
from .heard import Heard, model_of
from .signals import CHAT_LAG, audio_rms_db, baseline_z, normalise, onscreen_chat_motion
from .transcribe import (Transcriber, Transcript, exclamation_hits, extract_wav, in_language, snap_to_sentences,
                         snap_to_speech)
from .edit import FLASH_LEN, KEEP_PAUSE, MAX_REMOVED, avoid_words, cut, duration as kept_duration, filler_spans, remap_words, silences, speech_gaps, select_cuts, to_output, with_flash_forward, zoom_expr, zoom_peaks
from . import hooks as hook_lines
from .moments import BUCKETS, MAX_CLIPS, NOMINAL, Moment
from .llm_pass import PASS_BUDGET_SEC, PassResult, Proposal, Proposer, mix, run_pass
from .variety import HORIZON, min_gap_for, pick_distinct
from .windows import fits, pick_spread, pick_windows

WEIGHTS = {"chat_motion": 1.0, "audio": 0.7}   # hand-set; the learned ranker replaces these later
TRANSCRIPT_BONUS = 0.15                        # max re-rank bonus from exclamation phrases
PAD = 4.0                                      # seconds of audio transcribed either side of a candidate
JUDGE_PAD = 15.0                               # ... when a judge chooses the cut: room to grow a 30 s window to 60 s
JUDGE_MIN_LEN, JUDGE_MAX_LEN = 15.0, 60.0      # the clip lengths a judge may choose (U4: story cuts up to 60 s)
MIN_CLIP = 10.0
MIN_RELATIVE_SCORE = 0.2                      # candidates below 20% of the best window are dropped
MAX_CANDIDATES = 30                           # how many moments the judge may look at per video, for up to 10 clips
MAX_POOL = 100                                # ... when more clips are asked for (2 candidates per clip, see pool_size)
SILENT_DB = -90.0                             # the level given to seconds outside an analysed range
JUDGE_WEIGHT = 0.75                           # final rank = 0.75 * judge score + 0.25 * signal strength
JUDGE_FLOOR = 20                              # judge scores below this are junk (menus, intro cards, dead air)
JUDGE_THREADS = 4
STANDBY = "standby"                           # (U2) per-second signal, 1 = a BRB / starting-soon / empty-chair screen
STANDBY_SHARE = 0.5                           # a span at least this much on standby is a standby span
# (U4) Automatic discovery (a `duration` and no `limit`): a moment becomes a clip only when the judge rates it at
# least this; there is no quota, so a long video gets as many clips as it has moments this good (at most MAX_CLIPS).
# The prompt anchors an ordinary clip at 50, so 40 keeps ordinary-or-better moments. Not tuned yet: tune it on the
# tuning videos only (never the held-out one). The worker sets it from CLIP_QUALITY_FLOOR.
QUALITY_FLOOR = 40
PEAKS = 3                                     # per signal, the strongest seconds the judge is told about

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
    prompt: str | None = None             # the user's words for the moments they want: handed to the judge as data
    weights: dict | None = None           # per-signal weights overriding WEIGHTS, e.g. {"audio": 1.0}
    transcript_bonus: float | None = None # overrides TRANSCRIPT_BONUS
    judge_focus: str | None = None        # what kind of moment the judge should favour
    duration: str | None = None           # a key of moments.BUCKETS: every clip's length is inside it. None: clip_length
    limit: int | None = None              # clips to return, best first. None: max_clips, or with `duration` every
                                          # moment that passes the judge's floor (at most moments.MAX_CLIPS)
    range: dict | None = None             # {"start": s, "end": s}: analyse and clip only this part of the source
    project_name: str | None = None       # the user's label for this run (recorded, not interpreted here)
    # (languages, agent F)
    source_lang: str | None = None        # spoken language (a code of app/languages.py). None: the transcribers' own
    target_lang: str | None = None        # language of titles and translated subtitles (recorded, not interpreted here)
    caption_display: str = "original"     # original | translation | both (recorded: burned captions are the original)
    # (render, agent B)
    render: str = "full"                  # full | preview (fast and small) | none (no video: times, copy, thumbnail)
    hook_style: str = "serious"           # the tone the judge writes the hook in (render_options.HookStyle)
    hook_position: str = "beginning"      # beginning | end: where the burned hook shows
    hook_duration_ms: int | None = None   # how long it shows; None = 2.5 s
    quality_floor: int = QUALITY_FLOOR    # (U4) automatic discovery: the judge rating a moment needs to become a clip
    moment_layout: bool = False           # auto: draw each moment for what it shows (PROVISIONAL; off: one layout)


@dataclass
class ClipResult:
    start: float
    end: float
    score: float
    signals: dict                 # share of the score from each signal (user-facing "why this clip")
    features: dict                # raw features (training data for the future ranker)
    video_path: Path | None       # None: rendered with render "none" (no video yet)
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
                pad: float = PAD, audio: Path | None = None, floor: float = 0.0, heard: Heard | None = None,
                any_model: bool = False, timed=None) -> bool:
    """Whisper over the candidate plus `pad` either side, never outside [floor, duration]. `audio` is the job's
    extracted WAV: with it the piece is cut straight out of that file; without it ffmpeg seeks into the source.

    `heard`: what this upload already has transcribed. When it covers the piece (by this transcriber's model, or by
    any model with `any_model`) the text is read from it and nothing is transcribed: returns False. Otherwise the
    new piece is added to it: returns True. `timed`: a context manager the transcription itself runs in (a timer
    stage), so reading known text is not counted as transcribing."""
    c.offset = max(floor, c.start - pad)
    end = min(duration, c.end + pad)
    model = model_of(transcriber)
    known = heard.window(c.offset, end, None if any_model else model) if heard is not None else None
    if known is not None:
        c.transcript = known[0]
        return False
    wav = out_dir / f"cand{i}.wav"
    with timed if timed is not None else nullcontext():
        if audio is not None:
            slice_wav(audio, c.offset, end - c.offset, wav)
        else:
            extract_wav(src, c.offset, end - c.offset, wav, deadline)
        try:
            c.transcript = transcriber.transcribe(wav)
        finally:
            wav.unlink(missing_ok=True)
    if heard is not None:
        heard.add(c.offset, end, model, Transcript(
            words=[(s + c.offset, e + c.offset, w) for s, e, w in c.transcript.words],
            segments=[(s + c.offset, e + c.offset, x) for s, e, x in c.transcript.segments]))
    return True


def _with_prompt(judge: Judge, prompt: str) -> Judge:
    """The same judge, told what the user asked to find: `prompt` rides along in each candidate's context, next
    to the template's focus. Nothing else changes: the same candidates are judged, once each."""
    return lambda text, frame, context: judge(text, frame, {**context, "prompt": prompt})


def _with_hook_style(judge: Judge, style: str) -> Judge:
    """(render, agent B) The same judge, asked to write the on-screen hook in `style` (render_options.HookStyle).
    "serious" is the judge's own tone and is never passed, so a request without the option is what it was."""
    return lambda text, frame, context: judge(text, frame, {**context, "hook_style": style})


def run_pipeline(input_path: Path, options: PipelineOptions, out_dir: Path,
                 progress_cb: Callable[[str, int], None] | None = None,
                 transcriber: Transcriber | None = None,
                 deadline: Deadline | None = None,
                 judge: Judge | None = None,
                 fast_transcriber: Transcriber | None = None, timer: Timer | None = None,
                 transcript: Heard | None = None, source_audio: SourceAudio | None = None,
                 on_clip: Callable[[ClipResult], None] | None = None,
                 on_moments: Callable[[list[Moment]], None] | None = None,
                 proposer: Proposer | None = None,
                 hook_writer: hook_lines.Writer | None = None) -> list[ClipResult]:
    """`timer`, when given, receives how long each stage took and how much work it did (see timing.py).
    `transcript` (heard.Heard) is what earlier jobs transcribed of this recording: candidates it covers are read
    from it instead of transcribed again (the rough pass from any model, captions only from the caption model's
    own text), and what this run transcribes is added to it for the caller to keep.
    `source_audio` is the recording's audio already decoded by the caller (stt.extract_audio): candidates are
    then cut from it. Without it nothing is extracted up front, which is faster when only candidates are read.
    `on_clip` is called with each clip as soon as it is rendered (best first); the return value is every clip in
    the order of the video. `on_moments` is called once, before anything is rendered, with the chosen moments
    (moments.Moment, best first).
    `proposer` (llm_pass.Proposer, used only with a `judge`) reads the whole transcript in chunks and proposes
    moments for the judge (U3). It runs only when `transcript` covers the whole analysed part.
    `hook_writer` (hooks.Writer, U4) rewrites a hook that repeats an earlier clip's; without it a repeat is replaced
    by one of the clip's titles or its own best line."""
    progress = progress_cb or (lambda stage, pct: None)
    timer = timer or Timer()
    t_begin = time.monotonic()
    input_path, out_dir = Path(input_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if options.chat_region != "none" and options.chat_region not in CHAT_REGIONS:
        raise PipelineError("bad_options", "Unknown chat_region.")
    if judge is not None and options.prompt:
        judge = _with_prompt(judge, options.prompt)
    if judge is not None and options.hook_style != "serious":     # (render, agent B) the hook's tone
        judge = _with_hook_style(judge, options.hook_style)
    # (languages, agent F) Speech in another language than the transcribers' own goes to their multilingual
    # counterparts. English, or no language given, changes nothing.
    transcriber = in_language(transcriber, options.source_lang)
    fast_transcriber = in_language(fast_transcriber, options.source_lang)

    progress("probing", 2)
    with timer.stage("probe"):
        info = probe(input_path, deadline)
    # The part of the source that is analysed, [t0, t1] in source seconds: all of it unless a range is set.
    # Measuring starts on the whole second `base`, so second i of every series is source second base + i.
    t0, t1 = _span(options.range, info.duration)
    ranged = options.range is not None
    base = int(t0)
    span = t1 - base
    part = {"start": float(base), "length": span} if ranged else {}
    n = int(span) + 1
    limits = _limits(options.duration, t1 - t0)       # (shortest, longest) clip in seconds, or None: no bucket
    want = _wanted(options)
    timer.count("source_sec", round(info.duration, 1))
    if ranged:
        timer.count("analysed_sec", round(t1 - t0, 1))
    with timer.stage("facecam_detect"):
        layout, facecam = resolve_facecam(input_path, info, options, deadline)

    # 1. Cheap signals over the analysed part of the source.
    series: dict[str, np.ndarray] = {}
    if options.chat_region != "none":
        progress("chat_motion", 5)
        with timer.stage("chat_motion"):
            motion = onscreen_chat_motion(input_path, options.chat_region, deadline, **part)
        if motion:
            floor = max(float(np.std(motion)) * 0.1, 1e-6)
            series["chat_motion"] = normalise(baseline_z(motion, floor=floor), n, shift=CHAT_LAG)
    db: list[float] = []
    audio: Path | None = source_audio.path if source_audio is not None else None
    if info.has_audio:
        progress("audio", 30)
        with timer.stage("audio_signal"):
            # A caller that already decoded the audio measured its levels in that pass; otherwise measure now.
            db = (source_audio.levels if source_audio is not None else audio_rms_db(input_path, deadline, **part)) or []
        if ranged and source_audio is not None:
            db = db[base:int(math.ceil(t1))]
        if db:
            series["audio"] = normalise(baseline_z(db, floor=1.0), n)
        if ranged:      # the edit stage reads loudness by source second: put the measured part back in its place
            db = [SILENT_DB] * base + list(db)
    if not series:
        raise PipelineError("no_signal", "This video has no audio track and no chat region was set, "
                                         "so there is nothing to score moments with.")

    weights = {**WEIGHTS, **(options.weights or {})}
    total = np.zeros(n)
    for name, vals in series.items():
        total += weights[name] * vals

    # 2. Candidate windows. Over-generate when we can re-rank with the transcript.
    use_asr = transcriber is not None and info.has_audio
    length = NOMINAL[options.duration] if limits else options.clip_length
    count = pool_size(want, judge is not None, use_asr)
    if limits or options.limit is not None:
        count = min(count, fits(n, length))        # never ask for more windows than fit
    # Candidates the judge will mostly reject only need a rough transcript: use the fast model for them,
    # then the caption model for the ones that make the cut.
    rough = fast_transcriber if (judge is not None and fast_transcriber is not None) else transcriber
    # What the upload already has transcribed stands in for the rough pass: text by any model when the clips that
    # make the cut are transcribed again by the caption model below (so caption quality does not depend on where
    # the rough text came from), otherwise only the caption model's own text.
    heard = transcript if transcript is not None else Heard()
    second_pass = rough is not transcriber
    # (U3) With a judge, a proposer and the whole transcript, an LLM reads all of it and proposes moments.
    cut_lengths = limits or (JUDGE_MIN_LEN, JUDGE_MAX_LEN)
    passed = None
    if judge is not None and proposer is not None and use_asr:
        passed = _llm_pass(heard, t0, t1, proposer, options, cut_lengths, timer, progress, deadline)
    # With a judge, nominate from every quarter of a long video so it sees the whole thing; it still decides.
    # A pass that read every chunk has already seen the whole thing: the signals then add their strongest windows.
    spread = judge is not None and (passed is None or not passed.complete)
    picks = (pick_spread if spread else pick_windows)(total, length, count, span,
                                                      **({"skip_edges": False} if ranged else {}))
    if not picks and not (passed and passed.proposals):
        raise PipelineError("no_moments", "No stand-out moments were found in this video.")
    if ranged:      # back to source seconds, and inside the range
        picks = [(max(t0, s + base), min(t1, e + base), m) for s, e, m in picks]
    top = max((p[2] for p in picks), default=0.0) or 1.0
    # Don't pad the result with filler: drop windows far weaker than the best one.
    picks = [p for p in picks if p[2] / top >= MIN_RELATIVE_SCORE]
    nominated = [(s, e, None, m) for s, e, m in picks]
    if passed is not None:
        # Never a proposal on a standby screen (U2's signal): the transcript cannot see one, the signal can.
        fitted = [_fit_proposal(p, cut_lengths, t0, t1) for p in passed.proposals]
        kept = [p for p in fitted if not _standby(series, p.start, p.end, base)]
        if len(kept) < len(fitted):
            timer.count("llm_proposals_standby", len(fitted) - len(kept))
        nominated = mix(kept, picks, count)
        timer.count("llm_candidates", sum(1 for x in nominated if x[2] is not None))
    candidates: list[_Candidate] = []
    for start, end, proposal, mean in nominated:
        a, b = int(start) - base, max(int(start) + 1, int(end)) - base
        features = {"standby": True} if _standby(series, start, end, base) else {}
        if passed is not None:      # who nominated it, and what the proposer said about it
            features["nominated_by"] = "signals" if proposal is None else ("both" if mean is not None else "llm")
            if proposal is not None:
                features["proposal"] = {"kind": proposal.kind, "strength": proposal.strength, "why": proposal.why}
        if mean is None:            # a moment only the proposer found: the signals' strength over its own span
            mean = float(total[a:b].mean()) if b > a else 0.0
        parts = {name: float(weights[name] * vals[a:b].mean()) for name, vals in series.items()}
        denom = sum(parts.values()) or 1.0
        candidates.append(_Candidate(
            start=start, end=end, base=min(1.0, mean / top),
            signals={k: round(v / denom, 3) for k, v in parts.items()},
            features={"window_mean": round(mean, 4), **{f"{k}_mean": round(v, 4) for k, v in parts.items()},
                      **{f"{k}_peak": round(float(vals[a:b].max()), 4) for k, vals in series.items()}, **features}))

    # 3. Whisper on candidates only: features, re-rank bonus, edge snapping, captions.
    for i, c in enumerate(candidates):
        c.final = c.base
        if not use_asr:
            continue
        progress("transcribing", 45 + int((15 if judge else 25) * i / len(candidates)))
        pad = JUDGE_PAD if judge is not None else PAD
        if judge is not None and limits:      # enough either side for the judge to grow the window to the bucket's longest
            own = c.end - c.start if "proposal" in c.features else length      # a proposal has its own length
            pad = max(JUDGE_PAD, (limits[1] - own) / 2)
        made = _transcribe(c, i, rough, input_path, t1, out_dir, deadline, pad=pad, audio=audio, floor=t0,
                           heard=heard, any_model=second_pass, timed=timer.stage("transcribe_rough"))
        if made:
            timer.count("transcribed_rough_sec", round(c.end - c.start + 2 * pad, 1))
        else:
            timer.count("transcript_reused")
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
            _snap(c, t1, limits, t0)

    timer.count("candidates", len(candidates))
    if judge is None:
        ranked = sorted(candidates, key=lambda c: c.final, reverse=True)
    else:
        # A flash-forward adds FLASH_LEN to the rendered clip: the judge's cut leaves room for it in the bucket.
        cut_limits = (limits[0], limits[1] - (FLASH_LEN if options.flash_forward else 0.0)) if limits else None
        every = options.duration is not None and options.limit is None
        ranked = _judge(candidates, judge, input_path, out_dir, progress, deadline, t1, options.judge_focus,
                        timer, limits=cut_limits, floor=t0, every=every,
                        quality_floor=options.quality_floor,
                        timeline=lambda c: _timeline(series, c.offset, c.end + JUDGE_PAD, base))
    # Without the new options this is max_clips over the whole video, as before. A long list is spread by how
    # many moments there really are, and "same topic" only counts between clips near each other (variety.py).
    many = limits is not None or options.limit is not None
    distinct, _skipped = pick_distinct(
        ranked, want, window=lambda c: (c.start, c.end), meta=lambda c: c.meta,
        speech=lambda c: " ".join(s[2] for s in c.transcript.segments),
        min_gap=min_gap_for(t1 - t0, min(want, len(ranked)) if many else want),
        horizon=HORIZON if want > 10 else None)
    chosen = sorted(distinct, key=lambda c: c.start)
    if judge is not None:
        for i, c in enumerate(chosen):
            progress("transcribing", 62 + int(8 * i / len(chosen)))
            if use_asr and second_pass:
                made = _transcribe(c, 100 + i, transcriber, input_path, t1, out_dir, deadline, audio=audio,
                                   floor=t0, heard=heard, timed=timer.stage("transcribe_final"))
                if made:
                    timer.count("transcribed_final_sec", round(c.end - c.start + 2 * PAD, 1))
                else:
                    timer.count("transcript_reused")
            _snap(c, t1, limits, t0)
    if limits:
        for c in chosen:
            _fit(c, limits, t0, t1)
    if judge is not None:
        _distinct_hooks(chosen, hook_writer, timer, options.hook_style)
        for c in chosen:          # (U4) the judge's peak, for the thumbnail and the flash-forward: source seconds
            c.features["peak_sec"] = round(c.peak, 3) if c.peak is not None and c.start <= c.peak < c.end else None
    if on_moments is not None:
        on_moments([_moment(c) for c in sorted(chosen, key=lambda c: -c.final)])

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
            if limits:
                segments = _cut_keeping(quiet + filler_spans(spoken), c.start, c.end, limits[0])
            else:
                segments = cut(c.start, c.end, select_cuts(quiet + filler_spans(spoken), c.start, c.end))
        body = segments
        if options.flash_forward:
            segments = with_flash_forward(body, c.peak, c.end)
            if limits and kept_duration(segments) > limits[1]:
                segments = body                 # the tease would take the clip past the bucket's longest
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
        if c.features.get("peak_sec") is not None:   # where the peak plays in the rendered clip (after any tease)
            at = to_output(c.features["peak_sec"], segments, skip=1 if flash else 0)
            c.features["edit"]["peak_at"] = round(at, 2) if at is not None else None
        # (render, agent B) render "none" stores no video (POST /v1/clips/export makes one later), "preview" a
        # fast small one. With moment_layout on, auto draws each moment for what it shows (facecam.moment_facecam).
        video = out_dir / f"clip-{i}.mp4" if options.render != "none" else None
        thumb = out_dir / f"clip-{i}.jpg"
        timer.count("clips")
        if video is None:
            with timer.stage("thumbnail"):
                thumb = _frame(input_path, (c.peak if c.peak is not None else c.start + 1.0), thumb, deadline)
        else:
            lay, cam = layout, facecam
            if options.moment_layout and options.layout == "auto" and options.vertical and layout != "classic":
                with timer.stage("moment_scene"):
                    lay, cam = moment_facecam(input_path, info, c.start, c.end, layout, facecam, deadline)
            t0 = time.monotonic()
            with timer.stage("render"):
                render_clip(input_path, c.start, c.end, video, src_w=info.width, src_h=info.height,
                            vertical=options.vertical, zoom=options.zoom, chat=options.chat_region,
                            words=words, font=options.caption_font, layout=lay, facecam=cam,
                            style=options.caption_style, aspect=options.aspect, max_side=options.max_side,
                            deadline=deadline, segments=segments, punch=zoom_expr(zooms), has_audio=info.has_audio,
                            hook=hook, flash=flash, resolution=options.resolution, position=options.caption_position,
                            accent=options.caption_accent, camera=options.camera, split_ratio=options.split_ratio,
                            preview=options.render == "preview", hook_position=options.hook_position,
                            hook_ms=options.hook_duration_ms)
            c.features["edit"]["render_sec"] = round(time.monotonic() - t0, 2)
            timer.count("rendered_sec", round(kept_duration(segments), 1))
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


def _llm_pass(heard: Heard, t0: float, t1: float, proposer: Proposer, options: PipelineOptions,
              cut_lengths: tuple[float, float], timer: Timer, progress,
              deadline: Deadline | None = None) -> PassResult | None:
    """(U3) The transcript pass, or None when it cannot run or read nothing: nomination is then as before.
    The job's counts say what it did: chunks, failed chunks, proposals and tokens, or why it did not run."""
    if not heard.covers(t0, t1):
        timer.count("llm_pass_skipped")         # no whole transcript of the analysed part (TRANSCRIBE_WHOLE off)
        return None
    progress("judging", 40)                 # a stage name the dashboard already shows
    context = {"cut_range": (math.ceil(cut_lengths[0]), math.floor(cut_lengths[1])),
               **({"focus": options.judge_focus} if options.judge_focus else {}),
               **({"prompt": options.prompt} if options.prompt else {})}
    budget = deadline.remaining(PASS_BUDGET_SEC) if deadline else PASS_BUDGET_SEC     # out of time: the job times out
    with timer.stage("llm_pass"):
        try:
            passed = run_pass(heard, t0, t1, proposer, context, budget=budget)
        except Exception:                       # a broken proposer never fails the job: nominate as before
            passed = None
    if passed is None or not passed.ok:
        timer.count("llm_pass_failed")
        return None
    timer.count("llm_chunks", passed.chunks)
    timer.count("llm_chunks_failed", len(passed.failed))
    timer.count("llm_proposals", len(passed.proposals))
    timer.count("llm_tokens_in", passed.tokens_in)
    timer.count("llm_tokens_out", passed.tokens_out)
    return passed


def _standby(series: dict, start: float, end: float, base: int) -> bool:
    """Whether [start, end] is mostly a standby screen by the per-second `standby` signal (U2); False without it."""
    vals = series.get(STANDBY)
    a, b = max(0, int(start) - base), int(math.ceil(end)) - base
    if vals is None or b <= a or a >= len(vals):
        return False
    return float(np.mean(np.asarray(vals[a:b], dtype=float) > 0.5)) >= STANDBY_SHARE


def _fit_proposal(p: Proposal, lengths: tuple[float, float], floor: float, ceiling: float) -> Proposal:
    """A proposal as a candidate the judge can cut: at most the longest clip (keeping the end, where the payoff
    is), at least the shortest (grown on both sides), inside [floor, ceiling]."""
    shortest, longest = lengths
    start, end = max(floor, p.start), min(ceiling, p.end)
    if end - start > longest:
        start = end - longest
    if end - start < shortest:
        grow = (shortest - (end - start)) / 2
        start, end = max(floor, start - grow), min(ceiling, end + grow)
    return Proposal(round(start, 2), round(end, 2), p.kind, p.why, p.strength, list(p.chunks))


def _span(part: dict | None, duration: float) -> tuple[float, float]:
    """The analysed part of the source as (start, end) seconds: the whole video, or the `range` option. The end
    is clipped to the video."""
    if part is None:
        return 0.0, duration
    try:
        start, end = float(part["start"]), min(float(part["end"]), duration)
    except (KeyError, TypeError, ValueError):
        raise PipelineError("bad_options", "range must be {start, end} in seconds.") from None
    if not 0.0 <= start < end:
        raise PipelineError("bad_options", "range must lie inside the video, with start before end.")
    return start, end


def _limits(bucket: str | None, available: float) -> tuple[float, float] | None:
    """The shortest and longest clip (seconds) the `duration` bucket allows, or None without one. A bucket that
    starts at 0 still gets clips of at least MIN_CLIP when the video has that much."""
    if bucket is None:
        return None
    if bucket not in BUCKETS:
        raise PipelineError("bad_options", f"Unknown duration; use one of: {', '.join(BUCKETS)}.")
    shortest, longest = BUCKETS[bucket]
    if available < shortest:
        raise PipelineError("too_short_for_duration",
                            f"This video (or the chosen range) is {available:.0f} s long: shorter than the "
                            f"shortest clip of duration {bucket} ({shortest} s).")
    return float(max(shortest, min(MIN_CLIP, available))), float(longest)


def _wanted(options: PipelineOptions) -> int:
    """How many clips to select: `limit` when given; with a bucket and no limit, every good moment up to
    MAX_CLIPS; otherwise max_clips."""
    if options.limit is not None:
        if options.limit < 1:
            raise PipelineError("bad_options", "limit must be at least 1.")
        return min(MAX_CLIPS, options.limit)
    return MAX_CLIPS if options.duration is not None else options.max_clips


def pool_size(want: int, judged: bool, with_transcript: bool) -> int:
    """How many candidate windows to nominate for `want` clips.

    With a judge every candidate is one AI call, so this number is the AI cost of a run. Up to 10 clips: three
    per clip (at least five spare), at most MAX_CANDIDATES. Above that: two per clip, at most MAX_POOL. The
    judge rejects a smaller share of a long list than of a top 3, and the windows that fit in the video cap
    the pool anyway (windows.fits).
    Without a judge the transcript only re-ranks: twice as many as asked for, up to 10, and never fewer than
    asked for."""
    if judged:
        if want <= 10:
            return min(MAX_CANDIDATES, max(want * 3, want + 5))
        return min(MAX_POOL, max(MAX_CANDIDATES, want * 2))
    return max(want, min(10, want * 2)) if with_transcript else want


def _snap(c: _Candidate, duration: float, limits: tuple[float, float] | None = None, floor: float = 0.0) -> None:
    """(U4) Both edges on whole sentences when the transcript has word timings; otherwise on the nearest
    transcript segment edge, as before."""
    min_len, max_len = limits or (MIN_CLIP, 60.0)
    words = [(s + c.offset, e + c.offset, w) for s, e, w in c.transcript.words]
    snapped = snap_to_sentences(c.start, c.end, words, lo=floor, hi=duration, min_len=min_len, max_len=max_len)
    if snapped is None:
        segs = [(s + c.offset, e + c.offset, t) for s, e, t in c.transcript.segments]
        snapped = snap_to_speech(c.start, c.end, segs, lo=floor, hi=duration, min_len=min_len, max_len=max_len)
    c.start, c.end = snapped


def _distinct_hooks(chosen: list[_Candidate], writer, timer: Timer, style: str = "serious") -> None:
    """(U4) No two clips of the job with the same hook (hooks.distinct), best clip first: its hook is kept."""
    order = sorted(chosen, key=lambda c: -c.final)
    rows = []
    for c in order:
        meta = c.meta if isinstance(c.meta, dict) else {}
        lines = [t for s, _e, t in c.transcript.segments if c.start <= s + c.offset < c.end]
        rows.append({"hook": meta.get("hook"), "titles": meta.get("titles") or [], "lines": lines,
                     "context": {"title": meta.get("title"), "kind": meta.get("kind"), "hook_style": style}})
    stats = hook_lines.distinct(rows, writer)
    for c, row in zip(order, rows):
        if isinstance(c.meta, dict) and "rewritten" in row:
            c.meta["hook"] = row["hook"]
            c.features["hook_rewritten"] = row["rewritten"]
    for k, v in stats.items():
        timer.count(f"hook_{k}", v)


def _timeline(series: dict[str, np.ndarray], start: float, end: float, base: int) -> dict:
    """(U4) The signal timeline the judge reads: for each per-second signal, its PEAKS strongest seconds in
    [start, end] (at least 3 s apart), as (seconds from `start`, strength 0-1 against the signal's own peak in the
    video). Today's signals are loudness and chat motion; the U2 timeline adds its signals to `series`."""
    out = {}
    for name, vals in series.items():
        a, b = max(0, int(start) - base), min(len(vals), int(math.ceil(end)) - base)
        top = float(np.max(vals)) if len(vals) else 0.0
        if b <= a or top <= 0:
            continue
        peaks: list[int] = []
        for i in sorted(range(a, b), key=lambda i: -vals[i]):
            if vals[i] <= 0 or len(peaks) == PEAKS:
                break
            if all(abs(i - j) >= 3 for j in peaks):
                peaks.append(i)
        if peaks:
            out[name] = [(round(i + base - start, 1), round(min(1.0, float(vals[i]) / top), 2)) for i in sorted(peaks)]
    return out


def _fit(c: _Candidate, limits: tuple[float, float], floor: float, ceiling: float) -> None:
    """Force the clip's length into the bucket without leaving [floor, ceiling]: one that is too long loses its
    end; one that is too short grows at its end, then at its start. Times are set to whole milliseconds first,
    so the length that is reported is the length that was checked."""
    shortest, longest = limits
    c.start, c.end = round(c.start, 3), round(c.end, 3)
    if c.end - c.start > longest:
        c.end = round(c.start + longest, 3)
    if c.end - c.start < shortest:
        c.end = round(min(ceiling, c.start + shortest), 3)
        if c.end - c.start < shortest:
            c.start = round(max(floor, c.end - shortest), 3)


def _cut_keeping(spans: list, start: float, end: float, shortest: float) -> list:
    """Dead-air removal that never takes the clip under `shortest` seconds: less is cut, never more than the
    clip can spare. Same rules as the plain removal otherwise (edit.select_cuts)."""
    length = end - start
    spare = max(0.0, length - shortest - 0.01)
    cuts = select_cuts(spans, start, end, share=min(MAX_REMOVED, spare / length)) if spare > 0 else []
    segments = cut(start, end, cuts)
    while cuts and kept_duration(segments) < shortest:      # rounding or a dropped sliver: give one cut back
        cuts = sorted(cuts, key=lambda s: s[1] - s[0])[1:]
        segments = cut(start, end, cuts)
    return segments


def _moment(c: _Candidate) -> Moment:
    meta = c.meta if isinstance(c.meta, dict) else None
    judged = c.features.get("judge_score")
    return Moment(start=round(c.start, 3), end=round(c.end, 3),
                  score=float(judged) if judged is not None else round(c.final, 4),
                  kind=(meta or {}).get("kind"), why=(meta or {}).get("reason") or None, peak=c.peak,
                  signals=c.signals, features=c.features, meta=meta)


def _apply_trim(c: _Candidate, trim: dict | None, duration: float,
                limits: tuple[float, float] | None = None, floor: float = 0.0) -> None:
    """Take the judge's cut (seconds on the candidate's transcript timeline) when it is a sane clip of the same
    moment: 15-45 s (or inside `limits`, the bucket), inside what was transcribed, and still covering at least
    half of the nominated window."""
    if not isinstance(trim, dict):
        return
    try:
        start, end = c.offset + float(trim["start"]), c.offset + float(trim["end"])
    except (KeyError, TypeError, ValueError):
        return
    start, end = max(floor, start), min(duration, end)
    covered = min(end, c.end) - max(start, c.start)
    shortest, longest = limits or (JUDGE_MIN_LEN, JUDGE_MAX_LEN)
    if not (shortest <= end - start <= longest) or covered < 0.5 * min(end - start, c.end - c.start):
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
           duration: float = float("inf"), focus: str | None = None, timer: Timer | None = None,
           limits: tuple[float, float] | None = None, floor: float = 0.0, every: bool = False,
           quality_floor: int = QUALITY_FLOOR,
           timeline=None) -> list[_Candidate]:
    """Rate every candidate, drop the junk, and return them best first. The judge may also choose each clip's cut:
    15-60 s, or inside `limits` (told to the judge as `cut_range`, whole seconds).
    `every`: the caller returns all of them, not a top N, so only moments the judge rated at or above its floor
    count, and with it the clip count is not a quota: only moments rated at least `quality_floor` are kept;
    moments it failed to rate are used only when it rated none at all.
    `timeline(c)`: the signal peaks inside the candidate's transcript, sent to the judge (see _timeline)."""
    timer = timer or Timer()
    progress("judging", 60)
    # A candidate flagged as a standby screen (U2: BRB, intro card, empty chair, menu) is never judged or kept.
    standby = [c for c in candidates if c.features.get("standby")]
    if standby:
        timer.count("standby_rejected", len(standby))
        candidates = [c for c in candidates if not c.features.get("standby")]
        if not candidates:
            raise PipelineError("no_moments", "No stand-out moments were found in this video.")
    with timer.stage("judge_frames"):
        frames = [_frame(src, (c.start + c.end) / 2, out_dir / f"cand{i}.jpg", deadline) for i, c in enumerate(candidates)]

    def rate(i: int):
        c = candidates[i]
        text = " ".join(s[2] for s in c.transcript.segments)
        # Timed lines let the judge pick where the clip starts, ends and peaks (seconds from the transcript's start).
        return judge(text, frames[i], {"length": c.end - c.start, "signals": c.signals,
                                       "lines": [(round(s, 1), t) for s, _e, t in c.transcript.segments],
                                       "window": (round(c.start - c.offset, 1), round(c.end - c.offset, 1)),
                                       **({"cut_range": (math.ceil(limits[0]), math.floor(limits[1]))} if limits else {}),
                                       **({"timeline": timeline(c)} if timeline is not None else {}),
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
            _apply_trim(c, meta.pop("trim", None), duration, limits, floor)
        score = (meta or {}).get("virality", {}).get("score") if isinstance(meta, dict) else None
        if score is None:
            unrated.append(c)
            continue
        c.features["judge_score"] = score
        c.final = JUDGE_WEIGHT * score / 100 + (1 - JUDGE_WEIGHT) * min(1.0, c.final / top)
        rated.append(c)
    rated.sort(key=lambda c: c.final, reverse=True)
    bar = max(JUDGE_FLOOR, quality_floor) if every else JUDGE_FLOOR
    keep = [c for c in rated if c.features["judge_score"] >= bar]
    junk = [c for c in rated if c.features["judge_score"] < bar]
    # If the judge failed for some, rank them by signals after the good ones; junk only fills an otherwise empty result.
    unrated.sort(key=lambda c: c.final, reverse=True)
    out = (keep if rated else unrated) if every else keep + unrated
    return out if out else junk[:1]


__all__ = ["run_pipeline", "PipelineOptions", "ClipResult", "PipelineError", "PipelineTimeout", "Timer",
           "Deadline", "probe", "asdict", "Moment", "BUCKETS"]
