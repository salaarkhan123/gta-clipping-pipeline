"""The impact caption style (docs/CONTRACTS.md "Caption style: impact"): one or two big upper-case words in the
bundled font, the keyword in the accent colour, on the line between the panels or in the lower third, and never
on the streamer's face. It is the default; the five older styles write exactly what they wrote before."""
import itertools
import json
import re
import struct
from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline import captions as C
from app.pipeline import layouts as L
from app.pipeline import render as R
from app.pipeline.tools import RenderOptions, run_render
from app.render_options import LayoutOptions
from app.routes_media import ClipOptions
from app.templates import TEMPLATES
from tests.test_api import balance, upload
from tests.test_layouts import (BOTTOM, CORNER, SH, SW, camera, face_of, face_pixels, frac, frame, make_stream,
                                render)
from tests.test_tools import run

GOLDEN = Path(__file__).parent / "golden"
OLD_STYLES = ("pop", "bold", "neon", "boxed", "clean")


def timed(text, gap=0.02, length=0.3, pauses=()):
    """Words spoken back to back; `pauses` are the indexes a 0.6 s silence comes before."""
    out, t = [], 0.0
    for i, w in enumerate(text.split()):
        t += 0.6 if i in pauses else 0.0
        out.append((round(t, 2), round(t + length, 2), w))
        t += length + gap
    return out


def events(path, style="Cap"):
    return [line.split(",", 9) for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("Dialogue:") and line.split(",")[3] == style]


def shown(text):
    """An event's text as it reads on screen: no override tags."""
    return re.sub(r"\{[^}]*\}", "", text)


# ---------- nothing that existed has changed ----------
def test_the_five_older_styles_write_exactly_what_they_wrote_before(tmp_path):
    """tests/golden/captions_before_impact.json was written by the renderer as it was before this style existed."""
    golden = json.loads((GOLDEN / "captions_before_impact.json").read_text())
    words = [tuple(w) for w in golden["words"]]
    assert {key.split("/")[0] for key in golden["ass"]} == set(OLD_STYLES) and len(golden["ass"]) == 20
    for key, was in golden["ass"].items():
        style, case = key.split("/")
        kw = dict(golden["cases"][case])
        vertical, top = kw.pop("vertical"), kw.pop("caption_top")
        for name in ("play", "span"):
            if name in kw:
                kw[name] = tuple(kw[name])
        n = C.build_ass(words, tmp_path / "c.ass", vertical, top, "DejaVu Sans", style, **kw)
        assert (n, (tmp_path / "c.ass").read_text(encoding="utf-8")) == (was["chunks"], was["ass"]), key
        # The impact-only arguments change nothing for them either.
        C.build_ass(words, tmp_path / "d.ass", vertical, top, "DejaVu Sans", style, center=300, accent="#FF0000", **kw)
        assert (tmp_path / "d.ass").read_text(encoding="utf-8") == was["ass"], key


def test_impact_is_the_default_and_every_game_template_keeps_its_own_style():
    assert LayoutOptions().caption_style == "impact" and ClipOptions().caption_style == "impact"
    assert ClipOptions().model_dump()["caption_style"] == "impact"            # stored with the job, so the worker draws it
    assert (LayoutOptions().caption_position, LayoutOptions().caption_accent) == ("auto", None)
    assert tuple(C.CAPTION_STYLES) == ("impact",) + OLD_STYLES
    for style in OLD_STYLES:
        assert LayoutOptions(caption_style=style).caption_style == style
    for tid, t in TEMPLATES.items():                                          # game templates keep their own style;
        wanted = ("impact",) if t["kind"] == "preset" else OLD_STYLES         # the game-type presets use the new one
        assert t["options"]["caption_style"] in wanted and t["caption_style"] == t["options"]["caption_style"], tid
    for bad in ({"caption_style": "comic"}, {"caption_position": "top"}, {"caption_accent": "lime"},
                {"caption_accent": "#12345"}, {"caption_accent": "#12345G"}):
        with pytest.raises(ValidationError):
            LayoutOptions(**bad)
    assert LayoutOptions(caption_accent="#ff4d6d", caption_position="center").caption_accent == "#ff4d6d"
    for model in (PipelineOptions, RenderOptions):                            # the worker builds both from stored options
        assert {"caption_position", "caption_accent"} <= {f.name for f in fields(model)}


