"""What a link import downloads: which streams it picks, picture and sound served as two streams, a chosen time
range, and a recording that is still in progress. yt-dlp's own format selector runs on the stream lists below (the
shapes YouTube and Twitch really answer with, read on 2026-11-18); its three network seams are a stand-in, so
nothing here reaches the network. Joining and cutting is our own ffmpeg, on real local files."""
import subprocess

import pytest

from app.ingest import Refused, Span, platforms
from app.ingest.platforms import Limits
from app.pipeline.ff import probe
from tests.ingest_support import fake_ydl  # noqa: F401

ROOMY = Limits(max_bytes=500 * 1024 ** 2, max_duration_sec=6 * 3600, timeout_sec=60, min_duration_sec=5)
YOUTUBE = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
TWITCH = "https://www.twitch.tv/videos/2301234567"
MB = 1024 ** 2


def stream(format_id, height=None, vcodec="none", acodec="none", ext="mp4", size=None, protocol="https", **more):
    return {"format_id": format_id, "url": f"https://media.test/{format_id}", "ext": ext, "height": height,
            "vcodec": vcodec, "acodec": acodec, "protocol": protocol,
            **({"filesize": size} if size else {}), **more}


# YouTube: no stream has both picture and sound. This is every video above 360p, and most below it.
YOUTUBE_SPLIT = [
    stream("401", 2160, "av01.0.12M.08", size=700 * MB),
    stream("299", 1080, "avc1.64002a", size=250 * MB),
    stream("303", 1080, "vp9", ext="webm", size=160 * MB),
    stream("399", 1080, "av01.0.09M.08", size=120 * MB),
    stream("298", 720, "avc1.4d4020", size=150 * MB),
    stream("135", 480, "avc1.4d401f", size=28 * MB),
    stream("140", acodec="mp4a.40.2", ext="m4a", size=10 * MB),
    stream("251", acodec="opus", ext="webm", size=10 * MB),
]
# Twitch: every quality has picture and sound, as a segment list, with a bitrate but no size.
TWITCH_VOD = [
    stream("1080p60", 1080, "avc1.4D402A", "mp4a.40.2", protocol="m3u8_native", tbr=6000),
    stream("720p60", 720, "avc1.4D401F", "mp4a.40.2", protocol="m3u8_native", tbr=3000),
    stream("360p", 360, "avc1.4D401E", "mp4a.40.2", protocol="m3u8_native", tbr=700),
    stream("Audio Only", None, "none", "mp4a.40.2", protocol="m3u8_native", tbr=160),
    stream("sb0", 124, "none", "none", ext="mhtml", protocol="mhtml"),
]


def segments(count: int, seconds: float = 10.0, ended: bool = True, extra: str = "") -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:10", "#EXT-X-PLAYLIST-TYPE:EVENT", extra]
    for n in range(count):
        lines += [f"#EXTINF:{seconds:.3f},", f"{n}.ts"]
    return "\n".join(line for line in lines + (["#EXT-X-ENDLIST"] if ended else []) if line)


@pytest.fixture(scope="module")
def pieces(video, tmp_path_factory):
    """The test video (40 s) as a picture-only file, a sound-only file, a copy with a key frame every second
    (as streams have: a copied cut starts on a key frame), and seconds 10 to 30 of that as a transport stream
    (what the segments 1 and 2 of a 10-second segment list hold)."""
    folder = tmp_path_factory.mktemp("pieces")
    def make(name, *args):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args, str(folder / name)], check=True)
        return folder / name
    keyed = make("keyed.mp4", "-i", str(video), "-c:v", "libx264", "-preset", "ultrafast", "-g", "15", "-b:v",
                 "300k", "-c:a", "copy")
    return {"picture": make("picture.mp4", "-i", str(video), "-an", "-c", "copy"),
            "sound": make("sound.m4a", "-i", str(video), "-vn", "-c", "copy"),
            "keyed": keyed,
            "middle": make("middle.ts", "-ss", "10", "-t", "20", "-i", str(keyed), "-c", "copy", "-f", "mpegts")}


def chosen(fake_ydl, formats, limits=ROOMY, span=Span(), duration=600.0):
    fake_ydl.formats, fake_ydl.info = formats, {"duration": duration}
    ydl = platforms._new_ydl(platforms.NOWHERE, limits)
    info, span = platforms.look("youtube", YOUTUBE, platforms.NOWHERE, limits, ydl, span)
    _done, streams, cut = platforms.choose(ydl, "youtube", info, limits, span)
    return [f["format_id"] for f in streams], cut is not None


