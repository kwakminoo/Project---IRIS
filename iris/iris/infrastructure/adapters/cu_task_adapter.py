"""ComputerUseAgent ↔ Task Runtime Adapter."""

from __future__ import annotations

from typing import Any, Protocol

from iris.application.runtime_factory import TaskRuntimeServices
from iris.domain.execution.models import ActionAttempt, ActionProposal
from iris.domain.task.enums import StepStatus, TaskStatus
from iris.domain.task.models import PlanStep, Task
from iris.domain.task.models import PlanStep as TaskPlanStep


class CuTaskRuntimePort(Protocol):
    """ComputerUseAgent가 호출하는 Task Runtime 훅."""

    @property
    def task_id(self) -> str | None: ...

    def begin_cu_session(self, goal: str, slots: dict[str, Any] | None) -> str: ...
    def attach_task(self, task_id: str) -> bool: ...
    def on_cu_started(self, goal: str, slots: dict[str, Any] | None) -> str: ...
    def on_full_plan_created(self, items: list[Any]) -> None: ...
    def execute_tool_step(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
        reason: str,
        approved: bool = False,
        finalize_if_no_checkpoint: bool = True,
    ) -> CuToolExecuteResult: ...
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
    def execute_approved_proposal(
        self,
        *,
        proposal_id: str,
        approval_id: str,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
    ) -> CuToolExecuteResult: ...
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
    def on_cu_waiting_user(self, message: str) -> None: ...
    def on_cu_suspended(self, message: str) -> None: ...
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
        attempt_id: str | None = None,
        proposal_id: str | None = None,
        tool_success: bool = False,
    ) -> None:
        self.approval_required = approval_required
        self.approval_id = approval_id
        self.blocked = blocked
        self.message = message
        self.attempt_id = attempt_id
        self.proposal_id = proposal_id
        self.tool_success = tool_success


