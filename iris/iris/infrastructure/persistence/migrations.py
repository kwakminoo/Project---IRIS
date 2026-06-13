"""SQLite 스키마 마이그레이션 — Task Runtime."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime

MigrationFn = Callable[[sqlite3.Connection], None]


def _migration_001_create_task_runtime(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL,
            title TEXT NOT NULL,
            goal TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            constraints_json TEXT NOT NULL DEFAULT '[]',
            acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
            parent_task_id TEXT,
            workspace_id TEXT,
            active_plan_id TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            ended_at TEXT
        );
        CREATE TABLE IF NOT EXISTS task_plans (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            revision_reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS task_steps (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            title TEXT NOT NULL,
            capability_required TEXT NOT NULL DEFAULT '',
            target TEXT NOT NULL DEFAULT '',
            expected_result_json TEXT NOT NULL DEFAULT '{}',
            dependencies_json TEXT NOT NULL DEFAULT '[]',
            retry_policy_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            FOREIGN KEY (plan_id) REFERENCES task_plans(id)
        );
        CREATE TABLE IF NOT EXISTS task_checkpoints (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            plan_version INTEGER NOT NULL DEFAULT 1,
            completed_step_ids_json TEXT NOT NULL DEFAULT '[]',
            active_step_id TEXT,
            resumable INTEGER NOT NULL DEFAULT 1,
            snapshot_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS task_results (
            task_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            verification_summary TEXT NOT NULL DEFAULT '',
            unresolved_issues_json TEXT NOT NULL DEFAULT '[]',
            completed_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_task_plans_task_id ON task_plans(task_id);
        CREATE INDEX IF NOT EXISTS idx_task_steps_plan_id ON task_steps(plan_id);
        """
    )


def _migration_002_create_execution_records(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS action_proposals (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            plan_step_id TEXT NOT NULL,
            capability_id TEXT NOT NULL DEFAULT '',
            tool_name TEXT NOT NULL,
            arguments_json TEXT NOT NULL DEFAULT '{}',
            target TEXT NOT NULL DEFAULT '',
            expected_effect_json TEXT NOT NULL DEFAULT '{}',
            estimated_risk TEXT NOT NULL DEFAULT 'low',
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS action_attempts (
            id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'running',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            FOREIGN KEY (proposal_id) REFERENCES action_proposals(id)
        );
        CREATE TABLE IF NOT EXISTS action_results (
            attempt_id TEXT PRIMARY KEY,
            tool_success INTEGER NOT NULL,
            output_summary TEXT NOT NULL DEFAULT '',
            error_summary TEXT,
            FOREIGN KEY (attempt_id) REFERENCES action_attempts(id)
        );
        CREATE TABLE IF NOT EXISTS verification_results (
            id TEXT PRIMARY KEY,
            attempt_id TEXT NOT NULL,
            expected_state_json TEXT NOT NULL DEFAULT '{}',
            actual_state_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'unknown',
            confidence REAL NOT NULL DEFAULT 0.0,
            failure_reason TEXT,
            retryable INTEGER NOT NULL DEFAULT 0,
            suggested_next TEXT NOT NULL DEFAULT 'continue',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            verified_at TEXT NOT NULL,
            FOREIGN KEY (attempt_id) REFERENCES action_attempts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_proposals_task ON action_proposals(task_id);
        CREATE INDEX IF NOT EXISTS idx_attempts_proposal ON action_attempts(proposal_id);
        """
    )


def _migration_003_create_approval_records(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approval_requests (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            plan_step_id TEXT NOT NULL,
            action_proposal_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments_hash TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT '',
            risk_level TEXT NOT NULL DEFAULT 'critical',
            approval_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            approved_at TEXT,
            expires_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            FOREIGN KEY (action_proposal_id) REFERENCES action_proposals(id)
        );
        CREATE INDEX IF NOT EXISTS idx_approval_task ON approval_requests(task_id);
        CREATE INDEX IF NOT EXISTS idx_approval_proposal ON approval_requests(action_proposal_id);
        """
    )


def _migration_004_events_task_link(conn: sqlite3.Connection) -> None:
    """events 테이블에 Task 연계 컬럼 추가."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    if "related_task_id" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN related_task_id TEXT")
    if "related_plan_step_id" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN related_plan_step_id TEXT")
    if "related_action_attempt_id" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN related_action_attempt_id TEXT")


MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("001_create_task_runtime", _migration_001_create_task_runtime),
    ("002_create_execution_records", _migration_002_create_execution_records),
    ("003_create_approval_records", _migration_003_create_approval_records),
    ("004_events_task_link", _migration_004_events_task_link),
]


def run_pending_migrations(conn: sqlite3.Connection) -> list[str]:
    """미적용 마이그레이션 실행. 적용된 버전 ID 목록 반환."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {
        row[0]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    newly_applied: list[str] = []
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    for version, fn in MIGRATIONS:
        if version in applied:
            continue
        fn(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, now),
        )
        newly_applied.append(version)
    if newly_applied:
        conn.commit()
    return newly_applied
