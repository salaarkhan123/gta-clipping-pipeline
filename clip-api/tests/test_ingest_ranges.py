"""A chosen time range of a link, the same video never downloaded twice, progress while an import runs, and what
the link preview says a link is. Every failure path of a link clip job that these add ends in a full refund, shown
by the ledger: one `reserve:<job>` row and one `settle:<job>` row. Platforms come from the yt-dlp stand-in and
direct links from the fake DNS; no network."""
import subprocess

import pytest
from sqlalchemy import select, update

from app import worker
from app.config import get_settings
from app.db import new_session
from app.ingest import preview as link_preview
from app.ingest.takedown import takedown
from app.models import CreditLedger, ImportLog, Job, Upload, utcnow
from tests.ingest_support import fake_ydl, no_stray_imports, web  # noqa: F401
from tests.test_api import balance
from tests.test_ingest_media import TWITCH_VOD, YOUTUBE_SPLIT, segments

TWITCH = "https://www.twitch.tv/videos/2301234567"
YOUTUBE = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


@pytest.fixture(autouse=True)
def quiet_queue():
    def clear():
        with new_session() as db:
            db.execute(update(Job).where(Job.status.in_(("WAITING", "QUEUED", "RUNNING")))
                       .values(status="CANCELED", finished_at=utcnow()))
            db.commit()
    clear()
    link_preview.clear_cache()
    yield
    clear()
    link_preview.clear_cache()


@pytest.fixture(scope="module")
def long_video(tmp_path_factory):
    """130 s with a key frame every second, small: 3 credits whole, 1 credit for a range of up to a minute."""
    path = tmp_path_factory.mktemp("long") / "long.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=5:duration=130",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=130", "-c:v", "libx264", "-preset", "ultrafast",
                    "-g", "5", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


@pytest.fixture
def long_link(fake_ydl, long_video):
    fake_ydl.video, fake_ydl.info = long_video, {"duration": 130.0}
    return fake_ydl


