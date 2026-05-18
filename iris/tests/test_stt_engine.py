"""STT 프롬프트·장치 해석 테스트."""

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
