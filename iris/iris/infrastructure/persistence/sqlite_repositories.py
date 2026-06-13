"""SQLite Repository 구현."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from iris.domain.execution.enums import ApprovalStatus, VerificationStatus
from iris.domain.execution.models import (
    ActionAttempt,
    ActionProposal,
    ActionResult,
    ApprovalRequest,
    VerificationResult,
)
from iris.domain.task.enums import (
    AttemptStatus,
    StepStatus,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from iris.domain.task.models import Plan, PlanStep, Task, TaskCheckpoint, TaskResult
from iris.storage.database import Database

_ACTIVE_STATUSES = (
    TaskStatus.DRAFT.value,
    TaskStatus.QUEUED.value,
    TaskStatus.PLANNING.value,
    TaskStatus.RUNNING.value,
    TaskStatus.WAITING_APPROVAL.value,
    TaskStatus.WAITING_USER.value,
    TaskStatus.WAITING_RESOURCE.value,
    TaskStatus.SUSPENDED.value,
)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


class SqliteTaskRepository:
    """Task SQLite Repository."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, task: Task) -> None:
        self._db._execute(
            """
            INSERT INTO tasks (
                id, task_type, title, goal, status, priority,
                constraints_json, acceptance_criteria_json,
                parent_task_id, workspace_id, active_plan_id,
                created_at, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.task_type.value,
                task.title,
                task.goal,
                task.status.value,
                task.priority.value,
                _json_dumps(task.constraints),
                _json_dumps(task.acceptance_criteria),
                task.parent_task_id,
                task.workspace_id,
                task.active_plan_id,
                task.created_at,
                task.started_at,
                task.ended_at,
            ),
        )
        self._db._commit()

    def get_by_id(self, task_id: str) -> Task | None:
        row = self._db._execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_task(row)

    def update(self, task: Task) -> None:
        self._db._execute(
            """
            UPDATE tasks SET
                task_type=?, title=?, goal=?, status=?, priority=?,
                constraints_json=?, acceptance_criteria_json=?,
                parent_task_id=?, workspace_id=?, active_plan_id=?,
                started_at=?, ended_at=?
            WHERE id=?
            """,
            (
                task.task_type.value,
                task.title,
                task.goal,
                task.status.value,
                task.priority.value,
                _json_dumps(task.constraints),
                _json_dumps(task.acceptance_criteria),
                task.parent_task_id,
                task.workspace_id,
                task.active_plan_id,
                task.started_at,
                task.ended_at,
                task.id,
            ),
        )
        self._db._commit()

    def get_active(self) -> list[Task]:
        placeholders = ",".join("?" * len(_ACTIVE_STATUSES))
        rows = self._db._execute(
            f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY created_at DESC",
            _ACTIVE_STATUSES,
        ).fetchall()
        return [_row_to_task(r) for r in rows]


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        task_type=TaskType(row["task_type"]),
        title=row["title"],
        goal=row["goal"],
        status=TaskStatus(row["status"]),
        priority=TaskPriority(row["priority"]),
        constraints=_json_loads(row["constraints_json"], []),
        acceptance_criteria=_json_loads(row["acceptance_criteria_json"], []),
        parent_task_id=row["parent_task_id"],
        workspace_id=row["workspace_id"],
        active_plan_id=row["active_plan_id"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
    )


class SqlitePlanRepository:
    """Plan·PlanStep SQLite Repository."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save_plan(self, plan: Plan) -> None:
        self._db._execute(
            """
            INSERT INTO task_plans (id, task_id, version, revision_reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (plan.id, plan.task_id, plan.version, plan.revision_reason, plan.created_at),
        )
        self._db._commit()

    def get_plan(self, plan_id: str) -> Plan | None:
        row = self._db._execute(
            "SELECT * FROM task_plans WHERE id = ?", (plan_id,)
        ).fetchone()
        if row is None:
            return None
        return Plan(
            id=row["id"],
            task_id=row["task_id"],
            version=row["version"],
            revision_reason=row["revision_reason"],
            created_at=row["created_at"],
        )

    def get_latest_plan_for_task(self, task_id: str) -> Plan | None:
        row = self._db._execute(
            """
            SELECT * FROM task_plans WHERE task_id = ?
            ORDER BY version DESC LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return Plan(
            id=row["id"],
            task_id=row["task_id"],
            version=row["version"],
            revision_reason=row["revision_reason"],
            created_at=row["created_at"],
        )

    def save_step(self, step: PlanStep) -> None:
        self._db._execute(
            """
            INSERT INTO task_steps (
                id, plan_id, step_index, title, capability_required,
                target, expected_result_json, dependencies_json,
                retry_policy_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step.id,
                step.plan_id,
                step.index,
                step.title,
                step.capability_required,
                step.target,
                _json_dumps(step.expected_result),
                _json_dumps(step.dependencies),
                _json_dumps(step.retry_policy),
                step.status.value,
            ),
        )
        self._db._commit()

    def get_steps(self, plan_id: str) -> list[PlanStep]:
        rows = self._db._execute(
            "SELECT * FROM task_steps WHERE plan_id = ? ORDER BY step_index",
            (plan_id,),
        ).fetchall()
        return [_row_to_step(r) for r in rows]

    def update_step(self, step: PlanStep) -> None:
        self._db._execute(
            "UPDATE task_steps SET status=? WHERE id=?",
            (step.status.value, step.id),
        )
        self._db._commit()


def _row_to_step(row: sqlite3.Row) -> PlanStep:
    return PlanStep(
        id=row["id"],
        plan_id=row["plan_id"],
        index=row["step_index"],
        title=row["title"],
        capability_required=row["capability_required"],
        target=row["target"] or "",
        expected_result=_json_loads(row["expected_result_json"], {}),
        dependencies=_json_loads(row["dependencies_json"], []),
        retry_policy=_json_loads(row["retry_policy_json"], {}),
        status=StepStatus(row["status"]),
    )


class SqliteExecutionRepository:
    """Execution SQLite Repository."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save_proposal(self, proposal: ActionProposal) -> None:
        self._db._execute(
            """
            INSERT INTO action_proposals (
                id, task_id, plan_step_id, capability_id, tool_name,
                arguments_json, target, expected_effect_json,
                estimated_risk, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.id,
                proposal.task_id,
                proposal.plan_step_id,
                proposal.capability_id,
                proposal.tool_name,
                _json_dumps(proposal.arguments),
                proposal.target,
                _json_dumps(proposal.expected_effect),
                proposal.estimated_risk,
                proposal.created_at,
            ),
        )
        self._db._commit()

    def get_proposal(self, proposal_id: str) -> ActionProposal | None:
        row = self._db._execute(
            "SELECT * FROM action_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            return None
        return ActionProposal(
            id=row["id"],
            task_id=row["task_id"],
            plan_step_id=row["plan_step_id"],
            capability_id=row["capability_id"],
            tool_name=row["tool_name"],
            arguments=_json_loads(row["arguments_json"], {}),
            target=row["target"] or "",
            expected_effect=_json_loads(row["expected_effect_json"], {}),
            estimated_risk=row["estimated_risk"],
            created_at=row["created_at"],
        )

    def save_attempt(self, attempt: ActionAttempt) -> None:
        self._db._execute(
            """
            INSERT INTO action_attempts (
                id, proposal_id, attempt_number, status, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.id,
                attempt.proposal_id,
                attempt.attempt_number,
                attempt.status.value,
                attempt.started_at,
                attempt.ended_at,
            ),
        )
        self._db._commit()

    def update_attempt(self, attempt: ActionAttempt) -> None:
        self._db._execute(
            """
            UPDATE action_attempts SET status=?, ended_at=? WHERE id=?
            """,
            (attempt.status.value, attempt.ended_at, attempt.id),
        )
        self._db._commit()

    def save_result(self, result: ActionResult) -> None:
        self._db._execute(
            """
            INSERT OR REPLACE INTO action_results (
                attempt_id, tool_success, output_summary, error_summary
            ) VALUES (?, ?, ?, ?)
            """,
            (
                result.attempt_id,
                1 if result.tool_success else 0,
                result.output_summary,
                result.error_summary,
            ),
        )
        self._db._commit()

    def get_attempts_for_proposal(self, proposal_id: str) -> list[ActionAttempt]:
        rows = self._db._execute(
            "SELECT * FROM action_attempts WHERE proposal_id = ? ORDER BY attempt_number",
            (proposal_id,),
        ).fetchall()
        return [
            ActionAttempt(
                id=r["id"],
                proposal_id=r["proposal_id"],
                attempt_number=r["attempt_number"],
                status=AttemptStatus(r["status"]),
                started_at=r["started_at"],
                ended_at=r["ended_at"],
            )
            for r in rows
        ]


class SqliteApprovalRepository:
    """Approval SQLite Repository."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, request: ApprovalRequest) -> None:
        self._db._execute(
            """
            INSERT INTO approval_requests (
                id, task_id, plan_step_id, action_proposal_id,
                tool_name, arguments_hash, target, risk_level,
                approval_status, created_at, approved_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.id,
                request.task_id,
                request.plan_step_id,
                request.action_proposal_id,
                request.tool_name,
                request.arguments_hash,
                request.target,
                request.risk_level,
                request.approval_status.value,
                request.created_at,
                request.approved_at,
                request.expires_at,
            ),
        )
        self._db._commit()

    def get_by_id(self, approval_id: str) -> ApprovalRequest | None:
        row = self._db._execute(
            "SELECT * FROM approval_requests WHERE id = ?", (approval_id,)
        ).fetchone()
        return _row_to_approval(row) if row else None

    def get_pending_for_task(self, task_id: str) -> ApprovalRequest | None:
        row = self._db._execute(
            """
            SELECT * FROM approval_requests
            WHERE task_id = ? AND approval_status = 'pending'
            ORDER BY created_at DESC LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return _row_to_approval(row) if row else None

    def get_by_proposal(self, proposal_id: str) -> ApprovalRequest | None:
        row = self._db._execute(
            "SELECT * FROM approval_requests WHERE action_proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        return _row_to_approval(row) if row else None

    def update_status(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        approved_at: str | None = None,
    ) -> None:
        self._db._execute(
            "UPDATE approval_requests SET approval_status=?, approved_at=? WHERE id=?",
            (status.value, approved_at, approval_id),
        )
        self._db._commit()


def _row_to_approval(row: sqlite3.Row) -> ApprovalRequest:
    return ApprovalRequest(
        id=row["id"],
        task_id=row["task_id"],
        plan_step_id=row["plan_step_id"],
        action_proposal_id=row["action_proposal_id"],
        tool_name=row["tool_name"],
        arguments_hash=row["arguments_hash"],
        target=row["target"] or "",
        risk_level=row["risk_level"],
        approval_status=ApprovalStatus(row["approval_status"]),
        created_at=row["created_at"],
        approved_at=row["approved_at"],
        expires_at=row["expires_at"],
    )


class SqliteVerificationRepository:
    """Verification SQLite Repository."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, result: VerificationResult) -> None:
        self._db._execute(
            """
            INSERT INTO verification_results (
                id, attempt_id, expected_state_json, actual_state_json,
                status, confidence, failure_reason, retryable,
                suggested_next, evidence_json, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.id,
                result.attempt_id,
                _json_dumps(result.expected_state),
                _json_dumps(result.actual_state),
                result.status.value,
                result.confidence,
                result.failure_reason,
                1 if result.retryable else 0,
                result.suggested_next,
                _json_dumps(result.evidence),
                result.verified_at,
            ),
        )
        self._db._commit()

    def get_by_attempt(self, attempt_id: str) -> VerificationResult | None:
        row = self._db._execute(
            "SELECT * FROM verification_results WHERE attempt_id = ? ORDER BY verified_at DESC LIMIT 1",
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        return VerificationResult(
            id=row["id"],
            attempt_id=row["attempt_id"],
            expected_state=_json_loads(row["expected_state_json"], {}),
            actual_state=_json_loads(row["actual_state_json"], {}),
            status=VerificationStatus(row["status"]),
            confidence=row["confidence"],
            failure_reason=row["failure_reason"],
            retryable=bool(row["retryable"]),
            suggested_next=row["suggested_next"],
            evidence=_json_loads(row["evidence_json"], {}),
            verified_at=row["verified_at"],
        )


class SqliteCheckpointRepository:
    """Checkpoint SQLite Repository."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, checkpoint: TaskCheckpoint) -> None:
        self._db._execute(
            """
            INSERT INTO task_checkpoints (
                id, task_id, plan_version, completed_step_ids_json,
                active_step_id, resumable, snapshot_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint.id,
                checkpoint.task_id,
                checkpoint.plan_version,
                _json_dumps(checkpoint.completed_step_ids),
                checkpoint.active_step_id,
                1 if checkpoint.resumable else 0,
                _json_dumps(checkpoint.snapshot),
                checkpoint.created_at,
            ),
        )
        self._db._commit()

    def get_latest_for_task(self, task_id: str) -> TaskCheckpoint | None:
        row = self._db._execute(
            """
            SELECT * FROM task_checkpoints WHERE task_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return _row_to_checkpoint(row) if row else None

    def get_by_id(self, checkpoint_id: str) -> TaskCheckpoint | None:
        row = self._db._execute(
            "SELECT * FROM task_checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
        return _row_to_checkpoint(row) if row else None


def _row_to_checkpoint(row: sqlite3.Row) -> TaskCheckpoint:
    return TaskCheckpoint(
        id=row["id"],
        task_id=row["task_id"],
        plan_version=row["plan_version"],
        completed_step_ids=_json_loads(row["completed_step_ids_json"], []),
        active_step_id=row["active_step_id"],
        resumable=bool(row["resumable"]),
        snapshot=_json_loads(row["snapshot_json"], {}),
        created_at=row["created_at"],
    )


class SqliteTaskResultRepository:
    """TaskResult SQLite Repository."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, result: TaskResult) -> None:
        self._db._execute(
            """
            INSERT OR REPLACE INTO task_results (
                task_id, status, summary, verification_summary,
                unresolved_issues_json, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.task_id,
                result.status.value,
                result.summary,
                result.verification_summary,
                _json_dumps(result.unresolved_issues),
                result.completed_at,
            ),
        )
        self._db._commit()

    def get_by_task_id(self, task_id: str) -> TaskResult | None:
        row = self._db._execute(
            "SELECT * FROM task_results WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return TaskResult(
            task_id=row["task_id"],
            status=TaskStatus(row["status"]),
            summary=row["summary"],
            verification_summary=row["verification_summary"] or "",
            unresolved_issues=_json_loads(row["unresolved_issues_json"], []),
            completed_at=row["completed_at"],
        )


class SqliteRepositoryBundle:
    """모든 Task Runtime Repository 묶음."""

    def __init__(self, db: Database) -> None:
        self.tasks = SqliteTaskRepository(db)
        self.plans = SqlitePlanRepository(db)
        self.execution = SqliteExecutionRepository(db)
        self.approvals = SqliteApprovalRepository(db)
        self.verifications = SqliteVerificationRepository(db)
        self.checkpoints = SqliteCheckpointRepository(db)
        self.task_results = SqliteTaskResultRepository(db)
