# Evaluation protocol and local checks

**Decision question.** At the same clip count, does a new signal recover additional human-rated moments or improve their ordering and boundaries on unseen streams, within the existing processing budget? Test event detection, candidate discovery, ranking, editing, and public engagement separately. A better OCR character score can coexist with worse top-five clips.

## What ran

Using the unchanged scorer and evaluation files at RC `3d684f8e`, the v2 inventory is 0/30 rated and the 2h v1 sheet is 0/46. The saved staging run for the Zias reaction recording matches 7/15 Wayin proxy positives. Among its first 20 results, 6 match and 14 are unrated, yielding a 30–100% precision interval. That interval expresses incomplete judgement. It is not a sampling confidence interval. Existing hand-labelled HUD boxes measure caption occlusion, not interval quality. [Architecture and human evidence](CURRENT-ARCHITECTURE.md)

Run in `clip-api` at the audited revision. The benchmark sheet's “no labelled rows yet” is the expected outcome. The two commands below are read-only.

```sh
python3 scripts/eval_clips.py eval/labels-v2.csv
python3 scripts/eval_clips.py eval/wayin-zias-iceman.csv eval/runs/zias-iceman.staging-347ca2f.json
```

**Local selection probe.** For GTA Online, Fortnite and Valorant, take the same source interval [300,420) from each evaluation recording, with fixed parameters and no tuning. Compare the real #218 selector without ASR/judge to three simple experimental scorers. The latter use RMS, low-resolution frame differences, or their equal-weight sum. Those three share a fixed candidate grid. The real selector has its own nomination, standby and diversity rules and can return fewer clips. Outputs below are source starts in rank order for 10-second clips. Each input provided 120 paired seconds. Apple M4, FFmpeg 9.0.2, local files, no paid services.

| Source | RC offline selector | Audio-only probe | Visual-only probe | Audio + visual probe | RC selection wall (s) | Probe decode wall (audio / visual, s) |
|---|---|---|---|---|---:|---:|
| GTA Online | 347, 395, 316 | 395, 355, 385 | 355, 370, 380 | 395, 355, 345 | 0.370 | 0.220 / 8.900 |
| Fortnite | 355, 300, 391 | 360, 300, 350 | 365, 375, 405 | 365, 355, 300 | 0.341 | 0.205 / 15.567 |
| Valorant | 390, 347 | 345, 355, 390 | 350, 340, 300 | 345, 410, 355 | 0.361 | 0.212 / 11.952 |

Adding visual differences changed at least one of the audio top-three starts on every excerpt. The visual read alone took 8.9–15.6 s for 120 s of input, even though only one reduced frame per second reached the scorer. This argues for sharing decode and measuring recall at sparse cadences. It establishes neither a quality improvement nor a full-VOD cost. Times are one software-decode observation per excerpt. RC wall includes selection up to the callback. Probe decode wall excludes Python scoring. Different denominators preclude a speedup claim.

## Reproduce the excerpt experiment

Use a clean read-only checkout of the pinned release or main merge `8e0d9bad` with the release's existing Python environment. The first script needs only Python's standard library and FFmpeg. Save the first block as `/tmp/signal_probe.py` and the second as `/tmp/rc_select.py`. Neither script modifies the videos. Run both with the same authorized input files; exact timestamps require the same encodes. For private reproduction the basenames are `gta-online.mp4`, `fortnite.mp4`, and `valorant.mp4` under the owner's `ClutchClips-eval` folder.

```python
import array
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path


def decode(path, flags):
    start = time.perf_counter()
    data = subprocess.check_output([
        "ffmpeg", "-nostdin", "-v", "error", "-threads", "2",
        "-ss", "300", "-i", str(path), "-t", "120", *flags, "pipe:1"
    ])
    return data, round(time.perf_counter() - start, 3)


def scaled(values):
    center = statistics.median(values)
    spread = max(1e-6, 1.4826 * statistics.median(abs(x - center) for x in values))
    return [max(0, min(5, (x - center) / spread)) for x in values]


def winners(scores):
    starts = range(0, len(scores) - 9, 5)
    ordered = sorted(starts, key=lambda t: (-sum(scores[t:t + 10]), t))
    keep = []
    for t in ordered:
        if all(abs(t - u) >= 10 for u in keep):
            keep.append(t)
        if len(keep) == 3:
            break
    return [300 + t for t in keep]


for name in sys.argv[1:]:
    path = Path(name)
    pcm, audio_s = decode(path, ["-vn", "-ac", "1", "-ar", "8000", "-f", "s16le"])
    samples = array.array("h", pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    audio = [math.sqrt(sum(x*x for x in samples[t:t+8000]) / 8000)
             for t in range(0, len(samples)-7999, 8000)]
    raw, visual_s = decode(path, ["-an", "-vf", "fps=1,scale=64:36,format=gray",
                                  "-f", "rawvideo", "-pix_fmt", "gray"])
    width = 64 * 36
    frames = [raw[t:t+width] for t in range(0, len(raw)-width+1, width)]
    motion = [0.] + [sum(abs(x-y) for x,y in zip(a,b)) / width
                     for a,b in zip(frames, frames[1:])]
    n = min(len(audio), len(motion), 120)
    if n != 120:
        raise ValueError(f"{path.name}: only {n} paired seconds")
    a, v = scaled(audio[:n]), scaled(motion[:n])
    print(json.dumps(dict(file=path.name, n=n, audio_s=audio_s, visual_s=visual_s,
                          audio=winners(a), visual=winners(v),
                          fusion=winners([x+y for x,y in zip(a,v)]))))
```

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import time
from app.pipeline import PipelineOptions, run_pipeline

