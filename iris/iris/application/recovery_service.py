"""RecoveryService — TaskCheckpoint 생성·복원."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iris.application.task_runtime_repositories import TaskRuntimeRepositories
from iris.domain.execution.enums import ApprovalStatus
from iris.domain.execution.models import ActionAttempt, ActionProposal, ApprovalRequest
from iris.domain.shared.id_generator import new_id
from iris.domain.shared.time import utc_now_iso
from iris.domain.task.enums import TaskStatus
from iris.domain.task.events import TaskCheckpointCreated, TaskResumed
from iris.domain.task.models import Plan, PlanStep, Task, TaskCheckpoint
from iris.infrastructure.events.in_memory_dispatcher import InMemoryEventDispatcher


@dataclass
class RecoverySnapshot:
    """앱 재시작 시 복구 가능한 Task 스냅샷."""

    task: Task
    plan: Plan | None = None
    steps: list[PlanStep] = field(default_factory=list)
    active_step: PlanStep | None = None
    checkpoint: TaskCheckpoint | None = None
    pending_approval: ApprovalRequest | None = None
    latest_proposal: ActionProposal | None = None
    latest_attempt: ActionAttempt | None = None


class RecoveryService:
    """중단·승인 대기 후 복구 지점."""

    def __init__(
        self,
        repos: TaskRuntimeRepositories,
        events: InMemoryEventDispatcher,
        *,
        task_service: object | None = None,
    ) -> None:
        self._repos = repos
        self._events = events
        self._tasks = task_service

    def set_task_service(self, task_service: object) -> None:
        self._tasks = task_service

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

    def list_recoverable_tasks(self, *, normalize_running: bool = True) -> list[Task]:
        getter = getattr(self._repos.tasks, "get_recoverable", None)
        if callable(getter):
            tasks = getter()
        else:
            tasks = [
                t
                for t in self._repos.tasks.get_active()
                if t.status
                in (
                    TaskStatus.RUNNING,
                    TaskStatus.WAITING_APPROVAL,
                    TaskStatus.WAITING_USER,
                    TaskStatus.WAITING_RESOURCE,
                    TaskStatus.SUSPENDED,
                    TaskStatus.INTERRUPTED,
                )
            ]
        if normalize_running and self._tasks is not None:
            normalized: list[Task] = []
            for t in tasks:
                if t.status == TaskStatus.RUNNING:
                    marked = self._tasks.mark_task_interrupted(  # type: ignore[attr-defined]
                        t, "app_restart"
                    )
                    normalized.append(marked)
                else:
                    normalized.append(t)
            return normalized
        return tasks

    def load_recovery_snapshot(self, task_id: str) -> RecoverySnapshot | None:
        task = self._repos.tasks.get_by_id(task_id)
        if task is None:
            return None
        plan = None
        steps: list[PlanStep] = []
        if task.active_plan_id:
            plan = self._repos.plans.get_plan(task.active_plan_id)
            if plan is not None:
                steps = self._repos.plans.get_steps(plan.id)
        cp = self.get_latest(task_id)
        active_step = None
        if cp and cp.active_step_id:
            active_step = self._repos.plans.get_step(cp.active_step_id)
        pending = self._repos.approvals.get_pending_for_task(task_id)
        latest_proposal = None
        latest_attempt = None
        if pending:
            latest_proposal = self._repos.execution.get_proposal(
                pending.action_proposal_id
            )
        elif cp and cp.snapshot.get("proposal_id"):
            latest_proposal = self._repos.execution.get_proposal(
                str(cp.snapshot["proposal_id"])
            )
        if latest_proposal:
            attempts = self._repos.execution.get_attempts_for_proposal(
                latest_proposal.id
            )
            if attempts:
                latest_attempt = attempts[-1]
        return RecoverySnapshot(
            task=task,
            plan=plan,
            steps=steps,
            active_step=active_step,
            checkpoint=cp,
            pending_approval=pending,
            latest_proposal=latest_proposal,
            latest_attempt=latest_attempt,
        )

    def can_resume(self, task_id: str) -> bool:
        snap = self.load_recovery_snapshot(task_id)
        if snap is None:
            return False
        return snap.task.status in (
            TaskStatus.RUNNING,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.WAITING_USER,
            TaskStatus.WAITING_RESOURCE,
            TaskStatus.SUSPENDED,
            TaskStatus.INTERRUPTED,
        )

    def resume_task(self, task_id: str) -> Task | None:
        task = self._repos.tasks.get_by_id(task_id)
        if task is None or self._tasks is None:
            return None
        resumed = self._tasks.resume_task(task)
        self._events.publish(TaskResumed(task_id=task_id))
        return resumed

    def abandon_task(self, task_id: str) -> Task | None:
        task = self._repos.tasks.get_by_id(task_id)
        if task is None or self._tasks is None:
            return None
        pending = self._repos.approvals.get_pending_for_task(task_id)
        if pending is not None:
            self._repos.approvals.update_status(pending.id, ApprovalStatus.DENIED)
        self._tasks.cancel_task(task, "abandoned_on_recovery")
        cancelled = self._repos.tasks.get_by_id(task_id)
        return cancelled

    def normalize_startup_tasks(self) -> list[Task]:
        """앱 시작 시 RUNNING → INTERRUPTED 정규화 후 복구 목록 반환."""
        return self.list_recoverable_tasks(normalize_running=True)

    def interrupted_at_for_task(self, task_id: str) -> str | None:
        """최신 checkpoint 중단 시각."""
        cp = self.get_latest(task_id)
        if cp is None:
            return None
        raw = cp.snapshot.get("interrupted_at")
        return str(raw) if raw else None
