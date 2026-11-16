"""pick_spread: every quarter of a long video reaches the judge; short videos and silent parts are unchanged."""
import numpy as np

from app.pipeline.windows import pick_spread, pick_windows


def second_half_spiky(n=7200):
    """Like the benchmark VOD: clear moments in the first half, stronger ones throughout the second."""
    rng = np.random.default_rng(7)
    score = rng.random(n) * 0.05
    for t in range(400, 3400, 300):          # ten moments in the first half
        score[t:t + 20] += 0.5
    for t in range(3700, 6700, 100):         # thirty stronger ones in the second half
        score[t:t + 20] += 0.9
    return score


def quarters(picks, n=7200):
    return [sum(1 for s, _e, _m in picks if int(4 * s / n) == k) for k in range(4)]


def test_plain_ranking_starves_the_first_half_and_spread_does_not():
    score = second_half_spiky()
    plain, spread = pick_windows(score, 30, 30, 7200.0), pick_spread(score, 30, 30, 7200.0)
    assert quarters(plain)[0] + quarters(plain)[1] == 0                 # the problem from the 0.2e report
    assert all(q >= 5 for q in quarters(spread))                        # floor = 30 // 6 per quarter
    assert len(spread) == len(plain) == 30                              # same number of candidates: same judge cost
    assert spread[0] == plain[0]                                        # the strongest moment is still first
    assert [m for _s, _e, m in spread] == sorted((m for _s, _e, m in spread), reverse=True)
    starts = sorted(s for s, _e, _m in spread)
    assert all(b - a >= 60 for a, b in zip(starts, starts[1:]))         # still one clip length apart


def test_a_silent_quarter_gets_no_candidates():
    score = second_half_spiky()
    score[:1830] = 0.0                       # no window starting in the first quarter has any signal
    spread = pick_spread(score, 30, 30, 7200.0)
    assert quarters(spread)[0] == 0 and all(m > 0 for _s, _e, m in spread)


def test_short_videos_and_small_requests_use_the_plain_ranking():
    score = second_half_spiky(900)
    assert pick_spread(score, 30, 12, 900.0) == pick_windows(score, 30, 12, 900.0)        # under 20 minutes
    long = second_half_spiky()
    assert pick_spread(long, 30, 5, 7200.0) == pick_windows(long, 30, 5, 7200.0)          # floor would be 0


def test_only_the_judge_path_nominates_with_spread(video, tmp_path, monkeypatch):
    import app.pipeline as pipeline
    used = []
    for name in ("pick_spread", "pick_windows"):
        real = getattr(pipeline, name)
        monkeypatch.setattr(pipeline, name, lambda *a, _n=name, _r=real, **k: (used.append(_n), _r(*a, **k))[1])
    opts = pipeline.PipelineOptions(max_clips=1, clip_length=10)
    pipeline.run_pipeline(video, opts, tmp_path / "plain")
    pipeline.run_pipeline(video, opts, tmp_path / "judged", judge=lambda text, frame, ctx: {"virality": {"score": 80}})
    assert used == ["pick_windows", "pick_spread"]          # plain run, then judged run
