"""SendMessageFlow — mock registry."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import MagicMock, patch

from iris.ai.gemma_client import ChatMessage
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import USER_QUESTION_PREFIX
from iris.assistant.send_message_flow import SendMessageFlow, should_run_send_message
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.storage.database import Database


class _NoLlmGemma:
    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        raise AssertionError("LLM must not be called in mechanical success path")


def _make_assistant(tmp_path: Path) -> IrisAssistant:
    settings = SimpleNamespace(computer_use_input_notify_delay_seconds=0.5)
    db = Database(path=tmp_path / "smf.db")
    executor = ActionExecutor(db, {})
    return IrisAssistant(db, executor, _NoLlmGemma(), {}, settings=settings)  # type: ignore[arg-type]


def _perceive_discord() -> AutomationToolResult:
    detail = json.dumps(
        {
            "perception_source": "uia",
            "active_window": "Discord",
            "summary": "general chat",
        },
        ensure_ascii=False,
    )
    return AutomationToolResult(True, "perceive: uia | Discord | chat", detail)


def test_should_run_send_message() -> None:
    assert should_run_send_message({"task_type": "send_message"}) is True
    assert should_run_send_message({"skill_id": "send_message"}) is True


def test_missing_message_text(tmp_path: Path) -> None:
    from iris.assistant.computer_use_agent import ComputerUseAgent

    assistant = _make_assistant(tmp_path)
    agent = ComputerUseAgent(assistant, assistant._gemma, assistant._executor.tool_registry)  # type: ignore[arg-type]
    flow = SendMessageFlow(agent)
    msg = flow.run(
        "디스코드에 보내줘",
        {"task_type": "send_message", "app_key": "discord"},
    )
    assert msg.startswith(USER_QUESTION_PREFIX)
    assert "내용" in msg


def test_send_discord_message_mock(tmp_path: Path) -> None:
    assistant = _make_assistant(tmp_path)
    registry = assistant._executor.tool_registry

    def _registry_side_effect(name: str, ctx: object) -> AutomationToolResult:
        if name == "list_open_windows":
            return AutomationToolResult(True, "창", "Discord")
        if name == "perceive_desktop":
            return _perceive_discord()
        if name == "launch_app":
            return AutomationToolResult(True, "실행", "ok")
        if name == "focus_window":
            return AutomationToolResult(True, "포커스", "ok")
        if name == "uia_click":
            return AutomationToolResult(True, "클릭", "ok")
        if name == "type_text":
            return AutomationToolResult(True, "입력 완료", "unicode|verified")
        if name == "send_hotkey":
            return AutomationToolResult(True, "전송", "ok")
        return AutomationToolResult(True, "ok")

    registry.run = MagicMock(side_effect=_registry_side_effect)  # type: ignore[method-assign]

    from iris.assistant.computer_use_agent import ComputerUseAgent

    with patch(
        "iris.assistant.cu_mechanical_verify.read_focused_field_text",
        return_value=(True, ""),
    ), patch(
        "iris.automation.window_controller.find_windows_by_title_substring",
        return_value=[SimpleNamespace(hwnd=200, title="Discord")],
    ):
        agent = ComputerUseAgent(assistant, assistant._gemma, registry)  # type: ignore[arg-type]
        flow = SendMessageFlow(agent)
        msg = flow.run(
            "디스코드에 hi 보내",
            {
                "task_type": "send_message",
                "app_key": "discord",
                "message_text": "hi",
            },
        )

    assert "보냈" in msg or "완료" in msg
    tools = [c[0][0] for c in registry.run.call_args_list]
    assert "type_text" in tools
