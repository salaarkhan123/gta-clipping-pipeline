"""S5 GPU plug-in points stay off by default; CPU encode/Whisper paths are unchanged."""
from pathlib import Path

from app.config import Settings, get_settings
from app.pipeline import gpu
from app.pipeline.render import FULL_ENCODE, PREVIEW_ENCODE
from app.pipeline.transcribe import FasterWhisperTranscriber
from app import worker


def test_settings_gpu_flags_default_off():
    s = Settings()
    assert s.video_encoder == "libx264"
    assert s.whisper_device == "cpu"
    assert s.nvdec is False
    # Cached settings used by the app match the same defaults.
    live = get_settings()
    assert live.video_encoder == "libx264"
    assert live.whisper_device == "cpu"
    assert live.nvdec is False


def test_video_codec_defaults_match_render_presets():
    codec, flags = gpu.video_codec_and_encode("libx264", preview=False)
    assert codec == "libx264" and flags == FULL_ENCODE
    codec, flags = gpu.video_codec_and_encode("libx264", preview=True)
    assert codec == "libx264" and flags == PREVIEW_ENCODE
    codec, flags = gpu.video_codec_and_encode("h264_nvenc", preview=False)
    assert codec == "h264_nvenc" and flags == gpu.NVENC_FULL


def test_nvdec_args_empty_when_disabled():
    assert gpu.nvdec_input_args(False) == []
    assert gpu.nvdec_input_args(True) == ["-hwaccel", "cuda"]


def test_whisper_kwargs_cpu_default():
    assert gpu.whisper_model_kwargs("cpu") == {"device": "cpu", "compute_type": "int8"}
    assert gpu.whisper_model_kwargs("cuda") == {"device": "cuda", "compute_type": "float16"}
    assert gpu.whisper_model_kwargs("") == {"device": "cpu", "compute_type": "int8"}


def test_faster_whisper_defaults_to_cpu_device():
    t = FasterWhisperTranscriber("tiny.en")
    assert t.device == "cpu"


def test_worker_transcriber_uses_settings_device(monkeypatch):
    monkeypatch.setattr(worker.get_settings(), "whisper_model", "tiny.en")
    monkeypatch.setattr(worker.get_settings(), "whisper_device", "cpu")
    t = worker.default_transcriber()
    assert t is not None
    assert t.device == "cpu"


def test_render_clip_source_still_hardcodes_libx264():
    """Production encode path must not require GPU; keep the literal until a go decision."""
    src = Path(__file__).resolve().parents[1] / "app" / "pipeline" / "render.py"
    text = src.read_text()
    assert '"-c:v", "libx264"' in text
    assert "video_codec_and_encode" in text  # comment marks the plug-in