# ---- owner report 1: YouTube ------------------------------------------------------------------------------------

def test_the_old_selector_refused_every_video_that_has_no_single_file(fake_ydl):
    """The reported failure, reproduced: the importer asked yt-dlp for `b`, one file with picture and sound.
    YouTube lists none, so yt-dlp answers "Requested format is not available", and because the format was chosen
    while reading the metadata, the title and the thumbnail were lost with it."""
    fake_ydl.formats = YOUTUBE_SPLIT
    ydl = platforms._new_ydl(platforms.NOWHERE, ROOMY)
    info = platforms.metadata("youtube", YOUTUBE, ydl)
    old = f"b[height<=?1080][filesize<=?{ROOMY.max_bytes}][filesize_approx<=?{ROOMY.max_bytes}]"
    assert platforms._select(ydl, info, old) is None                 # what the old code turned into `no_format`
    assert platforms._select(ydl, info, platforms.format_spec(ROOMY.max_bytes)) is not None


def test_metadata_never_depends_on_the_formats(fake_ydl):
    """A video we cannot download (sound only here) still has its title, channel, length and thumbnail."""
    fake_ydl.formats = [stream("140", acodec="mp4a.40.2", ext="m4a")]
    fake_ydl.info = {"uploader": "Someone", "thumbnail": "https://i.ytimg.com/vi/x/hq.jpg", "duration": 300.0}
    info, refusal = platforms.preview("youtube", YOUTUBE, ROOMY, 10)
    assert refusal is None and info["title"] and info["uploader"] == "Someone" and info["duration"] == 300.0
    assert info["thumbnail"].endswith("hq.jpg")
    with pytest.raises(Refused) as e:                                 # the import says why, when it is asked for
        platforms.download("youtube", YOUTUBE, platforms.NOWHERE, ROOMY)
    assert e.value.code == "no_format" and "upload the file instead" in e.value.message.lower()


@pytest.mark.parametrize("formats, limits, picked", [
    (YOUTUBE_SPLIT, ROOMY, ["299", "140"]),                                   # H.264 + AAC at 1080p, not 4K AV1
    (YOUTUBE_SPLIT, Limits(200 * MB, 21600, 60), ["298", "140"]),             # 1080p is over the cap: 720p
    (YOUTUBE_SPLIT, Limits(20 * MB, 21600, 60), None),                        # nothing fits: refused
    ([f for f in YOUTUBE_SPLIT if f["format_id"] in ("303", "399", "251")], ROOMY, ["399", "251"]),   # no H.264: AV1
    ([f for f in YOUTUBE_SPLIT if f["format_id"] in ("303", "251")], ROOMY, ["303", "251"]),          # or VP9
    ([f for f in YOUTUBE_SPLIT if f["format_id"] in ("401", "140")], Limits(800 * MB, 21600, 60), ["401", "140"]),
    (YOUTUBE_SPLIT + [stream("18", 360, "avc1.42001E", "mp4a.40.2", size=30 * MB)], ROOMY, ["299", "140"]),
    (TWITCH_VOD, ROOMY, ["1080p60"]),                                         # already one stream: nothing to join
    (TWITCH_VOD, Limits(300 * MB, 21600, 60), ["720p60"]),                    # 6000 kbit/s x 600 s = 450 MB: too big
    ([stream("1080", 1080, None, None), stream("360", 360, None, None)], ROOMY, ["1080"]),   # a Twitch clip
])
def test_which_streams_are_picked(fake_ydl, formats, limits, picked):
    if picked is None:
        with pytest.raises(Refused) as e:
            chosen(fake_ydl, formats, limits)
        assert e.value.code == "file_too_large" and "shorter range" in e.value.message
    else:
        assert chosen(fake_ydl, formats, limits) == (picked, False)


