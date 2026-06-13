"""Task Runtime 재시작 복구 명령 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from iris.application.recovery_commands import (
    RecoveryCommand,
    classify_recovery_command,
    format_recovery_status,
    validate_resume_snapshot,
)
from iris.application.runtime_factory import build_task_runtime
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.recovery_turn_handler import try_handle_recovery_turn
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_registry import AutomationToolRegistry
from iris.domain.execution.models import ActionAttempt, ActionProposal
from iris.domain.shared.id_generator import new_id
from iris.domain.task.enums import AttemptStatus, TaskStatus
from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter
from iris.storage.database import Database


def _runtime(tmp_path: Path):
    db = Database(tmp_path / "rec.db")
    registry = AutomationToolRegistry(db)
    return build_task_runtime(db, registry), db, registry


def _assistant(tmp_path: Path) -> IrisAssistant:
    db = Database(tmp_path / "rec_ui.db")
    executor = ActionExecutor(db, {})
    settings = SimpleNamespace(computer_use_full_plan_enabled=False)
    a = IrisAssistant(db, executor, MagicMock(), {}, settings=settings)  # type: ignore[arg-type]
    a._ensure_task_runtime()
    return a


def _plan_step(runtime, task, *, tool: str = "launch_app"):
    _plan, step = runtime.tasks.ensure_adhoc_plan(task, tool_hint=tool)
    task.active_plan_id = _plan.id
    runtime.repos.tasks.update(task)
    return step


# --- 명령 분류 ---


@pytest.mark.parametrize(
    "text,expected",
    [
        ("계속 진행", RecoveryCommand.CONTINUE),
        ("상태 확인", RecoveryCommand.STATUS),
        ("작업 취소", RecoveryCommand.CANCEL),
        ("안녕", None),
    ],
)
def test_classify_recovery_command(text: str, expected):
    assert classify_recovery_command(text) == expected


# --- 앱 시작 복구 탐색 ---


def test_startup_discovers_recoverable_task(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build project")
    task = runtime.tasks.start_task(task)
    runtime2 = build_task_runtime(db, registry)
    found = runtime2.recovery.normalize_startup_tasks()
    assert any(t.id == task.id for t in found)


def test_running_task_normalized_to_interrupted_on_startup(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    task = runtime.tasks.start_task(task)
    assert task.status == TaskStatus.RUNNING
    runtime2 = build_task_runtime(db, registry)
    found = runtime2.recovery.normalize_startup_tasks()
    loaded = next(t for t in found if t.id == task.id)
    assert loaded.status == TaskStatus.INTERRUPTED


# --- 상태 확인 ---


def test_status_command_returns_recovery_snapshot(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("메모장 작업")
    task = runtime.tasks.start_task(task)
    task = runtime.tasks.suspend_for_user_input(task, "need text")
    runtime2 = build_task_runtime(db, registry)
    snap = runtime2.recovery.load_recovery_snapshot(task.id)
    assert snap is not None
    body = format_recovery_status(snap)
    assert "메모장 작업" in body
    assert "waiting_user" in body


def test_status_turn_handler(tmp_path: Path):
    assistant = _assistant(tmp_path)
    task = assistant._task_runtime_bundle.tasks.create_task_from_cu_request("build")
    task = assistant._task_runtime_bundle.tasks.start_task(task)
    assistant._task_runtime_bundle.tasks.suspend_for_user_input(task, "q")
    assistant.ctx.active_task_id = task.id
    result = try_handle_recovery_turn(assistant, "t1", "상태 확인", [])
    assert result is not None
    assert "이전 작업 상태" in result.user_visible
    assert task.goal in result.user_visible


# --- 계속 진행 ---


def test_continue_command_resumes_same_task_id(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    runtime.tasks.suspend_for_user_input(task, "need info")
    runtime2 = build_task_runtime(db, registry)
    resumed = runtime2.recovery.resume_task(task.id)
    assert resumed is not None
    assert resumed.id == task.id
    assert resumed.status == TaskStatus.RUNNING


def test_continue_does_not_create_new_task(tmp_path: Path):
    assistant = _assistant(tmp_path)
    bundle = assistant._task_runtime_bundle
    task = bundle.tasks.create_task_from_cu_request("메모장 열기")
    task = bundle.tasks.start_task(task)
    bundle.tasks.suspend_for_user_input(task, "q")
    assistant.ctx.active_task_id = task.id
    before = bundle.repos.tasks.get_active()
    with patch.object(
        assistant,
        "run_computer_use_loop",
        return_value="완료",
    ) as mock_cu:
        result = try_handle_recovery_turn(assistant, "t2", "계속 진행", [])
    assert result is not None
    mock_cu.assert_called_once()
    slots = mock_cu.call_args.kwargs.get("slots") or mock_cu.call_args[1].get("slots")
    assert slots["_resume_task_id"] == task.id
    after = bundle.repos.tasks.get_active()
    assert len([t for t in after if t.goal == "메모장 열기"]) == len(
        [t for t in before if t.goal == "메모장 열기"]
    )


# --- WAITING_APPROVAL 복원 ---


def test_waiting_approval_restores_existing_proposal(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    from unittest.mock import MagicMock
    from iris.infrastructure.adapters.safety_policy_adapter import SafetyPolicyAdapter
    from iris.infrastructure.adapters.tool_registry_adapter import ToolRegistryAdapter
    from iris.automation.tool_types import AutomationToolContext, AutomationToolResult

    mock_registry = MagicMock()
    mock_registry.run.return_value = AutomationToolResult(True, "ok")
    mock_registry.needs_approval.return_value = True
    mock_registry.preview.return_value = "preview"

    def ctx_factory(**kwargs):
        return AutomationToolContext(params=kwargs.get("params") or {})

    runtime.execution._policy = SafetyPolicyAdapter(mock_registry, default_tool_context=ctx_factory())
    runtime.execution._tools = ToolRegistryAdapter(mock_registry, ctx_factory)

    task = runtime.tasks.create_task_from_cu_request("shell")
    task = runtime.tasks.start_task(task)
    step = _plan_step(runtime, task, tool="run_shell")
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.run_shell",
        tool_name="run_shell",
        arguments={"command": "npm test"},
    )
    runtime.execution.execute_step(task, step, proposal, run_tool=False)
    snap = runtime.recovery.load_recovery_snapshot(task.id)
    assert snap is not None
    assert snap.pending_approval is not None
    assert snap.latest_proposal is not None


def test_expired_approval_requests_new_approval(tmp_path: Path):
    assistant = _assistant(tmp_path)
    bundle = assistant._task_runtime_bundle
    from unittest.mock import MagicMock
    from iris.infrastructure.adapters.safety_policy_adapter import SafetyPolicyAdapter
    from iris.infrastructure.adapters.tool_registry_adapter import ToolRegistryAdapter
    from iris.automation.tool_types import AutomationToolContext, AutomationToolResult

    mock_registry = MagicMock()
    mock_registry.needs_approval.return_value = True
    mock_registry.preview.return_value = "preview"

    def ctx_factory(**kwargs):
        return AutomationToolContext(params=kwargs.get("params") or {})

    bundle.execution._policy = SafetyPolicyAdapter(mock_registry, default_tool_context=ctx_factory())
    bundle.execution._tools = ToolRegistryAdapter(mock_registry, ctx_factory)

    task = bundle.tasks.create_task_from_cu_request("shell")
    task = bundle.tasks.start_task(task)
    step = _plan_step(bundle, task, tool="run_shell")
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.run_shell",
        tool_name="run_shell",
        arguments={"command": "npm test"},
    )
    expired = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    bundle.repos.execution.save_proposal(proposal)
    old_req = bundle.approvals.create_request(task, proposal, expires_at=expired)
    bundle.approvals.suspend_task_for_approval(task)
    assistant.ctx.active_task_id = task.id
    result = try_handle_recovery_turn(assistant, "t3", "계속 진행", [])
    assert result is not None
    assert "승인" in result.user_visible
    assert assistant.ctx.pending_cu is not None
    pending = bundle.approvals.get_pending_for_task(task.id)
    assert pending is not None
    assert pending.id != old_req.id


# --- 취소 ---


def test_cancel_recovered_task_sets_cancelled(tmp_path: Path):
    assistant = _assistant(tmp_path)
    task = assistant._task_runtime_bundle.tasks.create_task_from_cu_request("build")
    assistant._task_runtime_bundle.tasks.suspend_for_user_input(task, "q")
    assistant.ctx.active_task_id = task.id
    result = try_handle_recovery_turn(assistant, "t4", "작업 취소", [])
    assert result is not None
    loaded = assistant._task_runtime_bundle.repos.tasks.get_by_id(task.id)
    assert loaded is not None
    assert loaded.status == TaskStatus.CANCELLED
    assert assistant.ctx.active_task_id is None


# --- 중복 Attempt 방지 ---


def test_resume_does_not_duplicate_completed_attempt(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    task = runtime.tasks.create_task_from_cu_request("info")
    task = runtime.tasks.start_task(task)
    adapter._task = task
    step = _plan_step(runtime, task, tool="get_system_info")
    adapter._adhoc_step = step
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.get_system_info",
        tool_name="get_system_info",
        arguments={},
    )
    runtime.repos.execution.save_proposal(proposal)
    attempt = ActionAttempt(
        id=new_id(),
        proposal_id=proposal.id,
        attempt_number=1,
        status=AttemptStatus.SUCCEEDED,
    )
    runtime.repos.execution.save_attempt(attempt)
    assert adapter.proposal_has_completed_attempt(proposal.id)


# --- 불완전 스냅샷 ---


def test_invalid_recovery_snapshot_blocks_execution(tmp_path: Path):
    assistant = _assistant(tmp_path)
    task = assistant._task_runtime_bundle.tasks.create_task_from_cu_request("x")
    assistant._task_runtime_bundle.tasks.cancel_task(task, "done")
    assistant.ctx.active_task_id = task.id
    result = try_handle_recovery_turn(assistant, "t5", "계속 진행", [])
    assert result is None or "종료" in result.user_visible or "취소" in result.user_visible


def test_validate_resume_snapshot_cancelled():
    from iris.domain.task.enums import TaskType
    from iris.domain.task.models import Task

    task = Task(
        id="t1",
        task_type=TaskType.AUTOMATION,
        title="g",
        goal="g",
        status=TaskStatus.CANCELLED,
    )
    from iris.application.recovery_service import RecoverySnapshot

    snap = RecoverySnapshot(task=task)
    v = validate_resume_snapshot(snap)
    assert not v.ok


def test_turn_coordinator_routes_recovery_status(tmp_path: Path):
    assistant = _assistant(tmp_path)
    task = assistant._task_runtime_bundle.tasks.create_task_from_cu_request("build")
    task = assistant._task_runtime_bundle.tasks.start_task(task)
    assistant._task_runtime_bundle.tasks.suspend_for_user_input(task, "q")
    assistant.ctx.active_task_id = task.id
    coord = TurnCoordinator(assistant, MagicMock())
    result = coord.run_turn("상태 확인")
    assert "이전 작업 상태" in result.user_visible
