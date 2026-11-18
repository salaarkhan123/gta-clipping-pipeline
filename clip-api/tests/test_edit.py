"""Edit decisions: dead-air cuts, flash-forward, caption remapping and punch-in zoom times."""
import subprocess

import pytest

from app.pipeline import edit as E


def test_cut_removes_spans_and_keeps_a_short_pause():
    # A 2 s silence at 10-12 inside a 0-30 clip: 0.25 s of it stays, split between the two sides.
    assert E.cut(0, 30, [(10, 12)], keep_pause=0.25) == [(0, 10.125), (11.875, 30)]
    assert E.cut(0, 30, []) == [(0, 30)]
    assert E.cut(5, 30, [(0, 6), (29, 40)]) == [(6, 29)]                      # spans reaching past the clip


def test_cut_drops_slivers_and_never_guts_the_clip():
    assert E.cut(0, 30, [(10, 12), (12.2, 14)]) == [(0, 10), (14, 30)]         # 0.2 s between two cuts is not kept
    assert E.cut(0, 30, [(1, 29)]) == [(0, 30)]                                # would leave 2 s of 30: leave it alone


def test_filler_words_are_found_by_word_not_by_substring():
    words = [(1.0, 1.3, "Um,"), (1.3, 1.8, "umbrella"), (2.0, 2.2, "uh"), (2.2, 2.9, "huh"), (3.0, 3.4, "Hmm.")]
    assert E.filler_spans(words) == [(1.0, 1.3), (2.0, 2.2), (3.0, 3.4)]


def test_flash_forward_only_when_the_peak_is_worth_teasing():
    segs = [(100.0, 130.0)]
    assert E.with_flash_forward(segs, 118.0, 130.0) == [(118.0, 119.5), (100.0, 130.0)]
    assert E.with_flash_forward(segs, 102.0, 130.0) == segs                    # the clip already starts on it
    assert E.with_flash_forward(segs, None, 130.0) == segs
    assert E.with_flash_forward(segs, 129.8, 130.0) == segs                    # nothing left to show after the peak


def test_words_follow_the_segments_onto_the_rendered_timeline():
    segs = [(118.0, 119.5), (100.0, 110.0), (112.0, 130.0)]                    # flash-forward, then the body with a cut
    words = [(100.5, 101.0, "so"), (110.5, 111.0, "um"), (112.5, 113.0, "watch"), (118.2, 118.9, "NO WAY")]
    assert E.remap_words(words, segs) == [(0.2, 0.9, "NO WAY"), (2.0, 2.5, "so"), (12.0, 12.5, "watch"), (17.7, 18.4, "NO WAY")]
    assert E.duration(segs) == 29.5
    assert E.to_output(118.2, segs) == pytest.approx(0.2) and E.to_output(118.2, segs, skip=1) == pytest.approx(17.7)
    assert E.to_output(111.0, segs) is None                                    # inside the cut


def test_zoom_peaks_are_the_loud_seconds_spaced_apart_and_never_in_the_flash():
    db = [-40.0] * 200
    for sec, level in ((105, -8), (106, -9), (120, -10), (127, -12)):
        db[sec] = level
    segs = [(120.0, 121.5), (100.0, 130.0)]
    peaks = E.zoom_peaks(db, segs, flash=True)
    assert peaks == [7.0, 22.0, 29.0]                    # 105.5, 120.5, 127.5 on the output timeline; 106 is too close to 105
    assert all(p >= 1.5 for p in peaks)
    assert E.zoom_peaks([-30.0] * 200, [(100.0, 130.0)]) == []                 # evenly loud: no zoom
    assert E.zoom_peaks(db, [(100.0, 104.0)]) == []                            # too short to judge


def test_zoom_expression_is_one_at_rest_and_never_above_the_limit():
    assert E.zoom_expr([]) == "1"
    expr = E.zoom_expr([7.0, 22.0])
    assert expr.startswith("1+0.150*min(1,") and "abs(t-7.20)" in expr and "abs(t-22.20)" in expr

    def z(t):
        return eval(expr, {"t": t, "max": max, "min": min, "abs": abs})        # same syntax as ffmpeg's expr
    assert z(0) == 1 and z(15) == 1 and z(7.2) == pytest.approx(1.15) and max(z(x / 10) for x in range(300)) <= 1.15 + 1e-9