# ---------- the words ----------
def test_one_or_two_words_at_a_time_and_a_third_only_when_all_three_are_short():
    def lines(text, **kw):
        return [" ".join(C.impact_text(t) for _, _, t in chunk) for chunk in C.group_impact(timed(text, **kw))]
    assert lines("oh no I had to get out of here") == ["OH NO I", "HAD TO GET", "OUT OF HERE"]     # 5, 8 and 9 characters
    assert lines("that was absolutely unbelievable honestly") == ["THAT WAS", "ABSOLUTELY UNBELIEVABLE", "HONESTLY"]
    assert lines("what the hell") == ["WHAT THE HELL"]                        # 11 characters: together
    assert lines("what the heck bro") == ["WHAT THE HECK", "BRO"]
    assert lines("damn that clutch") == ["DAMN THAT", "CLUTCH"]               # 14 characters: the third waits
    assert lines("no way, bro. run!") == ["NO WAY", "BRO", "RUN!"]            # punctuation ends a caption and is dropped
    assert lines("he is gone now", pauses=(2,)) == ["HE IS", "GONE NOW"]      # so does a pause
    for text in ("a b c d e f g", "supercalifragilistic is a word I know", "it is what it is and that is that"):
        for chunk in C.group_impact(timed(text)):
            assert 1 <= len(chunk) <= 3
            assert len(chunk) < 3 or sum(len(C.impact_text(t)) for _, _, t in chunk) <= C.IMPACT_SHORT
    assert C.group_impact([]) == []
    assert lines("big moment", ) == ["BIG MOMENT"]
    narrow = C.group_impact(timed("big moment"), fits=lambda texts: len(texts) < 2)      # no room for two on the line
    assert [len(c) for c in narrow] == [1, 1]


def test_the_keyword_is_the_longest_word_that_is_not_a_stop_word():
    assert C.keyword(["I", "JUST", "FOUND"]) == 2
    assert C.keyword(["THE", "ULTIMATE"]) == 1
    assert C.keyword(["I", "JUST"]) is None and C.keyword(["OH", "NO"]) is None and C.keyword([]) is None
    assert C.keyword(["I'M", "SO", "JEALOUS"]) == 2 and C.keyword(["DON’T", "MOVE"]) == 1
    assert C.keyword(["DAMN", "GAME"]) == 0                                    # equal length: the first
    assert C.keyword(["RUN!", "NOW"]) == 0 and C.keyword(["100", "KILLS"]) == 1 and C.keyword(["!!!"]) is None
    assert {"the", "i'm", "just", "don't"} <= C.STOP_WORDS and not {"game", "money", "today"} & C.STOP_WORDS


