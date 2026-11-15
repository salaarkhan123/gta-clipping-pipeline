"""Optional "Censor swears": masked in burned captions and in SRT / VTT / TXT downloads, off by default."""
import pytest

from app import worker
from app.pipeline import render as render_mod
from app.pipeline.censor import mask, mask_words
from app.pipeline.transcribe import Transcript
from tests.test_api import upload


@pytest.mark.parametrize("word,masked", [
    ("fucking", "f***ing"), ("FUCKING", "F***ING"), ("Fuckin'", "F***in'"), ("SHIT!", "S***!"), ("shit", "s***"),
    ("motherfucker", "m***********"), ("bitch,", "b****,"), ('"shit"', '"s***"'), ("assholes", "a******s"),
])
def test_swears_keep_first_letter_and_ending(word, masked):
    assert mask(word) == masked


@pytest.mark.parametrize("word", ["Scunthorpe", "classic", "shitake", "dickens", "cocky", "hello", "pass", "GG"])
def test_whole_words_only(word):
    assert mask(word) == word


def test_times_are_unchanged():
    assert mask_words([(0.0, 0.4, "what"), (0.4, 0.9, "the"), (0.9, 1.3, "fuck")]) == \
        [(0.0, 0.4, "what"), (0.4, 0.9, "the"), (0.9, 1.3, "f***")]


class SwearingTranscriber:
    def transcribe(self, wav) -> Transcript:
        return Transcript(words=[(1.0, 1.4, "oh"), (1.4, 1.9, "shit,"), (2.0, 2.6, "fucking"), (2.6, 3.0, "sniper")],
                          segments=[(1.0, 3.0, "oh shit, fucking sniper")])


@pytest.fixture
def burned(monkeypatch):
    """The caption words each render receives (what gets burned into the video)."""
    seen = []
    real = render_mod.render_clip

    def spy(*a, **k):
        seen.append([w[2] for w in k.get("words") or []])
        return real(*a, **k)
    monkeypatch.setattr(render_mod, "render_clip", spy)
    import app.pipeline as P
    import app.pipeline.tools as T
    monkeypatch.setattr(P, "render_clip", spy)
    monkeypatch.setattr(T, "render_clip", spy)
    return seen


def clip_job(client, headers, upload_id, censor):
    options = {"max_clips": 1, "clip_length": 10}
    if censor is not None:
        options["censor"] = censor
    r = client.post("/v1/clips", json={"upload_id": upload_id, "options": options}, headers=headers)
    assert r.status_code in (200, 201, 202), r.text
    assert worker.run_once(SwearingTranscriber()) == "SUCCEEDED"
    return client.get(f"/v1/jobs/{r.json()['job_id']}", headers=headers).json()["clips"][0]


def subtitles(client, headers, clip_id):
    return {f: client.get(f"/v1/clips/{clip_id}/subtitles?format={f}", headers=headers).text for f in ("srt", "vtt", "txt")}


def test_censor_masks_burned_captions_and_every_download(client, user, video, burned):
    headers, _ = user
    up = upload(client, headers, video)
    clip = clip_job(client, headers, up["upload_id"], True)
    assert burned[-1] and "s***," in burned[-1] and "f***ing" in burned[-1] and "sniper" in burned[-1]
    for fmt, text in subtitles(client, headers, clip["id"]).items():
        assert "s***" in text and "f***ing" in text, fmt
        assert "shit" not in text.lower() and "fucking" not in text.lower(), fmt


def test_censor_is_off_by_default(client, user, video, burned):
    headers, _ = user
    up = upload(client, headers, video)
    clip = clip_job(client, headers, up["upload_id"], None)
    assert "fucking" in burned[-1]
    assert "fucking" in subtitles(client, headers, clip["id"])["txt"]


def test_captions_tool_also_censors(client, user, video, burned):
    headers, _ = user
    up = upload(client, headers, video)
    r = client.post("/v1/captions", json={"upload_id": up["upload_id"], "segments": [{"start": 0, "end": 5}],
                                          "options": {"censor": True}}, headers=headers)
    assert r.status_code in (200, 201, 202), r.text
    assert worker.run_once(SwearingTranscriber()) == "SUCCEEDED"
    assert burned and "f***ing" in burned[-1] and "fucking" not in burned[-1]