def ask(client, headers, url=TWITCH, **more) -> dict:
    r = client.post("/v1/imports/preview", json={"url": url, **more}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def start(client, headers, url=TWITCH, **more):
    return client.post("/v1/imports", json={"url": url, "consent": True, **more}, headers=headers)


def clip(client, headers, url=TWITCH, **more):
    return client.post("/v1/clips/from-url", json={"url": url, "consent": True, **more}, headers=headers)


def imp(client, headers, import_id) -> dict:
    return client.get(f"/v1/imports/{import_id}", headers=headers).json()


def job(client, headers, job_id) -> dict:
    return client.get(f"/v1/jobs/{job_id}", headers=headers).json()


def seconds(job_id) -> float:
    """The length of video a job runs on."""
    with new_session() as db:
        return db.get(Job, job_id).duration_sec


def money(job_id) -> list[tuple]:
    with new_session() as db:
        return [(r.kind, r.delta, r.idempotency_key) for r in db.execute(
            select(CreditLedger).where(CreditLedger.job_id == job_id).order_by(CreditLedger.id)).scalars()]


def refunded_once(job_id, credits) -> None:
    assert money(job_id) == [("reserve", -credits, f"reserve:{job_id}"), ("release", credits, f"settle:{job_id}")]


def downloads(fake) -> int:
    return sum(len(i.fetched) for i in fake.instances)


def stored_files(account_id) -> list[str]:
    folder = get_settings().storage_dir / "uploads" / account_id
    return sorted(p.name for p in folder.glob("*")) if folder.exists() else []


# ---- what the preview says a link is ----------------------------------------------------------------------------

def test_a_finished_twitch_recording_with_the_processing_thumbnail_is_a_vod_not_a_live_stream(client, user, fake_ydl):
    """Owner report 2, at the API. yt-dlp calls the VOD live and gives no thumbnail (Twitch still shows its
    placeholder); the VOD's closed segment list says the recording is complete."""
    headers, _ = user
    fake_ydl.formats = TWITCH_VOD
    fake_ydl.info = {"is_live": True, "was_live": True, "duration": 7000, "uploader": "SomeStreamer",
                     "uploader_id": "somestreamer", "thumbnails": None, "timestamp": 1794966309,
                     "chapters": [{"title": "Just Chatting", "start_time": 0, "end_time": 600},
                                  {"title": "Grand Theft Auto VI", "start_time": 600, "end_time": 7200}]}
    fake_ydl.playlists = {f["url"]: segments(720) for f in TWITCH_VOD}
    body = ask(client, headers)
    assert body["supported"] is True and body["refusal"] is None
    assert (body["video_type"], body["live_status"], body["kind"]) == ("vod", "was_live", "video")
    assert body["duration_sec"] == 7200.0 and body["channel"] == "SomeStreamer"
    assert body["channel_url"] == "https://www.twitch.tv/somestreamer"
    assert body["category"] == "Grand Theft Auto VI" and body["started_at"] == "2026-11-18T01:45:09Z"
    assert body["thumbnail_url"] is None                    # Twitch has not made one yet: the site shows its own
    assert body["options"] == {"import": True, "clip": True, "range": True, "range_download": "partial"}
    assert body["estimate"]["credits"] == 120


def test_a_recording_in_progress_can_be_imported_up_to_now(client, user, fake_ydl):
    headers, _ = user
    fake_ydl.formats = TWITCH_VOD
    fake_ydl.info = {"is_live": True, "was_live": True, "duration": 100, "uploader": "SomeStreamer",
                     "uploader_id": "somestreamer", "thumbnails": None}
    fake_ydl.playlists = {f["url"]: segments(12, ended=False) for f in TWITCH_VOD}
    body = ask(client, headers)
    assert body["supported"] is True
    assert (body["video_type"], body["live_status"], body["kind"]) == ("ongoing_recording", "recording", "live")
    assert body["duration_sec"] == body["available_sec"] == 120.0
    assert body["thumbnail_url"] == "https://static-cdn.jtvnw.net/previews-ttv/live_user_somestreamer-640x360.jpg"
    assert body["range"] == {"start_sec": 0.0, "end_sec": 120.0}        # "all of it" is pinned to what exists now
    assert body["estimate"]["credits"] == 2
    part = ask(client, headers, start_sec=30, end_sec=90)
    assert part["range"] == {"start_sec": 30.0, "end_sec": 90.0} and part["estimate"]["credits"] == 1
    late = ask(client, headers, start_sec=60, end_sec=600)              # past what is recorded so far
    assert late["supported"] is False and late["refusal"]["code"] == "bad_range"


@pytest.mark.parametrize("url, platform, channel", [
    ("https://www.twitch.tv/SomeStreamer", "twitch", "somestreamer"),
    ("https://kick.com/somestreamer", "kick", "somestreamer"),
])
def test_a_channel_page_is_named_and_refused_without_any_request(client, user, fake_ydl, web, url, platform, channel):
    headers, account = user
    body = ask(client, headers, url)
    assert body["supported"] is False and body["platform"] == platform and body["channel"] == channel
    assert (body["video_type"], body["live_status"], body["kind"]) == ("live_channel", None, "channel")
    assert body["refusal"]["code"] == "live_channel" and "upload the file" in body["refusal"]["message"]
    assert body["options"] == {"import": False, "clip": False, "range": False, "range_download": None}
    assert body["estimate"] is None and body["lookup_ms"] == 0
    for send in (start, clip):
        r = send(client, headers, url)
        assert r.status_code == 422 and r.json()["error"]["code"] == "live_channel"
    assert fake_ydl.instances == [] and web.resolved == []              # the site was never asked anything
    with new_session() as db:
        assert db.execute(select(ImportLog.id).where(ImportLog.account_id == account["id"])).all() == []
    assert balance(client, headers) == 30


@pytest.mark.parametrize("url, info, video_type, live_status", [
    (YOUTUBE, {"media_type": "video", "live_status": "not_live"}, "video", "not_live"),
    ("https://www.youtube.com/shorts/k5Z7sFwFF7Q", {"media_type": "short", "live_status": "not_live"}, "short", "not_live"),
    (YOUTUBE, {"media_type": "livestream", "live_status": "was_live"}, "live_recording", "was_live"),
    (YOUTUBE, {"media_type": "livestream", "live_status": "is_live", "duration": None}, "live_stream", "live"),
    (YOUTUBE, {"live_status": "is_upcoming", "duration": None}, "upcoming", "upcoming"),
    ("https://clips.twitch.tv/FunnyClipSlug-abc123", {"categories": ["Fortnite"]}, "clip", "not_live"),
    ("https://kick.com/somechannel/videos/0a1b2c3d-1111-2222-3333-444455556666", {"was_live": True}, "vod", "was_live"),
])
def test_video_types(client, user, fake_ydl, url, info, video_type, live_status):
    headers, _ = user
    fake_ydl.info = {"channel": "Someone", "channel_url": "https://www.youtube.com/channel/UC1", **info}
    body = ask(client, headers, url)
    assert (body["video_type"], body["live_status"]) == (video_type, live_status)
    assert body["supported"] is (video_type not in ("live_stream", "upcoming"))
    if not body["supported"]:
        assert body["refusal"]["code"] == video_type and "pload" in body["refusal"]["message"] + "upload"


def test_a_youtube_video_with_two_streams_previews_and_prices(client, user, fake_ydl):
    """Owner report 1, at the API: the preview of a video with no single file used to be `no_format` with no
    title, thumbnail or price."""
    headers, _ = user
    fake_ydl.formats = YOUTUBE_SPLIT
    fake_ydl.info = {"duration": 635, "channel": "Blender", "categories": ["Film & Animation"],
                     "thumbnail": "https://i.ytimg.com/vi/aqz-KE-bpKQ/maxresdefault.jpg"}
    body = ask(client, headers, "https://youtu.be/aqz-KE-bpKQ")
    assert body["supported"] is True and body["title"] and body["channel"] == "Blender"
    assert body["thumbnail_url"].endswith("maxresdefault.jpg") and body["category"] == "Film & Animation"
    assert body["estimate"]["credits"] == 11 and body["options"]["range_download"] == "full"
    assert downloads(fake_ydl) == 0                                     # a preview never downloads


def test_twitch_thumbnails_come_at_a_usable_size(client, user, fake_ydl):
    headers, _ = user
    base = "https://static-cdn.jtvnw.net/cf_vods/d2nvs/abc_somestreamer_1_2//thumb/thumb0"
    fake_ydl.info = {"thumbnails": [{"url": f"{base}-0x0.jpg", "preference": 1}, {"url": f"{base}-90x60.jpg"}]}
    assert ask(client, headers)["thumbnail_url"] == f"{base}-640x360.jpg"


# ---- a chosen range ---------------------------------------------------------------------------------------------

def test_importing_a_range_stores_only_that_part(client, user, long_link):
    headers, account = user
    r = start(client, headers, start_sec=20, end_sec=50)
    assert r.status_code == 202, r.text
    queued = r.json()
    assert queued["range"] == {"start_sec": 20.0, "end_sec": 50.0} and queued["bytes_done"] is None
    assert worker.run_once() == "SUCCEEDED"
    done = imp(client, headers, queued["import_id"])
    assert done["status"] == "SUCCEEDED" and done["stage"] == "done" and done["progress"] == 100
    assert done["range"] == {"start_sec": 20.0, "end_sec": 50.0}
    assert 29.5 <= done["upload"]["duration_sec"] <= 32 and len(stored_files(account["id"])) == 1
    assert balance(client, headers) == 30                               # an import costs nothing


@pytest.mark.parametrize("more, code", [
    ({"start_sec": 50, "end_sec": 20}, "bad_range"),
    ({"start_sec": 10, "end_sec": 10}, "bad_range"),
    ({"start_sec": -1}, "validation_error"),
    ({"end_sec": "soon"}, "validation_error"),
])
def test_a_range_that_is_not_a_range_is_a_422_everywhere(client, user, long_link, more, code):
    headers, account = user
    for send in (start, clip):
        r = send(client, headers, **more)
        assert r.status_code == 422 and r.json()["error"]["code"] == code, r.text
    r = client.post("/v1/imports/preview", json={"url": TWITCH, **more}, headers=headers)
    assert (r.status_code == 422) if code == "validation_error" else (r.json()["refusal"]["code"] == code)
    with new_session() as db:
        assert db.execute(select(Job.id).where(Job.account_id == account["id"])).all() == []
        assert db.execute(select(ImportLog.id).where(ImportLog.account_id == account["id"])).all() == []
    assert balance(client, headers) == 30 and downloads(long_link) == 0


def test_clips_from_a_range_are_priced_on_the_range_only(client, user, long_link, monkeypatch):
    headers, account = user
    monkeypatch.setattr("app.pipeline.run_pipeline", lambda *a, **k: [])
    whole = ask(client, headers)["estimate"]
    part = ask(client, headers, start_sec=20, end_sec=75)
    assert whole["credits"] == 3 and part["estimate"]["credits"] == 1 and part["estimate"]["duration_sec"] == 55.0
    r = clip(client, headers, start_sec=20, end_sec=75)
    assert r.status_code == 202, r.text
    made = r.json()
    assert made["credits_reserved"] == 1 and made["import"]["range"] == {"start_sec": 20.0, "end_sec": 75.0}
    assert balance(client, headers) == 29
    assert worker.run_once() == "SUCCEEDED"                             # the import: only the range
    queued = job(client, headers, made["job_id"])
    assert queued["status"] == "QUEUED" and 54.5 <= seconds(made["job_id"]) <= 57
    worker.run_once()
    done = job(client, headers, made["job_id"])
    assert done["credits_charged"] <= 1                                 # never more than the quote
    assert [k for k, _, _ in money(made["job_id"])] == ["reserve", done["status"] == "SUCCEEDED" and "commit" or "release"]
    assert len(money(made["job_id"])) == 2


def test_the_same_range_request_twice_is_one_job_and_one_charge(client, user, long_link):
    headers, account = user
    first = clip(client, headers, start_sec=20, end_sec=75)
    again = clip(client, headers, start_sec=20, end_sec=75)
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["job_id"] == first.json()["job_id"] and balance(client, headers) == 29
    other = clip(client, headers, start_sec=0, end_sec=30)              # another part: its own job and import
    assert other.status_code == 202 and other.json()["job_id"] != first.json()["job_id"]
    assert other.json()["import"]["import_id"] != first.json()["import"]["import_id"]
    assert balance(client, headers) == 28


# ---- never the same video twice ---------------------------------------------------------------------------------

def test_a_link_already_stored_is_not_downloaded_again(client, user, long_link):
    headers, account = user
    first = start(client, headers).json()
    assert worker.run_once() == "SUCCEEDED" and downloads(long_link) == 1
    upload_id = imp(client, headers, first["import_id"])["upload_id"]

    second = start(client, headers).json()                              # the whole link again
    assert second["import_id"] != first["import_id"]
    assert worker.run_once() == "SUCCEEDED"
    again = imp(client, headers, second["import_id"])
    assert again["upload_id"] == upload_id and again["reused"] is True
    assert downloads(long_link) == 1 and len(long_link.instances) == 1  # not even its metadata was asked for

    third = start(client, headers, start_sec=40, end_sec=70).json()     # a part of it: cut from the stored copy
    assert worker.run_once() == "SUCCEEDED"
    part = imp(client, headers, third["import_id"])
    assert part["upload_id"] not in (None, upload_id) and part["reused"] is False
    assert part["range"] == {"start_sec": 40.0, "end_sec": 70.0} and 29.5 <= part["upload"]["duration_sec"] <= 32
    assert downloads(long_link) == 1 and len(long_link.instances) == 1

    fourth = start(client, headers, start_sec=45, end_sec=60).json()    # inside the stored part: cut from that
    assert worker.run_once() == "SUCCEEDED"
    inner = imp(client, headers, fourth["import_id"])
    assert inner["range"] == {"start_sec": 45.0, "end_sec": 60.0} and 14.5 <= inner["upload"]["duration_sec"] <= 17
    fifth = start(client, headers, start_sec=40, end_sec=70).json()     # exactly a stored part: handed back
    assert worker.run_once() == "SUCCEEDED"
    assert imp(client, headers, fifth["import_id"])["upload_id"] == part["upload_id"]
    assert downloads(long_link) == 1 and len(stored_files(account["id"])) == 3

    # Every copy carries the source link, so one takedown of the link removes them all.
    takedown(url=TWITCH)
    assert stored_files(account["id"]) == [] and client.get("/v1/uploads", headers=headers).json()["uploads"] == []


def test_a_stored_part_is_not_mistaken_for_the_whole_video(client, user, long_link, monkeypatch):
    headers, account = user
    monkeypatch.setattr("app.pipeline.run_pipeline", lambda *a, **k: [])
    start(client, headers, start_sec=0, end_sec=30)
    assert worker.run_once() == "SUCCEEDED" and downloads(long_link) == 1
    whole = ask(client, headers)["estimate"]
    assert whole["credits"] == 3 and whole["basis"] == "source_minutes"      # priced as the whole video
    made = clip(client, headers).json()
    assert made["status"] == "WAITING" and made["credits_reserved"] == 3     # and imported as the whole video
    assert worker.run_once() == "SUCCEEDED" and downloads(long_link) == 2
    assert 129 <= seconds(made["job_id"]) <= 131


def test_an_import_of_the_same_part_already_on_its_way_is_joined(client, user, long_link):
    headers, account = user
    a = start(client, headers, start_sec=10, end_sec=40).json()
    b = start(client, headers, start_sec=10, end_sec=40).json()
    c = start(client, headers, start_sec=10, end_sec=41).json()
    d = start(client, headers).json()
    assert a["import_id"] == b["import_id"] and len({a["import_id"], c["import_id"], d["import_id"]}) == 3


# ---- progress ---------------------------------------------------------------------------------------------------

def test_progress_shows_stage_and_bytes_while_it_runs(client, user, long_link, monkeypatch):
    headers, _ = user
    long_link.formats = YOUTUBE_SPLIT
    seen = []
    real_dl = long_link.dl

    def watched(self, name, info, **how):
        out = real_dl(self, name, info, **how)
        seen.append(imp(client, headers, started["import_id"]))            # what a client polling now would get
        return out

    monkeypatch.setattr(long_link, "dl", watched)
    monkeypatch.setattr("app.ingest.runner.time.monotonic", iter(range(0, 10_000, 5)).__next__)   # no throttling
    started = start(client, headers, YOUTUBE).json()
    assert started["stage"] is None and started["progress"] == 0
    worker.run_once()
    assert [s["stage"] for s in seen] == ["downloading", "downloading"]
    assert seen[0]["status"] == "RUNNING" and 0 < seen[0]["bytes_done"] < seen[1]["bytes_done"]
    assert seen[0]["bytes_total"] == seen[1]["bytes_total"] == 260 * 1024 ** 2      # both streams, as the site sized them
    assert 2 <= seen[0]["progress"] <= seen[1]["progress"] <= 88


def test_the_stages_an_import_goes_through(client, user, long_link, monkeypatch):
    headers, _ = user
    from app.ingest import runner
    stages = []
    real = runner.new_session

    def spy():
        db = real()
        commit = db.commit

        def commit_and_note():
            for obj in db.dirty:
                if isinstance(obj, Job) and obj.id.startswith("imp_") and obj.stage and (not stages or stages[-1] != obj.stage):
                    stages.append(obj.stage)
            commit()
        db.commit = commit_and_note
        return db

    monkeypatch.setattr(runner, "new_session", spy)
    first = start(client, headers, start_sec=5, end_sec=40).json()
    assert worker.run_once() == "SUCCEEDED"
    assert stages == ["reading", "downloading", "merging", "checking", "storing"]
    assert imp(client, headers, first["import_id"])["stage"] == "done"
    stages.clear()
    start(client, headers, start_sec=10, end_sec=30)                    # from the stored copy: no download stage
    assert worker.run_once() == "SUCCEEDED"
    assert stages == ["reading", "copying", "checking", "storing"]


# ---- every new failure path ends in a refund --------------------------------------------------------------------

def broken_join(fake, tmp_path):
    garbage = tmp_path / "garbage.m4a"
    garbage.write_bytes(b"not sound at all " * 500)
    fake.formats, fake.files = YOUTUBE_SPLIT, {"140": garbage}
    return YOUTUBE, {}


def shorter_than_previewed(fake, tmp_path):
    return TWITCH, {"start_sec": 100, "end_sec": 125}


def stored_copy_gone(fake, tmp_path):
    return TWITCH, {"start_sec": 100, "end_sec": 125}


def recording_segments_refused(fake, tmp_path):
    fake.formats = TWITCH_VOD
    fake.info = {"is_live": True, "was_live": True, "duration": 130}
    fake.playlists = {f["url"]: segments(13, ended=False) for f in TWITCH_VOD}
    return TWITCH, {}


@pytest.mark.parametrize("setup, code", [
    (broken_join, "unsupported_media"),                 # the two streams cannot be joined
    (shorter_than_previewed, "bad_range"),              # the video is shorter than the preview said
    (stored_copy_gone, "import_failed"),                # the stored copy to cut from has gone
    (recording_segments_refused, "source_refused"),     # the site refuses the recording's segments
])
def test_new_failure_paths_refund_the_job_in_full(client, user, long_link, tmp_path, monkeypatch, setup, code):
    headers, account = user
    url, more = setup(long_link, tmp_path)
    if setup is stored_copy_gone:                       # the account has the whole video stored...
        whole = start(client, headers).json()
        assert worker.run_once() == "SUCCEEDED"
    made = clip(client, headers, url, **more)
    assert made.status_code == 202, made.text
    made = made.json()
    reserved = made["credits_reserved"]
    assert reserved >= 1 and balance(client, headers) == 30 - reserved
    if setup is shorter_than_previewed:
        long_link.info = {"duration": 90.0}             # ...but by the time of the import it is shorter
    if setup is stored_copy_gone:                       # ...and its file disappears from storage
        key = imp(client, headers, whole["import_id"])["upload"]["upload_id"]
        with new_session() as db:
            get_settings().storage_dir.joinpath(db.get(Upload, key).storage_key).unlink()
    if setup is recording_segments_refused:
        long_link.refuse_download = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
    assert worker.run_once() == "FAILED"
    out = job(client, headers, made["job_id"])
    assert out["status"] == "FAILED" and out["error"]["code"] == code, out
    assert out["import"]["status"] == "FAILED" and out["credits_charged"] == 0
    assert "credits were returned" in out["error"]["message"]
    refunded_once(made["job_id"], reserved)
    assert balance(client, headers) == 30 and worker.run_once() is None
    assert stored_files(account["id"]) == []


def test_a_plain_import_that_fails_charges_and_stores_nothing(client, user, long_link, tmp_path):
    headers, account = user
    url, _ = broken_join(long_link, tmp_path)
    started = start(client, headers, url).json()
    assert worker.run_once() == "FAILED"
    done = imp(client, headers, started["import_id"])
    assert done["error"]["code"] == "unsupported_media" and done["upload_id"] is None
    assert done["error"]["message"].endswith("Upload the file instead.")
    with new_session() as db:
        assert db.execute(select(CreditLedger.kind).where(CreditLedger.account_id == account["id"])).all() == [("grant",)]
    assert stored_files(account["id"]) == [] and list(get_settings().work_dir.glob("imp_*")) == []


def test_a_recording_in_progress_is_clipped_up_to_the_quote(client, user, long_link, monkeypatch, tmp_path):
    """The part recorded when the price was shown is what is imported, even though the stream went on."""
    headers, _ = user
    monkeypatch.setattr("app.pipeline.run_pipeline", lambda *a, **k: [])
    ts = tmp_path / "first60.ts"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-t", "60", "-i", str(long_link.video), "-c", "copy", "-f",
                    "mpegts", str(ts)], check=True)
    long_link.formats, long_link.files = TWITCH_VOD, {"1080p60": ts}
    long_link.info = {"is_live": True, "was_live": True, "duration": 50}
    long_link.playlists = {f["url"]: segments(6, ended=False) for f in TWITCH_VOD}
    made = clip(client, headers).json()
    assert made["status"] == "WAITING" and made["credits_reserved"] == 1
    assert made["import"]["range"] == {"start_sec": 0.0, "end_sec": 60.0}
    long_link.playlists = {f["url"]: segments(13, ended=False) for f in TWITCH_VOD}     # 70 more seconds went by
    assert worker.run_once() == "SUCCEEDED"
    asked = long_link.instances[-1].fetched[0][1]
    assert len(asked["fragments"]) == 6 and asked["protocol"] == "http_dash_segments"   # the first minute only
    assert 59 <= seconds(made["job_id"]) <= 62
