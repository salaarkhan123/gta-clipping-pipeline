"""U3: an LLM reads the upload's whole transcript and proposes moments; this replaces per-quarter nomination.

The transcript of [t0, t1] is cut into CHUNK_SEC chunks that overlap by OVERLAP_SEC (so a moment on a chunk edge is
seen whole by one of them). Every chunk goes to the proposer at once (THREADS at a time). Each proposes up to
MAX_PER_CHUNK moments: start, end, kind, why and how strong it is. Proposals found twice (in two overlapping
chunks) are merged. `mix` then combines them with the strongest signal windows, and the judge rates the mix as
before.

The pass is optional and can only help: with no proposer (no AI key), no whole transcript, or when every chunk
fails, `run_pass` says so and the pipeline nominates exactly as before (windows.pick_spread). Chunks that fail
alone (after the proposer's own retries) are listed, and the pipeline keeps the per-quarter guarantee then.

No file, network or database code: the proposer is handed in (app/ai.py ClaudeAI.propose_moments).
"""
import math
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable

from .heard import Heard, speaker_at
from .moments import kind_of

CHUNK_SEC = 300.0         # 5 minutes of transcript per call
OVERLAP_SEC = 60.0        # ... overlapping the next chunk by 1 minute
THREADS = 8               # chunks in flight at once (a 2-hour VOD has 30 chunks)
PASS_BUDGET_SEC = 150.0   # the whole pass; chunks still running then count as failed
MAX_PER_CHUNK = 6         # moments one chunk may propose
MIN_SPEECH_CHARS = 40     # a chunk with less speech than this is not sent: there is nothing to read
SAME_MOMENT = 0.5         # two proposals are the same moment when they share half of the shorter one
EDGE_SLACK = 2.0          # seconds a proposal may stick out of its chunk (the model rounds its marks)
SHORTEST, LONGEST = 5.0, 180.0   # a proposal outside these lengths is not a clip of one moment
LLM_SHARE = 2 / 3         # of the judge's candidates, at most this share are proposals; signal windows get the rest

# proposer(lines, context) -> {"moments": [{start, end, kind, why, strength}], "usage": {...}} or None.
# `lines` are (start, end, text, speaker or None) in source seconds; `context` has "chunk": (start, end) and the
# job's "focus" and "prompt" when set. None or an exception: the chunk failed.
Proposer = Callable[[list, dict], dict | None]


@dataclass
class Proposal:
    start: float
    end: float
    kind: str | None
    why: str
    strength: int             # 0-100, the model's own opinion of the moment, only used to order proposals
    chunks: list[int] = field(default_factory=list)


@dataclass
class PassResult:
    proposals: list[Proposal]          # best first
    chunks: int = 0                    # chunks with speech, sent to the proposer
    failed: list[tuple[float, float]] = field(default_factory=list)   # chunks whose call failed
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def ok(self) -> bool:
        """The pass read the transcript: at least one chunk answered (or there was no speech to read)."""
        return len(self.failed) < self.chunks or self.chunks == 0

    @property
    def complete(self) -> bool:
        return not self.failed


def chunks(t0: float, t1: float, size: float = CHUNK_SEC, overlap: float = OVERLAP_SEC) -> list[tuple[float, float]]:
    """[t0, t1] as chunks of `size` seconds, each starting `size - overlap` after the one before. The last one ends
    on t1; a remainder shorter than the overlap is already inside the chunk before it."""
    out, a, stride = [], t0, size - overlap
    while True:
        b = min(t1, a + size)
        out.append((round(a, 3), round(b, 3)))
        if b >= t1:
            return out
        a += stride


def lines_in(heard: Heard, a: float, b: float) -> list[tuple[float, float, str, str | None]]:
    """The transcript segments that start inside [a, b), with the speaker when the provider gave speakers."""
    t = heard.text(a, b)
    return [(s, e, x, speaker_at(t.turns, s, e) if t.turns is not None else None)
            for s, e, x in t.segments if str(x).strip()]


def _parse(reply, a: float, b: float) -> list[Proposal] | None:
    """The moments of one reply that are real clips inside the chunk, or None when the reply is not readable."""
    if not isinstance(reply, dict) or not isinstance(reply.get("moments"), list):
        return None
    out = []
    for m in reply["moments"][:MAX_PER_CHUNK]:
        if not isinstance(m, dict):
            continue
        try:
            start, end = float(m["start"]), float(m["end"])
            strength = max(0, min(100, int(round(float(m.get("strength", 50))))))
        except (KeyError, TypeError, ValueError):
            continue
        if not (a - EDGE_SLACK <= start < end <= b + EDGE_SLACK) or not SHORTEST <= end - start <= LONGEST:
            continue
        why = " ".join(str(m.get("why") or "").split())[:200]
        out.append(Proposal(max(a, start), min(b, end), kind_of(m.get("kind")), why, strength))
    return out


