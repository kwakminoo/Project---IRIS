"""복구 명령 분류·상태 포맷 — 앱 재시작 후 사용자 명령 처리."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from iris.application.recovery_service import RecoverySnapshot
from iris.domain.execution.enums import ApprovalStatus
from iris.domain.task.enums import TaskStatus


class RecoveryCommand(str, Enum):
    """복구 관련 사용자 명령."""

    CONTINUE = "continue"
    STATUS = "status"
    CANCEL = "cancel"


_CONTINUE_PATTERNS = (
    r"^계속\s*진행",
    r"^계속해",
    r"^이어서",
    r"^재개",
    r"^continue$",
)
_STATUS_PATTERNS = (
    r"^상태\s*확인",
    r"^상태\s*보여",
    r"^진행\s*상황",
    r"^status$",
)
_CANCEL_PATTERNS = (
    r"^작업\s*취소",
    r"^취소해",
    r"^중단해",
    r"^cancel$",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_recovery_command(user_text: str) -> RecoveryCommand | None:
    """복구 명령 여부·종류 판별."""
    norm = _normalize(user_text)
    if not norm:
        return None
    for pat in _CONTINUE_PATTERNS:
        if re.search(pat, norm):
            return RecoveryCommand.CONTINUE
    for pat in _STATUS_PATTERNS:
        if re.search(pat, norm):
            return RecoveryCommand.STATUS
    for pat in _CANCEL_PATTERNS:
        if re.search(pat, norm):
            return RecoveryCommand.CANCEL
    return None


@dataclass
class ResumeValidation:
    """재개 가능 여부 검증 결과."""

    ok: bool
    message: str = ""


def validate_resume_snapshot(snap: RecoverySnapshot | None) -> ResumeValidation:
    """불완전 스냅샷이면 Tool 실행 차단."""
    if snap is None:
        return ResumeValidation(False, "복구 정보를 찾을 수 없습니다.")
    task = snap.task
    if task.status == TaskStatus.CANCELLED:
        return ResumeValidation(False, "이미 취소된 작업입니다.")
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        return ResumeValidation(False, "이미 종료된 작업입니다.")
    if task.status not in (
        TaskStatus.RUNNING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.WAITING_USER,
        TaskStatus.WAITING_RESOURCE,
        TaskStatus.SUSPENDED,
        TaskStatus.INTERRUPTED,
    ):
        return ResumeValidation(False, f"재개할 수 없는 상태입니다: {task.status.value}")
    return ResumeValidation(True)


def format_recovery_status(snap: RecoverySnapshot) -> str:
    """상태 확인 응답 본문."""
    task = snap.task
    lines = [
        f"작업: {task.goal[:120]}",
        f"상태: {task.status.value}",
    ]
    if snap.plan:
        lines.append(f"Plan: {snap.plan.id} (v{snap.plan.version})")
    if snap.active_step:
        lines.append(
            f"현재 Step: [{snap.active_step.index}] {snap.active_step.title} "
            f"({snap.active_step.status.value})"
        )
    elif snap.steps:
        lines.append(f"Plan Steps: {len(snap.steps)}개")
    if snap.latest_proposal:
        lp = snap.latest_proposal
        lines.append(f"최근 Proposal: {lp.tool_name} ({lp.id[:8]}…)")
    if snap.latest_attempt:
        la = snap.latest_attempt
        lines.append(f"최근 Attempt: #{la.attempt_number} ({la.status.value})")
    verifications = _latest_verification_summary(snap)
    if verifications:
        lines.append(f"최근 Verification: {verifications}")
    if snap.pending_approval:
        pa = snap.pending_approval
        expired = pa.approval_status == ApprovalStatus.EXPIRED
        lines.append(
            f"승인 대기: {pa.tool_name} "
            f"({'만료됨' if expired else '대기 중'})"
        )
    if snap.checkpoint:
        lines.append(f"Checkpoint: {snap.checkpoint.id[:8]}…")
        if snap.checkpoint.snapshot.get("interrupted_at"):
            lines.append(f"중단 시각: {snap.checkpoint.snapshot['interrupted_at']}")
    can = snap.task.status in (
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.WAITING_USER,
        TaskStatus.WAITING_RESOURCE,
        TaskStatus.SUSPENDED,
        TaskStatus.INTERRUPTED,
        TaskStatus.RUNNING,
    )
    lines.append(f"재개 가능: {'예' if can else '아니오'}")
    return "\n".join(lines)


def _latest_verification_summary(snap: RecoverySnapshot) -> str:
    """스냅샷에 연결된 최근 검증 요약 (attempt 기반)."""
    if not snap.latest_attempt:
        return ""
    return f"attempt={snap.latest_attempt.id[:8]}… status={snap.latest_attempt.status.value}"


def build_resume_slots(snap: RecoverySnapshot) -> dict[str, Any]:
    """재개용 slots — 기존 ID 유지."""
    slots: dict[str, Any] = {"_resume_task_id": snap.task.id}
    cp = snap.checkpoint
    if cp and cp.snapshot:
        for key in ("task_type", "skill_id", "app_key", "display_name", "slots"):
            if key in cp.snapshot:
                slots[key] = cp.snapshot[key]
        if cp.snapshot.get("proposal_id"):
            slots["_task_proposal_id"] = cp.snapshot["proposal_id"]
        if cp.snapshot.get("approval_id"):
            slots["_task_approval_id"] = cp.snapshot["approval_id"]
    return slots


def resume_goal_from_snapshot(snap: RecoverySnapshot) -> str:
    """재개 goal — checkpoint 또는 task goal."""
    if snap.checkpoint and snap.checkpoint.snapshot.get("goal"):
        return str(snap.checkpoint.snapshot["goal"])
    return snap.task.goal
