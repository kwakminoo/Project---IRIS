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


def _migration_005_plan_integrity(conn: sqlite3.Connection) -> None:
    """Plan revision·FK 무결성 강화."""
    plan_cols = {row[1] for row in conn.execute("PRAGMA table_info(task_plans)").fetchall()}
    if "previous_plan_id" not in plan_cols:
        conn.execute("ALTER TABLE task_plans ADD COLUMN previous_plan_id TEXT")
    if "superseded_at" not in plan_cols:
        conn.execute("ALTER TABLE task_plans ADD COLUMN superseded_at TEXT")
    # SQLite는 ALTER TABLE ADD CONSTRAINT FK 미지원 — 인덱스·앱 레벨 검증 병행
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_plans_previous ON task_plans(previous_plan_id)"
    )


def _migration_006_google_workspace_email(conn: sqlite3.Connection) -> None:
    """Google Workspace 메일 연동: 원문은 저장하지 않고 계정/설정/감사 메타데이터만 저장."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS google_workspace_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_email TEXT NOT NULL,
            google_email TEXT NOT NULL,
            integration_name TEXT NOT NULL DEFAULT 'google_workspace',
            credentials_ref TEXT NOT NULL DEFAULT '',
            credentials_dir TEXT NOT NULL DEFAULT '',
            enabled_services_json TEXT NOT NULL DEFAULT '["gmail"]',
            tool_tier TEXT NOT NULL DEFAULT 'core',
            is_verified INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_google_workspace_email
            ON google_workspace_accounts(google_email);
        CREATE TABLE IF NOT EXISTS email_ui_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_account_id INTEGER NOT NULL,
            default_label TEXT NOT NULL DEFAULT 'INBOX',
            page_size INTEGER NOT NULL DEFAULT 30,
            density TEXT NOT NULL DEFAULT 'comfortable',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (google_account_id) REFERENCES google_workspace_accounts(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_email_ui_preferences_account
            ON email_ui_preferences(google_account_id);
        CREATE TABLE IF NOT EXISTS email_action_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_account_id INTEGER,
            action_type TEXT NOT NULL,
            provider_message_id TEXT,
            provider_draft_id TEXT,
            target_hash TEXT,
            status TEXT NOT NULL,
            error_code TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (google_account_id) REFERENCES google_workspace_accounts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_email_action_audit_account
            ON email_action_audit_logs(google_account_id, created_at);
        """
    )


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


def _drop_knowledge_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS knowledge_chunks_fts;
        DROP TABLE IF EXISTS knowledge_chunks;
        DROP TABLE IF EXISTS knowledge_sources;
        DROP TABLE IF EXISTS knowledge_source_roots;
        """
    )


def _migration_007_create_knowledge_index(conn: sqlite3.Connection) -> None:
    """Obsidian Vault + Iris Wiki FTS 인덱스."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_source_roots'"
    ).fetchone()
    if row is not None and not _table_has_column(conn, "knowledge_source_roots", "id"):
        _drop_knowledge_tables(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_source_roots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_path TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            root_id INTEGER NOT NULL,
            canonical_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'indexed',
            content_hash TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (root_id) REFERENCES knowledge_source_roots(id)
        );
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            heading TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (source_id) REFERENCES knowledge_sources(id)
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_sources_root ON knowledge_sources(root_id);
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source ON knowledge_chunks(source_id);
        """
    )
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                source_id UNINDEXED,
                title,
                path,
                tags,
                heading,
                content,
                tokenize='unicode61'
            )
            """
        )
    except sqlite3.OperationalError:
        pass


def _migration_008_knowledge_schema_repair(conn: sqlite3.Connection) -> None:
    """이전 실험 스키마 잔존 시 knowledge 테이블 재생성."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_source_roots'"
    ).fetchone()
    if row is None:
        _migration_007_create_knowledge_index(conn)
        return
    if not _table_has_column(conn, "knowledge_source_roots", "id"):
        _drop_knowledge_tables(conn)
        _migration_007_create_knowledge_index(conn)


def _migration_009_knowledge_legacy_reset(conn: sqlite3.Connection) -> None:
    """root_id PK 레거시 스키마 → id INTEGER PK 스키마로 교체."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_source_roots'"
    ).fetchone()
    if row is None:
        return
    if _table_has_column(conn, "knowledge_source_roots", "id"):
        return
    for name in (
        "knowledge_chunks_fts",
        "knowledge_chunks",
        "knowledge_sources",
        "knowledge_source_roots",
        "knowledge_reference_profiles",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {name}")
    _migration_007_create_knowledge_index(conn)


def _migration_010_knowledge_embedding_reference(conn: sqlite3.Connection) -> None:
    """청크 임베딩 BLOB·레퍼런스 Style Packet 테이블."""
    chunk_cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_chunks)").fetchall()}
    if chunk_cols and "embedding" not in chunk_cols:
        conn.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding BLOB")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_reference_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL DEFAULT '',
            style_packet TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """
    )


MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("001_create_task_runtime", _migration_001_create_task_runtime),
    ("002_create_execution_records", _migration_002_create_execution_records),
    ("003_create_approval_records", _migration_003_create_approval_records),
    ("004_events_task_link", _migration_004_events_task_link),
    ("005_plan_integrity", _migration_005_plan_integrity),
    ("006_google_workspace_email", _migration_006_google_workspace_email),
    ("007_create_knowledge_index", _migration_007_create_knowledge_index),
    ("008_knowledge_schema_repair", _migration_008_knowledge_schema_repair),
    ("009_knowledge_legacy_reset", _migration_009_knowledge_legacy_reset),
    ("010_knowledge_embedding_reference", _migration_010_knowledge_embedding_reference),
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
