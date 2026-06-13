"""Task Runtime 서비스 팩토리."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from iris.application.approval_service import ApprovalService
from iris.application.execution_coordinator import ExecutionCoordinator
from iris.application.recovery_service import RecoveryService
from iris.application.task_service import TaskApplicationService
from iris.application.verification_service import VerificationService
from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolContext
from iris.infrastructure.adapters.safety_policy_adapter import SafetyPolicyAdapter
from iris.infrastructure.adapters.tool_registry_adapter import ToolRegistryAdapter
from iris.infrastructure.events.in_memory_dispatcher import InMemoryEventDispatcher
from iris.infrastructure.persistence.sqlite_repositories import SqliteRepositoryBundle
from iris.storage.database import Database


@dataclass
class TaskRuntimeServices:
    """Task Runtime Application 서비스 묶음."""

    repos: SqliteRepositoryBundle
    events: InMemoryEventDispatcher
    tasks: TaskApplicationService
    approvals: ApprovalService
    verification: VerificationService
    recovery: RecoveryService
    execution: ExecutionCoordinator


def build_task_runtime(
    db: Database,
    registry: AutomationToolRegistry,
    *,
    ctx_factory: Callable[..., AutomationToolContext] | None = None,
) -> TaskRuntimeServices:
    """Database + Registry에서 Task Runtime 서비스 조립."""
    repos = SqliteRepositoryBundle(db)
    events = InMemoryEventDispatcher()

    def _default_ctx_factory(**kwargs: Any) -> AutomationToolContext:
        return AutomationToolContext(
            params=kwargs.get("params") or {},
            approved=bool(kwargs.get("approved")),
            summary=str(kwargs.get("summary") or ""),
            database=db,
        )

    factory = ctx_factory or _default_ctx_factory
    policy = SafetyPolicyAdapter(registry, default_tool_context=factory())
    tools = ToolRegistryAdapter(registry, factory)

    tasks = TaskApplicationService(repos, events)
    approvals = ApprovalService(repos, events)
    verification = VerificationService(repos, events)
    recovery = RecoveryService(repos, events)
    execution = ExecutionCoordinator(
        repos,
        events,
        policy,
        tools,
        approvals,
        tasks,
        verification,
        tool_context_factory=factory,
    )
    return TaskRuntimeServices(
        repos=repos,
        events=events,
        tasks=tasks,
        approvals=approvals,
        verification=verification,
        recovery=recovery,
        execution=execution,
    )
