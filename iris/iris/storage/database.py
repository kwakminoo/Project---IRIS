"""SQLite 저장소."""

from __future__ import annotations

import sqlite3
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
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate_legacy_actions()
        self._init_schema()

    def _migrate_legacy_actions(self) -> None:
        """구버전 actions(런처 로그) 테이블이 있으면 launcher_actions로 이름 변경."""
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='actions'"
        ).fetchone()
        if not row:
            return
        cols = self._conn.execute("PRAGMA table_info(actions)").fetchall()
        col_names = {c[1] for c in cols}
        if "target_id" in col_names:
            return
        self._conn.execute("ALTER TABLE actions RENAME TO launcher_actions")
        self._conn.commit()

    def _init_schema(self) -> None:
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
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def insert_log(self, type_: str, message: str, result: str | None = None) -> None:
        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO logs (timestamp, type, message, result) VALUES (?, ?, ?, ?)",
            (ts, type_, message, result),
        )
        self._conn.commit()

    def insert_action(self, action_type: str, target: str, approved: bool, result: str | None) -> None:
        """런처 등 레거시 액션 로그 → launcher_actions."""
        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            """
            INSERT INTO launcher_actions (timestamp, action_type, target, approved, result)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, action_type, target, 1 if approved else 0, result),
        )
        self._conn.commit()

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
        cur = self._conn.execute(
            """
            INSERT INTO actions (timestamp, target_id, action_type, command, approved, result)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, target_id, action_type, command, 1 if approved else 0, result),
        )
        self._conn.commit()
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
        row = self._conn.execute(
            "SELECT id FROM recent_work WHERE title = ?", (title,)
        ).fetchone()
        if row:
            self._conn.execute(
                """
                UPDATE recent_work
                SET work_type=?, apps=?, layout=?, last_opened_at=?, notes=?
                WHERE title=?
                """,
                (work_type, apps, layout, ts, notes, title),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO recent_work (title, work_type, apps, layout, last_opened_at, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, work_type, apps, layout, ts, notes),
            )
        self._conn.commit()

    def list_recent_work(self, limit: int = 5) -> list[sqlite3.Row]:
        cur = self._conn.execute(
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
        cur = self._conn.execute(
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
        self._conn.commit()
        return int(cur.lastrowid)

    def find_target_by_process_title(self, process_name: str, title_sub: str) -> sqlite3.Row | None:
        return self._conn.execute(
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
        row = self._conn.execute(
            """
            SELECT id FROM targets
            WHERE type = ? AND process_name = ? AND title = ? AND enabled = 1
            """,
            (TargetType.DESKTOP_WINDOW.value, process_name, title),
        ).fetchone()
        if row:
            tid = int(row["id"])
            self._conn.execute(
                "UPDATE targets SET handle=?, last_checked_at=? WHERE id=?",
                (handle, datetime.utcnow().isoformat(), tid),
            )
            self._conn.commit()
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
        self._conn.execute(
            """
            UPDATE targets SET status=?, last_event=?, last_checked_at=?
            WHERE id=?
            """,
            (status.value, last_event, ts, target_id),
        )
        self._conn.commit()

    def list_targets(self, enabled_only: bool = True) -> list[sqlite3.Row]:
        if enabled_only:
            return list(
                self._conn.execute(
                    "SELECT * FROM targets WHERE enabled = 1 ORDER BY id ASC"
                ).fetchall()
            )
        return list(self._conn.execute("SELECT * FROM targets ORDER BY id ASC").fetchall())

    def get_target(self, target_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM targets WHERE id=?", (target_id,)).fetchone()

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
        cur = self._conn.execute(
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
        self._conn.commit()
        return int(cur.lastrowid)

    def update_event_user_flags(
        self,
        event_id: int,
        user_confirmed: bool,
        action_executed: bool,
    ) -> None:
        self._conn.execute(
            """
            UPDATE events SET user_confirmed=?, action_executed=? WHERE id=?
            """,
            (1 if user_confirmed else 0, 1 if action_executed else 0, event_id),
        )
        self._conn.commit()

    def list_recent_events(self, limit: int = 50) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
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
        row = self._conn.execute(
            "SELECT id FROM recent_target_states WHERE target_id=?",
            (target_id,),
        ).fetchone()
        if row:
            self._conn.execute(
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
            self._conn.execute(
                """
                INSERT INTO recent_target_states
                (target_id, status, last_text_hash, last_changed_at, last_checked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_id, status.value, last_text_hash, last_changed_at, last_checked_at),
            )
        self._conn.commit()

    def get_recent_target_state(self, target_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM recent_target_states WHERE target_id=?",
            (target_id,),
        ).fetchone()

    def upsert_browser_tab_target(self, url: str, title: str) -> int:
        """동일 URL 브라우저 탭 타깃 재사용."""
        row = self._conn.execute(
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
            self._conn.execute(
                "UPDATE targets SET title=?, last_checked_at=? WHERE id=?",
                (title, ts, tid),
            )
            self._conn.commit()
            return tid
        return self.insert_target(
            TargetType.BROWSER_TAB,
            title=title,
            process_name="chrome",
            url=url,
        )

    def ensure_current_screen_target(self) -> int:
        """current_screen 타입이 없으면 생성."""
        row = self._conn.execute(
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
        row = self._conn.execute(
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
