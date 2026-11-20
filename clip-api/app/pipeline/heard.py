"""Everything transcribed of one upload so far (U1): the one transcript every job on the upload reads and adds to.

A job transcribes pieces of a recording (Clip Maker: the candidate windows; Video Finder, Transcripts and the whole
mode of Clip Maker: all of it). Each piece is kept with the model that made it, so the next job on the same upload
reads what is already known instead of transcribing it again:

- a rough pass (the judge reads it, nothing is burned in) takes text from any model;
- captions take only text made by the caption model itself, so a clip's captions never depend on which job ran
  first.

Where pieces overlap, the piece added first owns that time: a transcript that was complete stays exactly as it was,
so translations kept line for line with it stay valid.

No file, storage or database code: the worker loads and saves this (see worker.py). The stored shapes:
- the complete transcript, `{"version", "duration", "model", "language", "segments": [{start, end, text}],
  "words": [[start, end, word]]}`, plus `"speakers": {"turns": [[start, end, speaker]]}` and a `speaker` on each
  segment only when the provider identified speakers (never guessed);
- the pieces of an incomplete one, `{"version", "language", "pieces": [{start, end, model, segments, words}]}`.
"""
from bisect import bisect_left
from dataclasses import dataclass

from .transcribe import Transcript

VERSION = 2
TOLERANCE = 0.05          # seconds of a window that may be uncovered and still count as covered


NO_WORDS = ":nowords"


def model_of(transcriber) -> str:
    """The name a transcriber's pieces are kept under: the Whisper model's name, or the class of anything else,
    marked when it was told not to time each word."""
    name = str(getattr(transcriber, "model_name", None) or type(transcriber).__name__)
    beam = getattr(transcriber, "beam_size", None)
    if beam is not None and beam != 5:          # 5: the caption model's search width; others make other text
        name += f":beam{beam}"
    return name if getattr(transcriber, "words", True) else name + NO_WORDS


def has_words(model: str | None) -> bool:
    """Whether pieces kept under this name have word timings (legacy transcripts: unknown, so no)."""
    return model is not None and not model.endswith(NO_WORDS)


@dataclass
class Piece:
    start: float
    end: float
    model: str | None             # None: made by a model whose name was not recorded (transcripts from before U1)
    transcript: Transcript        # absolute times


