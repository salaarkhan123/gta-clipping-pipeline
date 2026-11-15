"""The clipping pipeline as one importable function. No web, database or path assumptions.

    run_pipeline(input_path, options, out_dir, progress_cb=None, transcriber=None, deadline=None) -> [ClipResult]

Flow: probe -> cheap signals (audio loudness, optional on-screen chat motion) -> fused per-second
score -> candidate windows -> Whisper on candidates only -> re-rank -> snap edges to speech ->
render with captions.
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .ff import Deadline, PipelineError, PipelineTimeout, probe  # noqa: F401 (re-exported)
from .render import CHAT_REGIONS, FACECAM_REGIONS, render_clip, render_thumb, resolve_layout
from .facecam import resolve_facecam
from .signals import CHAT_LAG, audio_rms_db, baseline_z, normalise, onscreen_chat_motion
from .transcribe import Transcriber, Transcript, exclamation_hits, extract_wav, snap_to_speech
from .windows import pick_windows

WEIGHTS = {"chat_motion": 1.0, "audio": 0.7}   # hand-set; the learned ranker replaces these later
TRANSCRIPT_BONUS = 0.15                        # max re-rank bonus from exclamation phrases
PAD = 4.0                                      # seconds of audio transcribed either side of a candidate
MIN_CLIP = 10.0
MIN_RELATIVE_SCORE = 0.2                      # candidates below 20% of the best window are dropped


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
    caption_style: str = "pop"            # pop | bold | neon | boxed | clean
    layout: str = "auto"                  # auto | split | fill | classic
    facecam_region: str | None = None     # "auto" (detect), or a preset key of FACECAM_REGIONS
    facecam_box: list | None = None       # [x, y, w, h] fractions; overrides the preset


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


def run_pipeline(input_path: Path, options: PipelineOptions, out_dir: Path,
                 progress_cb: Callable[[str, int], None] | None = None,
                 transcriber: Transcriber | None = None,
                 deadline: Deadline | None = None) -> list[ClipResult]:
    progress = progress_cb or (lambda stage, pct: None)
    input_path, out_dir = Path(input_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if options.chat_region != "none" and options.chat_region not in CHAT_REGIONS:
        raise PipelineError("bad_options", "Unknown chat_region.")

    progress("probing", 2)
    info = probe(input_path, deadline)
    n = int(info.duration) + 1
    layout, facecam = resolve_facecam(input_path, info, options, deadline)

    # 1. Cheap signals over the whole source.
    series: dict[str, np.ndarray] = {}
    if options.chat_region != "none":
        progress("chat_motion", 5)
        motion = onscreen_chat_motion(input_path, options.chat_region, deadline)
        if motion:
            floor = max(float(np.std(motion)) * 0.1, 1e-6)
            series["chat_motion"] = normalise(baseline_z(motion, floor=floor), n, shift=CHAT_LAG)
    if info.has_audio:
        progress("audio", 30)
        db = audio_rms_db(input_path, deadline)
        if db:
            series["audio"] = normalise(baseline_z(db, floor=1.0), n)
    if not series:
        raise PipelineError("no_signal", "This video has no audio track and no chat region was set, "
                                         "so there is nothing to score moments with.")

    total = np.zeros(n)
    for name, vals in series.items():
        total += WEIGHTS[name] * vals

    # 2. Candidate windows. Over-generate when we can re-rank with the transcript.
    use_asr = transcriber is not None and info.has_audio
    count = min(10, options.max_clips * 2) if use_asr else options.max_clips
    picks = pick_windows(total, options.clip_length, count, info.duration)
    if not picks:
        raise PipelineError("no_moments", "No stand-out moments were found in this video.")
    top = max(p[2] for p in picks) or 1.0
    # Don't pad the result with filler: drop windows far weaker than the best one.
    picks = [p for p in picks if p[2] / top >= MIN_RELATIVE_SCORE]
    candidates: list[_Candidate] = []
    for start, end, mean in picks:
        a, b = int(start), max(int(start) + 1, int(end))
        parts = {name: float(WEIGHTS[name] * vals[a:b].mean()) for name, vals in series.items()}
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
        progress("transcribing", 45 + int(25 * i / len(candidates)))
        c.offset = max(0.0, c.start - PAD)
        length = min(info.duration, c.end + PAD) - c.offset
        wav = out_dir / f"cand{i}.wav"
        extract_wav(input_path, c.offset, length, wav, deadline)
        try:
            c.transcript = transcriber.transcribe(wav)
        finally:
            wav.unlink(missing_ok=True)
        text = " ".join(s[2] for s in c.transcript.segments)
        hits = exclamation_hits(text)
        inside = [w for w in c.transcript.words if c.start <= w[0] + c.offset < c.end]
        c.features.update(exclamation_hits=hits, words=len(inside),
                          words_per_sec=round(len(inside) / max(c.end - c.start, 1), 3))
        bonus = TRANSCRIPT_BONUS * min(hits, 3) / 3
        if bonus:
            c.signals["transcript"] = round(bonus / (c.base + bonus), 3)
            scale = 1 - c.signals["transcript"]
            for k in list(c.signals):
                if k != "transcript":
                    c.signals[k] = round(c.signals[k] * scale, 3)
        c.final = c.base + bonus
        segs = [(s + c.offset, e + c.offset, t) for s, e, t in c.transcript.segments]
        c.start, c.end = snap_to_speech(c.start, c.end, segs, lo=0.0, hi=info.duration,
                                        min_len=MIN_CLIP, max_len=60.0)

    chosen = sorted(sorted(candidates, key=lambda c: c.final, reverse=True)[: options.max_clips],
                    key=lambda c: c.start)

    # 4. Render.
    results: list[ClipResult] = []
    for i, c in enumerate(chosen, 1):
        progress("rendering", 70 + int(28 * (i - 1) / len(chosen)))
        words = []
        if options.captions:
            for s, e, t in c.transcript.words:
                rs, re_ = s + c.offset - c.start, e + c.offset - c.start
                if rs >= 0 and rs < c.end - c.start:
                    words.append((round(rs, 3), round(min(re_, c.end - c.start), 3), t))
        video = out_dir / f"clip-{i}.mp4"
        render_clip(input_path, c.start, c.end, video, src_w=info.width, src_h=info.height,
                    vertical=options.vertical, zoom=options.zoom, chat=options.chat_region,
                    words=words, font=options.caption_font, layout=layout, facecam=facecam,
                    style=options.caption_style, aspect=options.aspect, max_side=options.max_side,
                    deadline=deadline)
        thumb = out_dir / f"clip-{i}.jpg"
        try:
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
                                  thumb_path=thumb, captions_path=caps))
    progress("done", 100)
    return results


__all__ = ["run_pipeline", "PipelineOptions", "ClipResult", "PipelineError", "PipelineTimeout",
           "Deadline", "probe", "asdict"]
