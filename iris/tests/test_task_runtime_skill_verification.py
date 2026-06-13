"""Skill checkpoint → VerificationResult 통합 테스트."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from iris.application.runtime_factory import build_task_runtime
from iris.assistant.agent_adapter import IrisAssistant
from iris.assistant.text_compose_flow import TextComposeFlow
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolResult
from iris.domain.execution.enums import VerificationStatus
from iris.domain.task.enums import StepStatus, TaskStatus
from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter
from iris.storage.database import Database


def _runtime(tmp_path: Path):
    db = Database(tmp_path / "skill.db")
    registry = AutomationToolRegistry(db)
    return build_task_runtime(db, registry), db


def _assistant(tmp_path: Path) -> IrisAssistant:
    db = Database(tmp_path / "skill_a.db")
    executor = ActionExecutor(db, {})
    settings = SimpleNamespace(computer_use_full_plan_enabled=False)
    return IrisAssistant(db, executor, MagicMock(), {}, settings=settings)  # type: ignore[arg-type]


def _count_verifications(db: Database) -> int:
    row = db._execute("SELECT COUNT(*) FROM verification_results").fetchone()
    return int(row[0]) if row else 0


def test_skill_tool_attempts_are_recorded(tmp_path: Path):
    runtime, db = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("compose", {"skill_id": "text_compose"})
    from unittest.mock import MagicMock
    from iris.infrastructure.adapters.safety_policy_adapter import SafetyPolicyAdapter
    from iris.infrastructure.adapters.tool_registry_adapter import ToolRegistryAdapter
    from iris.automation.tool_types import AutomationToolContext, AutomationToolResult

    mock_registry = MagicMock()
    mock_registry.run.return_value = AutomationToolResult(True, "ok")
    mock_registry.needs_approval.return_value = False

    def ctx_factory(**kwargs):
        return AutomationToolContext(params=kwargs.get("params") or {})

    runtime.execution._policy = SafetyPolicyAdapter(mock_registry, default_tool_context=ctx_factory())
    runtime.execution._tools = ToolRegistryAdapter(mock_registry, ctx_factory)
    adapter.execute_tool_step(
        tool_name="launch_app",
        params={"app_key": "notepad"},
        step_index=0,
        reason="launch",
        approved=True,
    )
    adapter.execute_tool_step(
        tool_name="type_text",
        params={"text": "hi"},
        step_index=1,
        reason="type",
        approved=True,
    )
    row = db._execute("SELECT COUNT(*) FROM action_attempts").fetchone()
    assert int(row[0]) >= 2


def test_skill_checkpoint_creates_verification_result(tmp_path: Path):
    runtime, db = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("compose", {"skill_id": "text_compose"})
    step = adapter._adhoc_step
    assert step is not None
    from iris.domain.execution.models import ActionAttempt, ActionProposal
    from iris.domain.shared.id_generator import new_id

    proposal = ActionProposal(
        id=new_id(),
        task_id=adapter.task_id or "",
        plan_step_id=step.id,
        capability_id="computer.type_text",
        tool_name="type_text",
        arguments={"text": "hi"},
    )
    runtime.repos.execution.save_proposal(proposal)
    attempt = ActionAttempt(id=new_id(), proposal_id=proposal.id, attempt_number=1)
    runtime.repos.execution.save_attempt(attempt)
    adapter._last_attempt_id = attempt.id
    adapter.on_skill_checkpoint_verified(
        attempt_id=attempt.id,
        achieved=True,
        checkpoint_id="cp_text_typed",
        related_attempt_ids=[attempt.id],
    )
    assert _count_verifications(db) >= 1


def test_skill_success_requires_checkpoint_success(tmp_path: Path):
    runtime, db = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("compose", {})
    adapter._skill_final_achieved = False
    adapter.on_cu_finished(success=True, message="looks ok")
    task = runtime.repos.tasks.get_by_id(adapter.task_id or "")
    assert task is not None
    assert task.status != TaskStatus.COMPLETED


def test_skill_partial_result_does_not_complete_task(tmp_path: Path):
    runtime, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    task = runtime.tasks.create_task_from_cu_request("partial")
    task = runtime.tasks.start_task(task)
    adapter._task = task
    step = runtime.tasks.ensure_adhoc_plan(task)[1]
    adapter._adhoc_step = step
    from iris.domain.execution.models import ActionAttempt, ActionProposal
    from iris.domain.shared.id_generator import new_id

    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.focus_window",
        tool_name="focus_window",
        arguments={},
    )
    runtime.repos.execution.save_proposal(proposal)
    attempt = ActionAttempt(id=new_id(), proposal_id=proposal.id, attempt_number=1)
    runtime.repos.execution.save_attempt(attempt)
    adapter.on_skill_checkpoint_verified(
        attempt_id=attempt.id,
        achieved=True,
        checkpoint_id="cp_focus",
        partial=True,
    )
    loaded = runtime.repos.plans.get_step(step.id)
    assert loaded is not None
    assert loaded.status == StepStatus.PARTIALLY_SUCCEEDED


def test_skill_failed_checkpoint_marks_step_failed_or_retryable(tmp_path: Path):
    runtime, _ = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    task = runtime.tasks.create_task_from_cu_request("fail skill")
    task = runtime.tasks.start_task(task)
    adapter._task = task
    step = runtime.tasks.ensure_adhoc_plan(task)[1]
    adapter._adhoc_step = step
    from iris.domain.execution.models import ActionAttempt, ActionProposal
    from iris.domain.shared.id_generator import new_id

    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.type_text",
        tool_name="type_text",
        arguments={"text": "x"},
    )
    runtime.repos.execution.save_proposal(proposal)
    attempt = ActionAttempt(id=new_id(), proposal_id=proposal.id, attempt_number=1)
    runtime.repos.execution.save_attempt(attempt)
    adapter.on_skill_checkpoint_verified(
        attempt_id=attempt.id,
        achieved=False,
        checkpoint_id="cp_text_typed",
        gap="not found",
    )
    loaded = runtime.repos.plans.get_step(step.id)
    assert loaded is not None
    assert loaded.status == StepStatus.FAILED


def test_skill_verification_references_real_attempt(tmp_path: Path):
    runtime, db = _runtime(tmp_path)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("x", {})
    from iris.domain.execution.models import ActionAttempt, ActionProposal
    from iris.domain.shared.id_generator import new_id

    step = adapter._adhoc_step
    assert step is not None
    proposal = ActionProposal(
        id=new_id(),
        task_id=adapter.task_id or "",
        plan_step_id=step.id,
        capability_id="computer.launch_app",
        tool_name="launch_app",
        arguments={},
    )
    runtime.repos.execution.save_proposal(proposal)
    attempt = ActionAttempt(id=new_id(), proposal_id=proposal.id, attempt_number=1)
    runtime.repos.execution.save_attempt(attempt)
    vr = runtime.verification.record_skill_checkpoint(
        task_id=adapter.task_id or "",
        attempt_id=attempt.id,
        checkpoint_id="cp_app_open",
        achieved=True,
    )
    assert vr.attempt_id == attempt.id
    assert vr.status == VerificationStatus.SUCCESS


def test_multi_tool_skill_records_all_attempts(tmp_path: Path):
    assistant = _assistant(tmp_path)
    agent = assistant._create_computer_use_agent()
    registry = assistant._executor.tool_registry
    registry.run = MagicMock(return_value=AutomationToolResult(True, "ok", "ok|verified"))  # type: ignore[method-assign]

    with patch(
        "iris.assistant.cu_mechanical_verify.mechanical_verify_checkpoint",
        return_value=SimpleNamespace(status="success", gap=""),
    ), patch.object(
        agent, "_run_perceive_desktop", lambda *a, **k: None
    ), patch(
        "iris.automation.window_controller.find_windows_by_title_substring",
        return_value=[SimpleNamespace(hwnd=1, title="메모장")],
    ):
        slots = {
            "skill_id": "text_compose",
            "app_key": "notepad",
            "display_name": "메모장",
            "text_to_type": "smoke-test",
        }
        agent.run("메모장에 입력", slots=slots)
    count = assistant._db._execute("SELECT COUNT(*) FROM action_attempts").fetchone()
    assert int(count[0]) >= 2
