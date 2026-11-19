"""caption_look (render_options.CaptionLook): font, weight, slant, underline, colours, size, case and row of impact
captions, drawn by the one renderer previews and exports share; the fonts we ship (pipeline/fonts.py)."""
import numpy as np
import pytest
from pydantic import ValidationError

from app.pipeline import captions as C
from app.pipeline import fonts as F
from app.pipeline import layouts as L
from app.pipeline import render as R
from app.pipeline.ff import PipelineError
from app.render_options import CaptionLook, LayoutOptions
from tests.test_impact_captions import CYAN, events, lime, shown, stream, timed  # noqa: F401 (fixture)
from tests.test_layouts import frame, make_stream, render  # noqa: F401


def style_line(path, name="Cap"):
    return next(line for line in path.read_text().splitlines() if line.startswith(f"Style: {name},")).split(",")


def test_every_shipped_family_is_a_real_font_with_its_licence():
    for family, spec in F.FAMILIES.items():
        for (weight, italic), name in spec["files"].items():
            face = F.read_face(F.FONT_DIR / name)
            assert face.family == spec["name"], name
            assert face.italic == italic and abs(face.weight - F.WEIGHTS[weight]) <= 100, name
            assert 0.5 < face.cap < 1 and face.ascent > face.cap
        stem = spec["files"][("regular", False)].split("-")[0]
        assert any((F.FONT_DIR / f"{stem}-{lic}").is_file() for lic in ("OFL.txt", "LICENSE.txt")), family
    assert F.bundled("poppins", "black", True).file.name == "Poppins-BlackItalic.ttf"
    assert F.bundled("bebas", "black", True).file.name == "BebasNeue-Regular.ttf"      # the nearest it has
    # Anton read from its file agrees with the numbers the impact style was built on.
    anton = F.bundled()
    assert anton.cap == pytest.approx(C.ANTON_CAP) and anton.ascent == pytest.approx(C.ANTON_ASCENT)


def test_a_file_that_is_not_a_font_is_refused_with_a_reason(tmp_path):
    for data, why in ((b"PK\x03\x04 a zip", "not a TrueType"), (b"\x00\x01\x00\x00\x00\x02" + b"\x00" * 6, "damaged"),
                      ((F.FONT_DIR / "Anton-Regular.ttf").read_bytes()[:400], "damaged")):
        bad = tmp_path / "x.ttf"
        bad.write_bytes(data)
        F.read_face.cache_clear()
        with pytest.raises(F.BadFont, match=why):
            F.read_face(bad)


def test_the_option_is_checked():
    assert LayoutOptions(caption_look={"font": "poppins", "weight": "black", "colour": "#FF3355"}).caption_look.font == "poppins"
    assert LayoutOptions(caption_look={"font": "custom:abc123def"}).caption_look.font == "custom:abc123def"
    for bad in ({"font": "comic sans"}, {"colour": "red"}, {"size": 300}, {"y": 0.99}, {"case": "lower"}, {"blink": True}):
        with pytest.raises(ValidationError):
            LayoutOptions(caption_look=bad)
    assert "caption_look" not in LayoutOptions().model_dump()                   # stored only when sent
    assert CaptionLook().model_dump()["case"] == "upper"


def test_the_ass_file_takes_the_font_weight_slant_underline_colours_size_and_case(tmp_path):
    words = timed("he said Okay banana")
    look = {"font": "poppins", "weight": "black", "italic": True, "underline": True, "colour": "#FF3355",
            "outline_colour": "#102030", "size": 150, "case": "as_typed"}
    face = R.caption_face(look)
    C.build_ass(words, tmp_path / "l.ass", True, 0, "DejaVu Sans", "impact", look=look, face=face)
    cap = style_line(tmp_path / "l.ass")
    m = C.impact_size(1920, face, 1.5)
    assert cap[1:4] == ["Poppins", str(m.size), "&H005533FF"] and cap[5] == "&H00302010"
    assert cap[7:11] == ["900", "-1", "-1", "0"]                              # black, italic, underlined
    assert m.cap == pytest.approx(1.5 * C.IMPACT_CAP * 1920)
    said = [shown(e[9]) for e in events(tmp_path / "l.ass")]
    assert said[0].startswith("he") and "Okay" in " ".join(said) and "OKAY" not in " ".join(said)   # as typed
    C.build_ass(words, tmp_path / "d.ass", True, 0, "DejaVu Sans", "impact")
    assert style_line(tmp_path / "d.ass")[1:4] == ["Anton", str(C.impact_size(1920).size), "&H00FFFFFF"]


def test_the_font_is_resolved_or_the_job_fails_clearly(tmp_path):
    assert R.caption_face(None) is None and R.caption_face({"size": 120}) is None
    assert R.caption_face({"weight": "bold"}).family == "Anton"
    with pytest.raises(PipelineError) as e:
        R.caption_face({"font": "custom:abcdef12"})
    assert e.value.code == "caption_font_missing"
    junk = tmp_path / "f.ttf"
    junk.write_bytes(b"nope")
    with pytest.raises(PipelineError) as e:
        R.caption_face({"font": "custom:abcdef12"}, junk)
    assert e.value.code == "caption_font_bad"
    assert R.caption_face({"font": "custom:abcdef12"}, F.FONT_DIR / "Bangers-Regular.ttf").family == "Bangers"


def test_a_chosen_row_is_kept_but_never_on_the_head():
    plan = L.compose(1920, 1080, "full", "9:16", scene="gameplay")
    assert R.impact_rows(plan, 1920, "auto", 300, want=0.4 * 1920)[0] == round(0.4 * 1920)
    boxes = {"canvas": [1080, 1920], "keep_out": [[0, 700, 1080, 860]], "text_span": [0, 1]}
    y, _ = R.impact_rows(None, 1920, "auto", 300, boxes=boxes, want=0.4 * 1920)
    assert y + C.impact_size(1920).half <= 700 or y - C.impact_size(1920).half >= 860


def test_rendered_the_look_is_what_is_drawn(stream, tmp_path):
    """The preview and the export are the same renderer: the chosen font's width, the size and the colour show."""
    plan = None
    words = [(0.0, 0.9, "okay"), (0.0, 0.9, "banana")]
    look = {"font": "poppins", "weight": "bold", "colour": "#FFC8FF", "size": 60}   # pink: nowhere in the stream
    face = R.caption_face(look)
    for kw in ({}, {"preview": True}):
        info = render(stream, tmp_path / "l.mp4", plan=plan, words=words, style="impact", accent=CYAN, look=look, **kw)
        img = frame(tmp_path / "l.mp4", 0.5)
        k = info.height / 1920
        red = (img[..., 0] > 220) & (img[..., 1] > 150) & (img[..., 1] < 235) & (img[..., 2] > 220)
        rows, cols = np.nonzero(red | lime(img))
        assert red.sum() > 2000 * k * k and lime(img).sum() > 1000 * k * k     # OKAY in the colour, the keyword accented
        m = C.impact_size(1920, face, 0.6)
        grow = C.ACTIVE_POP[1]                                                # BANANA is being said: grown
        assert (rows.max() - rows.min()) / k == pytest.approx(m.cap * grow, abs=12)   # 60% of the style's size
        letters = (C.impact_width(["OKAY", ""], m.em, face) + C.impact_width(["BANANA"], m.em, face) * grow
                   - 4 * m.outline)
        # Poppins Bold is far wider than Anton: the width shows which font was drawn.
        assert (cols.max() - cols.min()) / k == pytest.approx(letters, rel=0.06)
