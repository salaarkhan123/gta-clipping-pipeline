"""Game events read from on-screen banners (pipeline/events.py)."""
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.pipeline.events import (EVENT_LEAD, Banner, BannerReader, available, event_seconds, game_of, match, text_ink)


def frame(text: str | None, seed: int = 0) -> np.ndarray:
    """A 320x180 game-like frame (mid-grey noise), with white banner text in the top band when given."""
    rng = np.random.default_rng(seed)
    img = Image.fromarray(rng.integers(40, 150, (180, 320, 3), dtype=np.uint8))
    if text:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        except OSError:
            font = ImageFont.load_default(26)
        ImageDraw.Draw(img).text((160, 30), text, fill=(255, 255, 255), font=font, anchor="mm")
    return np.asarray(img)


def test_phrases_match_whole_words_with_small_misreads_and_by_game():
    assert match("last round before sw") == ("last round before swap", "round")
    assert match("1 victory royal", "fortnite") == ("victory royale", "event")
    assert match("x wasted y", "gta5") == ("wasted", "event") and match("x wasted y", "valorant") is None
    assert match("a or won sli", "valorant") == ("won", "event")
    assert match("a or won sli") is None                 # game unknown: a 3-letter word in OCR noise is not trusted
    assert match("wonderful", "valorant") is None and match("") is None and match("press b to buy") is None


def test_event_seconds_cover_the_lead_up_to_a_banner():
    b = [Banner(t=100.0, kind="event", phrase="won", text="won", band="top"),
         Banner(t=30.0, kind="menu", phrase="settings", text="settings", band="mid")]
    ev = event_seconds(b, "event", 50, 100, EVENT_LEAD, 2.0)
    assert ev[100 - 50 - 15] == 1 and ev[100 - 50 + 2] == 1 and ev[100 - 50 - 16] == 0 and ev[100 - 50 + 3] == 0
    assert not event_seconds(b, "menu", 50, 100, 3, 3).any()             # before the analysed part
    assert game_of(None) is None and game_of("valorant-ranked-comms") == "valorant" and game_of("stream-talk") is None


def test_banner_text_stands_out_from_the_picture():
    assert text_ink(frame("VICTORY")[4:58, 80:240]).mean() > 5 * text_ink(frame(None)[4:58, 80:240]).mean() + 0.01


@pytest.mark.skipif(not available(), reason="tesseract is not installed")
def test_the_reader_reads_only_the_strongest_frames_and_finds_the_banner():
    reader = BannerReader(max_reads=5)
    for i in range(40):
        reader.on_frame(2.0 * i, frame("VICTORY" if i == 25 else None, seed=i))
    assert reader.chosen() == [50.0]
    found = reader.read()
    assert [(b.t, b.kind, b.phrase) for b in found] == [(50.0, "event", "victory")]


def test_without_tesseract_there_are_no_events(monkeypatch):
    import app.pipeline.events as events
    monkeypatch.setattr(events.shutil, "which", lambda name: None)
    reader = BannerReader()
    for i in range(10):
        reader.on_frame(float(i), frame("VICTORY" if i == 5 else None, seed=i))
    assert reader.read() == [] and not events.available()
