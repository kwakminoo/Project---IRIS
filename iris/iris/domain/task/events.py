"""Task 도메인 이벤트."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Union

from iris.domain.task.enums import StepStatus, TaskStatus


@dataclass(frozen=True)
class TaskCreated:
    task_id: str
    goal: str


@dataclass(frozen=True)
class TaskStarted:
    task_id: str


@dataclass(frozen=True)
class PlanCreated:
    task_id: str
    plan_id: str
    version: int


@dataclass(frozen=True)
class PlanStepStarted:
    task_id: str
    plan_step_id: str
    index: int


@dataclass(frozen=True)
class ActionProposed:
    task_id: str
    proposal_id: str
    tool_name: str


@dataclass(frozen=True)
class ApprovalRequested:
    task_id: str
    approval_id: str
    tool_name: str


@dataclass(frozen=True)
class ApprovalGranted:
    task_id: str
    approval_id: str


@dataclass(frozen=True)
class ActionAttemptStarted:
    task_id: str
    attempt_id: str
    proposal_id: str


@dataclass(frozen=True)
class ActionAttemptCompleted:
    task_id: str
    attempt_id: str
    success: bool


@dataclass(frozen=True)
class VerificationCompleted:
    task_id: str
    attempt_id: str
    status: str


@dataclass(frozen=True)
class PlanStepSucceeded:
    task_id: str
    plan_step_id: str


@dataclass(frozen=True)
class PlanStepFailed:
    task_id: str
    plan_step_id: str
    reason: str


@dataclass(frozen=True)
class TaskCheckpointCreated:
    task_id: str
    checkpoint_id: str


@dataclass(frozen=True)
class TaskCompleted:
    task_id: str
    summary: str


@dataclass(frozen=True)
class TaskFailed:
    task_id: str
    reason: str


@dataclass(frozen=True)
class TaskStatusChanged:
    task_id: str
    old_status: TaskStatus
    new_status: TaskStatus


@dataclass(frozen=True)
class PlanStepStatusChanged:
    task_id: str
    plan_step_id: str
    new_status: StepStatus


DomainEvent = Union[
    TaskCreated,
    TaskStarted,
    PlanCreated,
    PlanStepStarted,
    ActionProposed,
    ApprovalRequested,
    ApprovalGranted,
    ActionAttemptStarted,
    ActionAttemptCompleted,
    VerificationCompleted,
    PlanStepSucceeded,
    PlanStepFailed,
    TaskCheckpointCreated,
    TaskCompleted,
    TaskFailed,
    TaskStatusChanged,
    PlanStepStatusChanged,
]


class DomainEventHandler(Protocol):
    """도메인 이벤트 구독자."""

    def on_event(self, event: DomainEvent) -> None: ...
