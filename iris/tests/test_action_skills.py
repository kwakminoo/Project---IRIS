"""action_skills — 스킬 ID 매칭·dispatch."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from iris.assistant.action_skills import (
    SKILL_RUNNERS,
    clarify_missing_skill_slots,
    describe_skill_route,
    resolve_skill_id,
    run_skill,
    should_dispatch_skill,
)
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.automation.action_executor import ActionExecutor
from iris.storage.database import Database


def test_resolve_skill_id_from_task_type() -> None:
    assert resolve_skill_id({"task_type": "compose_text"}) == "text_compose"


def test_resolve_skill_id_explicit() -> None:
    assert resolve_skill_id({"skill_id": "media_play", "task_type": "open_app"}) == "media_play"


def test_describe_compose_text() -> None:
    m = describe_skill_route(
        "메모장에 적어줘",
        {"task_type": "compose_text", "text_to_type": "hello"},
    )
    assert m is not None
    assert m.skill_id == "text_compose"
    assert "hello" in m.reason


def test_clarify_missing_compose_slots() -> None:
    assert clarify_missing_skill_slots("compose_text", {}) == "어느 앱에 어떤 내용을 입력할까요?"
    assert clarify_missing_skill_slots(
        "compose_text", {"app_key": "notepad"}
    ) == "어떤 내용을 입력할까요?"


def test_clarify_missing_send_message_slots() -> None:
    assert clarify_missing_skill_slots("send_message", {"app_key": "discord"}) == "어떤 내용을 보낼까요?"


def test_should_dispatch_text_compose() -> None:
    assert should_dispatch_skill(
        {"task_type": "compose_text", "app_key": "notepad", "text_to_type": "hi"}
    )


def test_run_skill_text_compose(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "sk.db")
    executor = ActionExecutor(db, {})
    assistant = IrisAssistant(db, executor, object(), {}, settings=SimpleNamespace())  # type: ignore[arg-type]
    agent = ComputerUseAgent(assistant, assistant._gemma, assistant._executor.tool_registry)  # type: ignore[arg-type]
    with patch(
        "iris.assistant.text_compose_flow.TextComposeFlow.run",
        return_value="ok",
    ) as mock_run:
        out = run_skill(
            "text_compose",
            agent,
            "goal",
            {"app_key": "notepad", "text_to_type": "x"},
        )
    assert out == "ok"
    mock_run.assert_called_once()
    assert "text_compose" in SKILL_RUNNERS or len(SKILL_RUNNERS) >= 1
