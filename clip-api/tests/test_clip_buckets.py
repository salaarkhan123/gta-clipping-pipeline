"""Clip length buckets, the clip limit and the time range: what the pipeline selects and how long each clip is.

The AI judge is a stand-in function here (there is no AI key on the test machine); Whisper is a stand-in too.
"""
import re
import subprocess
from pathlib import Path

import pytest

import app.pipeline as pipeline
from app.pipeline import PipelineError, PipelineOptions, Timer, probe, run_pipeline
from app.pipeline.edit import cut, duration as kept, select_cuts
from app.pipeline.moments import BUCKETS, KINDS, MAX_CLIPS, NOMINAL, Moment, kind_of
from app.pipeline.stt import extract_audio, wav_duration
from app.pipeline.transcribe import Transcript
from app.pipeline.variety import pick_distinct
from app.pipeline.windows import fits, pick_windows
from tests.test_launch import three_bursts  # noqa: F401  (fixture: 60 s, loud at 10-13, 30-33 and 48-51)

BURSTS = (260, 360, 160, 460, 560, 60)      # where the `long` video is loud, loudest first
# Loudness alone ranks these synthetic videos: every tone burst starts the same way, so the U2 sound-change
# signals rate them alike and "the loudest moment" would no longer be the strongest.
FAST = {"vertical": False, "captions": False, "punch_zoom": False, "tighten": False,
        "weights": {"audio_flux": 0, "audio_bursts": 0}}


def make_video(path: Path, seconds: int, volume: str, picture: str = "testsrc2=size=320x180:rate=10",
               sample_rate: int = 44100) -> Path:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", picture, "-f", "lavfi",
                    "-i", f"sine=frequency=440:sample_rate={sample_rate}:duration={seconds}",
                    "-af", f"volume='{volume}':eval=frame",
                    "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def long(tmp_path_factory) -> Path:
    """700 s with six 3-second loud moments 100 s apart; BURSTS lists them from the loudest to the quietest."""
    volume = "0.02"
    for k, t in enumerate(BURSTS):
        volume = f"if(between(t,{t},{t + 3}),{1.0 - 0.1 * k:.1f},{volume})"
    return make_video(tmp_path_factory.mktemp("long") / "long.mp4", 700, volume)


@pytest.fixture(scope="module")
def many(tmp_path_factory) -> Path:
    """80 minutes with a loud moment every 80 s: more good moments than one run may return. (A flat picture and
    8 kHz sound, so that making it takes seconds.)"""
    return make_video(tmp_path_factory.mktemp("many") / "many.mp4", 4800, "if(lt(mod(t,80),3),1.0,0.02)",
                      picture="color=c=gray:size=160x90:rate=1", sample_rate=8000)


@pytest.fixture
def no_render(monkeypatch):
    """For tests about which moments are chosen: clips are written as empty files instead of being rendered."""
    def fake_clip(src, start, end, out, **kwargs):
        Path(out).write_bytes(b"")

    def no_thumb(*args, **kwargs):
        raise PipelineError("no_thumb", "not rendered")
    monkeypatch.setattr(pipeline, "render_clip", fake_clip)
    monkeypatch.setattr(pipeline, "render_thumb", no_thumb)


class Marked:
    """Stands in for Whisper: a line every 2 s for as long as the excerpt is. The first line names the candidate
    (cand0 is the loudest), so a stand-in judge can tell the candidates apart."""
    def transcribe(self, wav) -> Transcript:
        t, name = Transcript(), re.sub(r"\D", "", Path(wav).stem)
        for k in range(0, int(wav_duration(wav)), 2):
            t.words += [(float(k), k + 0.4, "oh"), (k + 0.4, k + 0.9, "no")]
            t.segments.append((float(k), k + 0.9, f"cand{name}" if k == 0 else "oh no"))
        return t


def number(text: str) -> int:
    return int(text.split()[0][4:])


def length_ms(clip) -> int:
    return int(round(clip.end * 1000)) - int(round(clip.start * 1000))


def inside(clip, bucket: str, rendered: bool = True) -> bool:
    """The clip's length is inside the bucket: by its times (to the millisecond) and as a rendered file."""
    lo, hi = BUCKETS[bucket]
    ok = lo * 1000 <= length_ms(clip) <= hi * 1000
    return ok and (not rendered or lo - 0.25 <= probe(clip.video_path).duration <= hi + 0.25)


