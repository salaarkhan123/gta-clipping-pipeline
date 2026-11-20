"""scripts/bench_nvenc.py exits cleanly without a GPU and never fabricates NVENC timings."""
import importlib.util
import json
from pathlib import Path

from app.pipeline.gpu import SKIPPED_NO_NVENC, probe_nvenc

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bench_nvenc.py"


def load_script():
    spec = importlib.util.spec_from_file_location("bench_nvenc", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_probe_nvenc_skips_without_gpu():
    ok, detail = probe_nvenc()
    # This CI / cloud host has no NVIDIA driver (measured elsewhere as missing libcuda).
    if not ok:
        assert detail == SKIPPED_NO_NVENC


def test_cli_skips_cleanly_on_cpu_host(capsys):
    mod = load_script()
    code = mod.main(["--seconds", "1", "--runs", "1"])
    assert code == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    report = json.loads(line)
    assert report["libx264"] is not None
    assert report["libx264"]["wall_seconds_mean"] > 0
    ok, _ = probe_nvenc()
    if ok:
        assert report["status"] == "ok"
        assert report["nvenc"] is not None
    else:
        assert report["status"] == SKIPPED_NO_NVENC
        assert report["nvenc"] is None
        assert "skipped: no NVENC" in json.dumps(report)


def test_cli_rejects_missing_file(tmp_path):
    assert load_script().main([str(tmp_path / "missing.mp4")]) == 2


def test_optional_probes_do_not_crash(capsys):
    code = load_script().main(["--seconds", "1", "--nvdec-probe", "--whisper-probe"])
    assert code == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report["nvdec"] is not None and "detail" in report["nvdec"]
    assert report["cuda_whisper"] is not None and "detail" in report["cuda_whisper"]
