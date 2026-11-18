"""The render output that existed before trio, grid4, ots, export and the hook options stays byte for byte the same."""
import json
from pathlib import Path

from app.pipeline import captions as C
from app.pipeline import layouts as L

GOLDEN = json.loads((Path(__file__).parent / "golden" / "render_before_b3.json").read_text())
SOURCE = (1280, 720)


def test_every_layout_graph_built_before_is_unchanged():
    assert len(GOLDEN["graphs"]) == 75
    for key, was in GOLDEN["graphs"].items():
        aspect, layout, cam_name = key.split("/")
        cam, face = GOLDEN["cams"][cam_name]
        plan = L.compose(*SOURCE, layout, aspect, cam=cam, face=face)
        now = {"layout": plan.layout, "graph": L.layout_graph(plan), "caption_top": plan.caption_top,
               "hook_top": plan.hook_top, "seam": plan.seam, "text_span": list(plan.text_span),
               "head": list(plan.head) if plan.head else None}
        assert now == was, key


def test_every_caption_style_built_before_is_unchanged(tmp_path):
    words = [tuple(w) for w in GOLDEN["words"]]
    assert len(GOLDEN["ass"]) == 30
    for key, was in GOLDEN["ass"].items():
        style, case = key.split("/")
        kw = dict(GOLDEN["cases"][case])
        vertical, top = kw.pop("vertical"), kw.pop("caption_top")
        for name in ("play", "span"):
            if name in kw:
                kw[name] = tuple(kw[name])
        n = C.build_ass(words, tmp_path / "c.ass", vertical, top, "DejaVu Sans", style, **kw)
        assert (n, (tmp_path / "c.ass").read_text(encoding="utf-8")) == (was["chunks"], was["ass"]), key