def test_picture_and_sound_as_two_streams_are_joined_by_our_own_guarded_ffmpeg(fake_ydl, tmp_path, pieces):
    fake_ydl.formats = YOUTUBE_SPLIT
    fake_ydl.files = {"299": pieces["picture"], "140": pieces["sound"]}
    calls, real_run, progress, stages = [], platforms.run, [], []

    def spy(cmd, deadline=None, cap=None, check=True):
        calls.append([str(c) for c in cmd])
        assert deadline is not None and cap is not None                  # every call has a timeout
        return real_run(cmd, deadline, cap, check)

    platforms.run = spy
    try:
        got = platforms.download("youtube", YOUTUBE, tmp_path, ROOMY, lambda d, t: progress.append((d, t)),
                                 on_stage=stages.append)
    finally:
        platforms.run = real_run
    info = probe(got.path)
    assert got.path.name == "video.mp4" and 39 <= info.duration <= 41 and info.has_audio
    assert (info.width, info.height) == (640, 360)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["video.mp4"]   # the two downloads are gone
    ydl = fake_ydl.instances[0]
    assert [(name, f["format_id"]) for name, f in ydl.fetched] == [("download.0.mp4", "299"), ("download.1.m4a", "140")]
    assert ydl.given["ffmpeg_location"] == platforms.NO_FFMPEG           # yt-dlp itself still runs no program
    assert [c[0] for c in calls] == ["ffmpeg"] and calls[0].count("-protocol_whitelist") == 2
    assert not any(arg.startswith(("http:", "https:")) for arg in calls[0])
    assert "-c" in calls[0] and calls[0][calls[0].index("-c") + 1] == "copy"     # joined, never re-encoded
    # Progress counts both streams: it never goes backwards and ends at the bytes of both, of the size expected.
    done = [d for d, _ in progress]
    assert done == sorted(done) and done[-1] == pieces["picture"].stat().st_size + pieces["sound"].stat().st_size
    assert {t for _, t in progress} == {260 * MB} and stages == ["downloading", "merging"]


def test_streams_mp4_cannot_hold_are_joined_as_mkv(fake_ydl, tmp_path, pieces):
    webm = tmp_path / "picture.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(pieces["picture"]), "-t", "6", "-c:v", "libvpx",
                    "-b:v", "200k", "-deadline", "realtime", str(webm)], check=True)
    opus = tmp_path / "sound.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(pieces["sound"]), "-t", "6", "-c:a", "libopus",
                    str(opus)], check=True)
    fake_ydl.formats = [f for f in YOUTUBE_SPLIT if f["format_id"] in ("303", "251")]
    fake_ydl.files = {"303": webm, "251": opus}
    out = tmp_path / "work"
    out.mkdir()
    got = platforms.download("youtube", YOUTUBE, out, ROOMY)
    info = probe(got.path)
    assert got.path.name == "video.mkv" and 5 <= info.duration <= 7 and info.has_audio


def test_a_join_that_fails_is_a_clean_refusal(fake_ydl, tmp_path, pieces):
    garbage = tmp_path / "garbage.m4a"
    garbage.write_bytes(b"not sound at all " * 500)
    fake_ydl.formats, fake_ydl.files = YOUTUBE_SPLIT, {"299": pieces["picture"], "140": garbage}
    out = tmp_path / "work"
    out.mkdir()
    with pytest.raises(Refused) as e:
        platforms.download("youtube", YOUTUBE, out, ROOMY)
    assert e.value.code == "unsupported_media" and e.value.message.endswith("Upload the file instead.")
    assert not (out / "video.mp4").exists()


# ---- a time range -----------------------------------------------------------------------------------------------

def test_a_range_of_a_segment_list_downloads_only_its_segments(fake_ydl, tmp_path, pieces):
    fake_ydl.formats, fake_ydl.info = TWITCH_VOD, {"duration": 40.0}
    fake_ydl.playlists = {f["url"]: segments(4) for f in TWITCH_VOD}
    fake_ydl.files = {"360p": pieces["middle"]}
    progress = []
    got = platforms.download("twitch", TWITCH, tmp_path, Limits(5 * MB, 21600, 60, 5), lambda d, t: progress.append(t),
                             Span(12.0, 27.0))
    ydl = fake_ydl.instances[0]
    (name, asked), = ydl.fetched
    # 5 MB for 15 of 40 seconds allows a stream of up to 13.3 MB in all: 360p (3.5 MB), not 720p (15 MB).
    assert asked["format_id"] == "360p" and asked["protocol"] == "http_dash_segments" and name == "download.0.ts"
    assert [f["url"] for f in asked["fragments"]] == ["https://media.test/1.ts", "https://media.test/2.ts"]
    assert got.partial is True and got.span == Span(12.0, 27.0) and got.path.name == "video.mp4"
    info = probe(got.path)
    assert 14 <= info.duration <= 17.5 and info.has_audio          # 15 s, from the key frame before second 12
    assert progress[0] == int(700_000 / 8 * 40 * 15 / 40)           # expected bytes: the range's share


