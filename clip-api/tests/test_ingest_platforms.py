"""The platform downloader (yt-dlp): the exact options it is given, that nothing forbidden can be switched on from
a request or a setting, and that a refusal by the site is a clean failure. yt-dlp never reaches the network here:
either a stand-in takes its place, or a real YoutubeDL object is built and inspected without a request."""
import importlib.util
import inspect
import re
from pathlib import Path

import pytest

from app.config import Settings
from app.ingest import Refused, platforms
from app.ingest.platforms import Limits, ydl_options
from app.ingest import Span
from app.pipeline.ff import probe
from tests.ingest_support import ONE_FILE, fake_ydl  # noqa: F401

ROOMY = Limits(max_bytes=50 * 1024 ** 2, max_duration_sec=3600, timeout_sec=60)
TWITCH = "https://www.twitch.tv/videos/2301234567"

# Every option, written out. A change to app/ingest/platforms.py has to change this list too, in review.
EXPECTED = {
    # Picture and sound may be two streams; H.264 with AAC at up to 1080p first, then any codec, then any height.
    "format": ("bv*[height<=1080][vcodec^=avc1][filesize<=?1000][filesize_approx<=?1000]+ba[acodec^=mp4a]/"
               "b[height<=1080][vcodec^=avc1][filesize<=?1000][filesize_approx<=?1000]/"
               "bv*[height<=1080][filesize<=?1000][filesize_approx<=?1000]+ba/"
               "b[height<=1080][filesize<=?1000][filesize_approx<=?1000]/"
               "bv*[filesize<=?1000][filesize_approx<=?1000]+ba/"
               "b[filesize<=?1000][filesize_approx<=?1000]"),
    "allowed_extractors": ["twitch:vod", "twitch:clips", "kick:vod", "kick:clip", "youtube"],
    "noplaylist": True,
    "playlist_items": "1",
    "outtmpl": "/work/download.%(ext)s",
    "overwrites": True,
    "continuedl": False,
    "cachedir": False,
    "cookiefile": None,
    "cookiesfrombrowser": None,
    "username": None,
    "password": None,
    "videopassword": None,
    "usenetrc": False,
    "client_certificate": None,
    "proxy": "",
    "geo_bypass": False,
    "impersonate": None,
    "extractor_args": {},
    "js_runtimes": {},
    "remote_components": [],
    "allow_unplayable_formats": False,
    "nocheckcertificate": False,
    "http_headers": {"User-Agent": "ClutchClips-LinkImport/1.0"},
    "retries": 3,
    "fragment_retries": 3,
    "extractor_retries": 1,
    "file_access_retries": 1,
    "socket_timeout": 30,
    "concurrent_fragment_downloads": 1,
    "ignoreerrors": False,
    "ffmpeg_location": "/nonexistent/ffmpeg-is-not-for-yt-dlp",
    "fixup": "never",
    "postprocessors": [],
    "hls_prefer_native": True,
    "external_downloader": None,
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "color": "never",
}

# yt-dlp options that are a login, an identity, or a way around a block. None may ever be set.
FORBIDDEN = (
    "cookiefile", "cookiesfrombrowser", "username", "password", "videopassword", "twofactor", "usenetrc",
    "netrc_location", "netrc_cmd", "ap_mso", "ap_username", "ap_password", "client_certificate",
    "client_certificate_key", "client_certificate_password",
    "proxy", "geo_verification_proxy", "cn_verification_proxy", "source_address",
    "geo_bypass", "geo_bypass_country", "geo_bypass_ip_block",
    "impersonate", "extractor_args", "js_runtimes", "remote_components",
    "sleep_interval", "max_sleep_interval", "sleep_interval_requests", "sleep_interval_subtitles",
    "ratelimit", "throttledratelimit", "retry_sleep_functions", "wait_for_video",
    "allow_unplayable_formats", "nocheckcertificate", "legacyserverconnect", "prefer_insecure",
    "enable_file_urls", "external_downloader", "external_downloader_args", "postprocessors", "mark_watched",
    "age_limit", "live_from_start", "compat_opts", "plugin_dirs",
)


def options_without_logger(options: dict) -> dict:
    return {k: v for k, v in options.items() if k != "logger"}


