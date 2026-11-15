"""Caption lines break on pauses, punctuation and length, never on a short word that runs into the next."""
import re

from app.pipeline.captions import build_ass, group_words


def timed(text: str, gaps=None, dur=0.25):
    """Words with a 0.05 s gap between them, or the given gap before word i."""
    out, t = [], 0.0
    for i, word in enumerate(text.split()):
        t += (gaps or {}).get(i, 0.05) if i else 0.0
        out.append((round(t, 3), round(t + dur, 3), word))
        t += dur
    return out


def lines(text, gaps=None, **kw):
    return [" ".join(w[2] for w in c).upper() for c in group_words(timed(text, gaps), **kw)]


def test_no_line_ends_on_a_short_word_that_runs_into_the_next():
    # Before: "OH NO HAD" / "TO GET UP" / "GET OUT" (3 words each, by count only).
    assert lines("oh no had to get up get out") == ["OH NO", "HAD TO", "GET UP", "GET OUT"]


def test_a_pause_of_035_s_starts_a_new_line():
    assert lines("watch this jump", gaps={2: 0.36}) == ["WATCH THIS", "JUMP"]
    assert lines("watch this jump", gaps={2: 0.30}) == ["WATCH THIS JUMP"]


def test_punctuation_ends_a_line():
    assert lines("wait, what was that") == ["WAIT,", "WHAT WAS THAT"]
    assert lines("no way! he did it") == ["NO WAY!", "HE DID IT"]


def test_lines_stay_within_18_characters():
    out = lines("absolutely incredible helicopter landing tonight")
    assert all(len(line) <= 18 or " " not in line for line in out)
    assert out == ["ABSOLUTELY", "INCREDIBLE", "HELICOPTER LANDING", "TONIGHT"]


def test_short_word_followed_by_a_pause_stays_on_its_line():
    # "get" is short but the next word comes 0.25 s later (> 0.2 s glue): no carry.
    assert lines("we can get up there", gaps={3: 0.25}) == ["WE CAN GET", "UP THERE"]


def test_carry_never_leaves_a_word_alone():
    assert all(len(c) >= 1 for c in group_words(timed("a b c d e f g")))
    assert lines("big car had") == ["BIG CAR HAD"]          # nothing follows: no carry


def test_build_ass_uses_the_new_lines(tmp_path):
    n = build_ass(timed("oh no had to get up get out"), tmp_path / "c.ass", True, 1200, "DejaVu Sans", "pop")
    text = (tmp_path / "c.ass").read_text()
    shown = {re.sub(r"\{[^}]*\}", "", line.split(",,0,0,0,,", 1)[1]) for line in text.splitlines()
             if line.startswith("Dialogue:")}
    assert n == 4 and shown == {"OH NO", "HAD TO", "GET UP", "GET OUT"}
    assert "OH NO HAD" not in text


def test_clean_style_allows_longer_lines(tmp_path):
    assert len(group_words(timed("we are going to the airport now"), 5, 30)) == 2
