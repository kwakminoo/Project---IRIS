"""Intent Router / Tool Layer 스모크 테스트."""

from iris.core.command_router import CommandKind, classify_command


def test_movie_intent() -> None:
    assert classify_command("요즘 하는 영화 뭐 있어?") is CommandKind.MOVIE_SEARCH


def test_terminal_monitoring() -> None:
    assert classify_command("터미널 멈췄는지 확인해줘") is CommandKind.MONITORING_STATUS


def test_app_launch() -> None:
    assert classify_command("Cursor 열어줘") is CommandKind.APP_LAUNCH


def test_general_chat() -> None:
    assert classify_command("안녕") is CommandKind.GENERAL_CHAT