def test_the_ass_file_upper_case_bundled_font_size_outline_shadow_and_one_keyword_per_caption(tmp_path):
    words = timed("oh no, I just found the {ultimate} money glitch today")
    n = C.build_ass(words, tmp_path / "i.ass", True, 0, "DejaVu Sans", "impact", play=(1080, 1920), center=1344)
    text = (tmp_path / "i.ass").read_text(encoding="utf-8")
    assert "PlayResX: 1080\nPlayResY: 1920\n" in text and "ScaledBorderAndShadow: yes" in text
    m = C.impact_size(1920)
    assert (m.size, m.outline) == (232, 11)
    assert m.cap == pytest.approx(0.06 * 1920) and m.outline == pytest.approx(0.08 * m.em, abs=0.5)     # 8% of the font size
    assert 0.065 * 1920 < m.em < 0.075 * 1920 and m.half == m.cap / 2 + m.outline
    style = next(line for line in text.splitlines() if line.startswith("Style: Cap,"))
    # Anton, not bold (the face is already heavy: a faked bold would smear it), white on a black outline, no hard shadow.
    assert style.startswith("Style: Cap,Anton,232,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,")
    assert style.endswith(",0,1,11,0,5,0,0,0,1")
    shadow = next(line for line in text.splitlines() if line.startswith("Style: CapShadow,"))
    assert "&HFF000000,&HFF000000,&HFF000000,&H50000000" in shadow and shadow.endswith(f",1,11,{m.shadow},5,0,0,0,1")
    caps, shadows = events(tmp_path / "i.ass"), events(tmp_path / "i.ass", "CapShadow")
    assert n == len(caps) == len(shadows) == 5
    assert [shown(e[9]) for e in caps] == ["OH  NO", "I  JUST  FOUND", "THE  ULTIMATE", "MONEY  GLITCH", "TODAY"]
    assert [shown(e[9]) for e in shadows] == [shown(e[9]) for e in caps]
    lime = "{\\c&H3CFFB8&}"
    assert [e[9].count(lime) for e in caps] == [0, 1, 1, 1, 1]                 # one keyword at most, none among stop words
    assert lime + "FOUND{\\c&HFFFFFF&}" in caps[1][9] and lime + "ULTIMATE" in caps[2][9] and lime + "GLITCH" in caps[3][9]
    assert lime + "TODAY" in caps[4][9]
    for cap, sh in zip(caps, shadows):
        assert (cap[1], cap[2]) == (sh[1], sh[2]) and "\\blur" in sh[9] and "\\c&" not in sh[9]
        assert "\\pos(540," in cap[9] and "\\q2" in cap[9] and "\\fscx100\\fscy100" in cap[9]
        # The line hangs by the middle of the font's whole line; the capitals' middle is the row that was asked for.
        row = int(re.search(r"\\pos\(540,(\d+)\)", cap[9]).group(1))
        assert row == round(1344 - (C.ANTON_ASCENT - C.ANTON_DESCENT - C.ANTON_CAP) / 2 * m.em)
    assert all(c[1] <= c[2] for c in caps) and all(a[2] <= b[1] for a, b in zip(caps, caps[1:]))     # never two at once
    assert "{ultimate}" not in text and "ultimate" not in text                 # control characters gone, all upper case

    C.build_ass(words, tmp_path / "red.ass", True, 0, "DejaVu Sans", "impact", accent="#FF4D6D")
    red = events(tmp_path / "red.ass")
    assert "{\\c&H6D4DFF&}FOUND" in red[1][9] and "\\c&H3CFFB8&" not in (tmp_path / "red.ass").read_text()
    assert f"\\pos(540,{round(0.70 * 1920 - (C.ANTON_ASCENT - C.ANTON_DESCENT - C.ANTON_CAP) / 2 * m.em)})" in red[0][9]
    with pytest.raises(ValueError):
        C.build_ass(words, tmp_path / "bad.ass", True, 0, "DejaVu Sans", "impact", accent="lime")
    assert C.ass_colour(C.ACCENT) == "&H3CFFB8&" == C.CAPTION_STYLES["impact"]["hl"]
    assert C.HOOK_BOX.endswith("3CFFB8")                                       # the accent is the hook box's lime

    # The hook keeps its own look and the font it always had.
    C.build_ass(words, tmp_path / "h.ass", True, 0, "DejaVu Sans", "impact", hook="look at this", hook_top=345)
    hooked = (tmp_path / "h.ass").read_text()
    assert f"Style: Hook,DejaVu Sans,70,{C.HOOK_TEXT},{C.HOOK_TEXT},{C.HOOK_BOX},{C.HOOK_BOX},1,0,0,0,100,100,0,0,3,14,0,8,90,90,345,1" in hooked
    assert "Dialogue: 2,0:00:00.00,0:00:02.50,Hook,,0,0,0,,{\\fad(120,220)}LOOK AT THIS" in hooked
    assert C.build_ass([], tmp_path / "none.ass", True, 0, "DejaVu Sans", "impact") == 0


def test_a_caption_never_runs_off_the_frame_long_words_are_drawn_smaller(tmp_path):
    for play, span in (((1080, 1920), (0.0, 1.0)), ((1080, 1350), (0.0, 1.0)), ((1080, 1080), (0.0, 1.0)),
                       ((1920, 1080), (1 / 3, 1.0)), ((640, 360), (0.0, 1.0))):
        m = C.impact_size(play[1])
        room = (span[1] - span[0]) * play[0] * C.IMPACT_FILL
        words = timed("it was absolutely unbelievable supercalifragilisticexpialidocious WWWWWWWWWWWWWWWW ok I'm so jealous")
        C.build_ass(words, tmp_path / "w.ass", True, 0, "DejaVu Sans", "impact", play=play, span=span)
        caps = events(tmp_path / "w.ass")
        assert len(caps) >= 5
        for e in caps:
            texts = shown(e[9]).split(C.WORD_GAP)
            pct = int(re.search(r"\\t\(0,\d+,\\fscx(\d+)", e[9]).group(1))
            letters = C.impact_width(texts, m.em) - 2 * m.outline
            assert letters * pct / 100 + 2 * m.outline <= room + 0.5, (play, texts)     # inside the width it is centred in
            assert pct == 100 or len(texts) == 1                                # only a single long word is ever shrunk
            assert f"\\pos({round((span[0] + span[1]) / 2 * play[0])}," in e[9]
        if play[1] > play[0]:
            assert any("\\fscx100" not in e[9].split("\\t(")[1] for e in caps)  # the 34-letter word was
        assert all("\\N" not in e[9] and "\\q2" in e[9] for e in caps)          # one line, never wrapped


