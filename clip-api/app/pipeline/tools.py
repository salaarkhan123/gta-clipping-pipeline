"""Single-purpose tools built from the same pieces as run_pipeline.

run_render  reframe and/or caption given time ranges (no highlight detection)
run_find    find moments by what was said (keyword search over the transcript), optionally cut clips
"""
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import ClipResult
from .ff import Deadline, PipelineError, PipelineTimeout, probe
import logging

from .facecam import resolve_facecam
from .render import CHAT_REGIONS, render_clip, render_thumb
from .transcribe import Transcriber, Transcript, extract_wav
from .visual import build_visual_index, search_visual

log = logging.getLogger("clipapi.tools")


@dataclass
class RenderOptions:
    vertical: bool = True
    aspect: str = "9:16"
    max_side: int | None = None
    layout: str = "auto"
    facecam_region: str | None = None
    facecam_box: list | None = None
    chat_region: str = "none"
    zoom: float = 1.0
    captions: bool = False
    caption_style: str = "pop"
    caption_font: str = "DejaVu Sans"


def _layout(src, info, options, deadline=None) -> tuple[str, object]:
    if options.chat_region != "none" and options.chat_region not in CHAT_REGIONS:
        raise PipelineError("bad_options", "Unknown chat_region.")
    return resolve_facecam(src, info, options, deadline)


def transcribe_range(src: Path, start: float, end: float, transcriber: Transcriber, work_dir: Path,
                     deadline: Deadline | None = None, on_chunk: Callable[[int, int], None] | None = None,
                     chunk: float = 300.0) -> Transcript:
    """Transcribe [start, end] in fixed chunks (bounded memory). Times in the result are absolute."""
    out, t, i = Transcript(), start, 0
    total = max(1, math.ceil((end - start) / chunk))
    while t < end - 0.05:
        length = min(chunk, end - t)
        wav = work_dir / f"tr{i}.wav"
        extract_wav(src, t, length, wav, deadline)
        try:
            part = transcriber.transcribe(wav)
        finally:
            wav.unlink(missing_ok=True)
        out.words += [(round(s + t, 3), round(e + t, 3), w) for s, e, w in part.words]
        out.segments += [(round(s + t, 3), round(e + t, 3), x) for s, e, x in part.segments]
        i, t = i + 1, t + length
        if on_chunk:
            on_chunk(i, total)
    return out


def _render_one(src, info, start, end, idx, words, options, layout, facecam, out_dir, deadline):
    video = out_dir / f"clip-{idx}.mp4"
    render_clip(src, start, end, video, src_w=info.width, src_h=info.height, vertical=options.vertical,
                zoom=options.zoom, chat=options.chat_region, words=words, font=options.caption_font,
                layout=layout, facecam=facecam, style=options.caption_style, aspect=options.aspect,
                max_side=options.max_side, deadline=deadline)
    thumb = out_dir / f"clip-{idx}.jpg"
    try:
        render_thumb(video, thumb, deadline)
    except PipelineTimeout:
        raise
    except PipelineError:
        thumb = None
    caps = None
    if words:
        caps = out_dir / f"clip-{idx}.captions.json"
        caps.write_text(json.dumps({"words": [{"start": s, "end": e, "text": t} for s, e, t in words]}))
    return video, thumb, caps


def _relative(words, start: float, end: float):
    return [(round(s - start, 3), round(min(e, end) - start, 3), w) for s, e, w in words if start <= s < end]


def run_render(src: Path, segments: list, options: RenderOptions, out_dir: Path,
               progress_cb=None, transcriber: Transcriber | None = None,
               deadline: Deadline | None = None) -> list[ClipResult]:
    progress = progress_cb or (lambda stage, pct: None)
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress("probing", 2)
    info = probe(src, deadline)
    layout, facecam = _layout(src, info, options, deadline)
    want_caps = options.captions and info.has_audio
    if want_caps and transcriber is None:
        raise PipelineError("transcription_unavailable", "Captions are not available on this server right now.")
    results, n = [], len(segments)
    for i, (a, b) in enumerate(segments, 1):
        a, b = max(0.0, float(a)), min(float(b), info.duration)
        if b - a < 1:
            continue
        words = []
        if want_caps:
            base = 5 + int(45 * (i - 1) / n)
            progress("transcribing", base)
            t = transcribe_range(src, a, b, transcriber, out_dir, deadline,
                                 lambda k, m, base=base: progress("transcribing", base + int(45 / n * k / m)))
            words = _relative(t.words, a, b)
        progress("rendering", 50 + int(48 * (i - 1) / n))
        video, thumb, caps = _render_one(src, info, a, b, i, words, options, layout, facecam, out_dir, deadline)
        results.append(ClipResult(start=round(a, 3), end=round(b, 3), score=1.0, signals={"manual": 1.0},
                                  features={"words": len(words)}, video_path=video, thumb_path=thumb,
                                  captions_path=caps))
    if not results:
        raise PipelineError("bad_segment", "None of the requested segments fall inside this video.")
    progress("done", 100)
    return results


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def search_transcript(transcript: dict, query: str, limit: int = 5) -> list[dict]:
    """Keyword/phrase search over transcript segments. Exact phrase scores 1.0; partial matches score lower."""
    q = _tokens(query)
    if not q:
        return []
    want, phrase = set(q), " ".join(q)
    segs, hits = transcript.get("segments", []), []
    for i in range(len(segs)):
        for span in (1, 2, 3):          # a phrase can straddle neighbouring segments
            group = segs[i:i + span]
            if len(group) < span or group[-1]["end"] - group[0]["start"] > 30:
                break
            toks = _tokens(" ".join(g["text"] for g in group))
            exact = f" {phrase} " in f" {' '.join(toks)} "
            found = sum(1 for t in want if t in toks) / len(want)
            score = 1.0 if exact else 0.8 * found
            if score >= 0.6:
                hits.append({"start": group[0]["start"], "end": group[-1]["end"],
                             "text": " ".join(g["text"].strip() for g in group),
                             "score": round(score - 0.01 * (span - 1), 3)})
            if exact:
                break
    hits.sort(key=lambda h: (-h["score"], h["start"]))
    picked = []
    for h in hits:
        if all(h["end"] <= p["start"] or h["start"] >= p["end"] for p in picked):
            picked.append(h)
        if len(picked) >= limit:
            break
    return picked