# ---------- A. the shared shapes ----------
def test_buckets_and_the_moment_shape_match_the_contract():
    assert BUCKETS == {"0-30": (0, 30), "0-90": (0, 90), "30-60": (30, 60), "60-90": (60, 90), "90-180": (90, 180),
                       "180-300": (180, 300)}
    assert list(Moment.__dataclass_fields__) == ["start", "end", "score", "kind", "why", "peak", "signals", "features", "meta"]
    assert KINDS == ("funny", "argument", "reaction", "clutch", "fail", "story") and MAX_CLIPS == 50
    assert all(max(lo, 10) <= NOMINAL[b] <= hi for b, (lo, hi) in BUCKETS.items())      # nominated inside the bucket
    assert kind_of(" Fail ") == "fail" and kind_of("boss fight") is None and kind_of(None) is None


# ---------- B. clip length buckets ----------
@pytest.mark.parametrize("bucket", list(BUCKETS))
def test_every_bucket_yields_clips_inside_it_without_a_judge(long, tmp_path, bucket):
    clips = run_pipeline(long, PipelineOptions(duration=bucket, limit=2, **FAST), tmp_path / "o")
    assert clips and all(inside(c, bucket) for c in clips)
    assert all(abs(length_ms(c) - NOMINAL[bucket] * 1000) <= 1000 for c in clips)       # the bucket's nominal length
    assert BURSTS[0] - NOMINAL[bucket] <= max(clips, key=lambda c: c.score).start <= BURSTS[0]     # around the loudest moment


@pytest.mark.parametrize("bucket", list(BUCKETS))
def test_every_bucket_yields_clips_inside_it_with_a_judge_that_cuts_to_the_longest(long, tmp_path, bucket):
    seen = []

    def judge(text, frame, ctx):
        seen.append(ctx)
        (a, b), longest = ctx["window"], ctx["cut_range"][1]
        mid = (a + b) / 2
        return {"title": "t", "virality": {"score": 80},
                "trim": {"start": mid - longest / 2, "end": mid + longest / 2, "peak": mid}}
    clips = run_pipeline(long, PipelineOptions(duration=bucket, limit=1, **FAST), tmp_path / "o",
                         transcriber=Marked(), judge=judge)
    lo, hi = BUCKETS[bucket]
    assert all(c["cut_range"] == (max(lo, 10), hi - 2) for c in seen)        # the range the judge is told (room for the flash)
    widest = max(c["lines"][-1][0] - c["lines"][0][0] for c in seen)
    assert widest >= hi - 2 - 4                                              # enough transcript to cut the longest clip
    clip = clips[0]
    assert inside(clip, bucket) and "nominated" in clip.features             # the judge's cut was taken
    assert length_ms(clip) >= (hi - 2 - 5) * 1000                            # ... about as long as it asked for


@pytest.mark.parametrize("cut, why", [
    (lambda a, b: {"start": a - 8, "end": b + 8, "peak": a + 5}, "61 s: longer than the bucket"),
    (lambda a, b: {"start": a + 10, "end": a + 35, "peak": a + 20}, "25 s: shorter than the bucket"),
    (lambda a, b: {"start": a - 6, "end": a + 52.3, "peak": a + 20}, "58 s: fits, but not with the flash-forward"),
])
def test_a_judge_cut_outside_the_bucket_is_rejected(long, tmp_path, no_render, cut, why):
    def judge(text, frame, ctx):
        return {"title": "t", "virality": {"score": 80}, "trim": cut(*ctx["window"])}
    clip = run_pipeline(long, PipelineOptions(duration="30-60", limit=1, **FAST, flash_forward=why.startswith("58")),
                        tmp_path / "o", transcriber=Marked(), judge=judge)[0]
    if why.startswith("58"):       # taken as a cut; snapped to speech it is 59 s, and the 1.5 s tease would pass 60 s
        assert "nominated" in clip.features and clip.features["edit"]["flash_forward"] is False
        assert length_ms(clip) + 1500 > 60000
    else:
        assert "nominated" not in clip.features, why
        assert abs(length_ms(clip) - 45000) <= 3000                          # the nominated window, on whole sentences
    assert inside(clip, "30-60", rendered=False)


