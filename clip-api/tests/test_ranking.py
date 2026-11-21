"""Per-game ranking: the five sub-scores are stored one by one, a game's weights only reorder clips, and the weights
come from the owner's labels (scripts/fit_score_weights.py), never from a guess."""
import json
import sys
from pathlib import Path

import pytest

import app.pipeline as P
from app.ai import SCORES, parse_meta
from app.pipeline.ranking import EQUAL, clean, rank_score, weights_for
from app.worker import game_weights

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fit_score_weights as fit  # noqa: E402

RACING = {"hook": 1, "payoff": 1, "clarity": 0, "emotion": 1, "pacing": 7}
V2 = {"titles": ["a", "b", "c"], "hook": "h", "hashtags": ["gta"], "reason": "r", "kind": "story"}


def scores(hook, payoff, clarity, emotion, pacing):
    return dict(zip(SCORES, (hook, payoff, clarity, emotion, pacing)))


# ---------- the weights ----------

def test_no_weights_is_the_plain_mean_and_weights_are_shares():
    s = scores(80, 90, 70, 60, 50)
    assert rank_score(s, None) == 70.0
    w = clean(RACING)
    assert w == {"hook": 0.1, "payoff": 0.1, "clarity": 0.0, "emotion": 0.1, "pacing": 0.7}
    assert rank_score(s, w) == pytest.approx(8 + 9 + 0 + 6 + 35)
    assert rank_score({"hook": 80}, w) is None and rank_score(None, w) is None


@pytest.mark.parametrize("bad", [None, {}, {"hook": 1}, {**RACING, "pacing": -1}, dict.fromkeys(RACING, 0),
                                 {**RACING, "hook": "lots"}])
def test_an_unusable_set_of_weights_is_never_half_used(bad):
    assert clean(bad) is None
    assert weights_for("gta5", "open-world", {"gta5": bad}) == (None, EQUAL)


def test_a_game_uses_its_own_weights_then_its_genres_then_the_default():
    table = {"forza": RACING, "racing": scores(2, 2, 2, 2, 2), "default": scores(3, 1, 1, 1, 1)}
    own, v_own = weights_for("forza", "racing", table)
    genre, v_genre = weights_for("f1", "racing", table)
    other, v_other = weights_for("gta5", "open-world", table)
    assert own["pacing"] == 0.7 and v_own.startswith("forza:")
    assert genre["hook"] == 0.2 and v_genre.startswith("racing:")
    assert other["hook"] == pytest.approx(3 / 7, abs=1e-4) and v_other.startswith("default:")
    assert weights_for("gta5", None, {}) == (None, EQUAL) and weights_for(None, None, None) == (None, EQUAL)
    assert weights_for("forza", "racing", {"forza": {**RACING, "pacing": 6}})[1] != v_own      # new weights, new name


def test_the_worker_reads_the_setting_and_a_bad_one_never_fails_a_job():
    from app.templates import TEMPLATES
    template = next(t for t in TEMPLATES.values() if t.get("game"))
    table = json.dumps({template["game"]: RACING})
    weights, version = game_weights(template["id"], table)
    assert weights["pacing"] == 0.7 and version.startswith(template["game"] + ":")
    assert game_weights(None, table) == (None, EQUAL)                     # no template: no game
    assert game_weights(template["id"], "") == (None, EQUAL)              # nothing configured
    assert game_weights(template["id"], "{not json") == (None, EQUAL)     # unreadable: the plain mean
    assert game_weights(template["id"], "[1, 2]") == (None, EQUAL)


# ---------- in the judge ----------

def judged(tmp_path, metas, **kw):
    cands = [P._Candidate(start=100.0 * i, end=100.0 * i + 30, base=1.0, signals={"i": i}, features={})
             for i in range(len(metas))]

    def judge(text, frame, ctx):
        return parse_meta({**V2, "virality": metas[ctx["signals"]["i"]]})
    return P._judge(cands, judge, tmp_path / "none.mp4", tmp_path, lambda *a: None, None, **kw)


def test_weights_reorder_clips_and_leave_the_rating_and_the_sub_scores_alone(tmp_path):
    steady = scores(60, 60, 60, 60, 60)             # rating 60
    fast = scores(40, 40, 40, 40, 100)              # rating 52, but all pace
    plain = judged(tmp_path, [steady, fast])
    assert [c.start for c in plain] == [0.0, 100.0] and "rank_score" not in plain[0].features
    weights, version = weights_for("forza", None, {"forza": RACING})
    racing = judged(tmp_path, [steady, fast], weights=(weights, version))
    assert [c.start for c in racing] == [100.0, 0.0]                     # the fast one first
    top = racing[0]
    assert top.features["rank_score"] == 82.0 and top.features["rank_weights"] == version
    assert top.features["judge_score"] == 52 and top.meta["virality"]["score"] == 52     # the AI rating: the plain mean
    assert top.meta["scores"] == fast and top.meta["scoring_version"] == "judge-v2-equal"


def test_weights_never_change_how_many_clips_pass_the_quality_floor(tmp_path):
    weights, version = weights_for("forza", None, {"forza": RACING})
    metas = [scores(60, 60, 60, 60, 60), scores(20, 20, 20, 20, 100), scores(50, 50, 50, 50, 0)]   # ratings 60, 36, 40
    plain = judged(tmp_path, metas, every=True)
    racing = judged(tmp_path, metas, every=True, weights=(weights, version))
    assert sorted(c.start for c in plain) == sorted(c.start for c in racing) == [0.0, 200.0]