def run_find(src: Path, query: str, max_results: int, make_clips: bool, clip_length: int,
             options: RenderOptions, out_dir: Path, progress_cb=None, transcriber: Transcriber | None = None,
             deadline: Deadline | None = None, transcript: dict | None = None, mode: str = "auto",
             embedder=None, vindex: dict | None = None, indexer: Transcriber | None = None):
    """Search an upload by what was said (transcript) and what is on screen (CLIP frame index).

    mode: "auto" uses whatever is available, "speech" or "visual" require that one.
    Pass cached `transcript` / `vindex` to skip rebuilding them.
    Returns (clips, result, new_transcript_or_None, new_vindex_or_None).
    """
    progress = progress_cb or (lambda stage, pct: None)
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress("probing", 2)
    info = probe(src, deadline)
    want_speech, want_visual = mode in ("auto", "speech"), mode in ("auto", "visual")
    had_t, had_v, new_t, new_v = transcript is not None, vindex is not None, None, None

    if want_speech and transcript is None:
        tr = indexer or transcriber
        if info.has_audio and tr is not None:
            progress("transcribing", 5)
            t = transcribe_range(src, 0.0, info.duration, tr, out_dir, deadline,
                                 lambda k, m: progress("transcribing", 5 + int(35 * k / m)))
            transcript = new_t = {"duration": round(info.duration, 3),
                                  "segments": [{"start": s, "end": e, "text": x} for s, e, x in t.segments],
                                  "words": [[s, e, w] for s, e, w in t.words]}
        elif mode == "speech":
            if not info.has_audio:
                raise PipelineError("no_audio", "This video has no audio track to search.")
            raise PipelineError("transcription_unavailable", "Speech search is not available on this server right now.")

    if want_visual and vindex is None:
        try:
            if embedder is None:
                raise RuntimeError("no embedder configured")
            progress("indexing_frames", 40)
            emb, step = build_visual_index(src, info, embedder, deadline,
                                           lambda k, m: progress("indexing_frames", 40 + int(28 * k / m)))
            vindex = new_v = {"emb": emb, "step": step}
        except (PipelineTimeout, PipelineError):
            raise
        except Exception:
            if mode == "visual":
                raise PipelineError("visual_unavailable", "Visual search is not available on this server right now.") from None
            if embedder is not None:
                log.exception("visual indexing failed; continuing with speech search only")

    if transcript is None and vindex is None:
        raise PipelineError("search_unavailable", "This video has nothing searchable (no speech index, no visual index).")

    progress("searching", 68)
    matches = []
    if want_speech and transcript is not None:
        matches += [{**m, "kind": "speech"} for m in search_transcript(transcript, query, max_results)]
    if want_visual and vindex is not None and embedder is not None:
        try:
            matches += search_visual(vindex["emb"], vindex["step"], embedder, query, max_results, info.duration)
        except Exception:
            if mode == "visual":
                raise PipelineError("visual_unavailable", "Visual search is not available on this server right now.") from None
            log.exception("visual search failed; returning speech matches only")
    matches.sort(key=lambda m: (-m["score"], m["start"]))
    picked = []
    for m in matches:
        if all(m["end"] <= p["start"] or m["start"] >= p["end"] for p in picked):
            picked.append(m)
        if len(picked) >= max_results:
            break

    clips = []
    if make_clips and picked:
        layout, facecam = _layout(src, info, options, deadline)
        all_words = [tuple(w) for w in (transcript or {}).get("words", [])]
        for i, m in enumerate(picked, 1):
            progress("rendering", 70 + int(28 * (i - 1) / len(picked)))
            lead = 3.0 if m["kind"] == "speech" else 5.0
            start = max(0.0, m["start"] - lead)
            end = min(info.duration, start + clip_length)
            start = max(0.0, min(start, end - min(clip_length, info.duration)))
            words = []
            if options.captions and info.has_audio:
                if all_words:
                    words = _relative(all_words, start, end)
                elif transcriber is not None:   # the search index has no word timings: caption just this clip
                    words = _relative(transcribe_range(src, start, end, transcriber, out_dir, deadline).words, start, end)
            video, thumb, caps = _render_one(src, info, start, end, i, words, options, layout, facecam,
                                             out_dir, deadline)
            clips.append(ClipResult(start=round(start, 3), end=round(end, 3), score=m["score"],
                                    signals={m["kind"]: 1.0}, features={"query": query, "text": m["text"][:300]},
                                    video_path=video, thumb_path=thumb, captions_path=caps))
    progress("done", 100)
    result = {"query": query, "mode": mode, "matches": picked, "transcript_cached": had_t, "visual_cached": had_v}
    return clips, result, new_t, new_v
