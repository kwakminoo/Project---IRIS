"""Phase 2 — ComputerUseAgent.run() 실경로 Task 생성."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import MagicMock, patch

import pytest

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.assistant.agent_adapter import IrisAssistant
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.domain.task.enums import TaskStatus
from iris.storage.database import Database


class _StepQueueGemma:
    def __init__(self, steps: list[str]) -> None:
        self._steps = list(steps)

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        if messages and "Computer Use 플래너" in messages[0].content:
            if self._steps:
                return self._steps.pop(0)
            return '{"tool": "step_complete", "params": {}, "reason": "완료"}'
        return "unused"


def _perceive_ok() -> AutomationToolResult:
    return AutomationToolResult(
        True,
        "perceive: ocr | Notepad | hello",
        '{"perception_source":"ocr","active_window":"Notepad","summary":"hello"}',
    )


def _assistant_with_runtime(tmp_path: Path, gemma: object) -> IrisAssistant:
    settings = SimpleNamespace(
        computer_use_full_plan_enabled=False,
        computer_use_input_notify_delay_seconds=0.5,
    )
    db = Database(path=tmp_path / "p2.db")
    executor = ActionExecutor(db, {})
    return IrisAssistant(db, executor, gemma, {}, settings=settings)  # type: ignore[arg-type]


def _agent(assistant: IrisAssistant):
    return assistant._create_computer_use_agent()


def _count_tasks(db: Database) -> int:
    row = db._execute("SELECT COUNT(*) FROM tasks").fetchone()
    return int(row[0]) if row else 0


def test_real_quick_launch_creates_task(tmp_path: Path) -> None:
    assistant = _assistant_with_runtime(tmp_path, MagicMock())
    agent = _agent(assistant)
    registry = assistant._executor.tool_registry
    with patch.object(
        registry,
        "run",
        return_value=AutomationToolResult(True, "Chrome 실행됨", "ok"),
    ):
        slots = {"task_type": "open_app", "app_key": "chrome", "display_name": "Chrome"}
        agent.run("크롬 열어줘", slots=slots)
    assert _count_tasks(assistant._db) == 1
    tid = assistant.ctx.active_task_id
    assert tid
    bundle = assistant._task_runtime_bundle
    assert bundle is not None
    task = bundle.repos.tasks.get_by_id(tid)
    assert task is not None
    plan = bundle.repos.plans.get_latest_plan_for_task(tid)
    assert plan is not None
    steps = bundle.repos.plans.get_steps(plan.id)
    assert steps
    assert task.status == TaskStatus.COMPLETED


def _flex_mock_run(tool_name: str, ctx: object) -> AutomationToolResult:
    if tool_name == "list_open_windows":
        return AutomationToolResult(True, "창 목록", "Cursor")
    if tool_name == "perceive_desktop":
        return _perceive_ok()
    if tool_name == "get_system_info":
        return AutomationToolResult(True, "CPU info", "i7")
    if tool_name == "launch_app":
        return AutomationToolResult(True, "실행됨", "ok")
    return AutomationToolResult(True, "ok", "ok")


def test_real_action_skill_creates_task(tmp_path: Path) -> None:
    assistant = _assistant_with_runtime(tmp_path, MagicMock())
    agent = _agent(assistant)
    with patch(
        "iris.assistant.text_compose_flow.TextComposeFlow.run",
        return_value="메모장에 hello를 입력했습니다.",
    ):
        slots = {
            "task_type": "compose_text",
            "app_key": "notepad",
            "display_name": "메모장",
            "text_to_type": "hello",
        }
        agent.run("메모장에 hello 입력해줘", slots=slots)
    assert _count_tasks(assistant._db) == 1
    tid = assistant.ctx.active_task_id
    bundle = assistant._task_runtime_bundle
    assert bundle is not None
    plan = bundle.repos.plans.get_latest_plan_for_task(tid)
    assert plan is not None
    assert bundle.repos.plans.get_steps(plan.id)


def test_real_tier1_action_creates_task(tmp_path: Path) -> None:
    """Quick Launch = Tier1 launch_app."""
    test_real_quick_launch_creates_task(tmp_path)


def test_real_pav_loop_creates_single_task(tmp_path: Path) -> None:
    gemma = _StepQueueGemma(
        [
            '{"tool": "get_system_info", "params": {}, "reason": "사양 확인"}',
            '{"tool": "step_complete", "params": {}, "reason": "완료"}',
        ]
    )
    assistant = _assistant_with_runtime(tmp_path, gemma)
    agent = _agent(assistant)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(side_effect=_flex_mock_run)  # type: ignore[method-assign]
    agent.run("PC 사양 알려줘", slots={"task_type": "complex"})
    assert _count_tasks(assistant._db) == 1


def test_quick_launch_fallback_to_pav_keeps_same_task_id(tmp_path: Path) -> None:
    """open_app 아닌 slots → Quick Launch skip → PAV, Task 1개 유지."""
    gemma = _StepQueueGemma(
        [
            '{"tool": "get_system_info", "params": {}, "reason": "info"}',
            '{"tool": "step_complete", "params": {}, "reason": "done"}',
        ]
    )
    assistant = _assistant_with_runtime(tmp_path, gemma)
    agent = _agent(assistant)
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(side_effect=_flex_mock_run)  # type: ignore[method-assign]
    before = assistant._ensure_task_runtime()
    assert before is not None
    agent.run("시스템 정보", slots={"task_type": "query"})
    assert _count_tasks(assistant._db) == 1
    bundle = assistant._task_runtime_bundle
    assert bundle is not None
    tasks = bundle.repos.tasks.get_active()
    assert len(tasks) <= 1
