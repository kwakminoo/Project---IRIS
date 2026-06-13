"""ComputerUseAgent ↔ Task Runtime Adapter."""

from __future__ import annotations

from typing import Any, Protocol

from iris.application.runtime_factory import TaskRuntimeServices
from iris.domain.execution.models import ActionAttempt, ActionProposal
from iris.domain.shared.id_generator import new_id
from iris.domain.task.models import PlanStep, Task
from iris.domain.task.models import PlanStep as TaskPlanStep


class CuTaskRuntimePort(Protocol):
    """ComputerUseAgent가 호출하는 Task Runtime 훅."""

    @property
    def task_id(self) -> str | None: ...

    def on_cu_started(self, goal: str, slots: dict[str, Any] | None) -> str: ...
    def on_full_plan_created(self, items: list[Any]) -> None: ...
    def on_tool_execute(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
        reason: str,
        approved: bool = False,
        run_tool: bool = False,
    ) -> CuToolExecuteResult: ...
    def record_tool_result(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
        reason: str,
        success: bool,
        message: str,
        detail: str | None = None,
    ) -> None: ...
    def on_approval_pending(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
        snapshot: dict[str, Any],
    ) -> str | None: ...
    def on_approval_granted(self, tool_name: str, params: dict[str, Any]) -> bool: ...
    def on_checkpoint_verified(
        self,
        *,
        attempt_id: str | None,
        achieved: bool,
        checkpoint_id: str,
        gap: str = "",
        failure_kind: str = "",
    ) -> None: ...
    def on_cu_finished(self, *, success: bool, message: str) -> None: ...


class CuToolExecuteResult:
    """ExecutionCoordinator 결과 요약."""

    def __init__(
        self,
        *,
        approval_required: bool = False,
        approval_id: str | None = None,
        blocked: bool = False,
        message: str = "",
    ) -> None:
        self.approval_required = approval_required
        self.approval_id = approval_id
        self.blocked = blocked
        self.message = message


