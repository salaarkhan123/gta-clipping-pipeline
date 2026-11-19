"""Text-based caption editing (exports.EditWord, GET /v1/clips/{id}/words): edit words, hide a caption, cut a word
with its video, highlight, add emoji, split; saved in the clip's edit and rendered exactly by the export."""
import numpy as np
import pytest
from pydantic import ValidationError

from app import worker
from app.exports import ClipEditDoc
from app.pipeline import captions as C
from app.pipeline.censor import mask_words
from tests.test_api import upload
from tests.test_export import run_clips, short_side
from tests.test_impact_captions import events, shown, stream  # noqa: F401 (fixture)
from tests.test_layouts import frame, render


def doc(words, **kw):
    return ClipEditDoc.model_validate({"trim": {"start": 10.0, "end": 20.0}, "cuts": [], "words": words, **kw})


W = [{"start": 11.0, "end": 11.4, "text": "oh"}, {"start": 11.4, "end": 11.8, "text": "my"},
     {"start": 11.8, "end": 12.4, "text": "god", "highlight": "#FF3355", "emoji": "🔥"},
     {"start": 13.0, "end": 13.5, "text": "umm", "cut": True},
     {"start": 14.0, "end": 14.5, "text": "secret", "hidden": True},
     {"start": 15.0, "end": 15.4, "text": "no", "break_before": True}, {"start": 15.4, "end": 15.9, "text": "WAY"}]


def test_the_edit_keeps_each_words_time_and_marks():
    d = doc(W)
    words = d.caption_words()
    assert [(s, e, str(t)) for s, e, t in words] == [(11.0, 11.4, "oh"), (11.4, 11.8, "my"), (11.8, 12.4, "god"),
                                                   (15.0, 15.4, "no"), (15.4, 15.9, "WAY")]   # hidden and cut gone
    god = words[2][2]
    assert (god.highlight, god.emoji, god.brk) == ("#FF3355", "🔥", False) and words[3][2].brk
    assert d.segments() == [[10.0, 13.0], [13.5, 20.0]]                       # the cut word's video goes too
    assert doc(None).caption_words() == [] and doc(None, caption_lines=[{"start": 11, "end": 12, "text": "a b"}]) \
        .caption_words() == [(11.0, 11.5, "a"), (11.5, 12.0, "b")]
    for bad in ({"emoji": "lol"}, {"text": "{\\b1}x"}, {"end": 10.5}, {"highlight": "red"}, {"text": "  "}):
        with pytest.raises(ValidationError):
            doc([{"start": 11.0, "end": 11.4, "text": "ok", **bad}])


def test_the_ass_file_draws_highlight_emoji_and_split(tmp_path):
    words = [(s - 10, e - 10, t) for s, e, t in doc(W).caption_words()]
    words = mask_words(words)
    C.build_ass(words, tmp_path / "e.ass", True, 0, "DejaVu Sans", "impact", accent="#00C2FF")
    caps = events(tmp_path / "e.ass")
    lines = list(dict.fromkeys(shown(e[9]) for e in caps))
    assert lines[-1].startswith("NO") and not any("GOD" in x and "NO" in x.split() for x in lines)   # split at "no"
    god = next(e[9] for e in caps if "GOD" in shown(e[9]))
    assert "\\c&H5533FF&" in god.split("GOD")[0].rsplit("{", 1)[1]           # the user's colour on GOD
    assert "{\\fnNoto Emoji} 🔥{\\fnAnton}" in god                             # the emoji after it, in the emoji font
    swore = mask_words([(0.0, 0.5, C.Word.of("shit", highlight="#00FF00"))])[0][2]
    assert swore == "s***" and swore.highlight == "#00FF00"                  # censor keeps the marks


def test_rendered_the_emoji_is_drawn(stream, tmp_path):
    plain = [(0.0, 0.9, "okay")]
    marked = [(0.0, 0.9, C.Word.of("okay", emoji="🔥"))]
    ink = {}
    for name, words in (("plain", plain), ("emoji", marked)):
        render(stream, tmp_path / f"{name}.mp4", words=words, style="impact")
        img = frame(tmp_path / f"{name}.mp4", 0.5)
        cols = np.nonzero(img.min(axis=2) > 215)[1]
        ink[name] = (cols.min(), cols.max())
    # The line is wider by the emoji, and still centred.
    assert ink["emoji"][1] - ink["emoji"][0] > ink["plain"][1] - ink["plain"][0] + 60
    assert ink["emoji"][0] < ink["plain"][0]


def test_edit_words_through_the_api_and_the_export(client, user, video, transcriber, tmp_path):
    headers, _ = user
    up = upload(client, headers, video)
    job = run_clips(client, headers, up["upload_id"], {"max_clips": 1, "clip_length": 10, "render": "none"}, transcriber)
    clip = job["clips"][0]
    got = client.get(f"/v1/clips/{clip['id']}/words", headers=headers).json()
    assert got["edited"] is False and all(set(w) >= {"start", "end", "text", "hidden", "cut"} for w in got["words"])
    assert client.get("/v1/clips/nope/words", headers=headers).status_code == 404
    start, end = clip["segments"][0][0], clip["segments"][-1][1]
    words = [{"start": start + 1.0, "end": start + 1.5, "text": "edited"},
             {"start": start + 2.0, "end": start + 4.0, "text": "gone", "cut": True},
             {"start": start + 5.0, "end": start + 5.5, "text": "wow", "emoji": "🔥", "highlight": "#FF3355"}]
    edit = {"trim": {"start": start, "end": end}, "cuts": [], "words": words}
    r = client.patch(f"/v1/clips/{clip['id']}", json={"edit": edit}, headers=headers)
    assert r.status_code == 200, r.text
    back = client.get(f"/v1/clips/{clip['id']}/words", headers=headers).json()
    assert back["edited"] is True and [w["text"] for w in back["words"]] == ["edited", "gone", "wow"]
    bad = {**edit, "words": [{**words[0], "emoji": "no"}]}
    assert client.patch(f"/v1/clips/{clip['id']}", json={"edit": bad}, headers=headers).status_code == 422
    r = client.post("/v1/clips/export", json={"job_id": job["job_id"], "options": {"caption_style": "impact"}},
                    headers=headers)
    assert r.status_code == 202 and worker.run_once(transcriber) == "SUCCEEDED"
    out = client.get(f"/v1/jobs/{job['job_id']}", headers=headers).json()["clips"][0]
    _w, _h, length = short_side(client, out["export_url"], tmp_path)
    assert abs(length - (end - start - 2.0)) < 0.5                           # the cut word's 2 s are gone