def test_the_exact_options_yt_dlp_is_given():
    options = ydl_options(Path("/work"), 1000)
    assert options_without_logger(options) == EXPECTED
    assert isinstance(options["logger"], platforms._Quiet)


def test_nothing_forbidden_is_switched_on():
    options = ydl_options(Path("/work"), 1000)
    for name in FORBIDDEN:
        assert not options.get(name), f"{name} is set"
    assert options["proxy"] == ""                   # not None: None would let HTTPS_PROXY in; "" is a direct connection
    assert options["geo_bypass"] is False           # yt-dlp's own default is True
    assert options["js_runtimes"] == {}             # yt-dlp's own default enables deno
    agent = options["http_headers"]["User-Agent"].lower()
    assert "mozilla" not in agent and "chrome" not in agent and "safari" not in agent


def test_options_take_nothing_from_a_request_or_a_setting(monkeypatch):
    # The only inputs are a folder and the size cap.
    assert list(inspect.signature(ydl_options).parameters) == ["dest_dir", "max_bytes"]
    # Environment variables that could carry a proxy, cookies or a login change nothing.
    before = options_without_logger(ydl_options(Path("/work"), 1000))
    for name, value in {"HTTPS_PROXY": "http://proxy.invalid:3128", "HTTP_PROXY": "http://proxy.invalid:3128",
                        "ALL_PROXY": "socks5://proxy.invalid:1080", "IMPORT_PROXY": "http://proxy.invalid:3128",
                        "IMPORT_COOKIES": "/tmp/cookies.txt", "IMPORT_COOKIES_FROM_BROWSER": "chrome",
                        "IMPORT_USERNAME": "someone", "IMPORT_PASSWORD": "secret", "IMPORT_IMPERSONATE": "chrome",
                        "IMPORT_GEO_BYPASS": "true", "IMPORT_USER_AGENT": "Mozilla/5.0",
                        "YTDLP_COOKIES": "/tmp/cookies.txt", "IMPORT_EXTRACTOR_ARGS": "youtube:player_client=tv"}.items():
        monkeypatch.setenv(name, value)
    assert options_without_logger(ydl_options(Path("/work"), 1000)) == before
    # Settings have an on/off switch and three caps for imports, and nothing else.
    fields = sorted(name for name in Settings.model_fields if name.startswith("import"))
    assert fields == ["import_max_bytes", "import_max_duration_sec", "import_timeout_sec", "imports_enabled"]
    # The module never reads settings or the environment for its options.
    source = inspect.getsource(platforms)
    assert "get_settings" not in source and "getenv" not in source
    assert re.findall(r"os\.environ\[[^\]]+\]", source) == ['os.environ["YTDLP_NO_PLUGINS"]']


def test_a_real_yt_dlp_object_built_from_the_options(monkeypatch, tmp_path):
    """Builds yt-dlp's own YoutubeDL (no request is made) and reads back what it will do."""
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    ydl = platforms._new_ydl(tmp_path, ROOMY)
    try:
        assert ydl.proxies == {"all": "__noproxy__"}                        # proxy variables ignored
        assert len(ydl.cookiejar) == 0                                      # no cookies loaded from anywhere
        assert sorted(ie.IE_NAME for ie in ydl._ies.values()) == sorted(platforms.EXTRACTORS)   # nothing else can run
        assert list(ydl._get_available_impersonate_targets()) == []         # nothing to impersonate with
        assert ydl.params["js_runtimes"] == {} and ydl.params["remote_components"] == set()
        assert ydl.params.get("geo_bypass") is False
        with pytest.raises(platforms.DownloadError):                        # a link no allowed extractor takes
            ydl.extract_info("https://vimeo.com/123456", download=False)
    finally:
        ydl.close()


def test_impersonation_cannot_work_because_its_library_is_not_installed():
    assert importlib.util.find_spec("curl_cffi") is None
    requirements = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    lines = [line.split("#")[0].strip() for line in requirements.splitlines()]
    pins = [line for line in lines if line.lower().startswith("yt-dlp") or line.lower().startswith("yt_dlp")]
    assert len(pins) == 1 and re.fullmatch(r"yt-dlp==\d{4}\.\d{1,2}\.\d{1,2}", pins[0]), pins   # pinned, no extras
    assert not any("curl" in line.lower() or "impersonate" in line.lower() for line in lines)
    import yt_dlp.version
    assert pins[0] == f"yt-dlp=={yt_dlp.version.__version__}"
    assert platforms.os.environ.get("YTDLP_NO_PLUGINS") == "1"