def test_a_range_of_a_plain_file_downloads_it_all_and_cuts_it(fake_ydl, tmp_path, pieces):
    """A Twitch clip, or a YouTube video without a segment list: the site serves one file, so the whole file is
    fetched and the range is cut from it with our ffmpeg."""
    fake_ydl.info, fake_ydl.video = {"duration": 40.0}, pieces["keyed"]
    got = platforms.download("twitch", TWITCH, tmp_path, ROOMY, span=Span(10.0, 25.0))
    assert got.partial is False and got.span == Span(10.0, 25.0)
    assert fake_ydl.instances[0].fetched[0][1]["protocol"] == "https"
    assert 14 <= probe(got.path).duration <= 17.5 and sorted(p.name for p in tmp_path.iterdir()) == ["video.mp4"]


@pytest.mark.parametrize("extra", ['#EXT-X-KEY:METHOD=AES-128,URI="https://media.test/key"', "#EXT-X-BYTERANGE:100@0"])
def test_a_segment_list_we_do_not_handle_falls_back_to_the_whole_video(fake_ydl, tmp_path, extra, pieces):
    fake_ydl.formats, fake_ydl.info, fake_ydl.video = TWITCH_VOD, {"duration": 40.0}, pieces["keyed"]
    fake_ydl.playlists = {f["url"]: segments(4, extra=extra) for f in TWITCH_VOD}
    got = platforms.download("twitch", TWITCH, tmp_path, ROOMY, span=Span(10.0, 25.0))
    assert got.partial is False and fake_ydl.instances[0].fetched[0][1]["protocol"] == "m3u8_native"
    assert 14 <= probe(got.path).duration <= 17.5


@pytest.mark.parametrize("span, code", [
    (Span(50.0, 60.0), "bad_range"),            # starts after the end
    (Span(0.0, 45.0), "bad_range"),             # ends well past the end
    (Span(10.0, 12.0), "video_too_short"),
    (Span(0.0, 3700.0), "video_too_long"),      # of a 4000 s video, with a 1 hour limit
])
def test_a_range_that_does_not_fit_is_refused_before_anything_is_downloaded(fake_ydl, tmp_path, span, code):
    fake_ydl.info = {"duration": 4000.0 if code == "video_too_long" else 40.0}
    fake_ydl.refuse_download = "must not be reached"
    with pytest.raises(Refused) as e:
        platforms.download("twitch", TWITCH, tmp_path, Limits(50 * MB, 3600, 60, 5), span=span)
    assert e.value.code == code and fake_ydl.instances[0].fetched == []


def test_a_video_longer_than_the_limit_can_be_imported_one_range_at_a_time(fake_ydl, tmp_path, pieces):
    fake_ydl.formats, fake_ydl.info = TWITCH_VOD, {"duration": 40_000.0}            # 11 hours
    fake_ydl.playlists = {f["url"]: segments(4000) for f in TWITCH_VOD}
    fake_ydl.files = {"1080p60": pieces["middle"]}
    with pytest.raises(Refused) as e:
        platforms.download("twitch", TWITCH, tmp_path, ROOMY)
    assert e.value.code == "video_too_long" and "shorter range" in e.value.message
    got = platforms.download("twitch", TWITCH, tmp_path, ROOMY, span=Span(30_000.0, 30_020.0))
    assert got.partial and len(fake_ydl.instances[-1].fetched[0][1]["fragments"]) == 2
    assert fake_ydl.instances[-1].fetched[0][1]["fragments"][0]["url"] == "https://media.test/3000.ts"


def test_a_range_to_the_end_of_a_finished_video_is_the_rest_of_it(fake_ydl, tmp_path, pieces):
    fake_ydl.info, fake_ydl.video = {"duration": 40.0}, pieces["keyed"]
    got = platforms.download("twitch", TWITCH, tmp_path, ROOMY, span=Span(15.0, 40.5))
    assert got.span == Span(15.0, None) and 24 <= probe(got.path).duration <= 27.5


