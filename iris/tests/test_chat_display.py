from iris.ui.chat_display import (
    chat_body_to_html,
    effective_typing_duration_ms,
    extend_typing_timeline_ms,
    markdown_to_plain,
    normalize_chat_body,
    scale_typing_duration_ms,
    strip_speaker_prefix,
    typing_target_index,
)


def test_strip_iris_prefix() -> None:
    assert strip_speaker_prefix("Iris", "Iris: 안녕하세요") == "안녕하세요"
    assert strip_speaker_prefix("Iris", "iris: 테스트") == "테스트"
    assert strip_speaker_prefix("나", "Iris: 유지") == "Iris: 유지"


def test_markdown_to_plain() -> None:
    assert markdown_to_plain("*입력 중인* 실시간") == "입력 중인 실시간"
    assert markdown_to_plain("**굵게** 보통") == "굵게 보통"
    assert markdown_to_plain("- 항목") == "항목"


def test_normalize_chat_body() -> None:
    raw = "Iris: 현재 *입력 중인* 내용은 읽을 수 없습니다."
    assert normalize_chat_body("Iris", raw) == "현재 입력 중인 내용은 읽을 수 없습니다."


def test_chat_body_to_html_uses_br_not_raw_newlines() -> None:
    assert chat_body_to_html("첫 줄\n둘째 줄") == "첫 줄<br>둘째 줄"
    assert chat_body_to_html("a & b") == "a &amp; b"


def test_effective_typing_duration_respects_minimum_chars_per_sec() -> None:
    # TTS가 1초여도 120자 본문은 최소 10초(12자/초) 타이핑
    short_speech = effective_typing_duration_ms(120, 1000.0, min_chars_per_sec=12.0)
    assert short_speech == 10_000.0
    long_speech = effective_typing_duration_ms(10, 8000.0, min_chars_per_sec=12.0)
    assert long_speech == 8000.0


def test_typing_target_index_progresses_with_elapsed_time() -> None:
    assert typing_target_index(100, 0, 1000) == 0
    assert typing_target_index(100, 500, 1000) == 50
    assert typing_target_index(100, 2000, 1000) == 100


def test_scale_typing_duration_ms_scales_visible_to_spoken() -> None:
    assert scale_typing_duration_ms(1000.0, 100, 50) == 2000.0


def test_extend_typing_timeline_ms_adds_segment_budget() -> None:
    total = extend_typing_timeline_ms(500.0, 20, 2000.0, min_chars_per_sec=12.0)
    assert total > 500.0