def test_an_older_four_part_answer_ranks_by_its_rating(tmp_path):
    weights, version = weights_for("forza", None, {"forza": RACING})
    out = judged(tmp_path, [{"hook": 90, "flow": 80, "value": 70, "trend": 60}], weights=(weights, version))
    assert out[0].features["judge_score"] == 75 and "rank_score" not in out[0].features


# ---------- fitting on the owner's labels ----------

def clip(label, moment, **s):
    return {"start": 0.0, "end": 30.0, "label": label, "moment": moment, "scores": scores(**s)}


def videos_where_pacing_tells():
    """Two tuning videos: the owner's good clips are the well-paced ones; hook is noise."""
    out = []
    for v in range(2):
        clips = []
        for i in range(12):
            good = i % 2 == 0
            clips.append(clip(3 if good else 1, f"v{v}m{i}", hook=90 if not good else 30, payoff=50, clarity=50,
                              emotion=50, pacing=80 if good else 55))
        out.append(clips)
    return out


def test_precision_counts_a_moment_once_and_only_the_top_k():
    clips = [clip(3, "a", hook=90, payoff=0, clarity=0, emotion=0, pacing=0),
             clip(3, "a", hook=80, payoff=0, clarity=0, emotion=0, pacing=0),      # the same moment again: no hit
             clip(1, "b", hook=70, payoff=0, clarity=0, emotion=0, pacing=0),
             clip(3, "c", hook=10, payoff=0, clarity=0, emotion=0, pacing=0)]
    assert fit.precision_at([clips], lambda c: c["scores"]["hook"], 3) == (1, 3)
    assert fit.precision_at([clips], lambda c: c["scores"]["hook"], 10) == (2, 4)


def test_rank_correlation():
    assert fit.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0 and fit.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert fit.spearman([1, 2], [1, 2]) is None and fit.spearman([1, 1, 1], [1, 2, 3]) is None


def test_the_fit_finds_the_sub_score_that_tracks_the_labels_and_stays_equal_when_nothing_beats_it():
    videos = videos_where_pacing_tells()
    weights, equal, fitted = fit.fit(videos, 6)
    assert equal == (0, 12) and fitted == (12, 12)                     # equal weights follow the noisy hook
    assert weights["pacing"] > weights["hook"] and sum(weights.values()) == pytest.approx(1.0, abs=1e-3)
    already = [[clip(3, "a", hook=90, payoff=90, clarity=90, emotion=90, pacing=90),
                clip(1, "b", hook=10, payoff=10, clarity=10, emotion=10, pacing=10)]]
    assert fit.fit(already, 1)[0] is None                              # equal weights already get it right


def sheet(tmp_path, rows):
    path = tmp_path / "labels.csv"
    lines = ["id,vod,game,start,end,rating,reason,held_out,source"]
    lines += [f"{i},{vod},{game},{start},{end},{rating},{'why' if rating == 3 else ''},{held},x"
              for i, (vod, game, start, end, rating, held) in enumerate(rows, 1)]
    path.write_text("\n".join(lines) + "\n")
    return path


def hms(t):
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def test_the_script_fits_on_tuning_videos_only_and_reports_held_out_totals(tmp_path, capsys):
    rows, jobs = [], {}
    for vod, game, held in (("forza-1", "forza", "no"), ("forza-2", "forza", "no"), ("gta-rp-1", "gta-rp", "yes")):
        clips = []
        for i in range(12):
            good = i % 2 == 0
            start = 100 * i
            rows.append((vod, game, hms(start), hms(start + 30), 3 if good else 1, held))
            clips.append({"start_sec": start, "end_sec": start + 30,
                          "scores": scores(90 if not good else 30, 50, 50, 50, 80 if good else 55)})
        clips.append({"start_sec": 5000, "end_sec": 5030})                # not judged: no sub-scores, left out
        jobs[vod] = tmp_path / f"{vod}.json"
        jobs[vod].write_text(json.dumps({"clips": clips}))
    out = tmp_path / "weights.json"
    code = fit.main([str(sheet(tmp_path, rows)), *[f"{v}={p}" for v, p in jobs.items()], "--k", "6", "--min-rated", "20",
                     "--out", str(out)])
    text = capsys.readouterr().out
    assert code == 0
    weights = json.loads(out.read_text())
    assert set(weights) == {"default", "forza"} and weights["forza"]["pacing"] > weights["forza"]["hook"]
    assert "forza: 2 tuning video(s), 24 rated clips" in text and "equal weights precision@6 0/12 = 0% · fitted 12/12 = 100%" in text
    assert "held-out gta-rp-1 (gta-rp): 12 rated clips" in text and "totals only" in text
    assert "gta-rp:" not in text.replace("(gta-rp):", "")                  # no per-game fit on the held-out video
    assert game_weights(None, out.read_text())[0] == weights["default"]    # the file is what SCORE_WEIGHTS takes


def test_too_few_rated_clips_keep_equal_weights(tmp_path, capsys):
    rows = [("forza-1", "forza", hms(100 * i), hms(100 * i + 30), 3 if i % 2 == 0 else 1, "no") for i in range(4)]
    job = tmp_path / "j.json"
    job.write_text(json.dumps({"clips": [{"start_sec": 100 * i, "end_sec": 100 * i + 30, "scores": scores(50, 50, 50, 50, 50)}
                                         for i in range(4)]}))
    out = tmp_path / "w.json"
    assert fit.main([str(sheet(tmp_path, rows)), f"forza-1={job}", "--out", str(out)]) == 0
    assert json.loads(out.read_text()) == {} and "under 30: equal weights stay" in capsys.readouterr().out
