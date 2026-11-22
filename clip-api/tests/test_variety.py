"""Variety: after judging, skip candidates close in time or about the same thing as a picked clip."""
from types import SimpleNamespace as C

from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline.variety import pick_distinct
from tests.test_launch import three_bursts  # noqa: F401 (fixture)


def pick(ranked, n):
    picked, skipped = pick_distinct(ranked, n, window=lambda c: (c.start, c.end), meta=lambda c: c.meta,
                                    speech=lambda c: c.text)
    return [c.name for c in picked], skipped


def cand(name, start, title="", desc="", tags=(), text=""):
    meta = {"title": title, "description": desc, "hashtags": list(tags)} if (title or desc or tags) else None
    return C(name=name, start=float(start), end=float(start) + 30, meta=meta, text=text)


FILLER = [cand(f"f{i}", 6000 + 400 * i, f"Topic {w} thing", tags=("gta6", "gaming"))
          for i, w in enumerate(["casino heist", "street race", "police chase", "boat jump", "bank vault"])]


def test_skips_a_window_within_60_s_of_a_picked_clip():
    ranked = [cand("a", 1000, "Rooftop sniper duel"), cand("b", 1075, "Rooftop sniper rematch alley"),
              cand("c", 1100, "Totally different tank"), cand("d", 3000, "Motorbike wheelie fail")]
    # a is 1000-1030. b starts 45 s after a ends (too close); c starts 70 s after (far enough).
    names, skipped = pick(ranked, 3)
    assert names == ["a", "c", "d"]
    assert skipped == [(1, "within 60 s of a picked clip")]


def test_same_plane_moment_three_times_keeps_one_and_still_returns_the_count():
    # The 2-hour VOD: the same plane moment at 1:17, 1:20 and 1:23, three minutes apart.
    plane = [cand("plane1", 4620, "Plane crash into the bay", "He flies the plane straight into the water",
                  ("gta6", "plane", "crash")),
             cand("plane2", 4800, "Plane nosedive into water", "Another plane crash into the bay",
                  ("gta6", "plane")),
             cand("plane3", 4980, "Crash landing the plane", "The plane hits the water again", ("plane", "gaming"))]
    ranked = [plane[0], plane[1], FILLER[0], plane[2], *FILLER[1:]]
    names, skipped = pick(ranked, 4)
    assert names == ["plane1", "f0", "f1", "f2"]
    assert [r for _, r in skipped] == ["same topic as a picked clip"] * 2


def test_shared_hashtags_alone_do_not_make_clips_duplicates():
    names, skipped = pick(FILLER, 5)
    assert names == ["f0", "f1", "f2", "f3", "f4"] and skipped == []


def test_same_speech_is_a_duplicate_even_without_titles():
    said = "no no no get out of the car, the cops are shooting at us, drive drive drive toward the airport"
    ranked = [cand("a", 1000, text=said), cand("b", 2000, text=said + " now"), *FILLER[:3]]
    names, _ = pick(ranked, 3)
    assert names == ["a", "f0", "f1"]


def test_a_few_words_in_common_is_not_the_same_speech():
    ranked = [cand("a", 1000, text="oh my god no way"), cand("b", 2000, text="oh my god no way")]
    names, _ = pick(ranked, 2)
    assert names == ["a", "b"]


def test_min_gap_is_60_s_on_long_videos_and_shrinks_on_short_ones():
    from app.pipeline.variety import min_gap_for
    assert min_gap_for(7218, 10) == 60          # the 2-hour VOD
    assert min_gap_for(60, 3) == 10             # a 1-minute upload asking for 3 clips


def test_fewer_clips_when_not_enough_distinct_candidates():
    ranked = [cand("a", 1000, "Plane crash into the bay"), cand("b", 3000, "Plane crash bay again")]
    names, skipped = pick(ranked, 2)
    assert names == ["a"] and len(skipped) == 1


def test_third_same_kind_within_horizon_is_skipped_for_gaming_mix():
    def with_kind(c, kind):
        c.meta = {**(c.meta or {}), "kind": kind}
        return c

    ranked = [
        with_kind(cand("f1", 1000, "Fail one ragdoll"), "fail"),
        with_kind(cand("f2", 2000, "Fail two wallbang"), "fail"),
        with_kind(cand("f3", 3000, "Fail three dive"), "fail"),
        with_kind(cand("c1", 4000, "Clutch escape"), "clutch"),
    ]
    picked, skipped = pick_distinct(
        ranked, 4, window=lambda c: (c.start, c.end), meta=lambda c: c.meta,
        speech=lambda c: c.text, kind=lambda c: (c.meta or {}).get("kind"))
    assert [c.name for c in picked] == ["f1", "f2", "c1"]
    assert skipped == [(2, "same kind (fail) as picked clips")]


def test_kind_cap_does_not_apply_across_horizon():
    ranked = [
        cand("f1", 1000, "Fail early"),
        cand("f2", 2000, "Fail mid"),
        cand("f3", 2930, "Fail late"),  # ≥900 s from both earlier fails' windows
    ]
    for c, k in zip(ranked, ("fail", "fail", "fail")):
        c.meta = {**(c.meta or {}), "kind": k}
    picked, skipped = pick_distinct(
        ranked, 3, window=lambda c: (c.start, c.end), meta=lambda c: c.meta,
        speech=lambda c: c.text, horizon=900.0, kind=lambda c: (c.meta or {}).get("kind"))
    assert [c.name for c in picked] == ["f1", "f2", "f3"] and skipped == []


def test_missing_kind_is_not_limited():
    ranked = [cand("a", 1000, "One"), cand("b", 2000, "Two"), cand("c", 3000, "Three")]
    picked, skipped = pick_distinct(
        ranked, 3, window=lambda c: (c.start, c.end), meta=lambda c: c.meta,
        speech=lambda c: c.text, kind=lambda c: (c.meta or {}).get("kind"))
    assert [c.name for c in picked] == ["a", "b", "c"] and skipped == []


def test_pipeline_drops_a_repeated_topic_and_keeps_distinct_ones(three_bursts, tmp_path, transcriber):
    # Two of the three bursts get the same title; the third is distinct. Asking for 3 gives 2 distinct clips.
    def judge(text, frame, ctx):
        judge.n += 1
        same = judge.n != 2
        return {"title": "Plane crash into the bay" if same else "Motorbike wheelie fail",
                "description": "", "hashtags": [], "virality": {"score": 80}}
    judge.n = 0
    res = run_pipeline(three_bursts, PipelineOptions(max_clips=3, clip_length=8, captions=False), tmp_path / "o",
                       transcriber=transcriber, judge=judge)
    titles = sorted(r.meta["title"] for r in res)
    assert titles == ["Motorbike wheelie fail", "Plane crash into the bay"]