def test_silences_are_found_in_real_audio(tmp_path):
    src = tmp_path / "gaps.mp4"      # tone, 2 s of silence at 4-6, tone, 0.3 s gap at 8 (too short), tone
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=12",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
                    "-af", "volume='if(between(t,4,6)+between(t,8,8.3),0,0.5)':eval=frame",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src)], check=True)
    found = E.silences(src, 1.0, 11.0)
    assert len(found) == 1 and found[0][0] == pytest.approx(4.0, abs=0.15) and found[0][1] == pytest.approx(6.0, abs=0.15)
    assert E.silences(tmp_path / "missing.mp4", 0, 5) == []                    # never fails a job


def test_speech_gaps_are_dead_air_only_when_the_game_is_quiet_too():
    db = [-30.0] * 100
    db[20] = db[21] = -12.0                                   # a crash while nobody speaks
    words = [(10.0, 10.5, "ok"), (14.0, 14.4, "so"), (14.6, 15.0, "then"), (19.0, 19.5, "watch"), (23.0, 23.5, "WOW")]
    gaps = E.speech_gaps(words, db, 8.0, 38.0)
    assert gaps == [(10.5, 14.0), (15.0, 19.0)]               # 0.2 s between words is not a gap; 19.5-23 has the crash in it
    assert E.speech_gaps(words[:1], db, 8.0, 38.0) == [] and E.speech_gaps([], db, 8.0, 38.0) == []


def test_cuts_are_chosen_longest_first_within_a_third_of_the_clip():
    spans = [(2.0, 6.0), (10.0, 13.0), (20.0, 26.0), (27.5, 28.5)]           # 14 s of gaps in a 30 s clip
    chosen = E.select_cuts(spans, 0.0, 30.0)
    assert chosen == [(2.0, 6.0), (20.0, 26.0)] and sum(e - s for s, e in chosen) <= 0.35 * 30


def test_no_cut_leaves_a_fragment_and_there_are_at_most_four():
    # The 8-piece clip from the audit: gaps that would leave pieces of 0.8 s and 1.2 s between them.
    gaps = [(23.1, 24.6), (25.4, 25.9), (28.9, 29.3), (37.0, 37.5), (41.6, 45.0), (45.8, 49.4)]
    chosen = E.select_cuts(gaps, 21.9, 50.6)
    pieces = E.cut(21.9, 50.6, chosen)
    assert len(chosen) <= 4 and all(e - s >= 1.2 for s, e in pieces[1:-1])          # every piece between cuts is watchable
    assert (45.8, 49.4) in chosen and (41.6, 45.0) not in chosen                    # the longer gap goes; the 0.8 s of speech between them is not orphaned
    six = [(float(k), k + 0.9) for k in range(3, 60, 5)]                            # twelve short gaps in a minute
    assert len(E.select_cuts(six, 0.0, 60.0)) == 4


def test_a_cut_at_the_very_start_or_end_just_trims_the_clip():
    assert E.select_cuts([(0.0, 1.0), (29.2, 30.0)], 0.0, 30.0) == [(0.0, 1.0), (29.2, 30.0)]
    assert E.select_cuts([(0.5, 1.5)], 0.0, 30.0) == []                             # would leave half a second at the front


def test_a_cut_never_removes_a_spoken_word():
    words = [(19.0, 19.5, "no"), (19.5, 20.0, "way")]
    assert E.avoid_words([(18.0, 20.0), (24.0, 28.0)], words) == [(18.0, 18.9), (24.0, 28.0)]
    assert E.avoid_words([(18.6, 19.4)], words) == []                          # what is left is too short to cut
    assert E.avoid_words([(10.0, 30.0)], words) == [(10.0, 18.9), (20.1, 30.0)]
