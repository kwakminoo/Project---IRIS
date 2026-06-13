"""Task Runtime Repository Protocol 묶음 — Application 계층 의존."""

from __future__ import annotations

from dataclasses import dataclass

from iris.domain.execution.repositories import (
    ApprovalRepository,
    ExecutionRepository,
    VerificationRepository,
)
from iris.domain.task.repositories import (
    CheckpointRepository,
    PlanRepository,
    TaskRepository,
    TaskResultRepository,
)


@dataclass
class TaskRuntimeRepositories:
    """Infrastructure에서 주입하는 Repository Protocol 묶음."""

    tasks: TaskRepository
    plans: PlanRepository
    execution: ExecutionRepository
    approvals: ApprovalRepository
    verifications: VerificationRepository
    checkpoints: CheckpointRepository
    task_results: TaskResultRepository
