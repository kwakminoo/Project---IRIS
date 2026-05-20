"""STT 프롬프트·장치 해석 테스트."""

from unittest.mock import patch

from iris.audio.stt_engine import build_stt_initial_prompt, resolve_stt_device_compute
from iris.config.settings import load_settings


def test_build_stt_initial_prompt_includes_wake_words() -> None:
    settings = load_settings()
    prompt = build_stt_initial_prompt(settings)
    assert "아이리스" in prompt or "iris" in prompt.lower()


def test_resolve_stt_device_cpu_fallback() -> None:
    from dataclasses import replace

    settings = load_settings()
    forced = replace(settings, stt_device="cpu", stt_compute_type="int8")
    device, compute = resolve_stt_device_compute(forced)
    assert device == "cpu"
    assert compute == "int8"


def test_resolve_stt_auto_uses_cpu_when_cuda_runtime_not_ready() -> None:
    from dataclasses import replace

    settings = replace(load_settings(), stt_device="auto", stt_compute_type="auto")
    with patch("iris.audio.stt_engine.cuda_runtime_ready", return_value=False):
        device, compute = resolve_stt_device_compute(settings)
    assert device == "cpu"
    assert compute == "int8"
