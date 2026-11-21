"""The allow-list: which links are imported from, their canonical form, and every reason a link is refused."""
import pytest

from app.ingest import Refused
from app.ingest.sources import DIRECT, PLATFORM, SOURCES, VIDEO_EXT, canonical, classify
from app.routes_media import ALLOWED_EXT

UUID = "0a1b2c3d-1111-2222-3333-444455556666"


@pytest.mark.parametrize("url, platform, downloader, canon", [
    # Twitch: VODs and clips, in every spelling, are one canonical link each
    ("https://www.twitch.tv/videos/2301234567", "twitch", PLATFORM, "https://www.twitch.tv/videos/2301234567"),
    ("https://twitch.tv/videos/2301234567?t=1h2m3s", "twitch", PLATFORM, "https://www.twitch.tv/videos/2301234567"),
    ("https://m.twitch.tv/somechannel/v/2301234567", "twitch", PLATFORM, "https://www.twitch.tv/videos/2301234567"),
    ("https://clips.twitch.tv/FaintLightGull-abc_123", "twitch", PLATFORM, "https://clips.twitch.tv/FaintLightGull-abc_123"),
    ("https://www.twitch.tv/somechannel/clip/FaintLightGull-abc_123?filter=clips", "twitch", PLATFORM,
     "https://clips.twitch.tv/FaintLightGull-abc_123"),
    # Kick
    (f"https://kick.com/somechannel/videos/{UUID}", "kick", PLATFORM, f"https://kick.com/somechannel/videos/{UUID}"),
    (f"https://www.kick.com/somechannel/videos/{UUID}?t=10", "kick", PLATFORM, f"https://kick.com/somechannel/videos/{UUID}"),
    ("https://kick.com/somechannel/clips/clip_01ABCDEF", "kick", PLATFORM, "https://kick.com/somechannel/clips/clip_01ABCDEF"),
    ("https://kick.com/somechannel?clip=clip_01ABCDEF", "kick", PLATFORM, "https://kick.com/somechannel/clips/clip_01ABCDEF"),
    # YouTube
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLx&t=42", "youtube", PLATFORM, "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=tracking", "youtube", PLATFORM, "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "youtube", PLATFORM, "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    # Google Drive and Dropbox share links go to the direct downloader, under their own names
    ("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view?usp=sharing", "gdrive", DIRECT,
     "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view"),
    ("https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUv", "gdrive", DIRECT,
     "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view"),
    ("https://www.dropbox.com/scl/fi/abc123/stream.mp4?rlkey=k3y&st=zz&dl=0", "dropbox", DIRECT,
     "https://www.dropbox.com/scl/fi/abc123/stream.mp4?rlkey=k3y"),
    ("https://dropbox.com/s/abc123/stream.mov?dl=0", "dropbox", DIRECT, "https://www.dropbox.com/s/abc123/stream.mov"),
    # A direct link: any https host, a path that ends in a video file name
    ("https://cdn.example.com/vods/Night%20Stream.MP4?token=abc", "direct", DIRECT,
     "https://cdn.example.com/vods/Night%20Stream.MP4?token=abc"),
    ("https://CDN.Example.com:8443/a.webm#t=5", "direct", DIRECT, "https://cdn.example.com:8443/a.webm"),
])
def test_allowed_links_and_their_canonical_form(url, platform, downloader, canon):
    source = classify(url)
    assert (source.platform, source.downloader, source.url) == (platform, downloader, canon)
    assert canonical(url) == canon and canonical(canon) == canon        # canonical is stable


def test_drive_and_dropbox_download_urls():
    drive = classify("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view?usp=sharing")
    assert drive.fetch_url == ("https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOpQrStUv"
                               "&export=download&confirm=t")
    dropbox = classify("https://www.dropbox.com/scl/fi/abc123/stream.mp4?rlkey=k3y&dl=0")
    assert dropbox.fetch_url == "https://www.dropbox.com/scl/fi/abc123/stream.mp4?rlkey=k3y&dl=1"


@pytest.mark.parametrize("url, code", [
    ("http://cdn.example.com/a.mp4", "https_only"),
    ("ftp://cdn.example.com/a.mp4", "https_only"),
    ("file:///etc/passwd.mp4", "https_only"),
    ("cdn.example.com/a.mp4", "https_only"),
    ("https://user:pass@cdn.example.com/a.mp4", "credentials_in_url"),
    ("https://token@www.twitch.tv/videos/2301234567", "credentials_in_url"),
    ("https://vimeo.com/123456", "unsupported_source"),                  # not on the allow-list
    ("https://www.tiktok.com/@someone/video/123", "unsupported_source"),
    ("https://example.com/page.html", "unsupported_source"),
    ("https://example.com/", "unsupported_source"),
    ("https://nottwitch.tv/videos/2301234567", "unsupported_source"),    # a look-alike host is not the host
    ("https://www.twitch.tv.evil.example/videos/2301234567", "unsupported_source"),
    ("https://www.twitch.tv/somechannel", "live_channel"),               # a channel page: live, never read
    ("https://www.twitch.tv/somechannel/videos", "unsupported_link"),
    ("https://www.twitch.tv/collections/abcDEF", "unsupported_link"),
    ("https://kick.com/somechannel", "live_channel"),
    ("https://kick.com/somechannel/videos", "unsupported_link"),
    ("https://www.youtube.com/playlist?list=PL123", "unsupported_link"),
    ("https://www.youtube.com/@somechannel", "unsupported_link"),
    ("https://www.youtube.com/watch?v=short", "unsupported_link"),
    ("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUv", "unsupported_link"),
    ("https://www.dropbox.com/sh/abc/def", "unsupported_link"),
    ("https://www.dropbox.com/scl/fo/abc/def?rlkey=x", "unsupported_link"),
    ("https://www.twitch.tv:8443/videos/2301234567", "unsupported_source"),   # a platform on an odd port is not it
    ("", "bad_url"),
    ("https://cdn.example.com/a b.mp4", "bad_url"),
    ("https://cdn.example.com/" + "a" * 1000 + ".mp4", "bad_url"),
    ("https://[bad/a.mp4", "bad_url"),
])
def test_refused_links(url, code):
    with pytest.raises(Refused) as e:
        classify(url)
    assert e.value.code == code, e.value.message
    assert canonical(url) is None


def test_every_refusal_says_what_to_do():
    for url in ("https://vimeo.com/1", "http://x.example/a.mp4", "https://u:p@x.example/a.mp4"):
        with pytest.raises(Refused) as e:
            classify(url)
        assert "Upload the file instead." in e.value.message


def test_file_types_are_the_upload_file_types():
    assert VIDEO_EXT == ALLOWED_EXT


def test_listed_sources_are_in_the_agreed_order_and_all_classify():
    assert [s["platform"] for s in SOURCES] == ["twitch", "kick", "direct", "gdrive", "dropbox", "youtube"]
    for s in SOURCES:
        example = (s["example"].replace("FILE_ID", "1AbCdEfGhIjKlMnOpQrStUv").replace("VIDEO_ID", "dQw4w9WgXcQ"))
        assert classify(example).platform == s["platform"]
    youtube = SOURCES[-1]
    assert youtube["note"] == "YouTube often refuses automated downloads: upload the file instead."