class CuTaskAdapter:
    """Task Runtime ↔ ComputerUseAgent 연결."""

    def __init__(self, runtime: TaskRuntimeServices) -> None:
        self._runtime = runtime
        self._task: Task | None = None
        self._adhoc_step: PlanStep | None = None
        self._plan_steps: list[TaskPlanStep] = []
        self._step_by_index: dict[int, TaskPlanStep] = {}
        self._last_attempt_id: str | None = None
        self._last_approval_id: str | None = None
        self._last_proposal_id: str | None = None
        self._skill_final_achieved: bool | None = None

    @property
    def task_id(self) -> str | None:
        return self._task.id if self._task else None

    @property
    def last_attempt_id(self) -> str | None:
        return self._last_attempt_id

    def proposal_has_completed_attempt(self, proposal_id: str) -> bool:
        """이미 성공한 Attempt가 있으면 중복 실행 방지."""
        from iris.domain.task.enums import AttemptStatus

        attempts = self._runtime.repos.execution.get_attempts_for_proposal(proposal_id)
        return any(a.status == AttemptStatus.SUCCEEDED for a in attempts)

    def begin_cu_session(self, goal: str, slots: dict[str, Any] | None) -> str:
        """모든 CU 경로 진입 전 Task + ad-hoc Plan 생성."""
        task = self._runtime.tasks.create_task_from_cu_request(goal, slots=slots)
        task = self._runtime.tasks.start_task(task)
        self._task = task
        _plan, step = self._runtime.tasks.ensure_adhoc_plan(
            task, step_title=goal[:80], tool_hint=""
        )
        self._adhoc_step = step
        self._step_by_index[0] = step
        return task.id

    def attach_task(self, task_id: str) -> bool:
        """복구·재개 시 DB Task 연결."""
        task = self._runtime.tasks.attach_task(task_id)
        if task is None:
            return False
        self._task = task
        if task.active_plan_id:
            steps = self._runtime.repos.plans.get_steps(task.active_plan_id)
            self._plan_steps = steps
            self._step_by_index = {s.index: s for s in steps}
            if steps:
                self._adhoc_step = steps[0]
        pending = self._runtime.approvals.get_pending_for_task(task_id)
        if pending:
            self._last_approval_id = pending.id
            self._last_proposal_id = pending.action_proposal_id
        return True

    def on_cu_started(self, goal: str, slots: dict[str, Any] | None) -> str:
        """레거시 호환 — begin_cu_session과 동일."""
        if self._task is not None:
            return self._task.id
        return self.begin_cu_session(goal, slots)

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
        self._runtime.tasks.ensure_active_plan(self._task)
        self._task = self._runtime.tasks.get_task(self._task.id) or self._task
        plan_id = self._task.active_plan_id
        if not plan_id:
            raise RuntimeError("active plan missing")
        step = TaskPlanStep(
            id=__import__("iris.domain.shared.id_generator", fromlist=["new_id"]).new_id(),
            plan_id=plan_id,
            index=step_index,
            title=reason or tool_name,
            capability_required=f"computer.{tool_name}",
            target=tool_name,
        )
        self._runtime.repos.plans.save_step(step)
        self._step_by_index[step_index] = step
        return step

    def _build_proposal(
        self,
        step: TaskPlanStep,
        tool_name: str,
        params: dict[str, Any],
    ) -> ActionProposal:
        return ActionProposal(
            id=__import__("iris.domain.shared.id_generator", fromlist=["new_id"]).new_id(),
            task_id=self._task.id if self._task else "",
            plan_step_id=step.id,
            capability_id=f"computer.{tool_name}",
            tool_name=tool_name,
            arguments=dict(params),
            target=tool_name,
            estimated_risk="critical" if tool_name == "run_shell" else "low",
        )

    def _verify_launch_target(self, params: dict[str, Any]) -> bool:
        """launch_app 후 대상 창 존재 여부 확인."""
        display = str(params.get("display_name") or "").strip()
        app_key = str(params.get("app_key") or "").strip()
        title_hint = display or app_key
        if not title_hint:
            return False
        from iris.automation import window_controller

        wins = window_controller.find_windows_by_title_substring(title_hint)
        return bool(wins)

    def execute_tool_step(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
        reason: str,
        approved: bool = False,
        finalize_if_no_checkpoint: bool = True,
    ) -> CuToolExecuteResult:
        """정책+실행+기록 통합 (Quick Launch·Skill·Tier1)."""
        if self._task is None:
            return CuToolExecuteResult(blocked=True, message="no_task")
        step = self._resolve_step(step_index, tool_name, reason)
        proposal = self._build_proposal(step, tool_name, params)
        self._last_proposal_id = proposal.id
        outcome = self._runtime.execution.execute_step(
            self._task,
            step,
            proposal,
            approved=approved,
            run_tool=True,
        )
        if outcome.attempt:
            self._last_attempt_id = outcome.attempt.id
        if outcome.approval_id:
            self._last_approval_id = outcome.approval_id
        if outcome.approval_required:
            return CuToolExecuteResult(
                approval_required=True,
                approval_id=outcome.approval_id,
                proposal_id=proposal.id,
                message=outcome.message,
            )
        if outcome.blocked:
            return CuToolExecuteResult(blocked=True, message=outcome.message)
        if (
            finalize_if_no_checkpoint
            and outcome.verification
            and outcome.step_status == StepStatus.VERIFYING
        ):
            achieved = True
            gap = ""
            if tool_name == "launch_app":
                achieved = self._verify_launch_target(params)
                if not achieved:
                    gap = "target_window_not_found"
            vr = self._runtime.verification.record_checkpoint_result(
                task_id=self._task.id,
                attempt_id=outcome.attempt.id if outcome.attempt else "",
                achieved=achieved,
                checkpoint_id="lightweight_tool_ok",
                gap=gap,
                confidence=0.7 if achieved else 0.0,
            )
            self._runtime.verification.finalize_step_from_verification(
                self._task, step, vr
            )
        return CuToolExecuteResult(
            message=outcome.message,
            attempt_id=self._last_attempt_id,
            proposal_id=proposal.id,
            tool_success=bool(outcome.result and outcome.result.tool_success),
        )

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
        proposal = self._build_proposal(step, tool_name, params)
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
                proposal_id=proposal.id,
                message=outcome.message,
            )
        if outcome.blocked:
            return CuToolExecuteResult(blocked=True, message=outcome.message)
        return CuToolExecuteResult(
            message=outcome.message,
            proposal_id=proposal.id,
        )

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
        """on_tool_execute(proposal) 후 실제 실행 결과 기록 — 도구 재실행 없음."""
        if self._task is None:
            return
        from dataclasses import replace

        from iris.domain.execution.models import ActionResult
        from iris.domain.shared.time import utc_now_iso
        from iris.domain.task.enums import AttemptStatus

        step = self._resolve_step(step_index, tool_name, reason)
        proposal_id = self._last_proposal_id
        if not proposal_id:
            proposal = self._build_proposal(step, tool_name, params)
            self._runtime.repos.execution.save_proposal(proposal)
            proposal_id = proposal.id
            self._last_proposal_id = proposal_id
        prior = self._runtime.repos.execution.get_attempts_for_proposal(proposal_id)
        attempt = ActionAttempt(
            id=__import__("iris.domain.shared.id_generator", fromlist=["new_id"]).new_id(),
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
            self._runtime.tasks.mark_step_verifying(self._task, step)
        else:
            self._runtime.tasks.mark_step_failed(self._task, step, message)

    def execute_approved_proposal(
        self,
        *,
        proposal_id: str,
        approval_id: str,
        tool_name: str,
        params: dict[str, Any],
        step_index: int,
    ) -> CuToolExecuteResult:
        """승인 후 공통 execute_proposal 경로."""
        if self._task is None:
            return CuToolExecuteResult(blocked=True, message="no_task")
        outcome = self._runtime.execution.execute_proposal(
            proposal_id,
            approval_id=approval_id,
        )
        if outcome.attempt:
            self._last_attempt_id = outcome.attempt.id
        if outcome.blocked:
            return CuToolExecuteResult(
                blocked=True,
                message=outcome.message,
                proposal_id=proposal_id,
            )
        return CuToolExecuteResult(
            message=outcome.message,
            attempt_id=self._last_attempt_id,
            proposal_id=proposal_id,
            tool_success=bool(outcome.result and outcome.result.tool_success),
        )

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
        snapshot["proposal_id"] = self._last_proposal_id
        snapshot["tool_name"] = tool_name
        snapshot["params"] = params
        step_id = None
        if step_index in self._step_by_index:
            step_id = self._step_by_index[step_index].id
        self._runtime.recovery.create_checkpoint(
            self._task,
            active_step_id=step_id,
            snapshot=snapshot,
        )
        return self._last_approval_id

    def on_approval_granted(self, tool_name: str, params: dict[str, Any]) -> bool:
        if self._task is None:
            return False
        aid = self._last_approval_id
        if not aid:
            pending = self._runtime.approvals.get_pending_for_task(self._task.id)
            aid = pending.id if pending else None
        if not aid:
            return False
        req = self._runtime.approvals.grant(
            aid, tool_name=tool_name, arguments=params
        )
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
        aid = attempt_id or self._last_attempt_id
        if not aid:
            return
        vr = self._runtime.verification.record_checkpoint_result(
            task_id=self._task.id,
            attempt_id=aid,
            achieved=achieved,
            gap=gap,
            failure_kind=failure_kind,
            checkpoint_id=checkpoint_id,
        )
        step = self._adhoc_step
        if step is None and self._step_by_index:
            idx = max(self._step_by_index.keys())
            step = self._step_by_index.get(idx)
        if step is not None:
            self._runtime.verification.finalize_step_from_verification(
                self._task, step, vr
            )

    def on_skill_checkpoint_verified(
        self,
        *,
        attempt_id: str | None,
        achieved: bool,
        checkpoint_id: str,
        partial: bool = False,
        gap: str = "",
        related_attempt_ids: list[str] | None = None,
    ) -> None:
        """Skill Flow checkpoint → VerificationResult."""
        if self._task is None:
            return
        aid = attempt_id or self._last_attempt_id
        if not aid:
            return
        vr = self._runtime.verification.record_skill_checkpoint(
            task_id=self._task.id,
            attempt_id=aid,
            checkpoint_id=checkpoint_id,
            achieved=achieved,
            partial=partial,
            gap=gap,
            related_attempt_ids=related_attempt_ids,
        )
        step = self._adhoc_step
        if step is None and self._step_by_index:
            idx = max(self._step_by_index.keys())
            step = self._step_by_index.get(idx)
        if step is not None and vr.status.value != "unknown":
            self._runtime.verification.finalize_step_from_verification(
                self._task, step, vr
            )
        self._skill_final_achieved = achieved and not partial

    def on_cu_waiting_user(self, message: str) -> None:
        if self._task is None:
            return
        self._task = self._runtime.tasks.suspend_for_user_input(self._task, message)

    def on_cu_suspended(self, message: str) -> None:
        if self._task is None:
            return
        self._runtime.tasks.suspend_max_steps(self._task, message)

    def on_cu_finished(self, *, success: bool, message: str) -> None:
        if self._task is None:
            return
        # Skill checkpoint 실패 시 성공 문자열로 Task 완료 금지
        if self._skill_final_achieved is False:
            success = False
        elif self._skill_final_achieved is True:
            success = True
        if success:
            self._runtime.tasks.complete_task(self._task, message)
        elif self._task.status == TaskStatus.WAITING_USER:
            return
        elif self._task.status in (
            TaskStatus.SUSPENDED,
            TaskStatus.PARTIALLY_COMPLETED,
            TaskStatus.WAITING_APPROVAL,
        ):
            return
        else:
            self._runtime.tasks.fail_task(self._task, message)
