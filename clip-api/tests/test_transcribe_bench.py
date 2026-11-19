"""scripts/transcribe_bench.py: keys stay secret, the metrics are right, and a run writes results without a key."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.pipeline import hosted_stt
from app.pipeline.transcribe import Transcript
from tests.test_hosted_stt import DEEPGRAM
from tests.test_stt import tone

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "transcribe_bench.py"
KEY = "dg-secret-key-should-never-print"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("transcribe_bench", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def keys_file(tmp_path, mode=0o600):
    p = tmp_path / "bench.env"
    p.write_text(f"DEEPGRAM_API_KEY={KEY}\nOTHER_SECRET=x\n")
    p.chmod(mode)
    return p


def test_keys_are_read_only_from_a_private_file_and_never_into_the_environment(bench, tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    assert bench.load_keys(keys_file(tmp_path)) == {"DEEPGRAM_API_KEY": KEY}      # only the names it knows
    import os
    assert "DEEPGRAM_API_KEY" not in os.environ
    for mode in (0o644, 0o606):
        with pytest.raises(SystemExit, match="chmod 600"):
            bench.load_keys(keys_file(tmp_path, mode))
    assert bench.redact(f"failed with {KEY}", {"k": KEY}) == "failed with ***"


def test_audio_goes_to_assemblyai_only_where_it_is_not_trained_on(bench):
    from argparse import Namespace
    assert bench.training_block("assemblyai", Namespace(assemblyai_region="eu", assemblyai_opted_out=False)) is None
    assert "opt out" in bench.training_block("assemblyai", Namespace(assemblyai_region="us", assemblyai_opted_out=False))
    assert bench.training_block("assemblyai", Namespace(assemblyai_region="us", assemblyai_opted_out=True)) is None
    assert bench.training_block("deepgram", Namespace(assemblyai_region="us", assemblyai_opted_out=False)) is None


def test_wer_alignment_and_timestamp_error(bench):
    ref = "Oh my god, the Oppressor is right there! Let's go."
    assert bench.norm_words(ref) == ["oh", "my", "god", "the", "oppressor", "is", "right", "there", "let's", "go"]
    assert bench.edit_distance(bench.norm_words(ref), bench.norm_words("oh my god oppressor is right here let's go go")) == 3
    assert bench.edit_distance([], ["a"]) == 1 and bench.edit_distance(["a", "b"], []) == 2
    r = [(1.0, "oh"), (1.5, "my"), (2.0, "god")]
    h = [(1.1, "oh"), (1.5, "my"), (2.4, "god"), (3.0, "extra")]
    assert [round(x, 2) for x in bench.aligned_starts(r, h)] == [0.1, 0.0, 0.4]
    assert bench.pct([0.1, 0.0, 0.4], 0.5) == 0.1 and bench.pct([], 0.5) is None


def test_terms_loops_and_words_in_non_speech(bench, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("# c\nOppressor | oppressor mk2\nAK47 | AK-47\n")
    terms = bench.load_terms(f)
    words = bench.norm_words("the oppressor mk2 and an AK-47 and an ak47")
    assert bench.term_counts(words, terms) == {"Oppressor": 1, "AK47": 2}      # one use, however many spellings match it
    assert bench.loops("thanks for watching thanks for watching thanks for watching thanks for watching".split(),
                       ["a", "b", "b", "b"]) == ["thanks for watching x4", "segment 'b' x3+"]
    assert bench.loops("no no no".split(), []) == []
    t = Transcript(words=[(1.0, 1.4, "oh"), (10.0, 10.4, "thanks"), (20.2, 20.6, "you")])
    h = bench.hallucination(t, levels=[-20.0] * 20 + [-60.0] * 5, gaps=[(8.0, 15.0)])
    assert h["words_in_nonspeech"] == 1 and h["words_in_quiet_seconds"] == 1 and h["nonspeech_sec"] == 7.0


def test_moment_sets_are_compared_by_overlap_and_rank(bench):
    base = [{"rank": i, "start_sec": s, "end_sec": s + 30} for i, s in enumerate([100, 200, 300, 400], 1)]
    mine = [{"rank": i, "start_sec": s, "end_sec": s + 30} for i, s in enumerate([205, 100, 900, 400], 1)]
    c = bench.compare_sets(mine, base)
    assert c["overlap@all"] == 0.75 and c["moments"] == 4 and c["spearman_shared"] == 0.5


def test_a_run_writes_results_and_summary_without_any_key(bench, tmp_path, monkeypatch, capsys):
    real = httpx.Client
    monkeypatch.setattr(hosted_stt.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=DEEPGRAM)), **kw))
    wav = tone(tmp_path / "in.wav", 62)
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps({"words": [[1.0, 1.2, "Oh"], [1.2, 1.4, "my"], [1.45, 1.8, "god"], [3.0, 3.2, "no"],
                                         [3.2, 3.6, "way"]], "note": "test"}))
    out = tmp_path / "out"
    assert bench.main(["--audio", str(wav), "--out", str(out), "--providers", "deepgram,groq",
                       "--keys-file", str(keys_file(tmp_path)), "--reference", str(ref)]) == 0
    printed = capsys.readouterr().out
    res = json.loads((out / "results.json").read_text())
    dg, groq = res["providers"]
    assert dg["status"] == "ok" and dg["accuracy"]["wer"] == 0.0 and dg["accuracy"]["ts_median_sec"] == 0.0
    assert dg["accuracy"]["speaker_turns"] == 2 and dg["billed_sec"] == 61.5
    assert dg["cost_usd"] == pytest.approx(61.5 / 3600 * 0.258, abs=1e-4) and dg["usd_per_2h_vod"] == 0.516
    assert groq["status"] == "skipped"                                               # no key for it
    everything = printed + "".join(p.read_text() for p in out.rglob("*") if p.is_file())
    assert KEY not in everything and "keys: groq no, deepgram yes" in printed
    assert "| deepgram:nova-3 | ok |" in (out / "summary.md").read_text()
    assert not list(out.glob("tbench_*"))                                            # the WAV is gone


def test_moments_are_picked_from_a_given_transcript(bench, video):
    from app.pipeline.stt import extract_audio
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        audio = extract_audio(video, Path(d) / "a.wav")
        t = Transcript(words=[(21.0, 21.4, "oh"), (21.4, 21.8, "my"), (21.8, 22.2, "god")],
                       segments=[(21.0, 22.2, "oh my god")])
        moments = bench.select_moments(video, t, audio, None, "0-90")
    assert moments and moments[0]["rank"] == 1 and moments[0]["start_sec"] <= 21 <= moments[0]["end_sec"]
