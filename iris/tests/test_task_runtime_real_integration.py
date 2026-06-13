"""Phase 4·9 — 승인 재개 및 IrisAssistant 실경로 통합."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from iris.application.approval_hash import hash_arguments
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.computer_use_agent import ComputerUseAgent
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_types import AutomationToolResult
from iris.core.context_manager import PendingComputerUseGoal
from iris.domain.task.enums import TaskStatus
from iris.storage.database import Database


def _assistant(tmp_path: Path) -> IrisAssistant:
    db = Database(path=tmp_path / "int.db")
    executor = ActionExecutor(db, {})
    settings = SimpleNamespace(
        computer_use_full_plan_enabled=False,
        computer_use_input_notify_delay_seconds=0.5,
    )
    return IrisAssistant(db, executor, MagicMock(), {}, settings=settings)  # type: ignore[arg-type]


def test_real_assistant_constructs_agent_with_runtime(tmp_path: Path) -> None:
    assistant = _assistant(tmp_path)
    agent = assistant._create_computer_use_agent()
    assert isinstance(agent, ComputerUseAgent)
    assert agent._task_runtime is not None


def test_real_critical_approval_resume_creates_complete_history(tmp_path: Path) -> None:
    assistant = _assistant(tmp_path)
    agent = assistant._create_computer_use_agent()
    registry = assistant._executor.tool_registry
    registry.needs_approval = MagicMock(return_value=True)  # type: ignore[method-assign]
    registry.preview = MagicMock(return_value="npm test")  # type: ignore[method-assign]
    registry.run = MagicMock(  # type: ignore[method-assign]
        return_value=AutomationToolResult(True, "done", "ok"),
    )

    gemma = MagicMock()
    gemma.chat.return_value = (
        '{"tool": "run_shell", "params": {"command": "npm test"}, "reason": "test"}'
    )
    agent._gemma = gemma

    with patch.object(agent, "_run_perceive_desktop", return_value=None):
        reply = agent.run("npm test 실행", slots={"task_type": "shell"})

    assert "확인" in reply or "approval_required" in reply
    pending = assistant.ctx.pending_cu
    assert pending is not None
    tid = pending.slots.get("_task_id")
    pid = pending.slots.get("_task_proposal_id")
    aid = pending.slots.get("_task_approval_id")
    assert tid and pid and aid

    pending_cu = PendingComputerUseGoal(
        goal=pending.goal,
        risk_hint="critical",
        prompt=pending.prompt,
        slots=dict(pending.slots),
        pending_tool_name=pending.pending_tool_name,
        pending_tool_params=dict(pending.pending_tool_params),
        pending_tool_preview=pending.pending_tool_preview,
        pending_plan_index=0,
    )
    assistant.ctx.clear_pending_cu()
    agent.resume_after_critical_approval(pending_cu)

    db = assistant._db
    attempts = db._execute("SELECT COUNT(*) FROM action_attempts").fetchone()
    assert int(attempts[0]) >= 1


def test_real_database_restart_loads_task(tmp_path: Path) -> None:
    assistant = _assistant(tmp_path)
    agent = assistant._create_computer_use_agent()
    registry = assistant._executor.tool_registry
    with patch.object(
        registry,
        "run",
        return_value=AutomationToolResult(True, "Chrome", "ok"),
    ), patch(
        "iris.automation.window_controller.find_windows_by_title_substring",
        return_value=[SimpleNamespace(hwnd=1, title="Chrome")],
    ):
        agent.run(
            "크롬",
            slots={"task_type": "open_app", "app_key": "chrome", "display_name": "Chrome"},
        )
    tid = assistant.ctx.active_task_id
    assistant2 = _assistant(tmp_path)
    assistant2._ensure_task_runtime()
    bundle = assistant2._task_runtime_bundle
    assert bundle is not None
    task = bundle.repos.tasks.get_by_id(tid)
    assert task is not None


def test_legacy_fallback_emits_degraded_event(tmp_path: Path, monkeypatch):
    from iris.application.task_runtime_health import get_task_runtime_health, reset_task_runtime_health

    reset_task_runtime_health()
    monkeypatch.delenv("IRIS_STRICT_TASK_RUNTIME", raising=False)
    assistant = _assistant(tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("init fail")

    monkeypatch.setattr(
        "iris.application.runtime_factory.build_task_runtime",
        _boom,
    )
    assistant._cu_task_adapter = None
    assistant._task_runtime_bundle = None
    result = assistant._ensure_task_runtime()
    assert result is None
    health = get_task_runtime_health()
    assert health.status == "degraded"
    assert health.legacy_fallback is True
