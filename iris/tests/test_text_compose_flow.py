"""TextComposeFlow — mock registry, LLM planner 0회."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import MagicMock, patch

from iris.ai.gemma_client import ChatMessage
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent, USER_QUESTION_PREFIX
from iris.assistant.text_compose_flow import TextComposeFlow, should_run_text_compose
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.storage.database import Database


class _NoPlannerGemma:
    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        raise AssertionError("LLM planner must not be called")


def _make_assistant(tmp_path: Path, gemma: object) -> IrisAssistant:
    settings = SimpleNamespace(computer_use_input_notify_delay_seconds=0.5)
    db = Database(path=tmp_path / "tcf.db")
    executor = ActionExecutor(db, {})
    return IrisAssistant(db, executor, gemma, {}, settings=settings)  # type: ignore[arg-type]


def _perceive_notepad() -> AutomationToolResult:
    detail = json.dumps(
        {
            "perception_source": "uia",
            "active_window": "메모장",
            "summary": "hello",
        },
        ensure_ascii=False,
    )
    return AutomationToolResult(True, "perceive: uia | 메모장 | hello", detail)


def test_should_run_text_compose() -> None:
    assert should_run_text_compose({"task_type": "compose_text"}) is True
    assert should_run_text_compose({"skill_id": "text_compose"}) is True
    assert should_run_text_compose({"task_type": "open_app"}) is False


def test_missing_slots_returns_user_question(tmp_path: Path) -> None:
    assistant = _make_assistant(tmp_path, _NoPlannerGemma())
    agent = ComputerUseAgent(assistant, assistant._gemma, assistant._executor.tool_registry)  # type: ignore[arg-type]
    flow = TextComposeFlow(agent)
    msg = flow.run("메모장에 적어줘", {"task_type": "compose_text", "app_key": "notepad"})
    assert msg.startswith(USER_QUESTION_PREFIX)
    assert "내용" in msg


def test_compose_notepad_hello_mock_registry(tmp_path: Path) -> None:
    """메모장 + hello — TextComposeFlow, LLM 0회."""
    gemma = _NoPlannerGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry

    def _registry_side_effect(name: str, ctx: object) -> AutomationToolResult:
        if name == "list_open_windows":
            return AutomationToolResult(True, "창 목록", "메모장")
        if name == "perceive_desktop":
            return _perceive_notepad()
        if name == "launch_app":
            return AutomationToolResult(True, "실행", "ok")
        if name == "focus_window":
            return AutomationToolResult(True, "포커스", "ok")
        if name == "uia_snapshot":
            return AutomationToolResult(True, "uia", "{}")
        if name == "type_text":
            return AutomationToolResult(True, "입력 완료", "unicode|verified")
        return AutomationToolResult(True, "ok")

    registry.run = MagicMock(side_effect=_registry_side_effect)  # type: ignore[method-assign]

    with patch(
        "iris.assistant.cu_mechanical_verify.read_focused_field_text",
        return_value=(True, "hello"),
    ), patch(
        "iris.automation.window_controller.find_windows_by_title_substring",
        return_value=[SimpleNamespace(hwnd=100, title="메모장")],
    ):
        agent = ComputerUseAgent(assistant, gemma, registry)  # type: ignore[arg-type]
        msg = agent.run(
            "메모장 켜고 hello 입력",
            slots={
                "task_type": "compose_text",
                "app_key": "notepad",
                "text_to_type": "hello",
            },
        )

    assert "hello" in msg or "입력" in msg or "완료" in msg
    assert registry.run.call_count >= 5


def test_cu_agent_text_compose_skips_planner(tmp_path: Path) -> None:
    gemma = _NoPlannerGemma()
    assistant = _make_assistant(tmp_path, gemma)
    registry = assistant._executor.tool_registry
    with patch(
        "iris.assistant.text_compose_flow.TextComposeFlow.run",
        return_value="메모장에 입력했습니다.",
    ) as mock_flow:
        agent = ComputerUseAgent(assistant, gemma, registry)  # type: ignore[arg-type]
        msg = agent.run(
            "메모장 hello",
            slots={
                "task_type": "compose_text",
                "app_key": "notepad",
                "text_to_type": "hello",
            },
        )
    assert "입력" in msg
    mock_flow.assert_called_once()
