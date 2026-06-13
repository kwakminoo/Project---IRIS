"""Task·Plan·PlanStep·Checkpoint·TaskResult 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from iris.domain.shared.result import Result
from iris.domain.shared.time import utc_now_iso
from iris.domain.task.enums import (
    StepStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from iris.domain.task.transitions import can_transition_task


@dataclass
class Task:
    """사용자가 달성하려는 추적 가능한 목표."""

    id: str
    task_type: TaskType
    title: str
    goal: str
    status: TaskStatus = TaskStatus.DRAFT
    priority: TaskPriority = TaskPriority.NORMAL
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    parent_task_id: str | None = None
    workspace_id: str | None = None
    active_plan_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    ended_at: str | None = None

    def transition_to(self, new_status: TaskStatus) -> Result["Task"]:
        """유효한 상태 전이만 허용."""
        if not can_transition_task(self.status, new_status):
            return Result.failure(
                "invalid_transition",
                f"{self.status.value} → {new_status.value} 불가",
            )
        now = utc_now_iso()
        started = self.started_at
        ended = self.ended_at
        if new_status == TaskStatus.RUNNING and started is None:
            started = now
        if new_status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PARTIALLY_COMPLETED,
        ):
            ended = now
        return Result.success(
            replace(
                self,
                status=new_status,
                started_at=started,
                ended_at=ended,
            )
        )


@dataclass
class Plan:
    """Task 달성을 위한 실행 계획 (버전 관리)."""

    id: str
    task_id: str
    version: int = 1
    revision_reason: str | None = None
    previous_plan_id: str | None = None
    superseded_at: str | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def create_revision(self, reason: str) -> "Plan":
        """실패·환경 변화 시 새 Plan ID·버전."""
        from iris.domain.shared.id_generator import new_id

        return Plan(
            id=new_id(),
            task_id=self.task_id,
            version=self.version + 1,
            revision_reason=reason,
            previous_plan_id=self.id,
            created_at=utc_now_iso(),
        )


@dataclass
class PlanStep:
    """실제 실행 단위."""

    id: str
    plan_id: str
    index: int
    title: str
    capability_required: str
    status: StepStatus = StepStatus.PENDING
    target: str = ""
    expected_result: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    retry_policy: dict[str, Any] = field(default_factory=dict)

    def mark_running(self) -> "PlanStep":
        return replace(self, status=StepStatus.RUNNING)

    def mark_verifying(self) -> "PlanStep":
        return replace(self, status=StepStatus.VERIFYING)

    def mark_waiting_approval(self) -> "PlanStep":
        return replace(self, status=StepStatus.WAITING_APPROVAL)

    def mark_waiting_user(self) -> "PlanStep":
        return replace(self, status=StepStatus.WAITING_USER)

    def mark_succeeded(self) -> "PlanStep":
        return replace(self, status=StepStatus.SUCCEEDED)

    def mark_partially_succeeded(self) -> "PlanStep":
        return replace(self, status=StepStatus.PARTIALLY_SUCCEEDED)

    def mark_failed(self) -> "PlanStep":
        return replace(self, status=StepStatus.FAILED)

    def mark_cancelled(self) -> "PlanStep":
        return replace(self, status=StepStatus.CANCELLED)


@dataclass
class TaskCheckpoint:
    """중단·승인 대기·앱 종료 후 복구 지점."""

    id: str
    task_id: str
    plan_version: int
    completed_step_ids: list[str] = field(default_factory=list)
    active_step_id: str | None = None
    resumable: bool = True
    snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class TaskResult:
    """Task 최종 결과."""

    task_id: str
    status: TaskStatus
    summary: str
    verification_summary: str = ""
    unresolved_issues: list[str] = field(default_factory=list)
    completed_at: str = field(default_factory=utc_now_iso)
