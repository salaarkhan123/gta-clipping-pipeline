"""Highlight detector stub + FPR helper (AS-3 live scaffold)."""
from app.live.detect import DetectorConfig, HighlightDetector, false_positive_rate


def _quiet_then_loud(quiet: int, loud: int, quiet_db: float = -40.0, loud_db: float = -8.0) -> list[float]:
    return [quiet_db] * quiet + [loud_db] * loud + [quiet_db] * 10


def test_no_trigger_during_warm_up():
    det = HighlightDetector(DetectorConfig(warm_sec=60, threshold=1.0, refractory_sec=5.0))
    # Loud from the first second — still must wait for warm_sec.
    found = det.push_batch([ -5.0] * 50)
    assert found == []
    assert det.triggers == []


def test_loud_burst_after_baseline_triggers_once_with_refractory():
    det = HighlightDetector(DetectorConfig(
        warm_sec=30, baseline_sec=30, threshold=1.0, confirm_of=3, confirm_need=2,
        refractory_sec=20.0, audio_weight=1.0, chat_weight=0.0,
    ))
    series = _quiet_then_loud(40, 8)
    found = det.push_batch(series)
    assert len(found) >= 1
    assert found[0].at_sec >= 30
    # Refractory: a second burst immediately after should not double-fire inside the window.
    more = det.push_batch([-8.0] * 5)
    assert more == [] or (more[0].at_sec - found[0].at_sec) >= 20.0 - 1e-6


def test_trailing_z_ignores_future_samples():
    det = HighlightDetector(DetectorConfig(baseline_sec=10, mad_floor=1.0))
    # Index 5 is quiet; later samples are loud — trailing z at 5 must stay ~0.
    series = [-40.0] * 6 + [-5.0] * 10
    det._audio = list(series)
    assert det.trailing_z(series, 5) == 0.0


def test_fpr_unmeasured_without_labels():
    det = HighlightDetector()
    out = false_positive_rate([], [], 100.0)
    assert out["measured"] is False


def test_fpr_counts_false_positives_with_labels():
    from app.live.detect import Trigger
    triggers = [Trigger(at_sec=10.0, score=2.0, audio_z=2.0), Trigger(at_sec=50.0, score=2.0, audio_z=2.0)]
    # Only the first is near a labelled highlight.
    out = false_positive_rate(triggers, [(8.0, 12.0)], total_sec=60.0, hit_radius_sec=2.0)
    assert out["measured"] is True
    assert out["true_positives"] == 1
    assert out["false_positives"] == 1