# ---------- the font ----------
def read_font(path):
    """(family name, licence note, units per em, win ascent, win descent, cap height, {character: advance})."""
    data = path.read_bytes()
    tables = {}
    for i in range(struct.unpack(">H", data[4:6])[0]):
        tag, _sum, off, length = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        tables[tag.decode()] = data[off:off + length]
    upm = struct.unpack(">H", tables["head"][18:20])[0]
    os2 = tables["OS/2"]
    win_ascent, win_descent = struct.unpack(">HH", os2[74:78])
    cap = struct.unpack(">h", os2[88:90])[0]
    name, names = tables["name"], {}
    count, strings = struct.unpack(">HH", name[2:6])
    for i in range(count):
        pid, _eid, _lid, nid, length, off = struct.unpack(">HHHHHH", name[6 + 12 * i:18 + 12 * i])
        if pid == 3:
            names[nid] = name[strings + off:strings + off + length].decode("utf-16-be")
    cmap = tables["cmap"]
    for i in range(struct.unpack(">H", cmap[2:4])[0]):
        pid, eid, off = struct.unpack(">HHI", cmap[4 + 8 * i:12 + 8 * i])
        if (pid, eid) == (3, 1) and struct.unpack(">H", cmap[off:off + 2])[0] == 4:
            sub = cmap[off:]
    seg2 = struct.unpack(">H", sub[6:8])[0]
    seg = seg2 // 2
    ends = struct.unpack(f">{seg}H", sub[14:14 + seg2])
    starts = struct.unpack(f">{seg}H", sub[16 + seg2:16 + 2 * seg2])
    deltas = struct.unpack(f">{seg}h", sub[16 + 2 * seg2:16 + 3 * seg2])
    base = 16 + 3 * seg2
    offsets = struct.unpack(f">{seg}H", sub[base:base + seg2])
    n_metrics = struct.unpack(">H", tables["hhea"][34:36])[0]

    def advance(ch):
        cp = ord(ch)
        for i in range(seg):
            if starts[i] <= cp <= ends[i]:
                if offsets[i] == 0:
                    glyph = (cp + deltas[i]) & 0xFFFF
                else:
                    at = base + 2 * i + offsets[i] + 2 * (cp - starts[i])
                    glyph = struct.unpack(">H", sub[at:at + 2])[0]
                    glyph = (glyph + deltas[i]) & 0xFFFF if glyph else 0
                if not glyph:
                    return None
                return struct.unpack(">H", tables["hmtx"][4 * min(glyph, n_metrics - 1):][:2])[0] / upm
        return None
    return names.get(1), names.get(13, ""), upm, win_ascent, win_descent, cap, advance


def test_the_bundled_font_is_anton_under_the_open_font_licence_and_the_numbers_match_the_file():
    font, licence = C.FONT_DIR / C.IMPACT_FILE, C.FONT_DIR / "Anton-OFL.txt"
    assert font.is_file() and font.parent.name == "fonts" and font.parent.parent.name == "app"      # inside the image: COPY app
    text = licence.read_text()
    assert text.startswith("Copyright 2020 The Anton Project Authors")
    assert "SIL OPEN FONT LICENSE Version 1.1" in text and "Reserved Font Name" in text
    assert "with Reserved Font Name" not in text                               # none is reserved: the name may be used
    family, note, upm, ascent, descent, cap, advance = read_font(font)
    assert family == C.IMPACT_FONT == "Anton" and "SIL Open Font License, Version 1.1" in note
    assert (ascent / upm, descent / upm, cap / upm) == (C.ANTON_ASCENT, C.ANTON_DESCENT, C.ANTON_CAP)
    for ch, width in C.ANTON_WIDTHS.items():
        assert advance(ch) == pytest.approx(width, abs=0.0006), ch
    assert set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !?'*") <= set(C.ANTON_WIDTHS)       # * is what a censored word has
    assert all(advance(ch) for ch in "ÉÑÜÇ")                                   # accented capitals are in the font too


