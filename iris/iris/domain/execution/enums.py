"""실행·승인·검증 Enum."""

from __future__ import annotations

from enum import Enum


class PolicyDecisionKind(str, Enum):
    """ActionProposal 정책 판단."""

    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    REQUIRE_ISOLATION = "require_isolation"
    DENY = "deny"


class VerificationStatus(str, Enum):
    """검증 결과 상태."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ApprovalStatus(str, Enum):
    """승인 요청 상태."""

    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    EXPIRED = "expired"


class SuggestedNext(str, Enum):
    """검증 실패 후 제안."""

    CONTINUE = "continue"
    RETRY = "retry"
    REPLAN = "replan"
    COMPENSATE = "compensate"
    ASK_USER = "ask_user"
    DELEGATE = "delegate"
