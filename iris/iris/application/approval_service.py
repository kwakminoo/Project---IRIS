"""ApprovalService — 도구+인수에 묶인 승인."""

from __future__ import annotations

from iris.application.approval_hash import hash_arguments
from iris.domain.execution.enums import ApprovalStatus
from iris.domain.execution.models import ActionProposal, ApprovalRequest
from iris.domain.shared.id_generator import new_id
from iris.domain.shared.time import utc_now_iso
from iris.domain.task.enums import TaskStatus
from iris.domain.task.events import ApprovalGranted, ApprovalRequested, TaskStatusChanged
from iris.domain.task.models import Task
from iris.infrastructure.events.in_memory_dispatcher import InMemoryEventDispatcher
from iris.infrastructure.persistence.sqlite_repositories import SqliteRepositoryBundle


class ApprovalService:
    """승인 요청 생성·승인·거부."""

    def __init__(
        self,
        repos: SqliteRepositoryBundle,
        events: InMemoryEventDispatcher,
    ) -> None:
        self._repos = repos
        self._events = events

    def create_request(
        self,
        task: Task,
        proposal: ActionProposal,
        *,
        risk_level: str = "critical",
    ) -> ApprovalRequest:
        """ActionProposal에 대한 승인 요청 생성."""
        req = ApprovalRequest(
            id=new_id(),
            task_id=task.id,
            plan_step_id=proposal.plan_step_id,
            action_proposal_id=proposal.id,
            tool_name=proposal.tool_name,
            arguments_hash=hash_arguments(proposal.arguments),
            target=proposal.target,
            risk_level=risk_level,
        )
        self._repos.approvals.save(req)
        self._events.publish(
            ApprovalRequested(task_id=task.id, approval_id=req.id, tool_name=req.tool_name)
        )
        return req

    def grant(
        self,
        approval_id: str,
        *,
        tool_name: str,
        arguments: dict,
    ) -> ApprovalRequest | None:
        """승인 — 도구+인수 해시 일치 필수."""
        req = self._repos.approvals.get_by_id(approval_id)
        if req is None:
            return None
        if req.approval_status != ApprovalStatus.PENDING:
            return None
        if req.tool_name != tool_name:
            return None
        if req.arguments_hash != hash_arguments(arguments):
            return None
        now = utc_now_iso()
        self._repos.approvals.update_status(
            approval_id, ApprovalStatus.GRANTED, approved_at=now
        )
        req.approval_status = ApprovalStatus.GRANTED
        req.approved_at = now
        self._events.publish(
            ApprovalGranted(task_id=req.task_id, approval_id=approval_id)
        )
        return req

    def deny(self, approval_id: str) -> None:
        self._repos.approvals.update_status(approval_id, ApprovalStatus.DENIED)

    def get_pending_for_task(self, task_id: str) -> ApprovalRequest | None:
        return self._repos.approvals.get_pending_for_task(task_id)

    def suspend_task_for_approval(self, task: Task) -> Task:
        """Task → waiting_approval."""
        result = task.transition_to(TaskStatus.WAITING_APPROVAL)
        if not result.ok or result.value is None:
            return task
        updated = result.value
        old = task.status
        self._repos.tasks.update(updated)
        self._events.publish(
            TaskStatusChanged(
                task_id=task.id, old_status=old, new_status=TaskStatus.WAITING_APPROVAL
            )
        )
        return updated
