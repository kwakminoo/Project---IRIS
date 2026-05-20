"""SQLite 저장소."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from iris.monitoring.models import StatusCategory, TargetType


def default_db_path() -> Path:
    """사용자 데이터 디렉터리에 DB 저장."""
    base = Path.home() / ".iris"
    base.mkdir(parents=True, exist_ok=True)
    return base / "iris.db"


class Database:
    """logs / launcher_actions / recent_work / targets / events / actions / recent_target_states."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        # UI·AgentWorker·모니터·HTTP 스레드가 동일 연결을 쓰므로 직렬화
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._migrate_legacy_actions()
            self._init_schema()

    def _execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def _migrate_legacy_actions(self) -> None:
        """구버전 actions(런처 로그) 테이블이 있으면 launcher_actions로 이름 변경."""
        row = self._execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='actions'"
        ).fetchone()
        if not row:
            return
        cols = self._execute("PRAGMA table_info(actions)").fetchall()
        col_names = {c[1] for c in cols}
        if "target_id" in col_names:
            return
        self._execute("ALTER TABLE actions RENAME TO launcher_actions")
        self._commit()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                result TEXT
            );
            CREATE TABLE IF NOT EXISTS launcher_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target TEXT NOT NULL,
                approved INTEGER NOT NULL,
                result TEXT
            );
            CREATE TABLE IF NOT EXISTS recent_work (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                work_type TEXT NOT NULL,
                apps TEXT NOT NULL,
                layout TEXT NOT NULL,
                last_opened_at TEXT NOT NULL,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                process_name TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                handle TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'UNKNOWN',
                last_checked_at TEXT,
                last_event TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                target_id INTEGER,
                target_title TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL,
                recommended_action TEXT NOT NULL DEFAULT '',
                user_confirmed INTEGER,
                action_executed INTEGER,
                FOREIGN KEY (target_id) REFERENCES targets(id)
            );
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                target_id INTEGER,
                action_type TEXT NOT NULL,
                command TEXT,
                approved INTEGER NOT NULL,
                result TEXT,
                FOREIGN KEY (target_id) REFERENCES targets(id)
            );
            CREATE TABLE IF NOT EXISTS recent_target_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER NOT NULL UNIQUE,
                status TEXT NOT NULL,
                last_text_hash TEXT NOT NULL DEFAULT '',
                last_changed_at TEXT,
                last_checked_at TEXT NOT NULL,
                FOREIGN KEY (target_id) REFERENCES targets(id)
            );
            CREATE TABLE IF NOT EXISTS task_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL UNIQUE,
                current_goal TEXT NOT NULL DEFAULT '',
                tools_run_json TEXT NOT NULL DEFAULT '[]',
                observations_json TEXT NOT NULL DEFAULT '[]',
                approvals_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                source_hint TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS automation_tool_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                approved INTEGER NOT NULL,
                success INTEGER NOT NULL,
                result TEXT
            );
            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                target_id INTEGER,
                event_id INTEGER,
                category TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                user_decision TEXT NOT NULL DEFAULT '',
                snooze_until TEXT,
                FOREIGN KEY (target_id) REFERENCES targets(id)
            );
            CREATE TABLE IF NOT EXISTS notification_prefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                category TEXT NOT NULL DEFAULT '',
                pref_type TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(target_id, category, pref_type)
            );
            CREATE TABLE IF NOT EXISTS app_launcher_entries (
                app_key TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                exe_path TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'scan',
                added_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def insert_log(self, type_: str, message: str, result: str | None = None) -> None:
        ts = datetime.utcnow().isoformat()
        self._execute(
            "INSERT INTO logs (timestamp, type, message, result) VALUES (?, ?, ?, ?)",
            (ts, type_, message, result),
        )
        self._commit()

    def insert_action(self, action_type: str, target: str, approved: bool, result: str | None) -> None:
        """런처 등 레거시 액션 로그 → launcher_actions."""
        ts = datetime.utcnow().isoformat()
        self._execute(
            """
            INSERT INTO launcher_actions (timestamp, action_type, target, approved, result)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, action_type, target, 1 if approved else 0, result),
        )
        self._commit()

    def insert_monitoring_action(
        self,
        action_type: str,
        approved: bool,
        result: str | None,
        target_id: int | None = None,
        command: str | None = None,
    ) -> int:
        """모니터링 승인 후 실행 기록 → actions."""
        ts = datetime.utcnow().isoformat()
        cur = self._execute(
            """
            INSERT INTO actions (timestamp, target_id, action_type, command, approved, result)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, target_id, action_type, command, 1 if approved else 0, result),
        )
        self._commit()
        return int(cur.lastrowid)

    def upsert_recent_work(
        self,
        title: str,
        work_type: str,
        apps: str,
        layout: str,
        notes: str | None = None,
    ) -> None:
        ts = datetime.utcnow().isoformat()
        row = self._execute(
            "SELECT id FROM recent_work WHERE title = ?", (title,)
        ).fetchone()
        if row:
            self._execute(
                """
                UPDATE recent_work
                SET work_type=?, apps=?, layout=?, last_opened_at=?, notes=?
                WHERE title=?
                """,
                (work_type, apps, layout, ts, notes, title),
            )
        else:
            self._execute(
                """
                INSERT INTO recent_work (title, work_type, apps, layout, last_opened_at, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, work_type, apps, layout, ts, notes),
            )
        self._commit()

    def list_recent_work(self, limit: int = 5) -> list[sqlite3.Row]:
        cur = self._execute(
            "SELECT * FROM recent_work ORDER BY last_opened_at DESC LIMIT ?",
            (limit,),
        )
        return list(cur.fetchall())

    # --- 모니터링: targets ---

    def insert_target(
        self,
        type_: TargetType,
        title: str,
        process_name: str = "",
        url: str = "",
        handle: str = "",
        enabled: bool = True,
    ) -> int:
        ts = datetime.utcnow().isoformat()
        cur = self._execute(
            """
            INSERT INTO targets (type, title, process_name, url, handle, enabled, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                type_.value,
                title,
                process_name,
                url,
                handle,
                1 if enabled else 0,
                StatusCategory.UNKNOWN.value,
                ts,
            ),
        )
        self._commit()
        return int(cur.lastrowid)

    def find_target_by_process_title(self, process_name: str, title_sub: str) -> sqlite3.Row | None:
        return self._execute(
            """
            SELECT * FROM targets
            WHERE process_name = ? AND title LIKE ? AND enabled = 1
            LIMIT 1
            """,
            (process_name, f"%{title_sub}%"),
        ).fetchone()

    def merge_or_insert_desktop_target(
        self,
        title: str,
        process_name: str,
        handle: str = "",
    ) -> int:
        """동일 프로세스+제목 유사 시 업데이트, 없으면 삽입."""
        row = self._execute(
            """
            SELECT id FROM targets
            WHERE type = ? AND process_name = ? AND title = ? AND enabled = 1
            """,
            (TargetType.DESKTOP_WINDOW.value, process_name, title),
        ).fetchone()
        if row:
            tid = int(row["id"])
            self._execute(
                "UPDATE targets SET handle=?, last_checked_at=? WHERE id=?",
                (handle, datetime.utcnow().isoformat(), tid),
            )
            self._commit()
            return tid
        return self.insert_target(
            TargetType.DESKTOP_WINDOW,
            title=title,
            process_name=process_name,
            handle=handle,
        )

    def update_target_runtime(
        self,
        target_id: int,
        status: StatusCategory,
        last_event: str,
        last_checked_at: Optional[str] = None,
    ) -> None:
        ts = last_checked_at or datetime.utcnow().isoformat()
        self._execute(
            """
            UPDATE targets SET status=?, last_event=?, last_checked_at=?
            WHERE id=?
            """,
            (status.value, last_event, ts, target_id),
        )
        self._commit()

    def list_targets(self, enabled_only: bool = True) -> list[sqlite3.Row]:
        if enabled_only:
            return list(
                self._execute(
                    "SELECT * FROM targets WHERE enabled = 1 ORDER BY id ASC"
                ).fetchall()
            )
        return list(self._execute("SELECT * FROM targets ORDER BY id ASC").fetchall())

    def get_target(self, target_id: int) -> sqlite3.Row | None:
        return self._execute("SELECT * FROM targets WHERE id=?", (target_id,)).fetchone()

    def set_target_enabled(self, target_id: int, enabled: bool) -> None:
        self._execute(
            "UPDATE targets SET enabled=? WHERE id=?",
            (1 if enabled else 0, target_id),
        )
        self._commit()

    # --- events ---

    def insert_event(
        self,
        target_id: int | None,
        target_title: str,
        category: StatusCategory,
        confidence: float,
        reason: str,
        recommended_action: str,
        user_confirmed: bool | None = None,
        action_executed: bool | None = None,
    ) -> int:
        ts = datetime.utcnow().isoformat()
        cur = self._execute(
            """
            INSERT INTO events (
                timestamp, target_id, target_title, category, confidence,
                reason, recommended_action, user_confirmed, action_executed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                target_id,
                target_title,
                category.value,
                confidence,
                reason,
                recommended_action,
                None if user_confirmed is None else (1 if user_confirmed else 0),
                None if action_executed is None else (1 if action_executed else 0),
            ),
        )
        self._commit()
        return int(cur.lastrowid)

    def update_event_user_flags(
        self,
        event_id: int,
        user_confirmed: bool,
        action_executed: bool,
    ) -> None:
        self._execute(
            """
            UPDATE events SET user_confirmed=?, action_executed=? WHERE id=?
            """,
            (1 if user_confirmed else 0, 1 if action_executed else 0, event_id),
        )
        self._commit()

    def list_recent_events(self, limit: int = 50) -> list[sqlite3.Row]:
        return list(
            self._execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        )

    # --- recent_target_states ---

    def upsert_recent_target_state(
        self,
        target_id: int,
        status: StatusCategory,
        last_text_hash: str,
        last_changed_at: str | None,
        last_checked_at: str,
    ) -> None:
        row = self._execute(
            "SELECT id FROM recent_target_states WHERE target_id=?",
            (target_id,),
        ).fetchone()
        if row:
            self._execute(
                """
                UPDATE recent_target_states
                SET status=?, last_text_hash=?, last_changed_at=?, last_checked_at=?
                WHERE target_id=?
                """,
                (
                    status.value,
                    last_text_hash,
                    last_changed_at,
                    last_checked_at,
                    target_id,
                ),
            )
        else:
            self._execute(
                """
                INSERT INTO recent_target_states
                (target_id, status, last_text_hash, last_changed_at, last_checked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_id, status.value, last_text_hash, last_changed_at, last_checked_at),
            )
        self._commit()

    def get_recent_target_state(self, target_id: int) -> sqlite3.Row | None:
        return self._execute(
            "SELECT * FROM recent_target_states WHERE target_id=?",
            (target_id,),
        ).fetchone()

    def upsert_browser_tab_target(self, url: str, title: str) -> int:
        """동일 URL 브라우저 탭 타깃 재사용."""
        row = self._execute(
            """
            SELECT id FROM targets
            WHERE type = ? AND url = ? AND enabled = 1
            LIMIT 1
            """,
            (TargetType.BROWSER_TAB.value, url),
        ).fetchone()
        ts = datetime.utcnow().isoformat()
        if row:
            tid = int(row["id"])
            self._execute(
                "UPDATE targets SET title=?, last_checked_at=? WHERE id=?",
                (title, ts, tid),
            )
            self._commit()
            return tid
        return self.insert_target(
            TargetType.BROWSER_TAB,
            title=title,
            process_name="chrome",
            url=url,
        )

    def ensure_current_screen_target(self) -> int:
        """current_screen 타입이 없으면 생성."""
        row = self._execute(
            "SELECT id FROM targets WHERE type = ? AND enabled = 1 LIMIT 1",
            (TargetType.CURRENT_SCREEN.value,),
        ).fetchone()
        if row:
            return int(row["id"])
        return self.insert_target(
            TargetType.CURRENT_SCREEN,
            title="현재 화면",
            process_name="",
        )

    def ensure_system_log_target(self) -> int:
        row = self._execute(
            "SELECT id FROM targets WHERE type = ? AND enabled = 1 LIMIT 1",
            (TargetType.SYSTEM_LOG.value,),
        ).fetchone()
        if row:
            return int(row["id"])
        return self.insert_target(
            TargetType.SYSTEM_LOG,
            title="Windows 이벤트",
            process_name="System",
        )

    # --- user_preferences ---

    def get_preference(self, key: str, default: str = "") -> str:
        row = self._execute(
            "SELECT value FROM user_preferences WHERE key=?", (key,)
        ).fetchone()
        return str(row["value"]) if row else default

    def set_preference(self, key: str, value: str) -> None:
        ts = datetime.utcnow().isoformat()
        self._execute(
            """
            INSERT INTO user_preferences (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, ts),
        )
        self._commit()

    def get_auto_approve_low_risk(self) -> bool:
        return self.get_preference("auto_approve_low_risk", "0") in ("1", "true", "True")

    def set_auto_approve_low_risk(self, enabled: bool) -> None:
        self.set_preference("auto_approve_low_risk", "1" if enabled else "0")

    # --- task_sessions ---

    def upsert_task_session(
        self,
        session_key: str,
        current_goal: str,
        tools_run_json: str = "[]",
        observations_json: str = "[]",
        approvals_json: str = "[]",
    ) -> int:
        ts = datetime.utcnow().isoformat()
        row = self._execute(
            "SELECT id FROM task_sessions WHERE session_key=?", (session_key,)
        ).fetchone()
        if row:
            tid = int(row["id"])
            self._execute(
                """
                UPDATE task_sessions
                SET current_goal=?, tools_run_json=?, observations_json=?,
                    approvals_json=?, updated_at=?
                WHERE id=?
                """,
                (current_goal, tools_run_json, observations_json, approvals_json, ts, tid),
            )
        else:
            cur = self._execute(
                """
                INSERT INTO task_sessions
                (session_key, current_goal, tools_run_json, observations_json,
                 approvals_json, updated_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_key, current_goal, tools_run_json, observations_json, approvals_json, ts, ts),
            )
            tid = int(cur.lastrowid)
        self._commit()
        return tid

    def get_task_session(self, session_key: str) -> sqlite3.Row | None:
        return self._execute(
            "SELECT * FROM task_sessions WHERE session_key=?", (session_key,)
        ).fetchone()

    # --- memory_summaries ---

    def insert_memory_summary(self, category: str, summary: str, source_hint: str = "") -> int:
        ts = datetime.utcnow().isoformat()
        cur = self._execute(
            """
            INSERT INTO memory_summaries (category, summary, source_hint, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (category, summary[:4000], source_hint[:500], ts),
        )
        self._commit()
        return int(cur.lastrowid)

    def list_memory_summaries(self, limit: int = 20) -> list[sqlite3.Row]:
        return list(
            self._execute(
                "SELECT * FROM memory_summaries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        )

    # --- automation_tool_logs ---

    def insert_automation_tool_log(
        self,
        tool_name: str,
        summary: str,
        approved: bool,
        success: bool,
        result: str | None = None,
    ) -> None:
        ts = datetime.utcnow().isoformat()
        self._execute(
            """
            INSERT INTO automation_tool_logs
            (timestamp, tool_name, summary, approved, success, result)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, tool_name, summary[:1000], 1 if approved else 0, 1 if success else 0, result),
        )
        self._commit()

    # --- notification_log / notification_prefs ---

    def insert_notification_log(
        self,
        target_id: int | None,
        event_id: int | None,
        category: str,
        title: str,
        message: str,
        user_decision: str = "",
        snooze_until: str | None = None,
    ) -> int:
        ts = datetime.utcnow().isoformat()
        cur = self._execute(
            """
            INSERT INTO notification_log
            (timestamp, target_id, event_id, category, title, message,
             user_decision, snooze_until)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, target_id, event_id, category, title[:500], message[:2000], user_decision, snooze_until),
        )
        self._commit()
        return int(cur.lastrowid)

    def set_notification_pref(
        self,
        pref_type: str,
        value: str,
        target_id: int | None = None,
        category: str = "",
    ) -> None:
        """pref_type: cooldown_seconds | ignore | snooze_until | disabled."""
        ts = datetime.utcnow().isoformat()
        tid = target_id if target_id is not None else -1
        self._execute(
            """
            INSERT INTO notification_prefs (target_id, category, pref_type, value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(target_id, category, pref_type)
            DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (tid, category, pref_type, value, ts),
        )
        self._commit()

    def get_notification_pref(
        self,
        pref_type: str,
        target_id: int | None = None,
        category: str = "",
    ) -> str | None:
        tid = target_id if target_id is not None else -1
        row = self._execute(
            """
            SELECT value FROM notification_prefs
            WHERE target_id=? AND category=? AND pref_type=?
            """,
            (tid, category, pref_type),
        ).fetchone()
        return str(row["value"]) if row else None

    def is_target_notification_disabled(self, target_id: int) -> bool:
        v = self.get_notification_pref("disabled", target_id=target_id, category="")
        return v in ("1", "true", "True")

    def is_notification_ignored(self, target_id: int, category: str) -> bool:
        v = self.get_notification_pref("ignore", target_id=target_id, category=category)
        return v in ("1", "true", "True")

    def get_notification_snooze_until(self, target_id: int, category: str) -> str | None:
        return self.get_notification_pref("snooze_until", target_id=target_id, category=category)

    def get_notification_cooldown_seconds(
        self, target_id: int, category: str, default: float = 90.0
    ) -> float:
        v = self.get_notification_pref("cooldown_seconds", target_id=target_id, category=category)
        if v is None:
            return default
        try:
            return float(v)
        except ValueError:
            return default

    def get_last_notification_shown_at(self, target_id: int, category: str) -> str | None:
        return self.get_notification_pref("last_shown_at", target_id=target_id, category=category)

    def set_last_notification_shown_at(self, target_id: int, category: str) -> None:
        self.set_notification_pref(
            "last_shown_at",
            datetime.utcnow().isoformat(),
            target_id=target_id,
            category=category,
        )

    # --- app_launcher_entries ---

    def list_app_launcher_entries(self) -> list[sqlite3.Row]:
        return list(
            self._execute(
                "SELECT * FROM app_launcher_entries ORDER BY display_name COLLATE NOCASE ASC"
            ).fetchall()
        )

    def get_app_launcher_entry(self, app_key: str) -> sqlite3.Row | None:
        return self._execute(
            "SELECT * FROM app_launcher_entries WHERE app_key=?",
            (app_key,),
        ).fetchone()

    def upsert_app_launcher_entry(
        self,
        app_key: str,
        display_name: str,
        exe_path: str,
        source: str = "scan",
    ) -> None:
        ts = datetime.utcnow().isoformat()
        row = self.get_app_launcher_entry(app_key)
        if row:
            self._execute(
                """
                UPDATE app_launcher_entries
                SET display_name=?, exe_path=?, source=?, updated_at=?
                WHERE app_key=?
                """,
                (display_name, exe_path, source, ts, app_key),
            )
        else:
            self._execute(
                """
                INSERT INTO app_launcher_entries
                (app_key, display_name, exe_path, source, added_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (app_key, display_name, exe_path, source, ts, ts),
            )
        self._commit()

    def delete_app_launcher_entry(self, app_key: str) -> bool:
        cur = self._execute(
            "DELETE FROM app_launcher_entries WHERE app_key=?",
            (app_key,),
        )
        self._commit()
        return cur.rowcount > 0

    def merge_scan_results(
        self,
        entries: list[tuple[str, str, str, str]],
    ) -> tuple[int, list[str]]:
        """
        스캔 결과 병합. (신규 키 개수, 신규 표시명 목록) 반환.
        entries: (app_key, display_name, exe_path, source)
        """
        new_names: list[str] = []
        for app_key, display_name, exe_path, source in entries:
            row = self.get_app_launcher_entry(app_key)
            if row is None:
                self.upsert_app_launcher_entry(app_key, display_name, exe_path, source)
                new_names.append(display_name)
                continue
            if str(row["exe_path"]) != exe_path:
                self.upsert_app_launcher_entry(app_key, display_name, exe_path, source)
        return len(new_names), new_names