# ---------- where it sits ----------
def test_auto_is_the_seam_in_a_split_and_the_lower_third_otherwise_and_the_other_three_positions():
    half = C.impact_size(1920).half
    assert L.CAPTION_POSITIONS == ("auto", "seam", "lower", "center")
    assert L.caption_y(1920, "auto", half) == L.caption_y(1920, "lower", half) == L.caption_y(1920, "seam", half) == 1344
    assert L.caption_y(1920, "center", half) == 960
    assert L.caption_y(1920, "auto", half, seam=640) == L.caption_y(1920, "seam", half, seam=640) == 640
    assert L.caption_y(1920, "lower", half, seam=640) == 1344 and L.caption_y(1920, "center", half, seam=640) == 960
    assert L.caption_y(1350, "auto", 40) == 945 and L.caption_y(1080, "lower", 40) == 756
    with pytest.raises(L.PipelineError):
        L.caption_y(1920, "top", half)
    # The plans say where the seam is: only two stacked panels have one.
    cam, face = frac(CORNER[0]), face_of(CORNER[1])
    assert L.compose(SW, SH, "split2", "9:16", cam=cam).seam == 640
    assert L.compose(SW, SH, "gameplay_b", "9:16", cam=cam).seam == 960
    assert L.compose(SW, SH, "screen_first", "9:16", cam=cam).seam == 1344
    assert L.compose(SW, SH, "split2", "9:16", cam=cam, camera="bottom", split_ratio=0.6).seam == 1152
    for name, aspect in (("full", "9:16"), ("pip", "9:16"), ("fit", "9:16"), ("split2", "16:9"), ("screen_first", "16:9")):
        assert L.compose(SW, SH, name, aspect, cam=cam, face=face).seam is None, name
    wide = L.compose(SW, SH, "split2", "16:9", cam=cam)                         # beside the camera: centred on the gameplay
    assert L.caption_center(wide, "auto", 40) == 756 and wide.text_span == (pytest.approx(1 / 3, abs=0.01), 1.0)


def test_a_caption_moves_the_least_distance_that_clears_the_head_and_stays_in_the_frame():
    half, gap = 70, L.FACE_GAP
    head = (300, 400, 780, 630)                                               # ends just above a seam at 640
    y = L.caption_y(1920, "auto", half, seam=640, head=head)
    assert y == 630 + gap + half                                              # down, onto the gameplay under the camera
    under = (300, 1160, 780, 1500)                                            # a camera under the gameplay, seam at 1152
    assert L.caption_y(1920, "auto", half, seam=1152, head=under) == 1160 - gap - half      # up, onto the gameplay
    assert L.caption_y(1920, "lower", half, head=(300, 1300, 780, 1500)) == 1300 - gap - half
    assert L.caption_y(1920, "center", half, head=(300, 800, 780, 1000)) == 1000 + gap + half
    assert L.caption_y(1920, "auto", half, seam=640, head=(300, 100, 780, 500)) == 640      # clear of it: not moved
    assert L.caption_y(1920, "lower", half, head=(0, 1300, 100, 1500), reach=(120, 960)) == 1344     # off to the side
    lo, hi = L.SAFE_ROWS[0] * 1920 + half, L.SAFE_ROWS[1] * 1920 - half
    assert L.caption_y(1920, "lower", half, head=(0, 300, 1080, 1900)) == 300 - gap - half   # no room under it: over it
    assert L.caption_y(1920, "center", half, head=(0, 0, 1080, 1920)) in (round(lo), round(hi))       # nowhere clear: an edge
    for position, seam in itertools.product(L.CAPTION_POSITIONS, (None, 100, 480, 1152, 1900)):
        assert lo - 1 <= L.caption_y(1920, position, half, seam=seam) <= hi + 1               # never off the frame


