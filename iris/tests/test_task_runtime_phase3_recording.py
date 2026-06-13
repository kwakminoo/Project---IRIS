"""Phase 3 — Quick Launch·Skill 실행 기록."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from iris.application.runtime_factory import build_task_runtime
from iris.assistant.agent_adapter import IrisAssistant
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolContext, AutomationToolResult
from iris.domain.task.enums import StepStatus
from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter
from iris.infrastructure.adapters.safety_policy_adapter import SafetyPolicyAdapter
from iris.infrastructure.adapters.tool_registry_adapter import ToolRegistryAdapter
from iris.storage.database import Database


def _assistant(tmp_path: Path) -> IrisAssistant:
    db = Database(path=tmp_path / "p3.db")
    executor = ActionExecutor(db, {})
    settings = SimpleNamespace(computer_use_full_plan_enabled=False)
    return IrisAssistant(db, executor, MagicMock(), {}, settings=settings)  # type: ignore[arg-type]


def _count_table(db: Database, table: str) -> int:
    row = db._execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


def test_quick_launch_records_proposal_attempt_result(tmp_path: Path) -> None:
    assistant = _assistant(tmp_path)
    agent = assistant._create_computer_use_agent()
    registry = assistant._executor.tool_registry
    with patch.object(
        registry,
        "run",
        return_value=AutomationToolResult(True, "Chrome 실행", "ok"),
    ), patch(
        "iris.automation.window_controller.find_windows_by_title_substring",
        return_value=[SimpleNamespace(hwnd=1, title="Chrome")],
    ):
        slots = {"task_type": "open_app", "app_key": "chrome", "display_name": "Chrome"}
        agent.run("크롬 열어줘", slots=slots)
    db = assistant._db
    assert _count_table(db, "action_proposals") >= 1
    assert _count_table(db, "action_attempts") >= 1
    assert _count_table(db, "action_results") >= 1
    assert _count_table(db, "verification_results") >= 1


def test_quick_launch_verifies_process_or_window(tmp_path: Path) -> None:
    assistant = _assistant(tmp_path)
    agent = assistant._create_computer_use_agent()
    registry = assistant._executor.tool_registry
    with patch.object(
        registry,
        "run",
        return_value=AutomationToolResult(True, "Chrome 실행", "ok"),
    ), patch(
        "iris.automation.window_controller.find_windows_by_title_substring",
        return_value=[],
    ):
        slots = {"task_type": "open_app", "app_key": "chrome", "display_name": "Chrome"}
        agent.run("크롬 열어줘", slots=slots)
    bundle = assistant._task_runtime_bundle
    assert bundle is not None
    plan = bundle.repos.plans.get_latest_plan_for_task(assistant.ctx.active_task_id)
    step = bundle.repos.plans.get_steps(plan.id)[0]
    assert step.status != StepStatus.SUCCEEDED


def test_skill_records_each_tool_attempt(tmp_path: Path) -> None:
    from iris.assistant.text_compose_flow import TextComposeFlow

    assistant = _assistant(tmp_path)
    agent = assistant._create_computer_use_agent()
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(  # type: ignore[method-assign]
        return_value=AutomationToolResult(True, "ok", "ok"),
    )

    def _fake_compose(self: TextComposeFlow, goal: str, slots: dict) -> str:
        self._agent.run_tool_recorded(
            "launch_app",
            {"app_key": "notepad", "display_name": "메모장"},
            step_index=0,
            summary="launch",
        )
        self._agent.run_tool_recorded(
            "type_text",
            {"text": "hi"},
            step_index=1,
            summary="type",
        )
        return "메모장에 입력했습니다."

    with patch.object(TextComposeFlow, "run", _fake_compose):
        slots = {
            "task_type": "compose_text",
            "app_key": "notepad",
            "display_name": "메모장",
            "text_to_type": "hi",
        }
        agent.run("메모장에 hi", slots=slots)
    assert _count_table(assistant._db, "action_attempts") >= 2


def test_tool_success_without_target_state_does_not_complete_step(tmp_path: Path) -> None:
    db = Database(tmp_path / "p3b.db")
    registry = AutomationToolRegistry(db)
    runtime = build_task_runtime(db, registry)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("chrome", {"task_type": "open_app"})
    mock_registry = MagicMock()
    mock_registry.run.return_value = AutomationToolResult(True, "launched", "ok")
    mock_registry.needs_approval.return_value = False

    def ctx_factory(**kwargs):
        return AutomationToolContext(params=kwargs.get("params") or {})

    runtime.execution._policy = SafetyPolicyAdapter(
        mock_registry, default_tool_context=ctx_factory()
    )
    runtime.execution._tools = ToolRegistryAdapter(mock_registry, ctx_factory)
    with patch(
        "iris.automation.window_controller.find_windows_by_title_substring",
        return_value=[],
    ):
        adapter.execute_tool_step(
            tool_name="launch_app",
            params={"app_key": "chrome", "display_name": "Chrome"},
            step_index=0,
            reason="launch",
            approved=True,
            finalize_if_no_checkpoint=True,
        )
    step = adapter._adhoc_step
    assert step is not None
    loaded = runtime.repos.plans.get_step(step.id)
    assert loaded is not None
    assert loaded.status != StepStatus.SUCCEEDED