def test_download_through_the_stand_in(fake_ydl, tmp_path, video):
    seen = []
    stages = []
    got = platforms.download("twitch", TWITCH, tmp_path, ROOMY, lambda done, total: seen.append(done),
                             on_stage=stages.append)
    assert got.path.read_bytes() == video.read_bytes() and got.path.suffix == ".mp4"
    assert got.filename == "Ranked grind_ part 3 _ finale.mp4"
    assert got.span.whole and got.partial is False and stages == ["downloading", "merging"]
    ydl = fake_ydl.instances[0]
    assert len(fake_ydl.instances) == 1 and ydl.urls == [TWITCH]
    assert [(name, info["format_id"]) for name, info in ydl.fetched] == [("download.0.mp4", "source")]
    hooks = ydl.given.pop("progress_hooks")
    assert len(hooks) == 1 and seen == [video.stat().st_size] * 2
    expected = {**EXPECTED, "outtmpl": str(tmp_path / "download.%(ext)s"),
                "format": EXPECTED["format"].replace("1000]", f"{ROOMY.max_bytes}]")}
    assert options_without_logger(ydl.given) == expected


SIGN_IN = ("ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you’re not a bot. Use --cookies-from-browser or "
           "--cookies for the authentication. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ for how to pass cookies")


@pytest.mark.parametrize("platform, raw, code", [
    ("youtube", SIGN_IN, "source_refused"),         # a bot check, not a private video: the site refused us
    ("youtube", "ERROR: [youtube] x: Requested format is not available", "no_format"),
    ("youtube", "ERROR: [youtube] x: Private video. Sign in if you've been granted access to this video",
     "private_video"),
    ("youtube", "ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate for some users.",
     "age_restricted"),
    ("youtube", "ERROR: [youtube] x: Join this channel to get access to members-only content like this video, and "
                "other exclusive perks.", "members_only"),
    ("youtube", "ERROR: [youtube] x: This video is available to this channel's members on level: Gold (or any "
                "higher level). Join this channel to get access", "members_only"),
    ("youtube", "ERROR: [youtube] x: Video unavailable. This video has been removed by the uploader", "not_found"),
    ("youtube", "ERROR: [youtube] x: This video is no longer available because the YouTube account associated "
                "with this video has been terminated.", "not_found"),
    ("youtube", "ERROR: [youtube] x: This live event will begin in 40 hours.", "upcoming"),
    ("youtube", "ERROR: [youtube] x: Premieres in 3 days", "upcoming"),
    ("youtube", "ERROR: [youtube] x: This video requires payment to watch", "source_failed"),
    ("twitch", "ERROR: [twitch:vod] 1: Video 1 does not exist", "expired"),
    ("kick", "ERROR: [kick:vod] x: Unable to download JSON metadata: HTTP Error 404: Not Found", "expired"),
    ("twitch", "ERROR: [twitch:vod] 1: This video is only available for subscribers", "members_only"),
    ("twitch", "ERROR: [twitch:vod] 1: Sign in to view this video", "login_required"),
    ("kick", "ERROR: [kick:vod] x: Unable to download JSON metadata: HTTP Error 403: Forbidden (caused by "
             "<HTTPError 403: Forbidden>)", "source_refused"),
    ("kick", "ERROR: [kick:vod] x: This request requires impersonation, but no impersonate target is available",
     "source_refused"),
    ("twitch", "ERROR: [twitch:vod] 1: This video is DRM protected", "drm_protected"),
    ("youtube", "ERROR: [youtube] x: The uploader has not made this video available in your country", "geo_blocked"),
    ("twitch", "ERROR: something nobody has seen before", "source_failed"),
])
def test_a_refusal_is_a_clean_failure_that_says_upload_instead(fake_ydl, tmp_path, platform, raw, code):
    fake_ydl.refuse_extract = raw
    with pytest.raises(Refused) as e:
        platforms.download(platform, TWITCH, tmp_path, ROOMY)
    assert e.value.code == code
    message = e.value.message
    if platform == "youtube":
        assert message.startswith("YouTube often refuses automated downloads: upload the file instead")
    else:
        assert message.endswith("Upload the file instead.")
    for hint in ("cookie", "--", "github.com", "impersonat", "proxy", "vpn"):   # never a hint at a way around it
        assert hint not in message.lower()
    assert "upload" in message.lower()                                          # always: what to do instead
    assert list(tmp_path.iterdir()) == []
    assert len(fake_ydl.instances) == 1 and len(fake_ydl.instances[0].urls) == 1    # asked once; no second approach