class Heard:
    """What has been transcribed of one recording, in one language."""

    def __init__(self, language: str = "en", pieces: list[Piece] | None = None):
        self.language = language
        self.pieces: list[Piece] = list(pieces or [])
        self.added: list[Piece] = []              # pieces added since loading: what the caller has to save

    # ---------- reading ----------

    def _spans(self, model: str | None) -> list[tuple[float, float]]:
        return merge_spans([(p.start, p.end) for p in self.pieces if model is None or p.model == model])

    def covers(self, start: float, end: float, model: str | None = None) -> bool:
        """Whether [start, end] is transcribed (by `model`, when given)."""
        return sum(b - a for a, b in gaps(self._spans(model), start, end)) <= TOLERANCE

    def gaps(self, start: float, end: float, min_len: float = 0.5) -> list[tuple[float, float]]:
        """The parts of [start, end] nothing has transcribed yet, each at least `min_len` long."""
        return [(a, b) for a, b in gaps(self._spans(None), start, end) if b - a >= min_len]

    def complete(self, duration: float) -> bool:
        return self.covers(0.0, duration)

    def timed(self) -> "Heard":
        """Only the pieces with word timings, sharing their objects: what a whole transcript is built from."""
        return Heard(self.language, [p for p in self.pieces if has_words(p.model)])

    def text(self, start: float, end: float, model: str | None = None) -> Transcript:
        """Every word and segment that starts inside [start, end), absolute times. Each moment is read from the
        first piece that covers it (by `model`, when given), so overlapping pieces never repeat words."""
        use = [p for p in self.pieces if (model is None or p.model == model) and p.end > start and p.start < end]
        out = Transcript()
        turns: list | None = []
        for i, p in enumerate(use):
            earlier = use[:i]

            def mine(t: float, p=p, earlier=earlier) -> bool:
                return start <= t < end and p.start <= t < p.end and not any(q.start <= t < q.end for q in earlier)
            out.words += [w for w in _starting(p.transcript.words, start, end) if mine(w[0])]
            out.segments += [s for s in _starting(p.transcript.segments, start, end) if mine(s[0])]
            if turns is not None and p.transcript.turns is not None:
                turns += [t for t in _starting(p.transcript.turns, start, end) if mine(t[0])]
            else:
                turns = None                      # one piece without speakers: no speakers for the whole window
        out.words.sort(key=lambda w: w[0])
        out.segments.sort(key=lambda s: s[0])
        if use and turns is not None:
            out.turns = sorted(turns, key=lambda t: t[0])
        return out

    def window(self, start: float, end: float, model: str | None = None) -> tuple[Transcript, float] | None:
        """[start, end] as the pipeline keeps a candidate's transcript (times from `start`, and `start`), or None
        when part of it was never transcribed (by `model`, when given)."""
        if not self.covers(start, end, model):
            return None
        t = self.text(start, end, model)
        return Transcript(words=[(s - start, e - start, w) for s, e, w in t.words],
                          segments=[(s - start, e - start, x) for s, e, x in t.segments]), start

    # ---------- adding ----------

    def add(self, start: float, end: float, model: str | None, transcript: Transcript) -> None:
        """A newly transcribed piece, absolute times."""
        if end - start <= 0:
            return
        piece = Piece(round(start, 3), round(end, 3), model, transcript)
        self.pieces.append(piece)
        self.added.append(piece)

    # ---------- stored shapes ----------

    @classmethod
    def load(cls, language: str, complete: dict | None = None, parts: dict | None = None) -> "Heard":
        """From the stored complete transcript and the stored pieces, each used only when it is in `language`."""
        heard = cls(language)
        if complete is not None and (complete.get("language") or "en") == language:
            heard.pieces.append(Piece(0.0, float(complete.get("duration") or 0.0) + 1.0, complete.get("model"),
                                      from_doc(complete)))
        if parts is not None and (parts.get("language") or "en") == language:
            for p in parts.get("pieces") or []:
                heard.pieces.append(Piece(float(p["start"]), float(p["end"]), p.get("model"), Transcript(
                    words=[tuple(w) for w in p.get("words", [])], segments=[tuple(s) for s in p.get("segments", [])],
                    turns=[tuple(t) for t in p["turns"]] if p.get("turns") is not None else None)))
        return heard

    def parts_doc(self) -> dict:
        """Every piece, in the order they were added (that order decides who owns overlapping time)."""
        return {"version": VERSION, "language": self.language, "pieces": [
            {"start": p.start, "end": p.end, "model": p.model,
             "segments": [list(s) for s in p.transcript.segments], "words": [list(w) for w in p.transcript.words],
             **({"turns": [list(t) for t in p.transcript.turns]} if p.transcript.turns is not None else {})}
            for p in self.pieces]}


def doc_of(t: Transcript, duration: float, model: str | None = None) -> dict:
    """A whole recording's transcript in the stored shape. Speakers only when the provider gave them."""
    turns = t.turns
    segments = []
    for s, e, x in t.segments:
        seg = {"start": s, "end": e, "text": x}
        if turns is not None:
            seg["speaker"] = speaker_at(turns, s, e)
        segments.append(seg)
    return {"version": VERSION, "duration": round(duration, 3), "model": model, "segments": segments,
            "words": [[s, e, w] for s, e, w in t.words],
            **({"speakers": {"turns": [[s, e, who] for s, e, who in turns]}} if turns is not None else {})}


def from_doc(doc: dict) -> Transcript:
    """The stored complete transcript as a Transcript (absolute times)."""
    turns = (doc.get("speakers") or {}).get("turns")
    return Transcript(words=[tuple(w) for w in doc.get("words", [])],
                      segments=[(x["start"], x["end"], x["text"]) for x in doc.get("segments", [])],
                      turns=[tuple(t) for t in turns] if turns is not None else None)


def _starting(items: list, start: float, end: float) -> list:
    """The items (sorted by start time) that start inside [start, end)."""
    keys = [x[0] for x in items]
    return items[bisect_left(keys, start):bisect_left(keys, end)]


def speaker_at(turns: list, start: float, end: float) -> str | None:
    """The speaker who talks longest during [start, end], or None when no turn overlaps it."""
    best, most = None, 0.0
    for a, b, who in turns:
        o = min(b, end) - max(a, start)
        if o > most:
            best, most = who, o
    return best


def merge_spans(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def gaps(spans: list[tuple[float, float]], start: float, end: float) -> list[tuple[float, float]]:
    """The parts of [start, end] outside the (merged, sorted) spans."""
    out, t = [], start
    for a, b in spans:
        if b <= t:
            continue
        if a >= end:
            break
        if a > t:
            out.append((t, a))
        t = max(t, b)
    if t < end:
        out.append((t, end))
    return out
