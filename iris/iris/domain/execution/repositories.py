"""Execution Repository 인터페이스."""

from __future__ import annotations

from typing import Protocol

from iris.domain.execution.models import (
    ActionAttempt,
    ActionProposal,
    ActionResult,
    ApprovalRequest,
    VerificationResult,
)
from iris.domain.execution.enums import ApprovalStatus


class ExecutionRepository(Protocol):
    """ActionProposal·Attempt·Result 영속."""

    def save_proposal(self, proposal: ActionProposal) -> None: ...
    def get_proposal(self, proposal_id: str) -> ActionProposal | None: ...
    def save_attempt(self, attempt: ActionAttempt) -> None: ...
    def update_attempt(self, attempt: ActionAttempt) -> None: ...
    def save_result(self, result: ActionResult) -> None: ...
    def get_attempts_for_proposal(self, proposal_id: str) -> list[ActionAttempt]: ...


class ApprovalRepository(Protocol):
    """ApprovalRequest 영속."""

    def save(self, request: ApprovalRequest) -> None: ...
    def get_by_id(self, approval_id: str) -> ApprovalRequest | None: ...
    def get_pending_for_task(self, task_id: str) -> ApprovalRequest | None: ...
    def get_by_proposal(self, proposal_id: str) -> ApprovalRequest | None: ...
    def update_status(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        approved_at: str | None = None,
    ) -> None: ...


class VerificationRepository(Protocol):
    """VerificationResult 영속."""

    def save(self, result: VerificationResult) -> None: ...
    def get_by_attempt(self, attempt_id: str) -> VerificationResult | None: ...
