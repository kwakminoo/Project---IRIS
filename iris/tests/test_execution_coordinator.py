"""ExecutionCoordinator·Approval 통합 테스트."""

from pathlib import Path
from unittest.mock import MagicMock

from iris.application.runtime_factory import build_task_runtime
from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolResult
from iris.domain.execution.models import ActionProposal
from iris.domain.shared.id_generator import new_id
from iris.domain.task.enums import TaskStatus, StepStatus
from iris.domain.task.models import PlanStep
from iris.infrastructure.adapters.tool_registry_adapter import ToolRegistryAdapter
from iris.storage.database import Database


def test_execution_coordinator_approval_interrupts(tmp_path: Path):
    db = Database(tmp_path / "exec.db")
    registry = AutomationToolRegistry(db)
    runtime = build_task_runtime(db, registry)

    mock_registry = MagicMock(spec=AutomationToolRegistry)
    mock_registry.needs_approval.return_value = True
    mock_registry.preview.return_value = "run shell preview"

    def ctx_factory(**kwargs):
        from iris.automation.tool_types import AutomationToolContext
        return AutomationToolContext(params=kwargs.get("params") or {})

    from iris.infrastructure.adapters.safety_policy_adapter import SafetyPolicyAdapter

    runtime.execution._policy = SafetyPolicyAdapter(mock_registry, default_tool_context=ctx_factory())
    runtime.execution._tools = ToolRegistryAdapter(mock_registry, ctx_factory)

    task = runtime.tasks.create_task_from_cu_request("run tests")
    task = runtime.tasks.start_task(task)
    step = PlanStep(
        id=new_id(),
        plan_id=new_id(),
        index=0,
        title="shell",
        capability_required="computer.run_shell",
        target="run_shell",
    )
    runtime.repos.plans.save_plan(
        __import__("iris.domain.task.models", fromlist=["Plan"]).Plan(
            id=step.plan_id, task_id=task.id
        )
    )
    runtime.repos.plans.save_step(step)

    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.run_shell",
        tool_name="run_shell",
        arguments={"command": "npm test"},
    )
    outcome = runtime.execution.execute_step(task, step, proposal, run_tool=False)
    assert outcome.approval_required
    assert outcome.approval_id is not None
    updated = runtime.repos.tasks.get_by_id(task.id)
    assert updated is not None
    assert updated.status == TaskStatus.WAITING_APPROVAL


def test_approval_grant_requires_matching_hash(tmp_path: Path):
    db = Database(tmp_path / "appr.db")
    runtime = build_task_runtime(db, AutomationToolRegistry(db))
    task = runtime.tasks.create_task_from_cu_request("shell")
    from iris.domain.execution.models import ActionProposal

    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=new_id(),
        capability_id="computer.run_shell",
        tool_name="run_shell",
        arguments={"command": "npm test"},
    )
    req = runtime.approvals.create_request(task, proposal)
    ok = runtime.approvals.grant(req.id, tool_name="run_shell", arguments={"command": "npm test"})
    assert ok is not None
    bad = runtime.approvals.grant(req.id, tool_name="run_shell", arguments={"command": "rm -rf /"})
    assert bad is None


def test_tool_execution_records_attempt(tmp_path: Path):
    db = Database(tmp_path / "tool.db")
    registry = AutomationToolRegistry(db)
    runtime = build_task_runtime(db, registry)

    mock_tools = MagicMock()
    mock_tools.run.return_value = AutomationToolResult(True, "ok")
    mock_tools.needs_approval.return_value = False
    runtime.execution._tools = mock_tools
    from iris.infrastructure.adapters.safety_policy_adapter import SafetyPolicyAdapter

    runtime.execution._policy = SafetyPolicyAdapter(registry)

    task = runtime.tasks.create_task_from_cu_request("info")
    task = runtime.tasks.start_task(task)
    step = PlanStep(
        id=new_id(),
        plan_id=new_id(),
        index=0,
        title="sys",
        capability_required="computer.get_system_info",
    )
    from iris.domain.task.models import Plan

    runtime.repos.plans.save_plan(Plan(id=step.plan_id, task_id=task.id))
    runtime.repos.plans.save_step(step)
    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.get_system_info",
        tool_name="get_system_info",
        arguments={},
    )
    outcome = runtime.execution.execute_step(task, step, proposal)
    assert outcome.attempt is not None
    assert outcome.result is not None
    assert outcome.result.tool_success
    assert outcome.step_status == StepStatus.SUCCEEDED
