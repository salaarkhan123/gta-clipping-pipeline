"""Rolling segment buffer unit tests (AS-3 live scaffold)."""
from pathlib import Path

from app.live.buffer import RollingSegmentBuffer, Segment


def test_append_advances_timeline_and_indexes():
    buf = RollingSegmentBuffer(retention_sec=10.0, segment_sec=2.0)
    a = buf.append(rms_db=[-40.0, -39.0])
    b = buf.append(rms_db=[-38.0, -12.0])
    assert a.index == 0 and b.index == 1
    assert a.start_sec == 0.0 and b.start_sec == 2.0
    assert buf.covered_sec == 4.0
    assert buf.rms_timeline() == [-40.0, -39.0, -38.0, -12.0]


def test_retention_drops_oldest_whole_segments():
    buf = RollingSegmentBuffer(retention_sec=6.0, segment_sec=2.0)
    for _ in range(5):
        buf.append()
    # 5 * 2s = 10s → trim until <= 6s → keep last 3 segments
    assert len(buf) == 3
    assert buf.head_sec == 4.0
    assert buf.tail_sec == 10.0


def test_slice_paths_overlaps_only():
    buf = RollingSegmentBuffer(retention_sec=60.0, segment_sec=2.0)
    buf.append(Segment(0, 0.0, 2.0, path=Path("/tmp/a.mp4")))
    buf.append(Segment(1, 2.0, 2.0, path=Path("/tmp/b.mp4")))
    buf.append(Segment(2, 4.0, 2.0, path=None))
    paths = buf.slice_paths(1.0, 3.5)
    assert paths == [Path("/tmp/a.mp4"), Path("/tmp/b.mp4")]


def test_clear():
    buf = RollingSegmentBuffer()
    buf.append()
    buf.clear()
    assert len(buf) == 0
    assert buf.tail_sec is None
