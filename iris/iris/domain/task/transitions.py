"""Task 상태 전이 규칙."""

from __future__ import annotations

from iris.domain.task.enums import TaskStatus

# 허용 전이: from -> {to, ...}
_TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT: frozenset(
        {TaskStatus.QUEUED, TaskStatus.PLANNING, TaskStatus.CANCELLED}
    ),
    TaskStatus.QUEUED: frozenset(
        {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.CANCELLED}
    ),
    TaskStatus.PLANNING: frozenset(
        {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.WAITING_USER,
            TaskStatus.WAITING_RESOURCE,
            TaskStatus.SUSPENDED,
            TaskStatus.PARTIALLY_COMPLETED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_APPROVAL: frozenset(
        {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.WAITING_USER: frozenset(
        {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.WAITING_RESOURCE: frozenset(
        {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.SUSPENDED: frozenset(
        {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED}
    ),
    TaskStatus.PARTIALLY_COMPLETED: frozenset(
        {TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.CANCELLED: frozenset(),
}


def can_transition_task(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """Task 상태 전이 가능 여부."""
    if from_status == to_status:
        return True
    return to_status in _TASK_TRANSITIONS.get(from_status, frozenset())