class Captured(Exception):
    pass

for arg in sys.argv[1:]:
    selected = []
    def capture(moments):
        selected.extend((m.start, m.end) for m in moments)
        raise Captured()
    with TemporaryDirectory() as out:
        options = PipelineOptions(range={"start": 300, "end": 420},
                                  clip_length=10, max_clips=3, vertical=False)
        start = time.perf_counter()
        try:
            run_pipeline(Path(arg), options, Path(out), on_moments=capture)
        except Captured:
            print(Path(arg).name, selected, round(time.perf_counter()-start, 3))
```

```sh
python3 /tmp/signal_probe.py "$GTA_ONLINE" "$FORTNITE" "$VALORANT"
PYTHONPATH=clip-api python /tmp/rc_select.py "$GTA_ONLINE" "$FORTNITE" "$VALORANT"
```

## Preregistered experiments to run on rated media

Freeze the media digests, consent scope, VOD/creator partitions, annotation instructions, thresholds, candidate limits and primary outcome before inspecting outputs. Develop models on new streams. Freeze all prior evaluation sources, every derivative and any near-duplicate episode. Use a disjoint development, calibration and locked test cohort. If later reuse of the legacy v2 scorer needs new ratings, copy the format to a new versioned manifest. Never alter a prior score sheet or treat blank ratings as negatives. A reviewer who did not tune the system opens the locked results once. [Dataset plan](DATASET-PLAN.md)

| Arm | Inputs and restrictions | Question |
|---|---|---|
| B0 / B1 | Pinned RC as used by the current job, with identical template, ASR, judge, window range, quality floor and clip limits in paired runs. B0 local signal-only; B1 includes cached, authorized judge/ASR data or a separately approved real run. Report fallback and cache status. | What does the actual service select under each mode? |
| A | Only audio RMS/flux/bursts, then add the real named-sound scorer in a second arm. No speech semantics, image, chat or judge. Evaluate timed events on complete labelled seconds. | Do named sounds recover quiet/no-commentary events at acceptable false-alarm rates? |
| V | Only image-derived motion/scene cuts, then ROI text/template evidence in a nested arm. Give the selector the same clip budget. No audio, transcript, chat or judge. | Do cues survive overlays, low bitrate, different patches and spectator screens? |
| T | Only cached transcript and timestamps. Compare lexical/turn features with the same pinned semantic proposer. Handle unvoiced or absent ASR by abstaining. | Does narrative context find payoffs missing from the baseline pool? |
| G | Game profile alone on known titles, then one title withheld. Compare event/state logic against both universal detectors and existing banner branch. Add oracle profile/ROI labels only in a diagnostic arm. | Quantify losses from routing versus recognition versus intrinsic event salience. |
| F | Frozen B1 plus each A/V/T/G or reaction/chat family individually, then joint fusion, then leave one family out. Keep the judge and nominal number of proposals fixed. For live chat, also test dropouts, time shifts and shuffled chat. | Which signals add independent information, and how much does each cost? |
| Verification ceiling | Human-confirmed events plus baseline ranker, and a capped VLM pass on uncertain cases only. Annotators and ranker never see the test labels as model features in a deployable arm. | Is the bottleneck event detection, candidate recall or entertainment ranking? |

Run each arm twice conceptually. **Fixed-pool** experiments rerank the identical union of baseline, event, transcript and grid proposals. **Full discovery** lets each route nominate at the same maximum pool size and judge calls. Include independently annotated whole-timeline windows outside that union to measure missed events. Log run JSON in the scorer's source-seconds format, sorted by rank with explicit source IDs. For B1, cache a deterministic judge response per content/prompt/model hash; do not reuse a baseline response for a different interval. Record asynchronous completion separately from rank.

## Scores and denominators

| Output | Computation and interpretation |
|---|---|
| Preserve product metrics | Run the unmodified v1/v2 scorer on compatible sheets. On v2 match the most-overlapping rated moment of the same VOD with the repo's overlap rule (≥10 s, or a third of the clip when shorter than 30 s). Keep hits, repeats, misses, unrated, precision of rated and lower/upper bounds at 20/40. Include strict denominators for a shortlist shorter than K and recall of rating-3 moments over all outputs. [Scorer](https://github.com/salaarkhan123/gta-clipping-pipeline/blob/3d684f8e03b02257467e03fb9dc4fcb297499e13/clip-api/scripts/eval_clips.py) |
| Precision / recall / F1 | On exhaustively annotated material use one-to-one episode matches, stable ties in rank order. TP = unique relevant episode retrieved, FP = duplicate or irrelevant candidate, FN = relevant episode missed. Precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = 2TP/(2TP+FP+FN). A zero denominator is NA with counts. Report human clip-worthiness separately from named event precision per class. |
| Ranked retrieval | Primary NDCG@5, plus P@5/20/40 and R@5/20/40. First match to rating 3, 2, 1 receives gain 3, 1, 0 respectively. Duplicates, irrelevant and unfilled slots contribute zero. DCG sums gain/log2(rank+1) and normalizes by the ideal ordering of distinct judged events in that VOD. For incomplete judgements report coverage/bounds and adjudicate a blind pool before making the primary claim. |
| False positives and boundaries | Event-level false alarms per gameplay hour and FPR = FP/(FP+TN) on fixed labelled non-overlapping negative bins of a declared duration (1 s for sound, 10 s for clip-worthiness). Avoid counting every overlapping sliding window as a new TN. Report temporal IoU, start/end absolute error, median/p90 on matched episodes, rate containing the human payoff, extra dead-air seconds, and unmatched count. Evaluate at tIoU 0.3/0.5/0.7 separately from legacy matching. |
| Human and calibration | Two blind raters mark 1 weak / 2 post after trim / 3 ready to post and record setup, peak, payoff, reaction and boundary disagreement. A third adjudicates contradictions. Report denominators, weighted kappa, paired preference with ties, and edit seconds. Calibrate event probabilities against event annotations and preference probabilities against editor ratings; report Brier, reliability bins and abstention coverage. |
| Compute and cost | Report wall seconds / source hour, first preview and finish p50/p95, measured CPU time and peak RSS, peak GPU allocated/reserved and device-level memory, cold load, cache hit rate, decode count, model calls, retries and OOM. Cost per source hour = all billed machine/storage/transfer/model costs including failed attempts divided by successfully processed source hours. Match paid calls and stage timing across arms. [GPU protocol](GPU-REQUIREMENTS.md) |

For per-class timestamps, match the same class and compatible POV within a predeclared onset tolerance (primary ±1 s for a banner or short sound). For long episodes, use interval overlap and report duration. A predicted game event on a replay cannot match a separate live action twice. For FPR on fixed bins use per-bin false-positive decisions, separately from the one-to-one episode counts.

## Transfer, uncertainty and acceptance

- Compare pairs on the same VOD. Report macro averages by game and creator alongside pooled counts. Bootstrap creators, then VODs within creator (2,000 fixed-seed replicates); small creator counts get descriptive intervals and no generalization claim. Per-class precision requires counts and a binomial interval. Report highly correlated repeated detections as one episode.
- Test new creators, held-out titles, patch changes, source vs spectator, 1080p/720p/480p, HUD scale/localization, variable frame rates, overlays covering HUD, loud music and absent chat/camera. Re-encodes stay in their original source partition. Pair the same underlying event for degradation tests. Deliberately include sessions with zero highlights.
- Proposed quality gate for a supported title: NDCG@5 improvement at least **0.03 absolute** over B1, with a paired 95% lower bound above zero, and a lower bound on the difference in great-event recall@20 above **−0.02**. Require at least two eligible unseen creators per reported title and report sample size/power. Such a small pilot may remain inconclusive. Per-event precision/exact match must independently meet the existing ticket floor. Calibrate only on development data.
- Proposed performance gate: disabled and zero-weight production output has byte-identical ranked candidates, no added model calls or decode; a candidate enabled for promotion must meet its owner-approved compute/cost ceiling and preserve the existing targets (2h to 30–50 previews in ≤600 s, 4h in ≤900 s). If the baseline already misses a target, report absolute gaps and require a joint decision with the performance owner before enabling. An offline quality result alone cannot release a detector. [Issue #101](https://github.com/salaarkhan123/gta-clipping-pipeline/issues/101) · [Roadmap](IMPLEMENTATION-ROADMAP.md)
