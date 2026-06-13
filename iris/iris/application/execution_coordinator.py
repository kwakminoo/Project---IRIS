"""ExecutionCoordinator — ActionProposal 실행 오케스트레이션."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.application.approval_service import ApprovalService
from iris.application.task_runtime_repositories import TaskRuntimeRepositories
from iris.application.task_service import TaskApplicationService
from iris.application.verification_service import VerificationService
from iris.domain.execution.enums import PolicyDecisionKind
from iris.domain.execution.models import (
    ActionAttempt,
    ActionProposal,
    ActionResult,
    PolicyDecision,
    VerificationResult,
)
from iris.domain.execution.policy import AutomationToolPort, SafetyPolicyPort
from iris.domain.shared.id_generator import new_id
from iris.domain.shared.time import utc_now_iso
from iris.domain.task.enums import AttemptStatus, StepStatus
from iris.domain.task.events import (
    ActionAttemptCompleted,
    ActionAttemptStarted,
    ActionProposed,
)
from iris.domain.task.models import PlanStep, Task
from iris.infrastructure.events.in_memory_dispatcher import InMemoryEventDispatcher


@dataclass
class ExecutionOutcome:
    """한 Step 실행 결과."""

    attempt: ActionAttempt | None
    result: ActionResult | None
    verification: VerificationResult | None
    policy_decision: PolicyDecision | None
    approval_required: bool
    approval_id: str | None
    step_status: StepStatus
    blocked: bool = False
    message: str = ""
    proposal_id: str | None = None


class ExecutionCoordinator:
    """ActionProposal → Policy → Attempt → Verify."""

    def __init__(
        self,
        repos: TaskRuntimeRepositories,
        events: InMemoryEventDispatcher,
        policy: SafetyPolicyPort,
        tools: AutomationToolPort,
        approval_service: ApprovalService,
        task_service: TaskApplicationService,
        verification_service: VerificationService,
        *,
        tool_context_factory: Any = None,
    ) -> None:
        self._repos = repos
        self._events = events
        self._policy = policy
        self._tools = tools
        self._approval = approval_service
        self._tasks = task_service
        self._verify = verification_service
        self._ctx_factory = tool_context_factory

    def execute_proposal(
        self,
        proposal_id: str,
        *,
        approval_id: str | None = None,
    ) -> ExecutionOutcome:
        """DB Proposal 로드 후 공통 실행 (승인 재개 포함)."""
        proposal = self._repos.execution.get_proposal(proposal_id)
        if proposal is None:
            return ExecutionOutcome(
                attempt=None,
                result=None,
                verification=None,
                policy_decision=None,
                approval_required=False,
                approval_id=None,
                step_status=StepStatus.FAILED,
                blocked=True,
                message="proposal_not_found",
            )
        task = self._repos.tasks.get_by_id(proposal.task_id)
        if task is None:
            return ExecutionOutcome(
                attempt=None,
                result=None,
                verification=None,
                policy_decision=None,
                approval_required=False,
                approval_id=None,
                step_status=StepStatus.FAILED,
                blocked=True,
                message="task_not_found",
            )
        step = self._repos.plans.get_step(proposal.plan_step_id)
        if step is None:
            return ExecutionOutcome(
                attempt=None,
                result=None,
                verification=None,
                policy_decision=None,
                approval_required=False,
                approval_id=None,
                step_status=StepStatus.FAILED,
                blocked=True,
                message="step_not_found",
            )
        prior = self._repos.execution.get_attempts_for_proposal(proposal_id)
        if any(a.status == AttemptStatus.SUCCEEDED for a in prior):
            return ExecutionOutcome(
                attempt=None,
                result=None,
                verification=None,
                policy_decision=None,
                approval_required=False,
                approval_id=approval_id,
                step_status=step.status,
                blocked=True,
                message="already_executed",
                proposal_id=proposal_id,
            )
        approved = False
        if approval_id:
            req = self._approval.validate_for_execution(
                approval_id,
                tool_name=proposal.tool_name,
                arguments=proposal.arguments,
                require_granted=True,
            )
            if req is None:
                return ExecutionOutcome(
                    attempt=None,
                    result=None,
                    verification=None,
                    policy_decision=None,
                    approval_required=False,
                    approval_id=approval_id,
                    step_status=StepStatus.WAITING_APPROVAL,
                    blocked=True,
                    message="approval_invalid",
                    proposal_id=proposal_id,
                )
            approved = True
        return self.execute_step(
            task,
            step,
            proposal,
            approved=approved,
            run_tool=True,
            approval_id=approval_id,
            skip_proposal_save=True,
        )

    def execute_step(
        self,
        task: Task,
        step: PlanStep,
        proposal: ActionProposal,
        *,
        approved: bool = False,
        run_tool: bool = True,
        approval_id: str | None = None,
        skip_proposal_save: bool = False,
    ) -> ExecutionOutcome:
        """ActionProposal 기록 → 정책 → (선택) 실행 또는 승인 대기."""
        if not skip_proposal_save:
            self._repos.execution.save_proposal(proposal)
            self._events.publish(
                ActionProposed(
                    task_id=task.id,
                    proposal_id=proposal.id,
                    tool_name=proposal.tool_name,
                )
            )

        tool_ctx = None
        if self._ctx_factory is not None:
            tool_ctx = self._ctx_factory(params=proposal.arguments, approved=approved)

        decision = self._policy.evaluate(proposal, tool_context=tool_ctx)

        if decision.decision == PolicyDecisionKind.DENY.value:
            self._tasks.mark_step_failed(task, step, decision.reason)
            return ExecutionOutcome(
                attempt=None,
                result=None,
                verification=None,
                policy_decision=decision,
                approval_required=False,
                approval_id=None,
                step_status=StepStatus.FAILED,
                blocked=True,
                message=decision.reason,
                proposal_id=proposal.id,
            )

        needs_approval = (
            decision.decision == PolicyDecisionKind.REQUIRE_APPROVAL.value
            and not approved
        )
        if needs_approval:
            waiting = step.mark_waiting_approval()
            self._repos.plans.update_step(waiting)
            req = self._approval.create_request(task, proposal)
            self._approval.suspend_task_for_approval(task)
            return ExecutionOutcome(
                attempt=None,
                result=None,
                verification=None,
                policy_decision=decision,
                approval_required=True,
                approval_id=req.id,
                step_status=StepStatus.WAITING_APPROVAL,
                message="approval_required",
                proposal_id=proposal.id,
            )

        if not run_tool:
            return ExecutionOutcome(
                attempt=None,
                result=None,
                verification=None,
                policy_decision=decision,
                approval_required=False,
                approval_id=approval_id,
                step_status=StepStatus.RUNNING,
                message="policy_allowed",
                proposal_id=proposal.id,
            )

        running = self._tasks.mark_step_started(task, step)
        prior = self._repos.execution.get_attempts_for_proposal(proposal.id)
        attempt = ActionAttempt(
            id=new_id(),
            proposal_id=proposal.id,
            attempt_number=len(prior) + 1,
        )
        self._repos.execution.save_attempt(attempt)
        self._events.publish(
            ActionAttemptStarted(
                task_id=task.id,
                attempt_id=attempt.id,
                proposal_id=proposal.id,
            )
        )

        tool_result = self._tools.run(
            proposal.tool_name,
            proposal.arguments,
            approved=True,
            summary=step.title,
        )
        success = bool(getattr(tool_result, "success", False))
        msg = str(getattr(tool_result, "message", "") or "")
        detail = getattr(tool_result, "detail", None)

        attempt.status = AttemptStatus.SUCCEEDED if success else AttemptStatus.FAILED
        attempt.ended_at = utc_now_iso()
        self._repos.execution.update_attempt(attempt)

        action_result = ActionResult(
            attempt_id=attempt.id,
            tool_success=success,
            output_summary=msg[:1000],
            error_summary=None if success else (msg[:500] or str(detail or "")),
        )
        self._repos.execution.save_result(action_result)
        self._events.publish(
            ActionAttemptCompleted(
                task_id=task.id, attempt_id=attempt.id, success=success
            )
        )

        if not success:
            self._tasks.mark_step_failed(task, running, msg)
            verification = self._verify.record_tool_observation(
                task_id=task.id,
                attempt_id=attempt.id,
                tool_name=proposal.tool_name,
                observation=f"fail: {msg}",
                success=False,
            )
            return ExecutionOutcome(
                attempt=attempt,
                result=action_result,
                verification=verification,
                policy_decision=decision,
                approval_required=False,
                approval_id=approval_id,
                step_status=StepStatus.FAILED,
                message=msg,
                proposal_id=proposal.id,
            )

        verifying = self._tasks.mark_step_verifying(task, running)
        obs = msg if success else f"fail: {msg}"
        verification = self._verify.record_tool_observation(
            task_id=task.id,
            attempt_id=attempt.id,
            tool_name=proposal.tool_name,
            observation=obs,
            success=success,
        )

        return ExecutionOutcome(
            attempt=attempt,
            result=action_result,
            verification=verification,
            policy_decision=decision,
            approval_required=False,
            approval_id=approval_id,
            step_status=StepStatus.VERIFYING,
            message=msg,
            proposal_id=proposal.id,
        )