def test_the_flash_forward_stays_when_the_bucket_has_room_for_it(long, tmp_path):
    def judge(text, frame, ctx):
        a, _b = ctx["window"]
        return {"title": "t", "virality": {"score": 80}, "trim": {"start": a, "end": a + 26, "peak": a + 12}}
    opts = PipelineOptions(duration="0-30", limit=1, **FAST)
    clip = run_pipeline(long, opts, tmp_path / "o", transcriber=Marked(), judge=judge)[0]
    edit = clip.features["edit"]
    assert edit["flash_forward"] is True and len(edit["segments"]) == 2
    assert inside(clip, "0-30") and probe(clip.video_path).duration == pytest.approx(length_ms(clip) / 1000 + 1.5, abs=0.25)


@pytest.fixture(scope="module")
def gappy(tmp_path_factory) -> Path:
    """100 s of talk-level tone with a loud spike at 80-84 and 30 s of dead air in the minute before it."""
    quiet = "+".join(f"between(t,{a},{b})" for a, b in ((28, 36), (40, 48), (52, 60), (64, 70)))
    return make_video(tmp_path_factory.mktemp("gappy") / "gappy.mp4", 100, f"if({quiet},0,if(between(t,80,84),4,1.5))")


def test_dead_air_removal_cuts_less_so_the_clip_stays_inside_the_bucket(gappy, tmp_path):
    base = {**FAST, "tighten": True}
    plain = run_pipeline(gappy, PipelineOptions(max_clips=1, clip_length=75, **base), tmp_path / "p")[0]
    assert plain.features["edit"]["removed_sec"] > 20                        # without a bucket: 75 s becomes about 52 s
    clip = run_pipeline(gappy, PipelineOptions(duration="60-90", limit=1, **base), tmp_path / "b")[0]
    assert (clip.start, clip.end) == (plain.start, plain.end)                # the same 75 s
    removed = clip.features["edit"]["removed_sec"]
    assert 5 <= removed <= 15                                                # still tightened, by what the bucket can spare
    assert kept(clip.features["edit"]["segments"]) >= 60 and inside(clip, "60-90")
    assert probe(clip.video_path).duration == pytest.approx(75 - removed, abs=0.25)


def test_the_tightening_budget_is_what_the_clip_can_spare():
    spans = [(5.0, 9.0), (15.0, 19.0), (24.0, 25.5)]
    assert kept(cut(0.0, 32.0, select_cuts(spans, 0.0, 32.0))) == pytest.approx(22.5)       # the plain removal
    assert pipeline._cut_keeping(spans, 0.0, 32.0, 30.0) == [(0.0, 24.0), (25.5, 32.0)]      # only the 1.5 s fits
    assert pipeline._cut_keeping(spans, 0.0, 30.0, 30.0) == [(0.0, 30.0)]                    # nothing to spare
    assert kept(pipeline._cut_keeping(spans, 0.0, 32.0, 10.0)) == pytest.approx(22.5)        # plenty: as the plain removal


def test_a_clip_is_fitted_into_the_bucket_without_leaving_the_analysed_part():
    def fitted(start, end, limits=(30.0, 60.0), floor=0.0, ceiling=100.0):
        c = pipeline._Candidate(start=start, end=end, base=1.0, signals={}, features={})
        pipeline._fit(c, limits, floor, ceiling)
        return c.start, c.end
    assert fitted(10.0, 55.0) == (10.0, 55.0)                                # inside: untouched
    assert fitted(10.0, 80.0) == (10.0, 70.0)                                # too long: the end goes
    assert fitted(10.0, 25.0) == (10.0, 40.0)                                # too short: grows at the end
    assert fitted(80.0, 100.0) == (70.0, 100.0)                              # ... or at the start, at the end of the video
    assert fitted(50.4004, 79.9996, floor=50.4) == (50.4, 80.4)              # checked on the milliseconds that are reported


def test_a_video_shorter_than_the_bucket_fails_cleanly_and_a_short_one_still_clips(video, tmp_path, no_render):
    with pytest.raises(PipelineError) as e:
        run_pipeline(video, PipelineOptions(duration="60-90", **FAST), tmp_path / "a")       # a 40 s video
    assert e.value.code == "too_short_for_duration" and "60-90" in e.value.message
    with pytest.raises(PipelineError) as e:
        run_pipeline(video, PipelineOptions(duration="45-60", **FAST), tmp_path / "b")
    assert e.value.code == "bad_options"
    clip = run_pipeline(video, PipelineOptions(duration="30-60", **FAST), tmp_path / "c")[0]
    assert inside(clip, "30-60", rendered=False)                             # 40 s video: one clip of the whole of it


