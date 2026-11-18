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

from .censor import mask, mask_words
from .edit import remap_words
from .facecam import resolve_facecam
from .render import CHAT_REGIONS, render_clip
from .stt import LocalProvider, extract_audio
from .thumbs import Thumb, make_thumbnail
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
    caption_style: str = "pop"        # a name from captions.STYLE_NAMES
    caption_font: str = "DejaVu Sans"
    caption_position: str = "auto"    # impact only: auto | seam | lower | center
    caption_accent: str | None = None # impact only: the keyword's colour, #RRGGBB; None = the brand lime
    censor: bool = False
    thumbnail_text: bool = True       # the worker sets the AI's title on the thumbnail (thumbs.py); false: frame only
    resolution: str | None = None     # "480" | "720" | "1080" | "2k" | "4k"; None renders at the size it always did
    preview: bool = False             # a fast, small render to look at (540 on the short side)
    camera: str | None = None         # two-panel layouts: "top" | "bottom"; None = the layout's own
    split_ratio: float | None = None  # two-panel layouts: the top panel's share of the height, 0.25 to 0.75
    source_lang: str | None = None    # (languages, agent F) recorded; the worker hands the matching transcriber in
    render: str = "full"              # clip jobs only: Reframe and Captions always render in full
    hook_style: str = "serious"       # the AI's tone for the hook (clip jobs); recorded here
    hook_position: str = "beginning"  # exports: "beginning" | "end" of the clip
    hook_duration_ms: int | None = None   # exports: how long the hook shows; None = 2.5 s
    hook_overlay: bool = True         # exports: burn the clip's hook text in
    moment_layout: bool = False       # exports, auto: each moment drawn for what it shows (PROVISIONAL)


@dataclass
class ExportItem:
    """One stored clip to render again (run_export), as its job left it. Read from the database by the caller."""
    clip_id: str
    start: float
    end: float
    segments: list                    # source seconds, in playing order (cuts and the flash-forward included)
    flash: bool = False               # the first segment is a flash-forward
    zoom_at: list = ()                # punch-in zooms on the rendered timeline
    words: list | None = None         # caption words on the rendered timeline; None: transcribed now if wanted
    hook: str | None = None           # the clip's hook text


@dataclass
class ExportResult:
    clip_id: str
    video_path: Path
    seconds: float                    # the rendered length


def planned_seconds(segments: list) -> float:
    """What an export of these segments renders, in seconds: what it is priced on."""
    return round(sum(max(0.0, float(e) - float(s)) for s, e in segments), 3)


