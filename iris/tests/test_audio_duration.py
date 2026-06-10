"""audio_duration 유틸 테스트."""

from iris.audio.audio_duration import estimate_speech_duration_ms


def test_estimate_speech_duration_scales_with_text_and_rate() -> None:
    short = estimate_speech_duration_ms("안녕", speaking_rate=1.0)
    long = estimate_speech_duration_ms("안녕하세요 반갑습니다", speaking_rate=1.0)
    fast = estimate_speech_duration_ms("안녕하세요 반갑습니다", speaking_rate=1.5)

    assert long > short
    assert fast < long
