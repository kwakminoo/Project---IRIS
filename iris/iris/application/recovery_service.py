"""RecoveryService — TaskCheckpoint 생성·복원."""

from __future__ import annotations

from typing import Any

from iris.domain.shared.id_generator import new_id
from iris.domain.task.events import TaskCheckpointCreated
from iris.domain.task.models import Task, TaskCheckpoint
from iris.infrastructure.events.in_memory_dispatcher import InMemoryEventDispatcher
from iris.infrastructure.persistence.sqlite_repositories import SqliteRepositoryBundle


class RecoveryService:
    """중단·승인 대기 후 복구 지점."""

    def __init__(
        self,
        repos: SqliteRepositoryBundle,
        events: InMemoryEventDispatcher,
    ) -> None:
        self._repos = repos
        self._events = events

    def create_checkpoint(
        self,
        task: Task,
        *,
        plan_version: int = 1,
        completed_step_ids: list[str] | None = None,
        active_step_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> TaskCheckpoint:
        cp = TaskCheckpoint(
            id=new_id(),
            task_id=task.id,
            plan_version=plan_version,
            completed_step_ids=list(completed_step_ids or []),
            active_step_id=active_step_id,
            snapshot=dict(snapshot or {}),
        )
        self._repos.checkpoints.save(cp)
        self._events.publish(
            TaskCheckpointCreated(task_id=task.id, checkpoint_id=cp.id)
        )
        return cp

    def get_latest(self, task_id: str) -> TaskCheckpoint | None:
        return self._repos.checkpoints.get_latest_for_task(task_id)
