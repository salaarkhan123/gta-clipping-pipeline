"""Named sound events (gunshot, explosion, siren, crash, scream, laughter).

Weight 0 is the default, and that weight does not run the detector. A test can raise one
weight to see the series on a clip. YAMNet itself is not downloaded here.
"""
import wave
from pathlib import Path

import numpy as np
import pytest

import app.pipeline as pipeline
from app.pipeline import WEIGHTS, PipelineOptions, Timer, run_pipeline
from app.pipeline.ff import PipelineError
from app.pipeline.sound_events import (EVENTS, N_CLASSES, YAMNET_CLASSES, events_from_yamnet_scores,
                                       heuristic_detector, pool_patches, score_wav, yamnet_detector)


def write_wav(path: Path, samples: np.ndarray, rate: int = 16000) -> None:
    pcm = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((pcm * 32767.0).astype(np.int16).tobytes())


def test_every_sound_event_defaults_to_weight_zero():
    assert set(EVENTS) <= set(WEIGHTS)
    assert all(WEIGHTS[name] == 0.0 for name in EVENTS)


def test_score_wav_returns_one_value_per_second_for_every_event(tmp_path):
    write_wav(tmp_path / "a.wav", np.zeros(16000 * 3, np.float32))

    def det(samples, rate):
        assert rate == 16000 and len(samples) == 48000
        return {"gunshot": [0.2, 0.0, 1.0]}

    scores = score_wav(tmp_path / "a.wav", detector=det)
    assert set(scores) == set(EVENTS)
    assert scores["gunshot"] == [0.2, 0.0, 1.0]
    assert scores["siren"] == [0.0, 0.0, 0.0]


def test_a_span_of_the_wav_is_what_the_detector_hears(tmp_path):
    tone = np.zeros(16000 * 4, np.float32)
    tone[16000:32000] = 0.5
    write_wav(tmp_path / "a.wav", tone)

    def det(samples, _rate):
        return {"siren": [float(np.max(np.abs(samples)))]}

    scores = score_wav(tmp_path / "a.wav", start=1.0, length=1.0, detector=det)
    assert scores["siren"] == [pytest.approx(0.5, abs=1e-3)]
    assert all(len(v) == 1 for v in scores.values())


def test_a_wav_that_is_not_16khz_never_reaches_the_detector(tmp_path):
    write_wav(tmp_path / "a.wav", np.zeros(8000, np.float32), rate=8000)

    def det(*_a, **_k):
        raise AssertionError("detector ran on audio it cannot score")

    with pytest.raises(PipelineError) as err:
        score_wav(tmp_path / "a.wav", detector=det)
    assert err.value.code == "media_error"


def test_yamnet_gunshot_column_lands_on_the_seconds_the_patch_covers():
    scores = np.zeros((3, N_CLASSES))
    scores[2, 421] = 0.8                                   # Gunshot, gunfire; patch starts at 0.96 s
    out = events_from_yamnet_scores(scores, n_seconds=3)
    assert out["gunshot"] == pytest.approx([0.8, 0.8, 0.0])
    assert out["explosion"] == [0.0, 0.0, 0.0]
    assert set(out) == set(EVENTS)


def test_a_yamnet_vector_of_the_wrong_width_is_refused():
    with pytest.raises(PipelineError) as err:
        events_from_yamnet_scores(np.zeros((1, 3)), 1)
    assert err.value.code == "sound_events_unavailable"


def test_event_classes_do_not_share_a_column():
    indexes = [i for rows in YAMNET_CLASSES.values() for i, _name in rows]
    assert set(YAMNET_CLASSES) == set(EVENTS)
    assert YAMNET_CLASSES["gunshot"][0] == (421, "Gunshot, gunfire")
    assert len(indexes) == len(set(indexes)) and max(indexes) < N_CLASSES


def test_a_patch_lands_on_the_seconds_its_window_covers():
    frames = np.zeros(6)
    frames[5] = 0.4                                        # starts at 2.4 s, window runs to 3.36 s
    assert pool_patches(frames, 4) == pytest.approx([0.0, 0.0, 0.4, 0.4])


def test_the_yamnet_graph_is_not_loaded_until_it_scores(monkeypatch):
    called = []

    def boom(url):
        called.append(url)
        raise PipelineError("sound_events_unavailable", "no tensorflow")

    monkeypatch.setattr("app.pipeline.sound_events._load_yamnet", boom)
    monkeypatch.setattr("app.pipeline.sound_events._yamnet", None)
    det = yamnet_detector()
    assert called == []
    with pytest.raises(PipelineError) as err:
        det(np.zeros(16000, np.float32), 16000)
    assert err.value.code == "sound_events_unavailable" and called


def test_the_heuristic_separates_an_impulse_a_tone_and_silence():
    impulse = np.zeros(16000, np.float32)
    impulse[8000] = 1.0
    gun = heuristic_detector(impulse, 16000)
    assert gun["gunshot"][0] > 0.5 and gun["gunshot"][0] > gun["siren"][0]

    t = np.arange(16000) / 16000.0
    siren = heuristic_detector((0.25 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32), 16000)
    assert siren["siren"][0] > 0.2 and siren["siren"][0] > siren["gunshot"][0]
    assert siren["siren"][0] > siren["scream"][0]

    scream = heuristic_detector((0.25 * np.sin(2 * np.pi * 2500 * t)).astype(np.float32), 16000)
    assert scream["scream"][0] > scream["siren"][0]

    low = heuristic_detector((0.3 * np.sin(2 * np.pi * 80 * t)).astype(np.float32), 16000)
    assert low["explosion"][0] > 0.3 and low["explosion"][0] > low["gunshot"][0]

    silence = heuristic_detector(np.zeros(16000, np.float32), 16000)
    assert all(v == [0.0] for v in silence.values())


def test_the_heuristic_hears_noise_as_a_crash_and_a_pulse_as_laughter():
    rng = np.random.default_rng(0)
    noise = heuristic_detector(rng.normal(0, 0.2, 16000).astype(np.float32), 16000)
    assert noise["crash"][0] > noise["siren"][0] and noise["crash"][0] > 0.15

    t = np.arange(32000) / 16000.0
    gate = (np.sign(np.sin(2 * np.pi * 5 * t)) > 0).astype(np.float32)
    pulse = (rng.normal(0, 0.25, 32000).astype(np.float32) * gate)
    laugh = heuristic_detector(pulse, 16000)
    assert laugh["laughter"][0] > 0.3


def test_weight_zero_does_not_run_the_detector(video, tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("sound-event detector ran at weight 0")

    monkeypatch.setattr(pipeline, "score_sound_events", boom)
    timer = Timer()
    clips = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False,
                                                weights={name: 0.0 for name in EVENTS}),
                         tmp_path / "o", timer=timer)
    assert clips and set(clips[0].signals) == {"audio", "audio_flux", "audio_bursts"}
    assert "sound_events" not in timer.stages


def test_a_weight_above_zero_puts_that_series_on_the_clip(video, tmp_path, monkeypatch):
    def fake(_path, start=0.0, length=None, detector=None):
        n = 45
        gun = [0.0] * n
        gun[20] = 1.0
        return {name: (gun if name == "gunshot" else [0.0] * n) for name in EVENTS}

    monkeypatch.setattr(pipeline, "score_sound_events", fake)
    timer = Timer()
    clips = run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10, tighten=False,
                                                weights={"gunshot": 1.0}), tmp_path / "o", timer=timer)
    assert "sound_events" in timer.stages
    assert "gunshot" in clips[0].signals and "gunshot_peak" in clips[0].features
    assert "explosion" not in clips[0].signals
