"""Opt-in checks against the real sites. Skipped unless INGEST_LIVE_TESTS=1, so no normal test run reaches the
network. They are small on purpose: metadata, a 19-second video and a 10-second range, all public, with the fixed
import options (no login, cookies, proxy or impersonation). A site that refuses is a skip, not a failure: the
product's answer to a refusal is "upload the file instead", and these tests only say what worked on the day.

    INGEST_LIVE_TESTS=1 pytest -q tests/test_ingest_live_sites.py
    INGEST_LIVE_TWITCH_VOD=https://www.twitch.tv/videos/<id>   optional: Twitch VODs expire, so none is fixed here
"""
import os

import pytest

from app.ingest import Refused, Span, platforms
from app.ingest import preview as link_preview
from app.ingest.sources import classify
from app.pipeline.ff import probe

pytestmark = pytest.mark.skipif(os.environ.get("INGEST_LIVE_TESTS") != "1", reason="set INGEST_LIVE_TESTS=1")

LIMITS = platforms.Limits(max_bytes=200 * 1024 ** 2, max_duration_sec=6 * 3600, timeout_sec=300, min_duration_sec=5)
ME_AT_THE_ZOO = "https://youtu.be/jNQXAC9IVRw"                                  # 19 s, 240p, public since 2005
BIG_BUCK_BUNNY = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"                  # 10 min, Blender Foundation
TWITCH_CLIP = "https://clips.twitch.tv/BadCoweringGoshawkHeyGuys"               # 30 s, on Twitch's own channel


def look(url: str) -> dict:
    link_preview.clear_cache()
    body = link_preview.look(classify(url))
    if body["refusal"] and body["refusal"]["code"] in ("source_refused", "source_failed", "preview_timeout"):
        pytest.skip(f"the site refused today: {body['refusal']}")
    return body


def fetch(url: str, folder, span=Span()):
    source = classify(url)
    try:
        return platforms.download(source.platform, source.fetch_url, folder, LIMITS, span=span)
    except Refused as e:
        if e.code in ("source_refused", "source_failed", "import_timeout"):
            pytest.skip(f"the site refused today: {e.code} {e.message}")
        raise


@pytest.mark.parametrize("url, video_type, title", [
    (ME_AT_THE_ZOO, "video", "Me at the zoo"),
    (TWITCH_CLIP, "clip", "CUUUT"),
])
def test_metadata_in_under_two_seconds(url, video_type, title):
    body = look(url)
    assert body["supported"] is True and body["video_type"] == video_type and body["title"] == title
    assert body["channel"] and body["thumbnail_url"].startswith("https://") and body["duration_sec"] > 0
    assert body["lookup_ms"] < 2000, body["lookup_ms"]


def test_youtube_picture_and_sound_are_two_streams_and_come_out_as_one_file(tmp_path):
    got = fetch(ME_AT_THE_ZOO, tmp_path)
    info = probe(got.path)
    assert 18 <= info.duration <= 20 and info.has_audio and info.width > 0


def test_a_ten_second_range_of_a_long_youtube_video(tmp_path):
    got = fetch(BIG_BUCK_BUNNY, tmp_path, Span(60.0, 70.0))
    info = probe(got.path)
    assert got.partial is True and 9.5 <= info.duration <= 17 and info.has_audio and info.height <= 1080
    assert got.path.stat().st_size < 40 * 1024 ** 2             # the range, not the 10 minutes


def test_a_twitch_clip(tmp_path):
    info = probe(fetch(TWITCH_CLIP, tmp_path).path)
    assert 29 <= info.duration <= 31 and info.has_audio


def test_a_twitch_vod_and_twenty_seconds_of_it(tmp_path):
    url = os.environ.get("INGEST_LIVE_TWITCH_VOD")
    if not url:
        pytest.skip("set INGEST_LIVE_TWITCH_VOD to a public VOD link")
    body = look(url)
    assert body["video_type"] in ("vod", "ongoing_recording") and body["supported"] is True
    assert body["channel"] and body["duration_sec"] > 60 and body["lookup_ms"] < 2000
    got = fetch(url, tmp_path, Span(30.0, 50.0))
    info = probe(got.path)
    assert got.partial is True and 19.5 <= info.duration <= 31 and info.has_audio
