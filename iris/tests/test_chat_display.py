from iris.ui.chat_display import markdown_to_plain, normalize_chat_body, strip_speaker_prefix


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
