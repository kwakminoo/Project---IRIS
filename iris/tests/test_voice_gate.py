from iris.audio.voice_gate import VoiceCommandGate, find_wake_match


def test_wake_word_strips_command() -> None:
    gate = VoiceCommandGate(followup_seconds=5)

    result = gate.filter("아이리스 크롬 열어줘")

    assert result.accepted is True
    assert result.command_text == "크롬 열어줘"
    assert result.prompt_only is False


def test_fuzzy_wake_spaced_syllables() -> None:
    gate = VoiceCommandGate(followup_seconds=5)

    result = gate.filter("아이 리스 날씨 알려줘")

    assert result.accepted is True
    assert "날씨" in result.command_text


def test_fuzzy_wake_partial_ai() -> None:
    gate = VoiceCommandGate(followup_seconds=5)

    result = gate.filter("아이")

    assert result.accepted is True
    assert result.prompt_only is True


def test_fuzzy_find_hi_iris() -> None:
    assert find_wake_match("하이리스 뉴스", ("아이리스", "iris")) == "아이리스"


def test_ambient_voice_is_ignored_without_wake_word() -> None:
    gate = VoiceCommandGate(followup_seconds=0)

    result = gate.filter("오늘 날씨 알려줘")

    assert result.accepted is False
    assert result.reject_reason == "wake_word"


def test_wake_word_only_opens_followup_window() -> None:
    gate = VoiceCommandGate(followup_seconds=5)

    first = gate.filter("아이리스")
    second = gate.filter("오늘 뉴스 알려줘")

    assert first.prompt_only is True
    assert second.accepted is True
    assert second.command_text == "오늘 뉴스 알려줘"
