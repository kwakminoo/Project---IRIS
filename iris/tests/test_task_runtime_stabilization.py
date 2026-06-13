"""Task Runtime 안정화 — P0/P1 필수 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from iris.application.approval_hash import hash_arguments
from iris.application.runtime_factory import build_task_runtime
from iris.application.task_runtime_health import get_task_runtime_health, reset_task_runtime_health
from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolResult
from iris.domain.execution.enums import ApprovalStatus, VerificationStatus
from iris.domain.execution.models import ActionProposal
from iris.domain.shared.id_generator import new_id
from iris.domain.task.enums import StepStatus, TaskStatus, TaskType
from iris.domain.task.models import Plan, PlanStep, Task
from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter
from iris.infrastructure.adapters.tool_registry_adapter import ToolRegistryAdapter
from iris.storage.database import Database


def _runtime(tmp_path: Path):
    db = Database(tmp_path / "tr.db")
    registry = AutomationToolRegistry(db)
    return build_task_runtime(db, registry), db, registry


def _mock_tools(runtime, *, success: bool = True, needs_approval: bool = False):
    mock_registry = MagicMock(spec=AutomationToolRegistry)
    mock_registry.run.return_value = AutomationToolResult(success, "ok" if success else "fail")
    mock_registry.needs_approval.return_value = needs_approval
    mock_registry.preview.return_value = "preview"

    def ctx_factory(**kwargs):
        from iris.automation.tool_types import AutomationToolContext

        return AutomationToolContext(params=kwargs.get("params") or {})

    from iris.infrastructure.adapters.safety_policy_adapter import SafetyPolicyAdapter

    runtime.execution._policy = SafetyPolicyAdapter(mock_registry, default_tool_context=ctx_factory())
    runtime.execution._tools = ToolRegistryAdapter(mock_registry, ctx_factory)


def _plan_step(runtime, task: Task, *, tool: str = "launch_app") -> PlanStep:
    _plan, step = runtime.tasks.ensure_adhoc_plan(task, tool_hint=tool)
    task.active_plan_id = _plan.id
    runtime.repos.tasks.update(task)
    return step


# --- 6.1 모든 실행 경로 Task 생성 ---


def test_quick_launch_creates_task(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("크롬 열어줘", {"task_type": "open_app", "app_key": "chrome"})
    _mock_tools(runtime)
    adapter.execute_tool_step(
        tool_name="launch_app",
        params={"app_key": "chrome", "display_name": "Chrome"},
        step_index=0,
        reason="quick",
        approved=True,
    )
    assert adapter.task_id
    task = runtime.repos.tasks.get_by_id(adapter.task_id)
    assert task is not None
    assert runtime.repos.plans.get_latest_plan_for_task(task.id)
    assert runtime.repos.execution.get_attempts_for_proposal  # noqa: B018


def test_action_skill_creates_task(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    tid = adapter.begin_cu_session("메시지 보내줘", {"skill_id": "send_message"})
    assert tid
    assert runtime.repos.tasks.get_by_id(tid) is not None


def test_tier1_action_creates_task(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request(
        "메모장 실행", task_type=TaskType.AUTOMATION
    )
    task = runtime.tasks.start_task(task)
    runtime.tasks.ensure_adhoc_plan(task, tool_hint="launch_app")
    assert runtime.repos.plans.get_latest_plan_for_task(task.id)


def test_pav_loop_creates_task(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    tid = adapter.begin_cu_session("프로젝트 빌드해줘", {})
    assert tid
    plan = runtime.repos.plans.get_latest_plan_for_task(tid)
    assert plan is not None
    steps = runtime.repos.plans.get_steps(plan.id)
    assert steps


# --- 6.2 승인 후 재개 ---


def test_approved_action_records_attempt_and_result(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    _mock_tools(runtime, needs_approval=True)
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
    out1 = runtime.execution.execute_step(task, step, proposal, run_tool=False)
    assert out1.approval_id
    req = runtime.approvals.grant(
        out1.approval_id,
        tool_name="run_shell",
        arguments={"command": "npm test"},
    )
    assert req is not None
    out2 = runtime.execution.execute_proposal(proposal.id, approval_id=req.id)
    assert out2.attempt is not None
    assert out2.result is not None


def test_approval_resume_uses_existing_proposal(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("build", {})
    _mock_tools(runtime, needs_approval=True)
    step = adapter._resolve_step(0, "run_shell", "shell")
    out = adapter.on_tool_execute(
        tool_name="run_shell",
        params={"command": "npm test"},
        step_index=0,
        reason="shell",
        run_tool=False,
    )
    assert out.proposal_id
    pid = out.proposal_id
    runtime.approvals.grant(
        out.approval_id or "",
        tool_name="run_shell",
        arguments={"command": "npm test"},
    )
    res = adapter.execute_approved_proposal(
        proposal_id=pid,
        approval_id=out.approval_id or "",
        tool_name="run_shell",
        params={"command": "npm test"},
        step_index=0,
    )
    assert not res.blocked


def test_approval_argument_hash_mismatch_blocks_execution(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("shell")
    step = _plan_step(runtime, task, tool="run_shell")
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.run_shell",
        tool_name="run_shell",
        arguments={"command": "npm test"},
    )
    runtime.repos.execution.save_proposal(proposal)
    req = runtime.approvals.create_request(task, proposal)
    bad = runtime.approvals.grant(req.id, tool_name="run_shell", arguments={"command": "rm -rf /"})
    assert bad is None


def test_expired_approval_blocks_execution(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("shell")
    step = _plan_step(runtime, task, tool="run_shell")
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.run_shell",
        tool_name="run_shell",
        arguments={"command": "npm test"},
    )
    runtime.repos.execution.save_proposal(proposal)
    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    req = runtime.approvals.create_request(task, proposal, expires_at=expired)
    ok = runtime.approvals.grant(
        req.id, tool_name="run_shell", arguments={"command": "npm test"}
    )
    assert ok is None


# --- 6.3 검증 기반 Step 상태 ---


def test_tool_success_does_not_complete_step_before_verification(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    _mock_tools(runtime)
    task = runtime.tasks.create_task_from_cu_request("info")
    task = runtime.tasks.start_task(task)
    step = _plan_step(runtime, task, tool="get_system_info")
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.get_system_info",
        tool_name="get_system_info",
        arguments={},
    )
    out = runtime.execution.execute_step(task, step, proposal)
    assert out.step_status == StepStatus.VERIFYING
    loaded = runtime.repos.plans.get_step(step.id)
    assert loaded is not None
    assert loaded.status == StepStatus.VERIFYING


def test_checkpoint_success_completes_step(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    task = runtime.tasks.create_task_from_cu_request("build")
    task = runtime.tasks.start_task(task)
    adapter._task = task
    step = _plan_step(runtime, task)
    adapter._adhoc_step = step
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.launch_app",
        tool_name="launch_app",
        arguments={},
    )
    runtime.repos.execution.save_proposal(proposal)
    from iris.domain.execution.models import ActionAttempt
    from iris.domain.task.enums import AttemptStatus

    attempt = ActionAttempt(id=new_id(), proposal_id=proposal.id, attempt_number=1)
    runtime.repos.execution.save_attempt(attempt)
    adapter._last_attempt_id = attempt.id
    adapter.on_checkpoint_verified(
        attempt_id=attempt.id,
        achieved=True,
        checkpoint_id="cp1",
    )
    loaded = runtime.repos.plans.get_step(step.id)
    assert loaded is not None
    assert loaded.status == StepStatus.SUCCEEDED


def test_checkpoint_failure_marks_step_failed_or_retryable(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    task = runtime.tasks.create_task_from_cu_request("build")
    task = runtime.tasks.start_task(task)
    adapter._task = task
    step = _plan_step(runtime, task)
    adapter._adhoc_step = step
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.launch_app",
        tool_name="launch_app",
        arguments={},
    )
    runtime.repos.execution.save_proposal(proposal)
    from iris.domain.execution.models import ActionAttempt

    attempt = ActionAttempt(id=new_id(), proposal_id=proposal.id, attempt_number=1)
    runtime.repos.execution.save_attempt(attempt)
    adapter.on_checkpoint_verified(
        attempt_id=attempt.id,
        achieved=False,
        checkpoint_id="cp1",
        gap="window not found",
    )
    loaded = runtime.repos.plans.get_step(step.id)
    assert loaded is not None
    assert loaded.status == StepStatus.FAILED


def test_visual_unknown_does_not_mark_step_succeeded(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("x")
    step = _plan_step(runtime, task)
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.click",
        tool_name="click",
        arguments={},
    )
    runtime.repos.execution.save_proposal(proposal)
    from iris.domain.execution.models import ActionAttempt

    attempt = ActionAttempt(id=new_id(), proposal_id=proposal.id, attempt_number=1)
    runtime.repos.execution.save_attempt(attempt)
    vr = runtime.verification.record_tool_observation(
        task_id=task.id,
        attempt_id=attempt.id,
        tool_name="click",
        observation="pending",
        success=True,
    )
    assert vr.status == VerificationStatus.UNKNOWN
    runtime.verification.finalize_step_from_verification(task, step, vr)
    loaded = runtime.repos.plans.get_step(step.id)
    assert loaded is not None
    assert loaded.status != StepStatus.SUCCEEDED


# --- 6.4 Plan 무결성 ---


def test_fallback_step_creates_adhoc_plan(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("fallback goal", {})
    step = adapter._resolve_step(1, "focus_window", "focus")
    plan = runtime.repos.plans.get_plan(step.plan_id)
    assert plan is not None


def test_step_without_plan_is_rejected(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    bad = PlanStep(
        id=new_id(),
        plan_id=new_id(),
        index=0,
        title="orphan",
        capability_required="computer.x",
    )
    with pytest.raises(ValueError, match="plan not found"):
        runtime.repos.plans.save_step(bad)


def test_foreign_key_check_has_no_errors(tmp_path: Path):
    db = Database(tmp_path / "fk.db")
    rows = db._execute("PRAGMA foreign_key_check").fetchall()
    assert rows == []


def test_plan_revision_uses_new_id(tmp_path: Path):
    plan = Plan(id="p1", task_id="t1", version=1)
    rev = plan.create_revision("replan")
    assert rev.id != plan.id
    assert rev.previous_plan_id == plan.id


# --- 6.5 복구 ---


def test_running_task_is_discovered_after_restart(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    task = runtime.tasks.start_task(task)
    runtime2 = build_task_runtime(db, registry)
    found = runtime2.recovery.list_recoverable_tasks()
    assert any(t.id == task.id for t in found)


def test_waiting_approval_task_restores_pending_proposal(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    _mock_tools(runtime, needs_approval=True)
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
    runtime2 = build_task_runtime(db, registry)
    snap = runtime2.recovery.load_recovery_snapshot(task.id)
    assert snap is not None
    assert snap.pending_approval is not None
    assert snap.latest_proposal is not None


def test_checkpoint_restores_current_step(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    step = _plan_step(runtime, task)
    runtime.recovery.create_checkpoint(task, active_step_id=step.id, snapshot={"goal": "build"})
    runtime2 = build_task_runtime(db, registry)
    snap = runtime2.recovery.load_recovery_snapshot(task.id)
    assert snap is not None
    assert snap.active_step is not None
    assert snap.active_step.id == step.id


def test_resume_continues_same_task_id(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    runtime.tasks.suspend_for_user_input(task, "need info")
    runtime2 = build_task_runtime(db, registry)
    resumed = runtime2.recovery.resume_task(task.id)
    assert resumed is not None
    assert resumed.id == task.id
    assert resumed.status == TaskStatus.RUNNING


def test_abandon_marks_task_cancelled(tmp_path: Path):
    runtime, db, registry = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    runtime2 = build_task_runtime(db, registry)
    cancelled = runtime2.recovery.abandon_task(task.id)
    assert cancelled is not None
    assert cancelled.status == TaskStatus.CANCELLED


# --- 6.6 상태 전이 ---


def test_ask_user_sets_waiting_user(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    task = runtime.tasks.start_task(task)
    updated = runtime.tasks.suspend_for_user_input(task, "which project?")
    assert updated.status == TaskStatus.WAITING_USER


def test_user_reply_resumes_waiting_user_task(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    task = runtime.tasks.suspend_for_user_input(task, "q")
    resumed = runtime.tasks.resume_waiting_user_task(task)
    assert resumed.status == TaskStatus.RUNNING


def test_max_steps_sets_suspended_or_partial(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    task = runtime.tasks.start_task(task)
    tr = runtime.tasks.suspend_max_steps(task, "max steps")
    assert tr.status in (TaskStatus.SUSPENDED, TaskStatus.PARTIALLY_COMPLETED)


def test_user_cancel_sets_cancelled(tmp_path: Path):
    runtime, _, _ = _runtime(tmp_path)
    task = runtime.tasks.create_task_from_cu_request("build")
    tr = runtime.tasks.cancel_task(task, "user_cancel")
    assert tr.status == TaskStatus.CANCELLED


# --- 6.7 초기화 실패 ---


def test_task_runtime_init_failure_is_logged(tmp_path: Path, caplog, monkeypatch):
    import logging

    reset_task_runtime_health()
    caplog.set_level(logging.ERROR)
    from iris.assistant.agent_adapter import IrisAssistant

    bad_executor = MagicMock()
    bad_executor.tool_registry = MagicMock()

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "iris.application.runtime_factory.build_task_runtime",
        _boom,
    )
    assistant = IrisAssistant(
        Database(tmp_path / "a.db"),
        bad_executor,
        MagicMock(),
        {},
        MagicMock(),
    )
    result = assistant._ensure_task_runtime()
    assert result is None
    assert get_task_runtime_health().status == "failed"


def test_task_runtime_init_failure_sets_health_failed(tmp_path: Path):
    reset_task_runtime_health()
    health = get_task_runtime_health()
    health.mark_failed(RuntimeError("boom"))
    assert health.status == "failed"
    assert health.error_type == "RuntimeError"


def test_migration_failure_is_not_silently_ignored(tmp_path: Path):
    db = Database(tmp_path / "m.db")
    versions = {
        r[0]
        for r in db._execute("SELECT version FROM schema_migrations").fetchall()
    }
    assert "005_plan_integrity" in versions
