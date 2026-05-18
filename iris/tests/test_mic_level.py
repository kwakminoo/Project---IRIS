"""마이크 레벨 변환 단위 테스트."""

from iris.audio.mic_level import (
    MIC_LEVEL_SCALE,
    display_level_to_speech_rms,
    rms_to_display_level,
    speech_rms_to_display_level,
)


def test_rms_roundtrip() -> None:
    rms = 0.018
    display = speech_rms_to_display_level(rms)
    assert abs(display_level_to_speech_rms(display) - rms) < 1e-9


def test_display_capped_at_one() -> None:
    assert rms_to_display_level(1.0) == 1.0
    assert rms_to_display_level(0.2) == 1.0


def test_scale_matches_continuous_listen() -> None:
    assert MIC_LEVEL_SCALE == 12.0
    assert rms_to_display_level(0.018) == 0.018 * 12.0