# ---------- C. the clip limit ----------
def ranked_judge(scores: dict):
    """Rates candidate i with scores[i]; None means the judge failed for it."""
    def judge(text, frame, ctx):
        score = scores.get(number(text), 50)
        return None if score is None else {"title": "t", "virality": {"score": score}, "kind": "fail", "reason": "why"}
    return judge


SCORES = {0: 90, 1: 85, 2: 80, 3: 10, 4: None, 5: 60}       # candidate 3 is junk, the judge fails on candidate 4


def near(clips) -> list[int]:
    """Which loud moments the clips cover, as numbers in BURSTS (0 = the loudest), sorted."""
    return sorted(next(k for k, t in enumerate(BURSTS) if c.start <= t + 3 and t <= c.end) for c in clips)


def test_without_a_limit_a_bucket_returns_every_moment_that_passes_the_judges_floor(long, tmp_path, no_render):
    opts = {"duration": "0-30", **FAST}
    every = run_pipeline(long, PipelineOptions(**opts), tmp_path / "all", transcriber=Marked(), judge=ranked_judge(SCORES))
    assert near(every) == [0, 1, 2, 5]                                       # not the junk one, not the unrated one
    assert all(c.features["judge_score"] >= pipeline.JUDGE_FLOOR for c in every)
    top = run_pipeline(long, PipelineOptions(limit=2, **opts), tmp_path / "top", transcriber=Marked(), judge=ranked_judge(SCORES))
    assert near(top) == [0, 1]                                               # the two best by score
    six = run_pipeline(long, PipelineOptions(limit=6, **opts), tmp_path / "six", transcriber=Marked(), judge=ranked_judge(SCORES))
    assert near(six) == [0, 1, 2, 4, 5]                                      # a top N is filled with unrated ones, never junk
    down = run_pipeline(long, PipelineOptions(**opts), tmp_path / "down", transcriber=Marked(), judge=lambda t, f, c: None)
    assert near(down) == [0, 1, 2, 3, 4, 5]                                  # judge down: the signals decide, as without one


def test_the_limit_without_a_judge_and_without_a_bucket(long, tmp_path, no_render):
    assert near(run_pipeline(long, PipelineOptions(duration="0-30", **FAST), tmp_path / "a")) == [0, 1, 2, 3, 4, 5]
    assert near(run_pipeline(long, PipelineOptions(duration="0-30", limit=3, **FAST), tmp_path / "b")) == [0, 1, 2]
    # `limit` alone: clips keep clip_length, and it decides the count whatever max_clips says.
    five = run_pipeline(long, PipelineOptions(max_clips=1, clip_length=20, limit=5, **FAST), tmp_path / "c")
    assert near(five) == [0, 1, 2, 3, 4] and all(length_ms(c) == 20000 for c in five)
    one = run_pipeline(long, PipelineOptions(max_clips=4, clip_length=20, limit=1, **FAST), tmp_path / "d")
    assert near(one) == [0]
    with pytest.raises(PipelineError):
        run_pipeline(long, PipelineOptions(limit=0, **FAST), tmp_path / "e")


def test_a_run_never_returns_more_than_50_clips(many, tmp_path, no_render):
    timer = Timer()
    clips = run_pipeline(many, PipelineOptions(duration="0-30", **FAST), tmp_path / "all", transcriber=Marked(),
                         judge=lambda t, f, c: {"title": "t", "virality": {"score": 80}}, timer=timer)
    counts = timer.as_dict()["counts"]
    assert counts["candidates"] > 50 and counts["judged"] == counts["candidates"] <= pipeline.MAX_POOL     # one AI call each
    assert len(clips) == 50 and [c.index for c in clips] == list(range(1, 51))
    assert all(inside(c, "0-30", rendered=False) for c in clips)
    starts = [c.start for c in clips]
    assert starts == sorted(starts) and all(b - a >= 60 for a, b in zip(starts, starts[1:]))       # distinct moments
    asked = run_pipeline(many, PipelineOptions(duration="0-30", limit=80, **FAST), tmp_path / "80")
    assert len(asked) == 50                                                  # a larger limit is capped too


