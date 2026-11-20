"""Edit decisions for one clip: which pieces of the source play, in what order, and where the punch-in zooms go.

A clip is a list of source segments [(start, end), ...] played back to back. One segment is the plain clip.
Removing dead air splits it; a flash-forward puts a second or two of the peak in front. Everything here is pure
(times in, times out) except `silences`, which asks ffmpeg where the audio is quiet.
"""
import re

import numpy as np

from .ff import SAFE_IN, Deadline, PipelineError, PipelineTimeout, run

Segment = tuple[float, float]

SILENCE_DB = -38.0        # quieter than this is silence (gameplay audio almost never is, so action is not cut)
SILENCE_MIN = 0.6         # only silences longer than this are removed
KEEP_PAUSE = 0.25         # what is left of a removed silence, split between both sides, so speech does not collide
MIN_PIECE = 0.4           # never leave a sliver shorter than this between two cuts
LOUD_DB = 2.0             # a speech gap this much louder than the clip's typical level is action, not dead air
MAX_REMOVED = 0.35        # never cut more than this share of a clip as dead air
MAX_CUTS = 4              # jump cuts per clip: more than this looks like a glitch, not an edit
MIN_KEEP = 1.2            # seconds of video that must remain between two cuts
FILLERS = {"um", "uh", "uhh", "umm", "uhm", "erm", "er", "hmm", "mm", "mhm"}
FLASH_LEN = 1.5           # seconds of the peak shown first
FLASH_MIN_LEAD = 4.0      # no flash-forward when the peak is already this close to the start
ZOOM_MAX = 1.15
ZOOM_GAP = 4.0            # seconds between punch-ins
ZOOM_Z = 1.5              # a second this many deviations above the clip's own loudness is a spike
ZOOM_DB = 3.0             # ... and at least this many dB above its typical level


def silences(src, start: float, end: float, deadline: Deadline | None = None) -> list[Segment]:
    """Silent spans (source seconds) longer than SILENCE_MIN inside [start, end]. Empty on any ffmpeg problem."""
    try:
        out = run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", *SAFE_IN,
                   "-i", src, "-vn", "-af", f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-f", "null", "-"],
                  deadline, cap=120).stderr or ""
    except PipelineTimeout:
        raise
    except PipelineError:
        return []
    spans, opened = [], None
    for m in re.finditer(r"silence_(start|end): (-?[0-9.]+)", out):
        t = start + max(0.0, float(m.group(2)))
        if m.group(1) == "start":
            opened = t
        elif opened is not None:
            spans.append((opened, min(t, end)))
            opened = None
    if opened is not None:
        spans.append((opened, end))
    return [(s, e) for s, e in spans if e - s >= SILENCE_MIN]


def speech_gaps(words: list[tuple[float, float, str]], db: list[float], start: float, end: float) -> list[Segment]:
    """Dead air in a gaming clip: nobody speaks for more than SILENCE_MIN and the game is no louder than the clip's
    typical level. Loud stretches (gunfire, a crash, a scream Whisper did not transcribe) are never dead air, and
    the lead-in before the first word and the tail after the last are left to the clip's own start and end.
    `words` are (start, end, text) in source seconds; `db` is the source's loudness per second."""
    secs = [db[s] for s in range(int(start), min(int(end) + 1, len(db)))]
    if len(words) < 2 or not secs:
        return []
    typical = float(np.median(np.maximum(np.array(secs, dtype=float), -60.0)))
    out = []
    for (_s0, e0, _t0), (s1, _e1, _t1) in zip(words, words[1:]):
        if s1 - e0 <= SILENCE_MIN:
            continue
        inside = [max(db[s], -60.0) for s in range(int(e0), min(int(s1) + 1, len(db)))]
        if inside and max(inside) <= typical + LOUD_DB:
            out.append((e0, s1))
    return out


def avoid_words(spans: list[Segment], words: list[tuple[float, float, str]], margin: float = 0.1) -> list[Segment]:
    """`spans` with every spoken word (plus a margin) taken out of them: a cut never removes speech, however
    quiet it was. Pieces shorter than SILENCE_MIN are not worth a cut."""
    out = []
    for s, e in spans:
        pieces = [(s, e)]
        for ws, we, _t in words:
            a, b = ws - margin, we + margin
            pieces = [q for ps, pe in pieces for q in ((ps, min(pe, a)), (max(ps, b), pe)) if q[1] - q[0] > 0]
        out += [(ps, pe) for ps, pe in pieces if pe - ps >= SILENCE_MIN]
    return sorted(out)


def select_cuts(spans: list[Segment], start: float, end: float, share: float = MAX_REMOVED,
                max_cuts: int = MAX_CUTS, min_piece: float = MIN_KEEP) -> list[Segment]:
    """Which of the candidate removals to make, longest first, so the clip stays watchable: never more than
    `share` of the clip removed, never more than `max_cuts` cuts, and never a cut that would leave a piece of
    video shorter than `min_piece` between it and a neighbouring cut or the clip's own start or end."""
    chosen: list[Segment] = []
    used = 0.0
    for s, e in sorted(spans, key=lambda x: x[0] - x[1]):
        s, e = max(s, start), min(e, end)
        if e - s <= 0.05 or len(chosen) >= max_cuts or used + (e - s) > share * (end - start):
            continue
        if any(s < ce and cs < e for cs, ce in chosen):
            continue                                        # overlaps a cut already chosen
        before = max([ce for _cs, ce in chosen if ce <= s] + [start])
        after = min([cs for cs, _ce in chosen if cs >= e] + [end])
        # A cut flush with the clip's start or end only trims it; anywhere else both neighbours must be long enough.
        if (s - before < min_piece and s > start + 0.05) or (after - e < min_piece and e < end - 0.05):
            continue
        chosen.append((s, e))
        used += e - s
    return sorted(chosen)


