"""알림 정책·SQLite prefs 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from iris.monitoring.models import TargetType
from iris.monitoring.notification_policy import NotificationPolicy
from iris.storage.database import Database


def test_cooldown_suppresses(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "n.db")
    policy = NotificationPolicy(db, default_cooldown_seconds=120.0)
    policy.mark_shown(1, "ERROR_DETECTED")
    reason = policy.should_suppress(1, "ERROR_DETECTED")
    assert reason == "cooldown"


def test_ignore_permanent(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "n2.db")
    policy = NotificationPolicy(db)
    policy.dismiss_permanently(2, "TASK_STALLED")
    assert policy.should_suppress(2, "TASK_STALLED") == "ignored"


def test_snooze(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "n3.db")
    policy = NotificationPolicy(db)
    until = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
    db.set_notification_pref("snooze_until", until, target_id=3, category="RESPONSE_READY")
    assert policy.should_suppress(3, "RESPONSE_READY") == "snoozed"


def test_disable_target(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "n4.db")
    tid = db.insert_target(TargetType.DESKTOP_WINDOW, title="Test")
    policy = NotificationPolicy(db)
    policy.disable_target(tid)
    assert policy.should_suppress(tid, "ANY") == "target_disabled"
    row = db.get_target(tid)
    assert int(row["enabled"]) == 0
