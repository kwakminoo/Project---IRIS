"""최근 작업 SQLite 연동."""

from __future__ import annotations

import sqlite3
from typing import List

from iris.storage.database import Database


def format_recent_work_suggestion(db: Database, limit: int = 5) -> str:
    """최근 작업 제안 문구."""
    rows = db.list_recent_work(limit=limit)
    if not rows:
        return "최근 작업 기록이 없습니다."
    lines: List[str] = []
    for r in rows:
        lines.append(f"- {r['title']} ({r['work_type']})")
    return "최근 작업:\n" + "\n".join(lines)


def seed_demo_recent_work(db: Database) -> None:
    """데모용 시드 (비어 있을 때만)."""
    if db.list_recent_work(1):
        return
    db.upsert_recent_work(
        title="Iris 개발",
        work_type="개발",
        apps='["code","chrome","python"]',
        layout="dev_default",
        notes="Cursor, 터미널, Chrome",
    )
    db.upsert_recent_work(
        title="문서 작성",
        work_type="문서",
        apps='["chrome","edge"]',
        layout="doc_default",
        notes=None,
    )
