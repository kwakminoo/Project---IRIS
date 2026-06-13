"""ActionProposal·Attempt·Result·Verification·Approval 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iris.domain.execution.enums import ApprovalStatus, VerificationStatus
from iris.domain.shared.time import utc_now_iso
from iris.domain.task.enums import AttemptStatus


@dataclass
class ActionProposal:
    """실행 전 행동 제안."""

    id: str
    task_id: str
    plan_step_id: str
    capability_id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    target: str = ""
    expected_effect: dict[str, Any] = field(default_factory=dict)
    estimated_risk: str = "low"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class PolicyDecision:
    """정책 평가 결과."""

    proposal_id: str
    decision: str  # PolicyDecisionKind value
    reason: str = ""


@dataclass
class ActionAttempt:
    """정책 통과 후 한 번의 실행 기록."""

    id: str
    proposal_id: str
    attempt_number: int
    status: AttemptStatus = AttemptStatus.RUNNING
    started_at: str = field(default_factory=utc_now_iso)
    ended_at: str | None = None


@dataclass
class ActionResult:
    """도구 실행 결과."""

    attempt_id: str
    tool_success: bool
    output_summary: str = ""
    error_summary: str | None = None


@dataclass
class VerificationResult:
    """목표 상태 달성 여부 검증."""

    id: str
    attempt_id: str
    expected_state: dict[str, Any] = field(default_factory=dict)
    actual_state: dict[str, Any] = field(default_factory=dict)
    status: VerificationStatus = VerificationStatus.UNKNOWN
    confidence: float = 0.0
    failure_reason: str | None = None
    retryable: bool = False
    suggested_next: str = "continue"
    evidence: dict[str, Any] = field(default_factory=dict)
    verified_at: str = field(default_factory=utc_now_iso)


@dataclass
class ApprovalRequest:
    """도구+인수에 묶인 승인 요청."""

    id: str
    task_id: str
    plan_step_id: str
    action_proposal_id: str
    tool_name: str
    arguments_hash: str
    target: str = ""
    risk_level: str = "critical"
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = field(default_factory=utc_now_iso)
    approved_at: str | None = None
    expires_at: str | None = None
