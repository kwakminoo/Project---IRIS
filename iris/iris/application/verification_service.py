"""VerificationService — CU 검증 결과를 VerificationResult로 매핑."""

from __future__ import annotations

from typing import Any

from iris.application.task_runtime_repositories import TaskRuntimeRepositories
from iris.domain.execution.enums import SuggestedNext, VerificationStatus
from iris.domain.execution.models import VerificationResult
from iris.domain.shared.id_generator import new_id
from iris.domain.task.enums import StepStatus
from iris.domain.task.events import VerificationCompleted
from iris.domain.task.models import PlanStep, Task
from iris.infrastructure.events.in_memory_dispatcher import InMemoryEventDispatcher


class VerificationService:
    """검증 수행·저장·Step 최종 상태."""

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

    def record_checkpoint_result(
        self,
        *,
        task_id: str,
        attempt_id: str,
        achieved: bool,
        failure_kind: str = "",
        gap: str = "",
        checkpoint_id: str = "",
        confidence: float = 0.0,
    ) -> VerificationResult:
        """cu_checkpoint_verify 결과 → VerificationResult."""
        status = VerificationStatus.SUCCESS if achieved else VerificationStatus.FAILED
        vr = VerificationResult(
            id=new_id(),
            attempt_id=attempt_id,
            expected_state={"checkpoint_id": checkpoint_id},
            actual_state={"achieved": achieved, "gap": gap, "failure_kind": failure_kind},
            status=status,
            confidence=confidence if confidence else (1.0 if achieved else 0.0),
            failure_reason=gap or failure_kind or None,
            retryable=not achieved,
            suggested_next=(
                SuggestedNext.CONTINUE.value
                if achieved
                else SuggestedNext.RETRY.value
            ),
            evidence={"checkpoint_id": checkpoint_id},
        )
        self._repos.verifications.save(vr)
        self._events.publish(
            VerificationCompleted(
                task_id=task_id,
                attempt_id=attempt_id,
                status=status.value,
            )
        )
        return vr

    def record_tool_observation(
        self,
        *,
        task_id: str,
        attempt_id: str,
        tool_name: str,
        observation: str,
        success: bool,
    ) -> VerificationResult:
        """도구 실행 직후 pending 관측 — Step 완료 처리 금지."""
        vr = VerificationResult(
            id=new_id(),
            attempt_id=attempt_id,
            expected_state={"tool": tool_name, "pending_verify": True},
            actual_state={"observation": observation[:500], "tool_success": success},
            status=VerificationStatus.UNKNOWN,
            confidence=0.0,
            retryable=not success,
            suggested_next=SuggestedNext.CONTINUE.value,
        )
        self._repos.verifications.save(vr)
        self._events.publish(
            VerificationCompleted(
                task_id=task_id,
                attempt_id=attempt_id,
                status=VerificationStatus.UNKNOWN.value,
            )
        )
        return vr

    def finalize_step_from_verification(
        self,
        task: Task,
        step: PlanStep,
        vr: VerificationResult,
    ) -> StepStatus:
        """VerificationResult 기준으로만 Step 상태 확정."""
        if self._tasks is None:
            raise RuntimeError("task_service not configured")
        ts = self._tasks
        if vr.status == VerificationStatus.SUCCESS:
            ts.mark_step_succeeded(task, step)
            return StepStatus.SUCCEEDED
        if vr.status == VerificationStatus.PARTIAL:
            ts.mark_step_partially_succeeded(task, step)
            return StepStatus.PARTIALLY_SUCCEEDED
        if vr.status == VerificationStatus.FAILED:
            reason = vr.failure_reason or "verification_failed"
            ts.mark_step_failed(task, step, reason)
            return StepStatus.FAILED
        return StepStatus.VERIFYING

    def record_skill_checkpoint(
        self,
        *,
        task_id: str,
        attempt_id: str,
        checkpoint_id: str,
        achieved: bool,
        partial: bool = False,
        gap: str = "",
        related_attempt_ids: list[str] | None = None,
    ) -> VerificationResult:
        """Skill mechanical/LLM checkpoint → VerificationResult (Attempt 필수)."""
        if partial and achieved:
            status = VerificationStatus.PARTIAL
        elif achieved:
            status = VerificationStatus.SUCCESS
        else:
            status = VerificationStatus.FAILED
        evidence: dict[str, Any] = {"checkpoint_id": checkpoint_id, "skill": True}
        if related_attempt_ids:
            evidence["attempt_ids"] = list(related_attempt_ids)
        vr = VerificationResult(
            id=new_id(),
            attempt_id=attempt_id,
            expected_state={"checkpoint_id": checkpoint_id},
            actual_state={"achieved": achieved, "partial": partial, "gap": gap},
            status=status,
            confidence=1.0 if achieved and not partial else (0.5 if partial else 0.0),
            failure_reason=gap or None,
            retryable=not achieved,
            suggested_next=(
                SuggestedNext.CONTINUE.value
                if achieved
                else SuggestedNext.RETRY.value
            ),
            evidence=evidence,
        )
        self._repos.verifications.save(vr)
        self._events.publish(
            VerificationCompleted(
                task_id=task_id,
                attempt_id=attempt_id,
                status=status.value,
            )
        )
        return vr