def test_no_caption_position_ever_covers_the_head_in_any_layout_ratio_or_shape():
    """The plan's head box against the caption's box, over every layout, both camera sides and every ratio."""
    checked = moved = 0
    cams = ((CORNER[0], CORNER[1]), (BOTTOM[0], BOTTOM[1]), ((40, 40, 420, 300), (200, 90, 110, 140)),
            ((700, 380, 500, 320), (860, 400, 150, 190)))
    names = [n for n in L.BUILT] + ["split"]
    for (cam_px, face_px), aspect, name, side, ratio, position, known in itertools.product(
            cams, L.ALLOWED, names, (None, "top", "bottom"), (None, 0.25, 0.4, 0.6, 0.75), L.CAPTION_POSITIONS, (True, False)):
        plan = L.compose(SW, SH, name, aspect, cam=frac(cam_px), face=face_of(face_px) if known else None, camera=side,
                         split_ratio=ratio)
        ow, oh = plan.size
        half = C.impact_size(oh).half
        y = L.caption_center(plan, position, half, C.IMPACT_FILL)
        assert L.SAFE_ROWS[0] * oh + half - 1 <= y <= L.SAFE_ROWS[1] * oh - half + 1, (plan.layout, aspect, position)
        checked += 1
        if plan.head is None:
            continue
        x0, y0, x1, y1 = plan.head
        mid = (plan.text_span[0] + plan.text_span[1]) / 2 * ow
        reach = (plan.text_span[1] - plan.text_span[0]) * ow * C.IMPACT_FILL / 2
        if x1 <= mid - reach + 1 or x0 >= mid + reach - 1:
            continue                                                          # the text never reaches that far out
        clear = y + half <= y0 or y - half >= y1
        room = (y0 - half >= L.SAFE_ROWS[0] * oh + half) or (y1 + half <= L.SAFE_ROWS[1] * oh - half)
        assert clear or not room, (plan.layout, aspect, side, ratio, position, known, y, plan.head)
        want = plan.seam if (position in ("auto", "seam") and plan.seam is not None) else oh * (0.5 if position == "center" else 0.7)
        moved += abs(y - want) > 2
    assert checked > 10000 and moved > 500
    # With a face known the head is the head; without one it is the camera picture but for its lowest part.
    known = L.compose(SW, SH, "split2", "9:16", cam=frac(CORNER[0]), face=face_of(CORNER[1]))
    blind = L.compose(SW, SH, "split2", "9:16", cam=frac(CORNER[0]))
    assert blind.head == (0.0, 0.0, 1080.0, L.BLIND_HEAD * 640) and known.head[3] <= 640 and known.head != blind.head
    assert L.caption_center(blind, "auto", 68.6) == 640                        # camera on top, no face: on the line
    under = L.compose(SW, SH, "gameplay_b", "9:16", cam=frac(CORNER[0]))
    assert L.caption_center(under, "auto", 68.6) == round(960 - L.FACE_GAP - 68.6)       # camera below: wholly on the gameplay
    assert L.compose(SW, SH, "full", "9:16").head is None and L.caption_center(L.compose(SW, SH, "full", "9:16"), "auto", 68.6) == 1344


def test_the_hook_steps_clear_of_the_caption():
    cam, face = frac(CORNER[0]), face_of(CORNER[1])
    plan = L.compose(SW, SH, "split2", "9:16", cam=cam)                        # caption on the line, hook 120 under it
    assert R.impact_rows(plan, 1920, "auto", plan.hook_top) == (640, 760)
    tight = L.compose(SW, SH, "split2", "9:16", cam=cam, face=face)
    y, hook = R.impact_rows(tight, 1920, "auto", tight.hook_top)
    half = C.impact_size(1920).half
    if y != 640:                                                              # the caption moved down off the head ...
        assert hook >= y + half + R.TEXT_GAP                                  # ... so the hook moved down with it
    for name, position in itertools.product(("split2", "gameplay_a", "gameplay_b", "screen_first", "full", "pip"),
                                            L.CAPTION_POSITIONS):
        for ratio in (None, 0.25, 0.75):
            p = L.compose(SW, SH, name, "9:16", cam=cam, face=face, split_ratio=ratio)
            y, hook = R.impact_rows(p, 1920, position, p.hook_top)
            assert hook - 14 >= y + half or hook + 110 <= y - half, (name, position, ratio)      # one line of hook, clear
            assert 0 <= hook <= 1920 - 110
    assert R.impact_rows(None, 1080, "auto", 108) == (756, 108)                # a source frame: lower third, hook on top
    assert R.impact_rows(None, 1920, "auto", 345, below_video=1294)[0] == int(1294 + half)       # classic: under the picture


# ---------- rendered ----------
def white(img):
    return (img.min(axis=2) > 215)


CYAN = "#00C2FF"     # the accent the rendered checks use: nothing else in the test stream is this colour


def lime(img):
    """The keyword's pixels (drawn in CYAN here: the stream's camera is green and its face yellow)."""
    return (img[..., 0] < 90) & (img[..., 1] > 140) & (img[..., 2] > 200)


@pytest.fixture(scope="module")
def stream(tmp_path_factory):
    return make_stream(tmp_path_factory.mktemp("impact") / "corner.mp4", *CORNER)


