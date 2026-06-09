"""execution_tier_policy 테스트."""

from __future__ import annotations

from iris.assistant.execution_tier_policy import (
    COMPLEX_GOAL_RE,
    input_conflict_message,
    is_input_conflict_tool,
    should_skip_quick_launch,
    tool_tier_rank,
    TIER_DEDICATED_API,
    TIER_INPUT_SIM,
    TIER_TERMINAL,
)


def test_complex_goal_detects_write_intent() -> None:
    assert COMPLEX_GOAL_RE.search("메모장 켜서 안녕 적어줘")


def test_should_skip_quick_launch_multi_step() -> None:
    assert should_skip_quick_launch("메모장 켜줘", {"task_type": "multi_step"})


def test_should_skip_quick_launch_complex_text_empty_slots() -> None:
    """deprecated: slots 없을 때만 COMPLEX_GOAL_RE 폴백."""
    assert should_skip_quick_launch("메모장 켜고 안녕하세요 입력해줘", {})


def test_should_skip_quick_launch_open_app_with_slots() -> None:
    """Router slots 있으면 goal regex 무시."""
    assert not should_skip_quick_launch(
        "메모장 켜고 안녕하세요 입력해줘",
        {"task_type": "open_app", "app_key": "notepad"},
    )


def test_should_skip_quick_launch_skill_task() -> None:
    assert should_skip_quick_launch("메모장에 안녕", {"task_type": "compose_text"})


def test_tool_tier_ranks() -> None:
    assert tool_tier_rank("call_integration") == TIER_DEDICATED_API
    assert tool_tier_rank("type_text") == TIER_INPUT_SIM
    assert tool_tier_rank("run_shell") == TIER_TERMINAL


def test_input_conflict_tools() -> None:
    assert is_input_conflict_tool("send_hotkey")
    assert not is_input_conflict_tool("launch_app")


def test_input_conflict_message_hotkey() -> None:
    msg = input_conflict_message("send_hotkey", {"keys": ["ctrl", "l"]})
    assert "단축키" in msg
    assert "ctrl" in msg.lower()
