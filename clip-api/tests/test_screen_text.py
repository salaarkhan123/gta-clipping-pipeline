"""HUD OCR (#202): weight 0 does not rank; an unknown game decodes nothing; the harness needs no GPU."""
import sys

import numpy as np
import pytest

import app.pipeline as pipeline
from app.pipeline import WEIGHTS, PipelineOptions, run_pipeline
from app.pipeline import layouts as L
from app.pipeline import screen_text as st
from app.templates import TEMPLATES


def valorant_template():
    return next(t["id"] for t in TEMPLATES.values() if t.get("game") == "valorant")


class FakeOcr:
    requires_gpu = False

    def read(self, image):
        return [("WASTED", 0.99)]


def windows(clips):
    return [(c.start, c.end, c.score, c.signals) for c in clips]


def test_hud_signals_are_off_by_default():
    assert WEIGHTS["hud_killfeed"] == WEIGHTS["hud_banner"] == 0
    assert set(st.HUD_SIGNALS) <= set(WEIGHTS)
    assert st.LICENSE == "Apache-2.0" and st.PaddleBackend.license == "Apache-2.0"


def test_harness_does_not_require_gpu_or_downloaded_weights():
    assert "paddleocr" not in sys.modules and "paddle" not in sys.modules
    b = st.default_backend()
    assert isinstance(b, st.StubBackend) and not b.requires_gpu
    assert st.PaddleBackend.requires_gpu is False
    assert st.StubBackend().read(np.zeros((8, 8, 3), np.uint8)) == []


def test_unknown_game_reads_nothing_and_does_not_decode(video, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("decoded HUD for a game with no table")
    monkeypatch.setattr(st, "_crop_at", boom)
    assert st.ocr_regions(None) == st.ocr_regions("no-such-game") == st.ocr_regions("lol") == ()
    assert st.read_hud(video, "no-such-game", 0.0, 40.0, width=640, height=360) == []
    assert st.read_hud(video, None, 0.0, 40.0, width=640, height=360) == []


def test_ocr_regions_keep_only_killfeed_and_banner(monkeypatch):
    monkeypatch.setitem(L.HUD_REGIONS, "valorant", (
        ("killfeed", (0.80, 0.07, 0.19, 0.2)),
        ("minimap", (0.01, 0.75, 0.15, 0.22)),
        ("banner", (0.30, 0.40, 0.40, 0.12)),
    ))
    kinds = [k for k, _b in st.ocr_regions("valorant")]
    assert kinds == ["killfeed", "banner"]


def test_events_carry_region_time_and_text(video, monkeypatch):
    monkeypatch.setitem(L.HUD_REGIONS, "gta5", (("banner", (0.25, 0.40, 0.50, 0.20)),))
    monkeypatch.setattr(st, "_crop_at", lambda *a, **k: np.zeros((20, 40, 3), np.uint8))
    events = st.read_hud(video, "gta5", 0.0, 12.0, width=640, height=360, backend=FakeOcr(), step=4.0)
    assert [(e.text, e.region, e.t) for e in events] == [
        ("WASTED", "banner", 0.0), ("WASTED", "banner", 4.0), ("WASTED", "banner", 8.0)]
    assert events[0].as_dict() == {"text": "WASTED", "region": "banner", "t": 0.0}
    assert st.banner_hit("Wasted") == "wasted" and st.banner_hit("a red car") is None


def test_weight_zero_does_not_decode_hud_even_when_the_game_has_boxes(video, tmp_path, monkeypatch):
    monkeypatch.setitem(L.HUD_REGIONS, "valorant", (("killfeed", (0.80, 0.07, 0.19, 0.2)),
                                                    ("banner", (0.30, 0.40, 0.40, 0.12))))
    def boom(*a, **k):
        raise AssertionError("decoded HUD for a weight-0 ranking run")
    monkeypatch.setattr(st, "_crop_at", boom)
    monkeypatch.setattr(st, "read_hud", boom)
    clips = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False,
                                                template=valorant_template(), render="none"), tmp_path / "o")
    assert clips and "hud_killfeed" not in clips[0].signals and "hud_banner" not in clips[0].signals
    assert (clips[0].features.get("scene") or {}).get("text_events") in (None, [])


def test_observe_mode_does_not_change_candidates(video, tmp_path, monkeypatch):
    monkeypatch.setitem(L.HUD_REGIONS, "valorant", (("banner", (0.30, 0.40, 0.40, 0.12)),))
    monkeypatch.setattr(st, "read_hud",
                        lambda *a, **k: [st.TextEvent(text="WASTED", region="banner", t=21.0)])
    opts = dict(max_clips=2, clip_length=10, tighten=False, template=valorant_template(), render="none")
    plain = run_pipeline(video, PipelineOptions(**opts), tmp_path / "a")
    seen = run_pipeline(video, PipelineOptions(**opts, observe_hud_ocr=True), tmp_path / "b")
    assert windows(plain) == windows(seen)
    assert not any((c.features.get("scene") or {}).get("text_events") for c in plain)
    assert any(ev["text"] == "WASTED" and ev["region"] == "banner"
               for c in seen for ev in (c.features.get("scene") or {}).get("text_events") or [])


def test_a_hud_weight_above_zero_is_the_only_ranking_path(video, tmp_path, monkeypatch):
    """Lock the skip: turning the weight on is what would compute the detector, not observation."""
    called = []
    monkeypatch.setattr(st, "read_hud",
                        lambda *a, **k: called.append(True) or [st.TextEvent("WASTED", "banner", 21.0)])
    run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False, render="none"), tmp_path / "off")
    assert called == []
    run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False, render="none",
                                        weights={"hud_banner": 1.0}), tmp_path / "on")
    assert called == [True]


def test_series_from_events_counts_killfeed_changes_and_banner_hits():
    events = [st.TextEvent("P1 killed P2", "killfeed", 3.2),
              st.TextEvent("P1 killed P2", "killfeed", 3.8),
              st.TextEvent("P3 killed P1", "killfeed", 5.1),
              st.TextEvent("WASTED", "banner", 5.4),
              st.TextEvent("a red garage", "banner", 8.0)]
    s = st.series_from_events(events, n=10)
    assert s["hud_killfeed"][3] == 1.0 and s["hud_killfeed"][5] == 1.0
    assert s["hud_killfeed"][4] == 0.0 and sum(s["hud_killfeed"]) == 2.0
    assert s["hud_banner"][5] == 1.0 and s["hud_banner"][8] == 0.0
