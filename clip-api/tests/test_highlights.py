"""AS-2 one-click Generate Highlights: duration → auto clip upper bound."""
from app.pipeline import PipelineOptions, _wanted
from app.pipeline.highlights import MAX_CLIPS, MIN_WANT, SEC_PER_SLOT, suggest_want


def test_suggest_want_scales_to_north_star_band():
    assert suggest_want(0) == MIN_WANT and suggest_want(-1) == MIN_WANT
    assert suggest_want(60) == MIN_WANT                          # under three minutes → floor
    assert suggest_want(10 * 60) == MIN_WANT                     # 10 min
    assert suggest_want(30 * 60) == 10                           # 30 min
    assert suggest_want(60 * 60) == 20                           # 1 h
    assert suggest_want(2 * 60 * 60) == 40                       # 2 h → inside SPEC §14 30–50
    assert suggest_want(3 * 60 * 60) == MAX_CLIPS                # 3 h+ → hard cap
    assert SEC_PER_SLOT == 180 and MAX_CLIPS == 50


def test_wanted_uses_suggest_want_for_auto_discovery():
    auto = PipelineOptions(duration="0-90")
    assert _wanted(auto, 7200) == 40
    assert _wanted(auto, 300) == MIN_WANT
    assert _wanted(auto, None) == MIN_WANT                      # unknown span → floor, not MAX_CLIPS
    assert _wanted(PipelineOptions(duration="0-90", limit=12), 7200) == 12
    assert _wanted(PipelineOptions(max_clips=3), 7200) == 3     # no bucket: legacy max_clips