def test_rendered_the_bundled_font_is_what_is_drawn_where_the_plan_says_and_the_face_stays_whole(stream, tmp_path):
    words = [(0.0, 0.9, "okay"), (0.0, 0.9, "banana")]
    cam, face = frac(CORNER[0]), face_of(CORNER[1])
    bare = {}
    for name, plan in (("split", L.compose(SW, SH, "split2", "9:16", cam=cam, face=face)),
                       ("under", L.compose(SW, SH, "split2", "9:16", cam=cam, face=face, camera="bottom", split_ratio=0.6)),
                       ("full", L.compose(SW, SH, "full", "9:16"))):
        render(stream, tmp_path / f"{name}-bare.mp4", plan=plan)
        bare[name] = face_pixels(frame(tmp_path / f"{name}-bare.mp4")).sum()
        for position in L.CAPTION_POSITIONS:
            render(stream, tmp_path / "c.mp4", plan=plan, words=words, style="impact", position=position, accent=CYAN)
            img = frame(tmp_path / "c.mp4", 0.5)
            m = C.impact_size(1920)
            ink = white(img) | lime(img)
            rows, cols = np.nonzero(ink)
            assert len(rows) > 5000, (name, position)                         # the caption is there
            want = L.caption_center(plan, position, m.half, C.IMPACT_FILL)
            assert (rows.min() + rows.max()) / 2 == pytest.approx(want, abs=6), (name, position)
            assert rows.max() - rows.min() == pytest.approx(m.cap, abs=8)      # the capitals: 6% of the frame height
            # Anton is a condensed face: OKAY  BANANA is as wide as the font's own table says. Any stand-in
            # (the machine's default sans is half as wide again) fails this.
            letters = C.impact_width(["OKAY", "BANANA"], m.em) - 2 * m.outline
            assert cols.max() - cols.min() == pytest.approx(letters, rel=0.04), (name, position)
            assert (cols.min() + cols.max()) / 2 == pytest.approx(540, abs=8)
            assert cols.min() > 20 and cols.max() < 1060                      # nothing off the frame
            assert white(img).sum() > 2000 and lime(img).sum() > 3000         # OKAY white, the keyword in the accent
            assert np.nonzero(lime(img))[1].min() > np.nonzero(white(img))[1].min()      # BANANA is the second word
            # Not one pixel of the face is covered, and no caption sits in the head's rows.
            assert face_pixels(img).sum() == pytest.approx(bare[name], rel=0.002), (name, position)
            if plan.head:
                assert rows.max() < plan.head[1] or rows.min() > plan.head[3], (name, position)
    assert bare["split"] > 1000 and bare["full"] == 0


def test_rendered_at_every_size_the_caption_is_the_same_share_of_the_frame(stream, tmp_path):
    plan = L.compose(SW, SH, "split2", "9:16", cam=frac(CORNER[0]), face=face_of(CORNER[1]))
    words, seen = [(0.0, 0.9, "okay"), (0.0, 0.9, "banana")], {}
    for name, kw in (("full", {}), ("preview", {"preview": True}), ("480", {"resolution": "480"}), ("capped", {"max_side": 720})):
        info = render(stream, tmp_path / f"{name}.mp4", plan=plan, words=words, style="impact", accent=CYAN, **kw)
        img = frame(tmp_path / f"{name}.mp4", 0.5)
        rows, cols = np.nonzero(white(img) | lime(img))
        dark = (img.max(axis=2) < 40)[rows.min() - 2:rows.max() + 2, cols.min():cols.max()].mean()
        seen[name] = ((info.width, info.height), (rows.min() + rows.max()) / 2 / info.height, (rows.max() - rows.min()) / info.height,
                      (cols.max() - cols.min()) / info.width, dark)
    assert [seen[n][0] for n in ("full", "preview", "480", "capped")] == [(1080, 1920), (540, 960), (480, 852), (720, 1280)]
    for name in ("preview", "480", "capped"):
        assert seen[name][1] == pytest.approx(seen["full"][1], abs=0.006), name      # the same row
        assert seen[name][2] == pytest.approx(seen["full"][2], abs=0.006), name      # the same height
        assert seen[name][3] == pytest.approx(seen["full"][3], abs=0.02), name       # the same width
        assert seen[name][4] == pytest.approx(seen["full"][4], abs=0.06), name       # the outline scales with it


def test_rendered_in_the_source_frame_and_in_the_classic_layout(stream, tmp_path):
    words = [(0.0, 0.9, "okay"), (0.0, 0.9, "banana")]
    info = render(stream, tmp_path / "src.mp4", vertical=False, words=words, style="impact", accent=CYAN)
    img = frame(tmp_path / "src.mp4", 0.5)
    rows, cols = np.nonzero(white(img) | lime(img))
    m = C.impact_size(SH)
    assert (info.width, info.height) == (SW, SH)
    assert (rows.min() + rows.max()) / 2 == pytest.approx(0.70 * SH, abs=5) and rows.max() - rows.min() == pytest.approx(m.cap, abs=5)
    assert cols.max() - cols.min() == pytest.approx(C.impact_width(["OKAY", "BANANA"], m.em) - 2 * m.outline, rel=0.05)
    render(stream, tmp_path / "classic.mp4", layout="classic", words=words, style="impact", accent=CYAN)
    rows, _cols = np.nonzero(lime(frame(tmp_path / "classic.mp4", 0.5)))
    under = R.caption_top(SW, SH, "classic", 1.0, "none") + C.impact_size(1920).half
    assert (rows.min() + rows.max()) / 2 == pytest.approx(under, abs=6)       # under the picture, where captions always were


