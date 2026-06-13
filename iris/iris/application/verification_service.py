"""VerificationService — CU 검증 결과를 VerificationResult로 매핑."""

from __future__ import annotations

from typing import Any

from iris.domain.execution.enums import SuggestedNext, VerificationStatus
from iris.domain.execution.models import VerificationResult
from iris.domain.shared.id_generator import new_id
from iris.domain.task.events import VerificationCompleted
from iris.infrastructure.events.in_memory_dispatcher import InMemoryEventDispatcher
from iris.infrastructure.persistence.sqlite_repositories import SqliteRepositoryBundle


class VerificationService:
    """검증 수행·저장."""

    def __init__(
        self,
        repos: SqliteRepositoryBundle,
        events: InMemoryEventDispatcher,
    ) -> None:
        self._repos = repos
        self._events = events

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
        """도구 실행 후 간단 검증 기록."""
        status = VerificationStatus.SUCCESS if success else VerificationStatus.FAILED
        vr = VerificationResult(
            id=new_id(),
            attempt_id=attempt_id,
            expected_state={"tool": tool_name},
            actual_state={"observation": observation[:500]},
            status=status,
            confidence=0.8 if success else 0.2,
            retryable=not success,
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