class CuTaskAdapter:
    """Task Runtime ↔ ComputerUseAgent 연결."""

    def __init__(self, runtime: TaskRuntimeServices) -> None:
        self._runtime = runtime
        self._task: Task | None = None
        self._plan_steps: list[TaskPlanStep] = []
        self._step_by_index: dict[int, TaskPlanStep] = {}
        self._last_attempt_id: str | None = None
        self._last_approval_id: str | None = None
        self._last_proposal_id: str | None = None

    @property
    def task_id(self) -> str | None:
        return self._task.id if self._task else None

    def on_cu_started(self, goal: str, slots: dict[str, Any] | None) -> str:
        task = self._runtime.tasks.create_task_from_cu_request(goal, slots=slots)
        task = self._runtime.tasks.start_task(task)
        self._task = task
        return task.id

    def on_full_plan_created(self, items: list[Any]) -> None:
        if self._task is None:
            return
        _plan, steps = self._runtime.tasks.on_plan_from_full_plan_items(self._task, items)
        self._plan_steps = steps
        self._step_by_index = {s.index: s for s in steps}

    def _resolve_step(self, step_index: int, tool_name: str, reason: str) -> TaskPlanStep:
        if step_index in self._step_by_index:
            return self._step_by_index[step_index]
        if self._task is None:
            raise RuntimeError("task not started")
        step = TaskPlanStep(
            id=new_id(),
            plan_id=self._task.active_plan_id or new_id(),
            index=step_index,
            title=reason or tool_name,
            capability_required=f"computer.{tool_name}",
            target=tool_name,
        )
        self._runtime.repos.plans.save_step(step)
        self._step_by_index[step_index] = step
        return step

    def on_tool_execute(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
        reason: str,
        approved: bool = False,
        run_tool: bool = False,
    ) -> CuToolExecuteResult:
        if self._task is None:
            return CuToolExecuteResult(message="no_task")
        step = self._resolve_step(step_index, tool_name, reason)
        proposal = ActionProposal(
            id=new_id(),
            task_id=self._task.id,
            plan_step_id=step.id,
            capability_id=f"computer.{tool_name}",
            tool_name=tool_name,
            arguments=dict(params),
            target=tool_name,
            estimated_risk="critical" if tool_name == "run_shell" else "low",
        )
        self._last_proposal_id = proposal.id
        outcome = self._runtime.execution.execute_step(
            self._task,
            step,
            proposal,
            approved=approved,
            run_tool=run_tool,
        )
        if outcome.attempt:
            self._last_attempt_id = outcome.attempt.id
        if outcome.approval_id:
            self._last_approval_id = outcome.approval_id
        if outcome.approval_required:
            return CuToolExecuteResult(
                approval_required=True,
                approval_id=outcome.approval_id,
                message=outcome.message,
            )
        if outcome.blocked:
            return CuToolExecuteResult(blocked=True, message=outcome.message)
        return CuToolExecuteResult(message=outcome.message)

    def record_tool_result(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
        reason: str,
        success: bool,
        message: str,
        detail: str | None = None,
    ) -> None:
        """CU Agent가 Registry 실행 후 Attempt·Result·Verification 기록."""
        if self._task is None:
            return
        from dataclasses import replace

        from iris.domain.execution.models import ActionResult
        from iris.domain.shared.time import utc_now_iso
        from iris.domain.task.enums import AttemptStatus

        step = self._resolve_step(step_index, tool_name, reason)
        proposal_id = self._last_proposal_id
        if not proposal_id:
            proposal = ActionProposal(
                id=new_id(),
                task_id=self._task.id,
                plan_step_id=step.id,
                capability_id=f"computer.{tool_name}",
                tool_name=tool_name,
                arguments=dict(params),
                target=tool_name,
            )
            self._runtime.repos.execution.save_proposal(proposal)
            proposal_id = proposal.id
        prior = self._runtime.repos.execution.get_attempts_for_proposal(proposal_id)
        attempt = ActionAttempt(
            id=new_id(),
            proposal_id=proposal_id,
            attempt_number=len(prior) + 1,
        )
        self._runtime.repos.execution.save_attempt(attempt)
        attempt = replace(
            attempt,
            status=AttemptStatus.SUCCEEDED if success else AttemptStatus.FAILED,
            ended_at=utc_now_iso(),
        )
        self._runtime.repos.execution.update_attempt(attempt)
        self._last_attempt_id = attempt.id
        self._runtime.repos.execution.save_result(
            ActionResult(
                attempt_id=attempt.id,
                tool_success=success,
                output_summary=message[:1000],
                error_summary=None if success else (message[:500] or str(detail or "")),
            )
        )
        self._runtime.verification.record_tool_observation(
            task_id=self._task.id,
            attempt_id=attempt.id,
            tool_name=tool_name,
            observation=message if success else f"fail: {message}",
            success=success,
        )
        if success:
            self._runtime.tasks.mark_step_succeeded(self._task, step)
        else:
            self._runtime.tasks.mark_step_failed(self._task, step, message)
        self._last_proposal_id = None

    def on_approval_pending(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
        snapshot: dict[str, Any],
    ) -> str | None:
        if self._task is None:
            return None
        snapshot["approval_id"] = self._last_approval_id
        snapshot["tool_name"] = tool_name
        snapshot["params"] = params
        self._runtime.recovery.create_checkpoint(
            self._task,
            active_step_id=self._step_by_index.get(step_index, TaskPlanStep(
                id="", plan_id="", index=step_index, title="", capability_required=""
            )).id if step_index in self._step_by_index else None,
            snapshot=snapshot,
        )
        return self._last_approval_id

    def on_approval_granted(self, tool_name: str, params: dict[str, Any]) -> bool:
        if self._task is None or not self._last_approval_id:
            pending = self._runtime.approvals.get_pending_for_task(self._task.id) if self._task else None
            aid = pending.id if pending else None
        else:
            aid = self._last_approval_id
        if not aid:
            return False
        req = self._runtime.approvals.grant(aid, tool_name=tool_name, arguments=params)
        if req and self._task:
            self._task = self._runtime.tasks.resume_task(self._task)
        return req is not None

    def on_checkpoint_verified(
        self,
        *,
        attempt_id: str | None,
        achieved: bool,
        checkpoint_id: str,
        gap: str = "",
        failure_kind: str = "",
    ) -> None:
        if self._task is None:
            return
        aid = attempt_id or self._last_attempt_id or new_id()
        self._runtime.verification.record_checkpoint_result(
            task_id=self._task.id,
            attempt_id=aid,
            achieved=achieved,
            gap=gap,
            failure_kind=failure_kind,
            checkpoint_id=checkpoint_id,
        )

    def on_cu_finished(self, *, success: bool, message: str) -> None:
        if self._task is None:
            return
        if success:
            self._runtime.tasks.complete_task(self._task, message)
        else:
            self._runtime.tasks.fail_task(self._task, message)
