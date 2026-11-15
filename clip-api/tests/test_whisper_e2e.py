"""Opt-in end-to-end check with the real faster-whisper model (downloads ~75 MB tiny.en on first run).

    RUN_WHISPER_E2E=1 pytest -q tests/test_whisper_e2e.py
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.pipeline import PipelineOptions, run_pipeline
from app.pipeline.ff import SAFE_IN, probe, run
from app.pipeline.transcribe import FasterWhisperTranscriber, extract_wav

PHRASE = "clutch clips makes short videos"
SPEECH_AT = (5, 25)  # seconds into the 40 s clip

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_WHISPER_E2E"),
                                reason="opt-in: set RUN_WHISPER_E2E=1 to run the real faster-whisper test")


def _synthesize(dest: Path) -> Path:
    """Speak PHRASE to an audio file with whichever synthesizer is installed, or skip naming the missing tool."""
    if shutil.which("say"):
        cmd = ["say", "-o", str(dest), PHRASE]
    elif shutil.which("espeak-ng"):
        cmd = ["espeak-ng", "-w", str(dest), PHRASE]
    else:
        pytest.skip("no speech synthesizer on PATH: install macOS `say` or Linux `espeak-ng`")
    subprocess.run(cmd, check=True, timeout=60)
    return dest


@pytest.fixture(scope="module")
def spoken_clip(tmp_path_factory) -> Path:
    """40 s clip: the `video` fixture's test pattern, silence, PHRASE spoken at ~5 s and ~25 s."""
    tmp = tmp_path_factory.mktemp("whisper_e2e")
    speech = _synthesize(tmp / "speech.aiff")
    out = tmp / "spoken.mp4"
    delays = ";".join(f"[2:a]adelay={t * 1000}|{t * 1000}[s{i}]" for i, t in enumerate(SPEECH_AT))
    run(["ffmpeg", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15:duration=40",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=40",
         *SAFE_IN, "-i", speech,
         "-filter_complex", f"{delays};[1:a][s0][s1]amix=inputs=3:normalize=0:duration=first[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-t", "40", out], cap=120)
    return out


@pytest.fixture(scope="module")
def whisper():
    return FasterWhisperTranscriber("tiny.en")


def test_real_whisper_hears_the_phrase(spoken_clip, whisper, tmp_path):
    wav = tmp_path / "all.wav"
    extract_wav(spoken_clip, 0, 40, wav)
    text = " ".join(w for _, _, w in whisper.transcribe(wav).words).lower()
    assert "clutch" in text and "clips" in text, f"transcript was: {text!r}"


def test_run_pipeline_with_real_whisper(spoken_clip, whisper, tmp_path):
    results = run_pipeline(spoken_clip, PipelineOptions(max_clips=1, clip_length=10, chat_region="top-right"),
                           tmp_path / "out", None, whisper)
    assert len(results) >= 1
    info = probe(results[0].video_path)
    assert results[0].video_path.exists() and info.width > 0 and info.height > 0 and info.duration > 0
