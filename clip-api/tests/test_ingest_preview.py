"""Link preview: `POST /v1/imports/preview {url}` says what a link is before anything is imported. Metadata only,
free, nothing stored. Platforms come from the yt-dlp stand-in and direct links from the fake DNS; no network."""
import threading
import uuid

import pytest
from sqlalchemy import func, select

from app.db import new_session
from app.ingest import platforms
from app.ingest import preview as link_preview
from app.models import CreditLedger, ImportLog, Job, Upload
from tests.ingest_support import fake_ydl, no_stray_imports, web  # noqa: F401
from tests.test_api import balance

TWITCH = "https://www.twitch.tv/videos/2301234567"
THUMB = "https://static-cdn.jtvnw.net/cf_vods/d1m7jfoe9zdc1j/abc/thumb/thumb0-640x360.jpg"
KEYS = {"url", "platform", "supported", "title", "channel", "duration_sec", "thumbnail_url", "kind", "refusal"}


@pytest.fixture(autouse=True)
def fresh_cache():
    link_preview.clear_cache()
    yield
    link_preview.clear_cache()


def ask(client, headers, url):
    r = client.post("/v1/imports/preview", json={"url": url}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == KEYS
    return body


def stored(account_id) -> dict:
    with new_session() as db:
        count = lambda model: db.execute(select(func.count()).select_from(model)  # noqa: E731
                                         .where(model.account_id == account_id)).scalar_one()
        return {"log": count(ImportLog), "uploads": count(Upload), "jobs": count(Job), "ledger": count(CreditLedger)}


def test_a_supported_link_shows_its_metadata_and_imports_nothing(client, user, fake_ydl):
    headers, account = user
    before = stored(account["id"])
    fake_ydl.info = {"duration": 7260.5, "uploader": "SomeStreamer", "thumbnail": THUMB}
    body = ask(client, headers, "https://m.twitch.tv/videos/2301234567?t=1h")
    assert body == {"url": TWITCH, "platform": "twitch", "supported": True, "title": "Ranked grind: part 3 / finale!",
                    "channel": "SomeStreamer", "duration_sec": 7260.5, "thumbnail_url": THUMB, "kind": "video",
                    "refusal": None}
    # Metadata only, with the import's fixed options and a short socket timeout. Nothing is stored or charged.
    assert len(fake_ydl.instances) == 1 and fake_ydl.instances[0].urls == [TWITCH]
    options = fake_ydl.instances[0].params
    for name in ("cookiefile", "cookiesfrombrowser", "username", "password", "impersonate", "geo_bypass"):
        assert not options[name]
    assert options["proxy"] == "" and options["extractor_args"] == {} and options["js_runtimes"] == {}
    assert options["socket_timeout"] == link_preview.SOCKET_TIMEOUT_SEC
    assert options["outtmpl"].startswith(str(platforms.NOWHERE))
    assert stored(account["id"]) == before
    assert balance(client, headers) == 30


def test_a_clip_is_a_clip_and_channel_beats_curator(client, user, fake_ydl):
    headers, _ = user
    fake_ydl.info = {"channel": "TheBroadcaster", "uploader": "SomeCurator", "thumbnail": "http://insecure.test/t.jpg",
                     "thumbnails": [{"url": "https://cdn.test/small.jpg"}, {"url": "https://cdn.test/big.jpg"}]}
    body = ask(client, headers, "https://www.twitch.tv/somechannel/clip/FunnyClipSlug-abc123")
    assert body["url"] == "https://clips.twitch.tv/FunnyClipSlug-abc123" and body["kind"] == "clip"
    assert body["channel"] == "TheBroadcaster" and body["thumbnail_url"] == "https://cdn.test/big.jpg"


def test_an_unsupported_platform_is_refused_without_a_request(client, user, fake_ydl, web):
    headers, _ = user
    body = ask(client, headers, "https://vimeo.com/123456")
    assert body["supported"] is False and body["platform"] is None and body["kind"] is None
    assert body["refusal"]["code"] == "unsupported_source"
    assert body["refusal"]["message"].endswith("Upload the file instead.")
    assert body["title"] is None and body["thumbnail_url"] is None
    assert fake_ydl.instances == [] and web.resolved == []


@pytest.mark.parametrize("url", ["https://internal.test/video.mp4", "https://metadata.test/x.mp4",
                                 "https://10.0.0.5/video.mp4", "https://mixed.test/video.mp4"])
def test_a_private_address_is_refused_before_any_connection(client, user, web, url):
    headers, _ = user
    body = ask(client, headers, url)
    assert body["supported"] is False and body["platform"] == "direct"
    assert body["refusal"]["code"] == "private_address"
    assert "private or local address" in body["refusal"]["message"]
    assert "Upload the file instead." in body["refusal"]["message"]
    assert web.connected == [] and web.hits == []


def test_a_public_direct_link_is_only_looked_up(client, user, web):
    headers, _ = user
    body = ask(client, headers, "https://cdn.test/dir/My%20Stream.mp4")
    assert body["supported"] is True and body["platform"] == "direct" and body["title"] == "My Stream.mp4"
    assert body["kind"] == "video" and body["duration_sec"] is None
    assert web.resolved == ["cdn.test"] and web.connected == [] and web.hits == []     # a name lookup, no request


def test_too_long_is_refused_with_the_import_message_and_keeps_the_metadata(client, user, fake_ydl):
    headers, _ = user
    fake_ydl.info = {"duration": 7 * 3600.0, "thumbnail": THUMB}
    body = ask(client, headers, TWITCH)
    assert body["supported"] is False
    assert body["refusal"] == {"code": "video_too_long", "message": "Maximum video length is 6 hours."}
    assert body["title"] == "Ranked grind: part 3 / finale!" and body["thumbnail_url"] == THUMB
    assert body["duration_sec"] == 7 * 3600.0


def test_too_short_is_refused_with_the_import_message(client, user, fake_ydl):
    headers, _ = user
    fake_ydl.info = {"duration": 3.0}           # the tests run with MIN_DURATION_SEC=5
    body = ask(client, headers, TWITCH)
    assert body["supported"] is False
    assert body["refusal"] == {"code": "video_too_short", "message": "Minimum video length is 5 seconds."}
    assert body["duration_sec"] == 3.0


def test_a_live_stream_is_refused(client, user, fake_ydl):
    headers, _ = user
    fake_ydl.info = {"is_live": True, "live_status": "is_live"}
    body = ask(client, headers, TWITCH)
    assert body["kind"] == "live" and body["supported"] is False and body["refusal"]["code"] == "live_stream"


@pytest.mark.parametrize("url, raw, code, starts", [
    ("https://kick.com/somechannel/videos/0a1b2c3d-1111-2222-3333-444455556666",
     "ERROR: [kick:vod] x: Unable to download JSON metadata: HTTP Error 403: Forbidden", "source_refused",
     "Kick refused the download."),
    ("https://youtu.be/dQw4w9WgXcQ",
     "ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies",
     "login_required", "YouTube often refuses automated downloads: upload the file instead"),
])
def test_an_extractor_failure_is_a_clean_refusal(client, user, fake_ydl, url, raw, code, starts):
    headers, _ = user
    fake_ydl.refuse_extract = raw
    body = ask(client, headers, url)
    assert body["supported"] is False and body["refusal"]["code"] == code
    assert body["refusal"]["message"].startswith(starts) and "pload the file instead" in body["refusal"]["message"]
    assert "cookie" not in body["refusal"]["message"].lower()
    assert len(fake_ydl.instances) == 1 and len(fake_ydl.instances[0].urls) == 1     # one attempt, then stop


def test_a_crash_inside_the_extractor_is_a_refusal_not_a_500(client, user, fake_ydl, monkeypatch):
    headers, _ = user
    monkeypatch.setattr(fake_ydl, "extract_info", lambda self, url, download=False: 1 / 0)
    body = ask(client, headers, TWITCH)
    assert body["refusal"] == {"code": "source_failed", "message": "Twitch could not be read. Upload the file instead."}


def test_a_site_that_does_not_answer_times_out_cleanly(client, user, fake_ydl, monkeypatch):
    headers, _ = user
    release = threading.Event()
    monkeypatch.setattr(link_preview, "LOOKUP_TIMEOUT_SEC", 0.2)
    monkeypatch.setattr(fake_ydl, "extract_info", lambda self, url, download=False: release.wait(5) and {})
    try:
        body = ask(client, headers, TWITCH)
    finally:
        release.set()
    assert body["supported"] is False and body["refusal"]["code"] == "preview_timeout"
    assert body["refusal"]["message"] == "Twitch did not answer within 0.2 seconds. Upload the file instead."


def test_answers_are_cached_per_link(client, user, fake_ydl, monkeypatch):
    headers, _ = user
    first = ask(client, headers, TWITCH)
    again = ask(client, headers, "https://twitch.tv/videos/2301234567")      # another spelling, the same link
    other_user = client.post("/v1/auth/signup", json={"email": f"u{uuid.uuid4().hex[:10]}@example.org",
                                                      "password": "correct-horse-9"})
    assert ask(client, {"Authorization": f"Bearer {other_user.json()['token']}"}, TWITCH) == first == again
    assert len(fake_ydl.instances) == 1
    # An answer that has expired is looked up again.
    monkeypatch.setattr(link_preview, "CACHE_TTL_SEC", 0)
    ask(client, headers, "https://www.twitch.tv/videos/77")
    ask(client, headers, "https://www.twitch.tv/videos/77")
    assert len(fake_ydl.instances) == 3


def test_lookups_are_rate_limited_per_account_but_cached_answers_are_not(client, user, fake_ydl):
    headers, _ = user
    for n in range(link_preview.LOOKUPS_PER_MINUTE):
        ask(client, headers, f"https://www.twitch.tv/videos/{1000 + n}")
    r = client.post("/v1/imports/preview", json={"url": "https://www.twitch.tv/videos/9999"}, headers=headers)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert len(fake_ydl.instances) == link_preview.LOOKUPS_PER_MINUTE          # the refused one made no request
    assert ask(client, headers, "https://www.twitch.tv/videos/1000")["supported"] is True    # cached: still fine
    assert ask(client, headers, "https://vimeo.com/1")["refusal"]["code"] == "unsupported_source"   # no request


def test_needs_a_login_takes_only_a_url_and_follows_the_kill_switch(client, user, monkeypatch):
    headers, _ = user
    assert client.post("/v1/imports/preview", json={"url": TWITCH}).status_code == 401
    r = client.post("/v1/imports/preview", json={"url": TWITCH, "cookies": "x"}, headers=headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "imports_enabled", False)
    r = client.post("/v1/imports/preview", json={"url": TWITCH}, headers=headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "imports_disabled"


def test_a_bad_link_is_refused_with_the_import_message(client, user):
    headers, _ = user
    body = ask(client, headers, "https://cdn.test/" + "a" * 1000 + ".mp4")
    assert body["refusal"] == {"code": "bad_url", "message": "Send one link of at most 1000 characters."}
    assert len(body["url"]) == 1000
    assert ask(client, headers, "http://www.twitch.tv/videos/1")["refusal"]["code"] == "https_only"