def test_a_refusal_during_the_download_is_also_clean(fake_ydl, tmp_path):
    fake_ydl.refuse_download = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
    with pytest.raises(Refused) as e:
        platforms.download("twitch", TWITCH, tmp_path, ROOMY)
    assert e.value.code == "source_refused" and e.value.message.endswith("Upload the file instead.")


@pytest.mark.parametrize("info, code", [
    ({"is_live": True}, "live_stream"),
    ({"live_status": "post_live"}, "live_stream"),
    ({"live_status": "is_upcoming"}, "upcoming"),
    ({"duration": 3601.0}, "video_too_long"),
    ({"formats": [{**ONE_FILE, "filesize_approx": 50 * 1024 ** 2 + 1}]}, "file_too_large"),
    ({"formats": [{**ONE_FILE, "vcodec": "none"}]}, "no_format"),         # sound only: nothing with a picture
    ({"formats": []}, "no_format"),
    ({"formats": [{**ONE_FILE, "has_drm": True}]}, "drm_protected"),      # every stream is DRM: never touched
    ({"formats": [], "_has_drm": True}, "drm_protected"),
    ({"_type": "playlist"}, "unsupported_link"),
])
def test_refused_from_the_metadata_before_anything_is_downloaded(fake_ydl, tmp_path, info, code):
    fake_ydl.info = info
    fake_ydl.refuse_download = "must not be reached"
    with pytest.raises(Refused) as e:
        platforms.download("twitch", TWITCH, tmp_path, ROOMY)
    assert e.value.code == code


def test_size_and_time_caps_stop_a_download_in_progress(fake_ydl, tmp_path):
    fake_ydl.report_bytes = ROOMY.max_bytes + 1
    with pytest.raises(Refused) as e:
        platforms.download("twitch", TWITCH, tmp_path, ROOMY)
    assert e.value.code == "file_too_large"
    fake_ydl.report_bytes = None
    with pytest.raises(Refused) as e:
        platforms.download("twitch", TWITCH, tmp_path, Limits(ROOMY.max_bytes, 3600, timeout_sec=-1))
    assert e.value.code == "import_timeout"


def test_a_transport_stream_is_repackaged_as_mp4_with_our_own_guarded_ffmpeg(tmp_path, video):
    """HLS downloads are MPEG-TS under an .mp4 name. The repackaging is the one ffmpeg call in the import, and it
    is ours: local file in, protocol whitelist on, a timeout."""
    import subprocess
    ts = tmp_path / "download.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-c", "copy", "-f", "mpegts", str(ts)],
                   check=True)
    calls = []
    real_run = platforms.run

    def spy(cmd, deadline=None, cap=None, check=True):
        calls.append([str(c) for c in cmd])
        assert deadline is not None and cap is not None
        return real_run(cmd, deadline, cap, check)

    platforms.run = spy
    try:
        out = platforms.as_video_file(ts, platforms.Deadline(120))
    finally:
        platforms.run = real_run
    assert out.name == "video.mp4" and not ts.exists()
    from app.pipeline.ff import probe
    info = probe(out)
    assert 39 <= info.duration <= 41 and info.has_audio and (info.width, info.height) == (640, 360)
    assert [c[0] for c in calls] == ["ffprobe", "ffmpeg"]
    for cmd in calls:
        i = cmd.index("-protocol_whitelist")
        assert cmd[i + 1] == "file,pipe"
        assert not any(arg.startswith(("http:", "https:")) for arg in cmd)