def run_export(src: Path, items: list[ExportItem], options: RenderOptions, out_dir: Path, progress_cb=None,
               transcriber: Transcriber | None = None, deadline: Deadline | None = None,
               timer=None) -> list[ExportResult]:
    """Render stored clips again with new options (POST /v1/clips/export): the same moments, cuts and words,
    at `options.resolution`, in the layout, caption style and hook placement asked for. Captions are the clip's
    own words when it has them; a clip made without captions is transcribed now (needs `transcriber`). With
    moment_layout on, an auto layout gives each moment its own (facecam.moment_facecam). Counts `rendered_sec` on `timer`."""
    from .edit import zoom_expr
    from .facecam import moment_facecam
    progress = progress_cb or (lambda stage, pct: None)
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress("probing", 2)
    info = probe(src, deadline)
    layout, facecam = _layout(src, info, options, deadline)
    results = []
    for i, item in enumerate(items, 1):
        progress("rendering", 5 + int(93 * (i - 1) / max(1, len(items))))
        segments = [(max(0.0, float(s)), min(float(e), info.duration)) for s, e in item.segments]
        segments = [(s, e) for s, e in segments if e - s > 0.05]
        if not segments:
            raise PipelineError("bad_segment", "This clip's times fall outside its video.")
        body = segments[1:] if item.flash and len(segments) > 1 else segments      # the moment, without its tease
        lo, hi = min(s for s, _ in body), max(e for _, e in body)
        words = []
        if options.captions and info.has_audio:
            words = item.words
            if words is None:
                if transcriber is None:
                    raise PipelineError("transcription_unavailable", "Captions are not available on this server right now.")
                spoken = transcribe_range(src, lo, hi, transcriber, out_dir, deadline).words
                words = remap_words(spoken, segments)
            if options.censor:
                words = mask_words(words)
        hook = item.hook if options.hook_overlay else None
        if hook and options.censor:
            hook = " ".join(mask(w) for w in hook.split())
        lay, cam = layout, facecam
        if options.moment_layout and options.layout == "auto" and options.vertical and layout != "classic":
            lay, cam = moment_facecam(src, info, lo, hi, layout, facecam, deadline)
        video = out_dir / f"export-{i}.mp4"
        render_clip(src, item.start, item.end, video, src_w=info.width, src_h=info.height, vertical=options.vertical,
                    zoom=options.zoom, chat=options.chat_region, words=words, font=options.caption_font,
                    layout=lay, facecam=cam, style=options.caption_style, aspect=options.aspect,
                    max_side=options.max_side, deadline=deadline, segments=segments,
                    punch=zoom_expr(list(item.zoom_at)) if options.vertical else "1", has_audio=info.has_audio,
                    hook=hook, flash=item.flash, resolution=options.resolution, position=options.caption_position,
                    accent=options.caption_accent, camera=options.camera, split_ratio=options.split_ratio,
                    hook_position=options.hook_position, hook_ms=options.hook_duration_ms)
        seconds = planned_seconds(segments)
        if timer is not None:
            timer.count("clips")
            timer.count("rendered_sec", round(seconds, 1))
        results.append(ExportResult(item.clip_id, video, seconds))
    progress("done", 100)
    return results


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
    if options.censor:
        words = mask_words(words)
    video = out_dir / f"clip-{idx}.mp4"
    render_clip(src, start, end, video, src_w=info.width, src_h=info.height, vertical=options.vertical,
                zoom=options.zoom, chat=options.chat_region, words=words, font=options.caption_font,
                layout=layout, facecam=facecam, style=options.caption_style, aspect=options.aspect,
                max_side=options.max_side, deadline=deadline, resolution=options.resolution, preview=options.preview,
                position=options.caption_position, accent=options.caption_accent, camera=options.camera,
                split_ratio=options.split_ratio)
    thumb = None
    try:
        # No text yet: these clips have no hook. The worker sets the title on it when the AI writes one.
        thumb = make_thumbnail(src, info, start, end, out_dir / f"clip-{idx}.jpg", options=options, layout=layout,
                               facecam=facecam, deadline=deadline)
    except PipelineTimeout:
        raise
    except PipelineError:
        pass
    caps = None
    if words:
        caps = out_dir / f"clip-{idx}.captions.json"
        caps.write_text(json.dumps({"words": [{"start": s, "end": e, "text": t} for s, e, t in words]}))
    return video, thumb, caps


def _thumb_fields(thumb: Thumb | None, features: dict) -> dict:
    """ClipResult fields for a thumbnail (or none), its record kept in `features`."""
    if thumb is None:
        return {"features": features}
    return {"thumb_path": thumb.path, "frame_path": thumb.frame, "features": {**features, "thumbnail": thumb.record}}


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
                                  video_path=video, captions_path=caps, **_thumb_fields(thumb, {"words": len(words)})))
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
             embedder=None, vindex: dict | None = None, indexer: Transcriber | None = None,
             provider=None):
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
            # Decode the audio once, then let the provider transcribe the whole file (chunks cut at quiet points,
            # several at once where the machine allows). Default: the local model, one chunk at a time.
            stt = provider or LocalProvider(tr)
            audio = out_dir / "source-audio.wav"
            try:
                t = stt.transcribe_file(extract_audio(src, audio, deadline).path, out_dir, deadline,
                                        lambda k, m: progress("transcribing", 5 + int(35 * k / m)))
            finally:
                audio.unlink(missing_ok=True)
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
                                    signals={m["kind"]: 1.0}, video_path=video, captions_path=caps,
                                    **_thumb_fields(thumb, {"query": query, "text": m["text"][:300]})))
    progress("done", 100)
    result = {"query": query, "mode": mode, "matches": picked, "transcript_cached": had_t, "visual_cached": had_v}
    return clips, result, new_t, new_v