def test_segment_lists():
    plain = platforms.read_playlist(segments(3, 10.0), "https://cdn.test/a/index.m3u8")
    assert plain.plain and plain.ended and plain.seconds == 30.0 and plain.init is None
    assert plain.segments == [(0.0, 10.0, "https://cdn.test/a/0.ts"), (10.0, 10.0, "https://cdn.test/a/1.ts"),
                              (20.0, 10.0, "https://cdn.test/a/2.ts")]
    growing = platforms.read_playlist(segments(2, ended=False, extra='#EXT-X-MAP:URI="init-0.mp4"'), "https://cdn.test/a/i.m3u8")
    assert growing.plain and not growing.ended and growing.init == "https://cdn.test/a/init-0.mp4"
    master = platforms.read_playlist("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nlow.m3u8", "https://cdn.test/m.m3u8")
    assert not master.plain
    assert not platforms.read_playlist("#EXTM3U\n", "https://cdn.test/m.m3u8").plain


# ---- owner report 2: Twitch -------------------------------------------------------------------------------------

def test_a_finished_twitch_recording_is_not_a_live_stream(fake_ydl, tmp_path, video):
    """The reported failure, reproduced. While Twitch shows its "processing" placeholder as a VOD's thumbnail,
    yt-dlp reports `is_live: True` and no thumbnail (yt_dlp/extractor/twitch.py, _extract_info_gql): the VOD of a
    stream that has just ended looks exactly like one still being recorded. The VOD's own segment list says
    which it is: closed means the recording is complete."""
    fake_ydl.formats = TWITCH_VOD
    fake_ydl.info = {"is_live": True, "was_live": True, "duration": 39.0, "thumbnails": None}
    fake_ydl.playlists = {f["url"]: segments(4, ended=True) for f in TWITCH_VOD}
    ydl = platforms._new_ydl(platforms.NOWHERE, ROOMY)
    info = platforms.metadata("twitch", TWITCH, ydl)
    assert platforms.live_state(info) == "was_live" and info["duration"] == 40.0
    assert len(ydl.opened) == 1                                       # one small request, and only in this case
    got = platforms.download("twitch", TWITCH, tmp_path, ROOMY)       # and so it imports, whole
    assert got.span.whole and got.path.read_bytes() == video.read_bytes()


def test_a_recording_in_progress_gives_the_part_published_so_far(fake_ydl, tmp_path, pieces):
    fake_ydl.formats = TWITCH_VOD
    fake_ydl.info = {"is_live": True, "was_live": True, "duration": 25.0}
    fake_ydl.playlists = {f["url"]: segments(3, ended=False) for f in TWITCH_VOD}
    fake_ydl.files = {"1080p60": pieces["middle"]}
    ydl = platforms._new_ydl(platforms.NOWHERE, ROOMY)
    info = platforms.metadata("twitch", TWITCH, ydl)
    assert platforms.live_state(info) == "recording" and info["duration"] == 30.0    # the list, not the stale number
    got = platforms.download("twitch", TWITCH, tmp_path, ROOMY)
    asked = fake_ydl.instances[-1].fetched[0][1]
    # Never the live stream: the three segments the site has published, through yt-dlp's plain segment downloader.
    assert asked["protocol"] == "http_dash_segments" and asked["is_live"] is False
    assert [f["url"] for f in asked["fragments"]] == [f"https://media.test/{n}.ts" for n in range(3)]
    assert got.span == Span(0.0, 30.0) and got.partial is True


def test_a_finished_recording_is_not_asked_for_its_segment_list(fake_ydl):
    fake_ydl.formats, fake_ydl.info = TWITCH_VOD, {"is_live": False, "was_live": True}
    ydl = platforms._new_ydl(platforms.NOWHERE, ROOMY)
    assert platforms.live_state(platforms.metadata("twitch", TWITCH, ydl)) == "was_live" and ydl.opened == []


def test_a_live_vod_whose_segment_list_cannot_be_read_stays_refused(fake_ydl, tmp_path):
    fake_ydl.formats, fake_ydl.info = TWITCH_VOD, {"is_live": True}            # no playlists: the request fails
    with pytest.raises(Refused) as e:
        platforms.download("twitch", TWITCH, tmp_path, ROOMY)
    assert e.value.code == "live_stream" and fake_ydl.instances[0].fetched == []


def test_only_twitch_is_asked_and_the_stream_extractor_can_never_run(fake_ydl):
    fake_ydl.formats, fake_ydl.info = TWITCH_VOD, {"live_status": "is_live"}
    ydl = platforms._new_ydl(platforms.NOWHERE, ROOMY)
    assert platforms.live_state(platforms.metadata("youtube", YOUTUBE, ydl)) == "live" and ydl.opened == []
    assert not any("stream" in name or "live" in name for name in platforms.EXTRACTORS)
