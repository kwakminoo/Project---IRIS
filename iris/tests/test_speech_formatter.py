from iris.audio.speech_formatter import format_speech
from iris.audio.tts_edge import format_edge_plain_text
from iris.core.state_machine import AppState


def test_speech_formatter_removes_tool_markup() -> None:
    spoken = format_speech(
        '// action: speak\n{"tool": "launch_app", "intent": "test"}\n네, 실행할게요. speak',
        AppState.IDLE,
    )

    assert "//" not in spoken
    assert "tool" not in spoken
    assert "speak" not in spoken.lower()
    assert "실행할게요" in spoken


def test_speech_formatter_removes_inline_comment_and_ssml() -> None:
    spoken = format_speech(
        "<speak>// tts: speak\n좋아요. 필요한 내용만 말할게요.</speak> 스픽",
        AppState.IDLE,
    )

    assert "speak" not in spoken.lower()
    assert "스픽" not in spoken
    assert "//" not in spoken
    assert "좋아요" in spoken


def test_speech_formatter_phrase_map_work_request() -> None:
    spoken = format_speech("네, 요청하신 작업을 수행하겠습니다.", AppState.IDLE)
    assert "준비" in spoken
    assert "수행하겠습니다" not in spoken


def test_speech_formatter_web_search_phrase() -> None:
    spoken = format_speech(
        "최신 정보가 필요한 질문입니다. 웹 검색을 수행하겠습니다.",
        AppState.PROCESSING,
    )
    assert "검색" in spoken
    assert "수행하겠습니다" not in spoken


def test_speech_formatter_max_sentences() -> None:
    long_reply = "첫 문장. 둘째 문장. 셋째 문장. 넷째 문장. 다섯째 문장."
    spoken = format_speech(long_reply, AppState.IDLE, max_sentences=2)
    assert spoken.count("\n") + spoken.count(".") <= 4


def test_edge_tts_uses_plain_text_not_ssml() -> None:
    payload = format_edge_plain_text("첫 문장입니다. 둘째 문장입니다.")

    assert "<speak" not in payload
    assert "</speak>" not in payload
    assert "첫 문장" in payload
