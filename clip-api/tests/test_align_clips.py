"""Placing another tool's clips in the source by audio (align_clips.py, label_moments.py wayin), on encoded media:
pieces cut out of a source and re-encoded (one with a gap cut out, one louder) are found at their true span, and a
clip from another recording is refused rather than guessed.

Set ALIGN_REAL_SOURCE to a long real recording to run the same check on it (opt-in: not in the repo)."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod                       # dataclasses look their module up while it loads
    spec.loader.exec_module(mod)
    return mod


al, lm = load("align_clips"), load("label_moments")
FF = ["ffmpeg", "-loglevel", "error", "-y", "-protocol_whitelist", "file,pipe"]
ENC = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "35", "-c:a", "aac", "-b:a", "96k"]


def recording(path: Path, seconds: int, seed: int) -> Path:
    """Speech-like audio: pink noise under a slowly changing loudness and a wandering tone, with a test picture."""
    audio = (f"anoisesrc=color=pink:seed={seed}:duration={seconds}:sample_rate=16000,"
             f"volume='0.15+0.85*abs(sin(t*1.3+{seed}))*abs(sin(t*0.37))':eval=frame[n];"
             f"aevalsrc='0.2*sin(2*PI*(300+200*sin(t*0.21+{seed}))*t)':d={seconds}:s=16000[t];[n][t]amix=2")
    subprocess.run([*FF, "-f", "lavfi", "-i", f"testsrc2=size=160x90:rate=10:duration={seconds}",
                    "-filter_complex", audio, *ENC, "-shortest", str(path)], check=True)
    return path


def cut(src: Path, out: Path, start: float, length: float, gap: tuple[float, float] | None = None,
        audio: str = "anull") -> Path:
    """[start, start + length] of src, re-encoded; `gap` (seconds into the piece) is cut out of the middle."""
    if gap is None:
        subprocess.run([*FF, "-ss", str(start), "-t", str(length), "-i", str(src), "-af", audio, *ENC, str(out)],
                       check=True)
        return out
    a, b = gap
    graph = (f"[0:v]split[v1][v2];[0:a]asplit[a1][a2];[v1]trim=0:{a},setpts=PTS-STARTPTS[va];"
             f"[a1]atrim=0:{a},asetpts=PTS-STARTPTS[aa];[v2]trim={b}:{length},setpts=PTS-STARTPTS[vb];"
             f"[a2]atrim={b}:{length},asetpts=PTS-STARTPTS[ab];[va][aa][vb][ab]concat=n=2:v=1:a=1[v][a]")
    subprocess.run([*FF, "-ss", str(start), "-t", str(length), "-i", str(src), "-filter_complex", graph,
                    "-map", "[v]", "-map", "[a]", *ENC, str(out)], check=True)
    return out


def check_pieces(src: Path, folder: Path, other: Path, starts: tuple[float, float, float]) -> dict:
    folder.mkdir()
    a, b, c = starts
    cut(src, folder / "01_plain.mp4", a, 40, audio="loudnorm")
    cut(src, folder / "02_gap.mp4", b, 60, gap=(20, 35))                 # 15 s of the middle cut out
    cut(src, folder / "03_louder.mp4", c, 30, audio="volume=6dB")
    cut(other, folder / "04_elsewhere.mp4", 30, 30)
    out = folder.parent / "run.json"
    assert lm.main(["wayin", str(src), str(folder), str(out)]) == 0
    return json.loads(out.read_text())


def assert_spans(run: dict, starts: tuple[float, float, float]) -> None:
    a, b, c = starts
    spans = {x["file"]: (x["start_sec"], x["end_sec"], x["rank"]) for x in run["clips"]}
    assert set(spans) == {"01_plain.mp4", "02_gap.mp4", "03_louder.mp4"}
    for name, (s0, e0, rank) in {"01_plain.mp4": (a, a + 40, 1), "02_gap.mp4": (b, b + 60, 2),
                                 "03_louder.mp4": (c, c + 30, 3)}.items():
        s, e, r = spans[name]
        assert abs(s - s0) <= 0.1 and abs(e - e0) <= 0.1 and r == rank, (name, s, e)
    gap = next(x for x in run["clips"] if x["file"] == "02_gap.mp4")["match"]
    assert abs(gap["trimmed"] - 15) <= 0.2 and gap["clip_seconds"] == pytest.approx(45, abs=0.2)
    assert all(x["match"]["start_confidence"] >= al.MIN_CONFIDENCE for x in run["clips"])
    assert [x["file"] for x in run["refused"]] == ["04_elsewhere.mp4"] and run["system"] == "wayin"


def test_cut_pieces_are_found_at_their_true_span_and_a_stranger_is_refused(tmp_path):
    src, other = recording(tmp_path / "src.mp4", 420, 1), recording(tmp_path / "other.mp4", 90, 9)
    starts = (61.0, 200.0, 333.0)
    assert_spans(check_pieces(src, tmp_path / "clips", other, starts), starts)


@pytest.mark.skipif(not os.environ.get("ALIGN_REAL_SOURCE"), reason="set ALIGN_REAL_SOURCE to a long recording")
def test_the_same_on_a_real_recording(tmp_path):
    src = Path(os.environ["ALIGN_REAL_SOURCE"])
    other = recording(tmp_path / "other.mp4", 90, 9)
    starts = (2400.0, 4608.0, 641.0)
    assert_spans(check_pieces(src, tmp_path / "clips", other, starts), starts)


def test_a_clip_under_four_seconds_is_refused(tmp_path):
    src = recording(tmp_path / "src.mp4", 60, 2)
    short = cut(src, tmp_path / "short.mp4", 10, 3)
    m = al.align(al.Source.of(src), short)
    assert not m.ok and m.why == "clip under 4 s: too short to align"
