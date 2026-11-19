"""Every ffmpeg and ffprobe input in app/ is read with `-protocol_whitelist file,pipe` (ff.SAFE_IN), so a crafted
file (an HLS or concat playlist, for example) cannot make ffmpeg open a network address or another protocol."""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def unguarded_inputs() -> list[str]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            if '"-i"' not in line:
                continue
            context = " ".join(lines[max(0, i - 4):i + 1])        # the argv is built over a few lines
            if "SAFE_IN" in context or "protocol_whitelist" in context or "lavfi" in context:
                continue
            found.append(f"{path.relative_to(APP.parent)}:{i + 1}: {line.strip()}")
    return found


def test_every_ffmpeg_input_has_the_protocol_whitelist():
    assert unguarded_inputs() == [], "add *SAFE_IN (app/pipeline/ff.py) before these -i"


def test_the_scan_finds_an_input_without_it(tmp_path, monkeypatch):
    assert re.search(r"SAFE_IN = \[\"-protocol_whitelist\", \"file,pipe\"\]",
                     (APP / "pipeline" / "ff.py").read_text())
    bad = tmp_path / "app" / "x.py"
    bad.parent.mkdir()
    bad.write_text('run(["ffmpeg", "-y", "-i", src, out])\n')
    monkeypatch.setattr("tests.test_ffmpeg_inputs.APP", bad.parent)
    assert len(unguarded_inputs()) == 1