def test_the_candidate_pool_grows_with_the_count_and_is_unchanged_up_to_10_clips():
    for n in range(1, 11):                                                   # today's numbers, exactly
        assert pipeline.pool_size(n, True, True) == min(30, max(n * 3, n + 5))
        assert pipeline.pool_size(n, False, True) == min(10, n * 2) and pipeline.pool_size(n, False, False) == n
    assert [pipeline.pool_size(n, True, True) for n in (12, 15, 30, 50)] == [30, 30, 60, 100]     # two per clip above 10
    assert pipeline.pool_size(50, False, True) == 50 and pipeline.pool_size(50, False, False) == 50
    assert fits(7201, 45) == 80 and fits(7201, 240) == 15 and fits(40, 60) == 1          # what a 2-hour video holds
    score = [0.0] * 600
    for t in range(30, 600, 40):
        score[t] = 1.0
    assert len(pick_windows(score, 20, 99, 600.0)) <= fits(600, 20)


def test_variety_still_works_for_a_long_list():
    ranked = [{"at": 100.0 * i, "meta": {"title": f"police chase {i}", "description": "", "hashtags": []}} for i in range(60)]
    args = {"window": lambda c: (c["at"], c["at"] + 20), "meta": lambda c: c["meta"], "speech": lambda c: ""}
    assert len(pick_distinct(ranked, 50, **args)[0]) == 50
    # Two unrelated moments an hour apart that share their words: a top 3 keeps one, a long list keeps both.
    a, b = ({"at": t, "meta": {"title": "cop runs him over", "description": "", "hashtags": []}} for t in (0.0, 3600.0))
    assert len(pick_distinct([a, b], 3, **args)[0]) == 1
    assert len(pick_distinct([a, b], 50, **args, horizon=900.0)[0]) == 2
    close = {"at": 300.0, "meta": a["meta"]}
    assert len(pick_distinct([a, close], 50, **args, horizon=900.0)[0]) == 1          # within the horizon: still one
    assert len(pick_distinct([a, {"at": 30.0, "meta": None}], 50, **args, horizon=900.0)[0]) == 1      # too close in time


# ---------- D. the time range ----------
def test_a_range_restricts_what_is_analysed_and_where_clips_come_from(long, tmp_path, monkeypatch):
    read = []
    real = pipeline.audio_rms_db
    monkeypatch.setattr(pipeline, "audio_rms_db", lambda *a, **k: (read.append(k), real(*a, **k))[1])
    timer = Timer()
    whole = run_pipeline(long, PipelineOptions(duration="0-30", limit=2, **FAST), tmp_path / "w")
    part = run_pipeline(long, PipelineOptions(duration="0-30", limit=2, range={"start": 400.5, "end": 650}, **FAST),
                        tmp_path / "p", timer=timer)
    assert near(whole) == [0, 1] and near(part) == [3, 4]                    # the best of 400-650, in source seconds
    assert all(400.5 <= c.start and c.end <= 650 for c in part) and all(inside(c, "0-30") for c in part)
    assert read == [{}, {"start": 400.0, "length": 250.0}]                   # only that part was measured
    assert timer.as_dict()["counts"]["analysed_sec"] == 249.5
    assert probe(part[0].video_path).duration == pytest.approx(part[0].end - part[0].start, abs=0.25)


def test_a_range_limits_transcription_and_the_judges_cut(long, tmp_path, no_render):
    heard, seen = [], []

    class Listening(Marked):
        def transcribe(self, wav):
            heard.append(wav_duration(wav))
            return super().transcribe(wav)

    def judge(text, frame, ctx):
        seen.append(ctx)
        a, b = ctx["window"]
        return {"title": "t", "virality": {"score": 80}, "trim": {"start": a - 30, "end": b, "peak": a}}
    opts = PipelineOptions(duration="30-60", range={"start": 150, "end": 215}, **FAST)
    clips = run_pipeline(long, opts, tmp_path / "o", transcriber=Listening(), judge=judge)
    assert len(clips) == 1 and near(clips) == [2] and all(150 <= c.start and c.end <= 215 for c in clips)
    assert max(heard) <= 65.1                                                # never more than the range was transcribed
    assert inside(clips[0], "30-60", rendered=False)                         # the cut reached before the range: clipped to it


