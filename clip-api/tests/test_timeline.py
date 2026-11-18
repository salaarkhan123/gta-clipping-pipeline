"""U2: the per-second signal timeline. Audio signals come from the loudness decode without changing the loudness;
standby footage never becomes a clip."""
import subprocess

import numpy as np
import pytest

import app.pipeline as pipeline
from app import worker
from app.pipeline import WEIGHTS, PipelineError, PipelineOptions, Timer, run_pipeline
from app.pipeline.signals import audio_rms_db
from app.pipeline.stt import extract_audio
from app.pipeline.timeline import (AUDIO, STANDBY_REJECT, audio_timeline, keyframes, standby_seconds, standby_share,
                                   wav_timeline)
from tests.test_api import balance, upload


@pytest.fixture(scope="module")
def still_then_moving(tmp_path_factory):
    """60 s: a still card with quiet music for 30 s, then a moving picture with loud bursts."""
    out = tmp_path_factory.mktemp("v") / "standby.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=navy:size=320x240:rate=15:duration=30",
                    "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15:duration=30",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=60",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
                    "-map", "[v]", "-map", "2:a",
                    "-af", "volume='if(lt(t,30),0.05,if(lt(mod(t,8),2),1.0,0.2))':eval=frame",
                    "-g", "30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(out)], check=True)
    return out


@pytest.fixture(scope="module")
def all_still(tmp_path_factory):
    out = tmp_path_factory.mktemp("v") / "brb.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:size=320x240:rate=15:duration=40",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=40",
                    "-af", "volume='if(between(t,20,24),1.0,0.05)':eval=frame", "-g", "30",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
                   check=True)
    return out


def test_one_decode_gives_the_same_loudness_and_one_value_per_second_of_each_signal(video):
    levels, signals = audio_timeline(video)
    assert levels == audio_rms_db(video)                                    # to the last digit
    assert set(signals) == set(AUDIO) and all(len(v) == len(levels) for v in signals.values())
    part, cut = audio_timeline(video, start=10.0, length=20.0)
    assert part == audio_rms_db(video, start=10.0, length=20.0) and len(cut["audio_flux"]) == len(part)


def test_the_signals_rise_where_the_sound_changes(video):
    _, s = audio_timeline(video)
    flux = np.asarray(s["audio_flux"])
    assert flux[19:22].max() > 3 * np.median(flux)                         # the burst starts at 20 s


def test_signals_from_a_decoded_wav_match_the_pipe(video, tmp_path):
    _, piped = audio_timeline(video)
    wav = wav_timeline(extract_audio(video, tmp_path / "a.wav").path)
    assert len(wav["audio_flux"]) == len(piped["audio_flux"])
    # The burst starts at 20 s in both. The last second is left out: it is a padded part second where the sound stops.
    assert 19 <= int(np.argmax(wav["audio_flux"][:-2])) <= 21 and 19 <= int(np.argmax(piped["audio_flux"][:-2])) <= 21


def test_a_signal_with_weight_zero_costs_nothing(video, tmp_path, monkeypatch):
    def no(*a, **k):
        raise AssertionError("decoded for a signal that does not count")
    monkeypatch.setattr(pipeline, "audio_timeline", no)
    monkeypatch.setattr(pipeline, "scene_changes", no)
    clips = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False,
                                                weights={"audio_flux": 0, "audio_bursts": 0}), tmp_path / "o")
    assert clips and set(clips[0].signals) == {"audio"}
    assert WEIGHTS["scene"] == 0                                            # off by default: an extra frame decode


def test_the_default_moment_score_uses_the_new_signals(video, tmp_path):
    clips = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False), tmp_path / "o")
    assert {"audio", "audio_flux", "audio_bursts"} == set(clips[0].signals)
    assert {"audio_flux_mean", "audio_bursts_peak"} <= set(clips[0].features)


# ---------- standby ----------

def still(k: int, value: int = 40):
    return [(2.0 * i, np.full((9, 16), value, np.uint8)) for i in range(k)]


def test_still_seconds_are_standby_unless_someone_speaks():
    frames = still(6)
    assert standby_share(frames, 0.0, 10.0) == 1.0
    sec = standby_seconds(frames, 0.0, 10.0, speech=[(3.2, 4.1)])
    assert not sec[3] and not sec[4] and sec[0] and sec[9]
    moving = [(2.0 * i, np.full((9, 16), 40 + 30 * (i % 2), np.uint8)) for i in range(6)]
    assert standby_share(moving, 0.0, 10.0) == 0.0
    assert standby_seconds(still(1), 0.0, 10.0) is None and standby_share(still(1), 0.0, 10.0) == 0.0


def test_key_frames_come_with_source_times(still_then_moving):
    frames = keyframes(still_then_moving, 30.0, 20.0)
    assert len(frames) >= 5 and 29.5 <= frames[0][0] <= 32.5 and all(b[0] > a[0] for a, b in zip(frames, frames[1:]))
    assert standby_share(keyframes(still_then_moving, 2.0, 25.0), 2.0, 27.0) == 1.0
    assert standby_share(frames, 30.0, 50.0) == 0.0


def test_a_standby_candidate_never_becomes_a_clip(still_then_moving, tmp_path):
    timer = Timer()
    moments = []

    def keep(ms):
        moments.extend(ms)
    clips = run_pipeline(still_then_moving, PipelineOptions(max_clips=3, clip_length=10, tighten=False), tmp_path / "o",
                         timer=timer, on_moments=keep)
    assert clips and all(c.start >= 29 for c in clips)                   # nothing from the still card
    assert all(m.features["standby_share"] < STANDBY_REJECT and m.features["standby"] is False for m in moments)
    assert all("standby_share" in c.features for c in clips)


def test_a_candidate_with_a_little_standby_is_still_judged_and_the_judge_is_told(still_then_moving, tmp_path):
    seen = []

    def judge(text, frame, ctx):
        seen.append(ctx)
        return {"title": "t", "virality": {"score": 80}}
    clips = run_pipeline(still_then_moving, PipelineOptions(max_clips=1, clip_length=20, tighten=False,
                                                            range={"start": 20, "end": 40}), tmp_path / "o", judge=judge)
    assert clips and seen                                                  # judged, not dropped
    share = clips[0].features["standby_share"]
    assert 0 < share < STANDBY_REJECT and clips[0].features["standby"] is False
    assert seen[0]["standby"] == share


def test_the_judge_prompt_names_the_standby_share_only_when_there_is_some():
    from app.ai import _standby_line
    assert _standby_line({}) == "" and _standby_line({"standby": 0.0}) == ""
    assert "Standby share: 40%" in _standby_line({"standby": 0.4})


def test_only_standby_fails_cleanly_and_the_job_is_refunded(all_still, tmp_path, client, user):
    with pytest.raises(PipelineError) as e:
        run_pipeline(all_still, PipelineOptions(max_clips=1, clip_length=10, tighten=False), tmp_path / "o")
    assert e.value.code == "no_moments" and "standby" in e.value.message
    headers, _ = user
    up = upload(client, headers, all_still)
    before = balance(client, headers)
    r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": {"max_clips": 1, "clip_length": 10}},
                    headers=headers)
    assert r.status_code == 202
    assert worker.run_once(None) == "FAILED"
    job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()
    assert job["error"]["code"] == "no_moments" and job["credits_charged"] == 0 and balance(client, headers) == before