def test_a_missing_font_file_fails_the_render_instead_of_drawing_another_font(stream, tmp_path, monkeypatch):
    monkeypatch.setattr(R, "FONT_DIR", tmp_path / "nowhere")
    with pytest.raises(L.PipelineError) as e:
        render(stream, tmp_path / "x.mp4", layout="fill", words=[(0.0, 0.9, "okay")], style="impact")
    assert e.value.code == "captions_unavailable" and not (tmp_path / "x.mp4").exists()
    render(stream, tmp_path / "old.mp4", layout="fill", words=[(0.0, 0.9, "okay")], style="pop")      # the others need no file
    assert (tmp_path / "old.mp4").exists()


# ---------- the options reach the renderer, and cost nothing ----------
def test_the_caption_options_reach_the_renderer_from_the_pipeline_and_the_tools(video, transcriber, tmp_path, monkeypatch):
    seen = []
    real = R.render_clip

    def spy(*a, **kw):
        seen.append(kw)
        return real(*a, **kw)
    monkeypatch.setattr("app.pipeline.render_clip", spy)
    monkeypatch.setattr("app.pipeline.tools.render_clip", spy)
    sent = ClipOptions(max_clips=1, clip_length=10, caption_position="center", caption_accent="#FF4D6D").model_dump()
    run_pipeline(video, PipelineOptions(caption_font="DejaVu Sans", **sent), tmp_path / "a", transcriber=transcriber)
    assert (seen[-1]["style"], seen[-1]["position"], seen[-1]["accent"]) == ("impact", "center", "#FF4D6D")
    run_pipeline(video, PipelineOptions(max_clips=1, clip_length=10), tmp_path / "b", transcriber=transcriber)
    assert (seen[-1]["style"], seen[-1]["position"], seen[-1]["accent"]) == ("pop", "auto", None)      # a bare call: as before
    opts = RenderOptions(captions=True, caption_style="impact", caption_position="lower", caption_accent="#00C2FF")
    run_render(video, [(5, 9)], opts, tmp_path / "c", transcriber=transcriber)
    assert (seen[-1]["style"], seen[-1]["position"], seen[-1]["accent"]) == ("impact", "lower", "#00C2FF")


def test_a_job_with_the_new_caption_options_costs_what_it_cost_without_them(client, user, video, transcriber):
    headers, _ = user
    up = upload(client, headers, video)
    base = {"max_clips": 1, "clip_length": 10}
    plain = run(client, headers, "/v1/clips", {"upload_id": up["upload_id"], "options": {**base, "caption_style": "pop"}}, transcriber)
    default = run(client, headers, "/v1/clips", {"upload_id": up["upload_id"], "options": base}, transcriber)
    styled = run(client, headers, "/v1/clips", {"upload_id": up["upload_id"], "options": {
        **base, "caption_style": "impact", "caption_position": "center", "caption_accent": "#FF4D6D"}}, transcriber)
    assert plain["status"] == default["status"] == styled["status"] == "SUCCEEDED"
    assert default["options"]["caption_style"] == "impact" and default["options"]["caption_position"] == "auto"
    assert (styled["options"]["caption_position"], styled["options"]["caption_accent"]) == ("center", "#FF4D6D")
    assert plain["credits_charged"] == default["credits_charged"] == styled["credits_charged"] > 0
    assert balance(client, headers) == 30 - 3 * plain["credits_charged"]
    for bad in ({"caption_position": "top"}, {"caption_accent": "red"}, {"caption_style": "comic"}):
        r = client.post("/v1/clips", json={"upload_id": up["upload_id"], "options": bad}, headers=headers)
        assert r.status_code == 422, bad
    assert balance(client, headers) == 30 - 3 * plain["credits_charged"]        # refused before anything is reserved
    listed = client.get("/v1/options").json()["clips"]
    assert listed["caption_style"]["default"] == "impact" and listed["caption_style"]["values"][0] == "impact"
    assert listed["caption_position"] == {"type": "string", "values": ["auto", "seam", "lower", "center"], "default": "auto"}
    assert listed["caption_accent"]["nullable"] is True and listed["caption_accent"]["default"] is None
