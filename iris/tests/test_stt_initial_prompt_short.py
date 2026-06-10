"""initial_prompt — 설명형 문장 제거."""

from dataclasses import replace

from iris.audio.stt_engine import build_stt_initial_prompt
from iris.config.settings import load_settings


def test_default_prompt_has_no_descriptive_sentence() -> None:
    settings = load_settings()
    prompt = build_stt_initial_prompt(settings)
    assert "한국어 음성 비서" not in prompt
    assert "호출어와 명령" not in prompt


def test_custom_prompt_used_when_set() -> None:
    settings = replace(load_settings(), stt_initial_prompt="아이리스, iris, 이리스")
    prompt = build_stt_initial_prompt(settings)
    assert prompt == "아이리스, iris, 이리스"
