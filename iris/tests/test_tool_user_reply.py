"""tool_user_reply — preview/result 기반 사용자 멘트."""

from __future__ import annotations

from iris.assistant.tool_user_reply import (
    format_cu_early_ack,
    format_pending_tool_user_message,
    format_user_approval_message,
)
from iris.automation.tool_types import AutomationToolResult


def test_approval_message_uses_preview_verbatim() -> None:
    msg = format_user_approval_message(
        "run_shell", "쉘 실행: notepad", {"command": "notepad"}
    )
    assert "쉘 실행: notepad" in msg
    assert "진행할까요" in msg


def test_approval_message_launch_app_preview() -> None:
    msg = format_user_approval_message(
        "launch_app",
        "앱 실행: 메모장 (notepad)",
        {"app_key": "notepad", "display_name": "메모장"},
    )
    assert "앱 실행: 메모장 (notepad)" in msg


def test_pending_tool_message_uses_result_message() -> None:
    result = AutomationToolResult(True, "메모장 실행 시작", "notepad.exe")
    msg = format_pending_tool_user_message("launch_app", result, "메모장")
    assert msg == "메모장 실행 시작 (notepad.exe)"


def test_pending_tool_message_failure() -> None:
    result = AutomationToolResult(False, "app_key가 필요합니다.")
    msg = format_pending_tool_user_message("launch_app", result)
    assert "실행하지 못했습니다" in msg
    assert "app_key" in msg


def test_cu_early_ack_display_name_slot() -> None:
    ack = format_cu_early_ack("메모장 켜줘", {"display_name": "메모장"})
    assert ack == "메모장 관련 작업을 진행할게요."
    assert "메모장 켜줘" not in ack


def test_cu_early_ack_compose_text_slot() -> None:
    ack = format_cu_early_ack(
        "ignored",
        {
            "task_type": "compose_text",
            "app_key": "notepad",
            "text_to_type": "아이리스 테스트",
        },
    )
    assert "notepad" in ack
    assert "아이리스 테스트" in ack
    assert "입력할게요" in ack