def filler_spans(words: list[tuple[float, float, str]]) -> list[Segment]:
    """Source spans of filler words ("um", "uh"). `words` are (start, end, text) in source seconds."""
    return [(s, e) for s, e, t in words if re.sub(r"[^a-z]", "", t.lower()) in FILLERS and e > s]


def cut(start: float, end: float, remove: list[Segment], keep_pause: float = 0.0) -> list[Segment]:
    """[start, end] with the `remove` spans taken out. Each removed span keeps `keep_pause` seconds (half on each
    side). Pieces shorter than MIN_PIECE are dropped; if nothing sensible is left, the clip stays whole."""
    spans = sorted((max(start, s + keep_pause / 2), min(end, e - keep_pause / 2)) for s, e in remove)
    out, at = [], start
    for s, e in spans:
        if e - s <= 0.05 or e <= at:
            continue
        if s - at >= MIN_PIECE:
            out.append((round(at, 3), round(s, 3)))
        elif out:
            pass                                       # a sliver between two cuts: drop it with them
        at = max(at, e)
    if end - at >= MIN_PIECE or not out:
        out.append((round(at, 3), round(end, 3)))
    return out if sum(e - s for s, e in out) >= min(5.0, (end - start) / 2) else [(round(start, 3), round(end, 3))]


def with_flash_forward(segments: list[Segment], peak: float | None, clip_end: float) -> list[Segment]:
    """Put FLASH_LEN seconds of the peak in front, when the peak is far enough in to be worth teasing."""
    if peak is None or not segments:
        return segments
    start = segments[0][0]
    if peak - start < FLASH_MIN_LEAD or peak + 0.5 > clip_end:
        return segments
    return [(round(peak, 3), round(min(peak + FLASH_LEN, clip_end), 3)), *segments]


def duration(segments: list[Segment]) -> float:
    return sum(e - s for s, e in segments)


def to_output(t: float, segments: list[Segment], skip: int = 0) -> float | None:
    """Where source time t lands on the rendered timeline (the first segment after `skip` that contains it)."""
    at = sum(e - s for s, e in segments[:skip])
    for s, e in segments[skip:]:
        if s <= t < e:
            return at + (t - s)
        at += e - s
    return None


def remap_words(words: list[tuple[float, float, str]], segments: list[Segment]) -> list[tuple[float, float, str]]:
    """Caption words (source seconds) placed on the rendered timeline, segment by segment, cut words dropped."""
    out, at = [], 0.0
    for s, e in segments:
        for ws, we, text in words:
            if s <= ws < e:
                out.append((round(at + ws - s, 3), round(at + min(we, e) - s, 3), text))
        at += e - s
    return out


def source_words(words: list[tuple[float, float, str]], segments: list[Segment],
                 flash: bool = False) -> list[tuple[float, float, str]]:
    """The inverse of remap_words: words on a rendered timeline back in source seconds. Words in a flash-forward
    (the first segment, when `flash`) are left out: they are said again where the moment really happens."""
    out, at = [], 0.0
    for k, (s, e) in enumerate(segments):
        length = e - s
        if not (flash and k == 0):
            for ws, we, text in words:
                if at <= ws < at + length:
                    out.append((round(s + ws - at, 3), round(s + min(we, at + length) - at, 3), text))
        at += length
    return sorted(out)


def zoom_peaks(db: list[float], segments: list[Segment], flash: bool = False, max_peaks: int = 3) -> list[float]:
    """Rendered-timeline times for punch-in zooms: the loudest seconds of the clip that stand out from the rest
    of it, at least ZOOM_GAP apart. `db` is the source's loudness per second. Never inside the flash-forward."""
    body = segments[1:] if flash else segments
    secs = sorted({sec for s, e in body for sec in range(int(s), int(e)) if 0 <= sec < len(db)})
    if len(secs) < 6:
        return []
    vals = np.maximum(np.array([db[sec] for sec in secs], dtype=float), -60.0)    # digital silence is not -inf quiet
    typical = float(np.median(vals))
    # Median-based spread: a few silent or very loud seconds must not hide (or fake) a spike.
    spread = max(1.4826 * float(np.median(np.abs(vals - typical))), 1.0)
    z = np.where(vals - typical >= ZOOM_DB, (vals - typical) / spread, 0.0)
    picks: list[float] = []
    for i in np.argsort(-z):
        if z[i] < ZOOM_Z or len(picks) >= max_peaks:
            break
        t = to_output(secs[int(i)] + 0.5, segments, skip=1 if flash else 0)
        if t is not None and all(abs(t - p) >= ZOOM_GAP for p in picks):
            picks.append(round(t, 2))
    return sorted(picks)


def zoom_expr(peaks: list[float], amount: float = ZOOM_MAX - 1.0) -> str:
    """ffmpeg expression for the zoom factor over time t: 1.0, rising to 1 + amount around each peak."""
    if not peaks:
        return "1"
    bumps = "+".join(f"max(0,1-abs(t-{p + 0.2:.2f})/0.6)" for p in peaks)
    return f"1+{amount:.3f}*min(1,{bumps})"
