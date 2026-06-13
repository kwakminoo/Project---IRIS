"""Domain Event → UI/Monitoring 브리지."""

from __future__ import annotations

from iris.domain.task.enums import TaskStatus
from iris.domain.task.events import (
    ApprovalRequested,
    DomainEvent,
    TaskCompleted,
    TaskFailed,
    TaskStatusChanged,
)
from iris.monitoring.models import StatusCategory


class TaskStatusEventBridge:
    """Task 상태 이벤트를 모니터링·UI 후크로 전달."""

    def __init__(self, *, on_task_status: object | None = None) -> None:
        self._on_task_status = on_task_status
        self.last_task_id: str | None = None
        self.last_status: TaskStatus | None = None

    def on_event(self, event: DomainEvent) -> None:
        if isinstance(event, TaskStatusChanged):
            self.last_task_id = event.task_id
            self.last_status = event.new_status
            if self._on_task_status is not None:
                self._on_task_status(event.task_id, event.new_status.value)
        elif isinstance(event, ApprovalRequested):
            self.last_task_id = event.task_id
            self.last_status = TaskStatus.WAITING_APPROVAL
        elif isinstance(event, (TaskCompleted, TaskFailed)):
            self.last_task_id = event.task_id


def category_for_task_status(status: TaskStatus) -> StatusCategory | None:
    """Task 상태 → Monitoring category 매핑."""
    if status == TaskStatus.WAITING_APPROVAL:
        return StatusCategory.APPROVAL_WAITING
    if status == TaskStatus.FAILED:
        return StatusCategory.ERROR_DETECTED
    if status in (TaskStatus.SUSPENDED, TaskStatus.WAITING_USER):
        return StatusCategory.TASK_STALLED
    return None