def same_moment(a0: float, a1: float, b0: float, b1: float, share: float = SAME_MOMENT) -> bool:
    """Whether two spans are one moment: they share at least `share` of the shorter one."""
    shared = min(a1, b1) - max(a0, b0)
    return shared > 0 and shared >= share * min(a1 - a0, b1 - b0)


def dedupe(proposals: list[Proposal]) -> list[Proposal]:
    """One proposal per moment, strongest first. A moment proposed by two overlapping chunks keeps the stronger
    proposal's times and words, and remembers both chunks."""
    kept: list[Proposal] = []
    for p in sorted(proposals, key=lambda p: (-p.strength, p.start)):
        twin = next((k for k in kept if same_moment(p.start, p.end, k.start, k.end)), None)
        if twin is None:
            kept.append(p)
        else:
            twin.chunks = sorted(set(twin.chunks + p.chunks))
    return kept


def run_pass(heard: Heard, t0: float, t1: float, proposer: Proposer, context: dict | None = None,
             threads: int = THREADS, budget: float = PASS_BUDGET_SEC) -> PassResult:
    """Every chunk of [t0, t1] through `proposer`, `threads` at a time, within `budget` seconds in all."""
    context = context or {}
    todo = []
    for i, (a, b) in enumerate(chunks(t0, t1)):
        lines = lines_in(heard, a, b)
        if sum(len(x[2]) for x in lines) >= MIN_SPEECH_CHARS:      # nothing said: nothing to read
            todo.append((i, a, b, lines))
    result = PassResult(proposals=[], chunks=len(todo))
    if not todo:
        return result

    def call(item):
        i, a, b, lines = item
        return proposer(lines, {**context, "chunk": (a, b)})

    pool = ThreadPoolExecutor(max(1, min(threads, len(todo))), thread_name_prefix="llm_pass")
    try:
        futures = {pool.submit(call, item): item for item in todo}
        done, _late = wait(futures, timeout=budget)
    finally:      # a chunk still running after the budget is abandoned, not waited for
        pool.shutdown(wait=False, cancel_futures=True)
    found: list[Proposal] = []
    for future, (i, a, b, _lines) in futures.items():
        reply = None
        if future in done and future.exception() is None:
            reply = future.result()
        moments = _parse(reply, a, b)
        if moments is None:
            result.failed.append((a, b))
            continue
        usage = reply.get("usage") if isinstance(reply.get("usage"), dict) else {}
        result.tokens_in += int(usage.get("input_tokens") or 0)
        result.tokens_out += int(usage.get("output_tokens") or 0)
        for p in moments:
            p.chunks = [i]
        found += moments
    result.failed.sort()
    result.proposals = dedupe(found)
    return result


def mix(proposals: list[Proposal], picks: list[tuple[float, float, float]], count: int,
        share: float = LLM_SHARE) -> list[tuple[float, float, Proposal | None, float | None]]:
    """The candidates the judge rates: (start, end, proposal or None, signal window mean or None), at most `count`.

    A proposal that is the same moment as a signal window becomes one candidate with the proposal's times and the
    window's strength. Up to `share` of the slots go to proposals (strongest first, those the signals also found
    before the others) and the rest to the strongest signal windows the proposals did not find; slots one side
    leaves empty go to the other. So the judge sees the same number of candidates as before: the same AI cost."""
    picks = list(picks)
    paired: list[tuple[Proposal, float | None]] = []
    for p in proposals:
        twin = next((w for w in picks if same_moment(p.start, p.end, w[0], w[1])), None)
        if twin is not None:
            picks.remove(twin)
        paired.append((p, twin[2] if twin is not None else None))
    paired.sort(key=lambda pw: (pw[1] is None, -pw[0].strength, pw[0].start))
    llm = min(len(paired), max(count - len(picks), math.ceil(count * share)))
    out = [(p.start, p.end, p, mean) for p, mean in paired[:llm]]
    out += [(s, e, None, m) for s, e, m in picks[:count - len(out)]]
    return out
