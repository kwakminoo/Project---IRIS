"""DialogueAgent ack·turn_coordinator 병합 문구 테스트."""

from __future__ import annotations

from iris.assistant.computer_use_agent import format_user_approval_message
from iris.assistant.dialogue_agent import DialogueAgent
from iris.assistant.turn_coordinator import build_spoken_followup, build_user_visible


def test_cu_early_ack_notepad_no_goal_echo() -> None:
    agent = DialogueAgent(object(), object())  # type: ignore[arg-type]
    ack = agent.cu_early_ack("메모장 켜줘", {"task_type": "open_app"})
    assert "메모장 켜줘" not in ack
    assert "메모장을 실행" in ack
    assert "진행할게요" in ack or "실행할게요" in ack


def test_cu_early_ack_unknown_no_goal_echo() -> None:
    agent = DialogueAgent(object(), object())  # type: ignore[arg-type]
    ack = agent.cu_early_ack("뭔가 해줘", {})
    assert "뭔가 해줘" not in ack
    assert ack == "요청하신 작업을 진행할게요."


def test_cu_early_ack_media_search() -> None:
    agent = DialogueAgent(object(), object())  # type: ignore[arg-type]
    ack = agent.cu_early_ack(
        "유튜브에서 아이유 검색 결과를 연다",
        {
            "task_type": "media_play",
            "platform_hint": "youtube",
            "media_action": "search",
            "search_query": "아이유",
        },
    )
    assert "'아이유' 검색 결과를 열게요." == ack


def test_cu_early_ack_media_play() -> None:
    agent = DialogueAgent(object(), object())  # type: ignore[arg-type]
    ack = agent.cu_early_ack(
        "유튜브에서 치챗 영상을 재생한다",
        {
            "task_type": "media_play",
            "platform_hint": "youtube",
            "media_action": "play",
            "search_query": "치챗",
        },
    )
    assert "'치챗' 검색 후 재생까지 진행할게요." == ack


def test_build_user_visible_skips_ack_when_early_ack_shown() -> None:
    ack = "메모장을 실행할게요."
    exec_reply = "Iris: 메모장을 열었습니다."
    full = build_user_visible(ack, exec_reply, had_early_ack=True)
    followup = build_spoken_followup(ack, exec_reply, had_early_ack=True)

    assert "메모장을 실행할게요" not in full
    assert "메모장을 열었습니다" in full
    assert "메모장을 실행할게요" not in followup
    assert "메모장을 열었습니다" in followup


def test_format_user_approval_message_notepad_shell() -> None:
    msg = format_user_approval_message(
        "run_shell", "쉘 실행: notepad", {"command": "notepad"}
    )
    assert "쉘 실행:" not in msg
    assert "진행할까요" in msg
    assert "메모장 실행" in msg


def test_format_user_approval_message_launch_app() -> None:
    msg = format_user_approval_message(
        "launch_app",
        "앱 실행: 메모장 (notepad)",
        {"app_key": "notepad", "display_name": "메모장"},
    )
    assert "앱 실행:" not in msg
    assert "진행할까요" in msg
    assert "메모장 실행" in msg


def test_build_user_visible_keeps_ack_without_early_ack() -> None:
    ack = "유튜브를 열게요."
    exec_reply = "Iris: 재생을 시작했습니다."
    full = build_user_visible(ack, exec_reply, had_early_ack=False)

    assert "유튜브를 열게요" in full
    assert "재생" in full
