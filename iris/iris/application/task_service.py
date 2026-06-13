"""TaskApplicationService — Task 생명주기."""

from __future__ import annotations

from typing import Any

from iris.domain.shared.id_generator import new_id
from iris.domain.task.enums import StepStatus, TaskStatus, TaskType
from iris.domain.task.events import (
    PlanCreated,
    PlanStepStarted,
    TaskCompleted,
    TaskCreated,
    TaskFailed,
    TaskStarted,
    TaskStatusChanged,
)
from iris.domain.task.models import Plan, PlanStep, Task, TaskResult
from iris.infrastructure.events.in_memory_dispatcher import InMemoryEventDispatcher
from iris.infrastructure.persistence.sqlite_repositories import SqliteRepositoryBundle


class TaskApplicationService:
    """Task 생성·시작·완료·실패."""

    def __init__(
        self,
        repos: SqliteRepositoryBundle,
        events: InMemoryEventDispatcher,
    ) -> None:
        self._repos = repos
        self._events = events

    def create_task_from_cu_request(
        self,
        goal: str,
        *,
        title: str | None = None,
        slots: dict[str, Any] | None = None,
    ) -> Task:
        """Computer Use 요청에서 Task 생성."""
        task = Task(
            id=new_id(),
            task_type=TaskType.COMPUTER_USE,
            title=(title or goal[:80]).strip() or "Computer Use",
            goal=goal.strip(),
            status=TaskStatus.QUEUED,
            constraints=_slots_to_constraints(slots),
        )
        self._repos.tasks.save(task)
        self._events.publish(TaskCreated(task_id=task.id, goal=task.goal))
        return task

    def start_task(self, task: Task) -> Task:
        """Task → planning 또는 running."""
        for status in (TaskStatus.PLANNING, TaskStatus.RUNNING):
            result = task.transition_to(status)
            if result.ok and result.value:
                task = result.value
        self._repos.tasks.update(task)
        self._events.publish(TaskStarted(task_id=task.id))
        self._events.publish(
            TaskStatusChanged(
                task_id=task.id,
                old_status=TaskStatus.QUEUED,
                new_status=task.status,
            )
        )
        return task

    def on_plan_created(
        self,
        task: Task,
        *,
        steps: list[tuple[str, str, str, dict[str, Any]]],
    ) -> tuple[Plan, list[PlanStep]]:
        """Plan + PlanStep 저장. steps: (title, capability, tool_name, params)."""
        plan = Plan(id=new_id(), task_id=task.id, version=1)
        self._repos.plans.save_plan(plan)
        plan_steps: list[PlanStep] = []
        for idx, (title, cap, tool, params) in enumerate(steps):
            step = PlanStep(
                id=new_id(),
                plan_id=plan.id,
                index=idx,
                title=title,
                capability_required=cap or f"computer.{tool}",
                target=tool,
                expected_result={"tool": tool, "params": params},
            )
            self._repos.plans.save_step(step)
            plan_steps.append(step)
        task.active_plan_id = plan.id
        self._repos.tasks.update(task)
        self._events.publish(
            PlanCreated(task_id=task.id, plan_id=plan.id, version=plan.version)
        )
        return plan, plan_steps

    def on_plan_from_full_plan_items(
        self,
        task: Task,
        items: list[Any],
    ) -> tuple[Plan, list[PlanStep]]:
        """ComputerUseFullPlan plans[] → PlanStep."""
        steps_data: list[tuple[str, str, str, dict[str, Any]]] = []
        for item in items:
            tool = getattr(item, "tool", "") or ""
            params = dict(getattr(item, "params", {}) or {})
            reason = getattr(item, "reason", "") or tool
            steps_data.append((reason[:120], f"computer.{tool}", tool, params))
        return self.on_plan_created(task, steps=steps_data)

    def mark_step_started(self, task: Task, step: PlanStep) -> PlanStep:
        updated = step.mark_running()
        self._repos.plans.update_step(updated)
        self._events.publish(
            PlanStepStarted(task_id=task.id, plan_step_id=step.id, index=step.index)
        )
        return updated

    def mark_step_succeeded(self, task: Task, step: PlanStep) -> PlanStep:
        from iris.domain.task.events import PlanStepSucceeded

        updated = step.mark_succeeded()
        self._repos.plans.update_step(updated)
        self._events.publish(
            PlanStepSucceeded(task_id=task.id, plan_step_id=step.id)
        )
        return updated

    def mark_step_failed(self, task: Task, step: PlanStep, reason: str) -> PlanStep:
        from iris.domain.task.events import PlanStepFailed

        updated = step.mark_failed()
        self._repos.plans.update_step(updated)
        self._events.publish(
            PlanStepFailed(task_id=task.id, plan_step_id=step.id, reason=reason)
        )
        return updated

    def complete_task(self, task: Task, summary: str, *, verification_summary: str = "") -> TaskResult:
        result = task.transition_to(TaskStatus.COMPLETED)
        if result.ok and result.value:
            task = result.value
            self._repos.tasks.update(task)
        tr = TaskResult(
            task_id=task.id,
            status=TaskStatus.COMPLETED,
            summary=summary[:2000],
            verification_summary=verification_summary[:1000],
        )
        self._repos.task_results.save(tr)
        self._events.publish(TaskCompleted(task_id=task.id, summary=summary[:200]))
        return tr

    def fail_task(self, task: Task, reason: str) -> TaskResult:
        result = task.transition_to(TaskStatus.FAILED)
        if result.ok and result.value:
            task = result.value
            self._repos.tasks.update(task)
        tr = TaskResult(
            task_id=task.id,
            status=TaskStatus.FAILED,
            summary=reason[:2000],
            unresolved_issues=[reason[:500]],
        )
        self._repos.task_results.save(tr)
        self._events.publish(TaskFailed(task_id=task.id, reason=reason[:200]))
        return tr

    def resume_task(self, task: Task) -> Task:
        """승인 후 running 복귀."""
        old = task.status
        result = task.transition_to(TaskStatus.RUNNING)
        if not result.ok or result.value is None:
            return task
        updated = result.value
        self._repos.tasks.update(updated)
        self._events.publish(
            TaskStatusChanged(task_id=task.id, old_status=old, new_status=TaskStatus.RUNNING)
        )
        return updated

    def get_task(self, task_id: str) -> Task | None:
        return self._repos.tasks.get_by_id(task_id)


def _slots_to_constraints(slots: dict[str, Any] | None) -> list[str]:
    if not slots:
        return []
    return [f"{k}={v}" for k, v in slots.items() if v]