def test_a_range_with_audio_decoded_by_the_caller_picks_the_same_clips(long, tmp_path, no_render):
    opts = PipelineOptions(duration="0-30", range={"start": 150, "end": 400}, **FAST)
    plain = run_pipeline(long, opts, tmp_path / "a")
    audio = extract_audio(long, tmp_path / "audio.wav")
    given = run_pipeline(long, opts, tmp_path / "b", source_audio=audio)
    assert near(given) == near(plain) == [0, 1, 2] and all(150 <= c.start and c.end <= 400 for c in given)
    # The same moments either way (a window may sit a second earlier or later: every position that holds the
    # whole loud moment scores the same).
    assert all(abs(a.start - b.start) <= 2 and length_ms(a) == length_ms(b) for a, b in zip(given, plain))


@pytest.mark.parametrize("bad", [{"start": 50, "end": 20}, {"start": 800, "end": 900}, {"start": -5, "end": 30},
                                 {"start": 10}, [10, 60], {"start": "a", "end": "b"}])
def test_an_invalid_range_is_refused(long, tmp_path, bad):
    with pytest.raises(PipelineError) as e:
        run_pipeline(long, PipelineOptions(range=bad, **FAST), tmp_path / "o")
    assert e.value.code == "bad_options"


def test_a_range_shorter_than_the_bucket_is_refused(long, tmp_path):
    with pytest.raises(PipelineError) as e:
        run_pipeline(long, PipelineOptions(duration="90-180", range={"start": 100, "end": 160}, **FAST), tmp_path / "o")
    assert e.value.code == "too_short_for_duration"


# ---------- the chosen moments, and nothing changes without the new options ----------
def test_the_chosen_moments_are_reported_best_first_before_rendering(long, tmp_path, no_render):
    got = []
    clips = run_pipeline(long, PipelineOptions(duration="0-30", limit=3, **FAST), tmp_path / "o", transcriber=Marked(),
                         judge=ranked_judge({0: 70, 1: 95, 2: 80}), on_moments=got.append)
    assert len(got) == 1 and all(isinstance(m, Moment) for m in got[0])
    assert [m.score for m in got[0]] == [95.0, 80.0, 70.0]                   # the judge's 0-100, best first
    assert {(m.start, m.end) for m in got[0]} == {(c.start, c.end) for c in clips}
    assert all(m.kind == "fail" and m.why == "why" and m.meta["title"] == "t" for m in got[0])
    plain = []
    run_pipeline(long, PipelineOptions(max_clips=2, clip_length=20, **FAST), tmp_path / "p", on_moments=plain.append)
    assert len(plain[0]) == 2 and all(m.kind is None and m.why is None and m.meta is None and m.score <= 1.2 for m in plain[0])


def test_without_the_new_options_the_pipeline_asks_for_exactly_what_it_did_before(three_bursts, tmp_path, monkeypatch, no_render):  # noqa: F811
    calls, seen = [], []
    for name in ("pick_windows", "pick_spread", "audio_rms_db"):
        real = getattr(pipeline, name)
        monkeypatch.setattr(pipeline, name, lambda *a, _n=name, _r=real, **k: (calls.append((_n, a[1:], k)), _r(*a, **k))[1])

    def judge(text, frame, ctx):
        seen.append(ctx)
        return {"title": "t", "virality": {"score": 80}}
    opts = PipelineOptions(max_clips=2, clip_length=20, captions=False, tighten=False)
    assert (opts.duration, opts.limit, opts.range, opts.project_name) == (None, None, None, None)
    run_pipeline(three_bursts, opts, tmp_path / "plain")
    run_pipeline(three_bursts, opts, tmp_path / "asr", transcriber=Marked())
    run_pipeline(three_bursts, opts, tmp_path / "judged", transcriber=Marked(), judge=judge)
    duration = probe(three_bursts).duration
    assert [(n, a, k) for n, a, k in calls if n != "audio_rms_db"] == [
        ("pick_windows", (20, 2, duration), {}),             # max_clips windows of clip_length over the whole video
        ("pick_windows", (20, 4, duration), {}),             # twice as many with a transcript
        ("pick_spread", (20, 7, duration), {})]              # five spare for the judge
    assert all(k == {} and len(a) == 1 for n, a, k in calls if n == "audio_rms_db")          # the whole file, no seek
    assert all(set(c) == {"length", "signals", "lines", "window", "timeline"} for c in seen)  # no cut_range
