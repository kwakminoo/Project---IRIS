from __future__ import annotations

import os
import sqlite3
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

from iris.email.controller import EmailController
from iris.email.google_workspace import (
    GoogleWorkspaceAccountRegistry,
    GoogleWorkspaceGateway,
    sanitize_email_html,
)
from iris.storage.database import Database
from iris.storage.user_profile import UserProfile, save_user_profile
from iris.ui.email_window import EmailWindow
from iris.ui.workspace_action_panel import WorkspaceActionPanel


def _db(tmp_path):
    return Database(tmp_path / "iris.db")


def test_email_migration_creates_metadata_only_tables(tmp_path) -> None:
    db = _db(tmp_path)
    tables = {
        row[0]
        for row in db._execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()  # noqa: SLF001
    }
    assert "google_workspace_accounts" in tables
    assert "email_ui_preferences" in tables
    assert "email_action_audit_logs" in tables
    cols = {
        row[1]
        for row in db._execute("PRAGMA table_info(email_action_audit_logs)").fetchall()  # noqa: SLF001
    }
    assert "target_hash" in cols
    assert "subject" not in cols
    assert "body" not in cols
    db.close()


def test_google_account_requires_profile_email_match(tmp_path, monkeypatch) -> None:
    db = _db(tmp_path)
    save_user_profile(db, UserProfile(email="me@example.com"))
    monkeypatch.setenv("USER_GOOGLE_EMAIL", "other@example.com")
    try:
        GoogleWorkspaceAccountRegistry(db).upsert_from_env()
    except ValueError as exc:
        assert "match" in str(exc)
    else:
        raise AssertionError("expected mismatch to be blocked")
    db.close()


def test_sanitizer_removes_scripts_events_and_images() -> None:
    html = '<p onclick="x()">Hi<script>x()</script><img src="https://x.test/a.png"><a href="https://ok">ok</a></p>'
    safe = sanitize_email_html(html)
    assert "script" not in safe
    assert "onclick" not in safe
    assert "img" not in safe
    assert 'href="https://ok"' in safe


def test_gateway_discovers_and_calls_mcp_tools(tmp_path) -> None:
    db = _db(tmp_path)
    db.upsert_integration_endpoint("google_workspace", kind="mcp", base_url="http://localhost:9999")
    with patch("iris.email.google_workspace.IntegrationClient") as client_cls:
        client = MagicMock()
        client.list_tools.return_value = (
            True,
            "ok",
            [{"name": "gmail_list_messages"}, {"name": "gmail_get_message"}],
        )
        client.call_json.return_value = (True, "ok", {"messages": [{"id": "m1"}]})
        client_cls.return_value = client
        data = GoogleWorkspaceGateway(db).list_messages(label="INBOX")
    assert data["messages"][0]["id"] == "m1"
    client.call_json.assert_called_once()
    db.close()


def test_controller_logs_hash_not_recipient_or_body(tmp_path) -> None:
    db = _db(tmp_path)
    save_user_profile(db, UserProfile(email="me@example.com"))
    db.upsert_integration_endpoint("google_workspace", kind="mcp", base_url="http://localhost:9999")
    monkeypatch_env = {
        "USER_GOOGLE_EMAIL": "me@example.com",
    }
    old = {k: os.environ.get(k) for k in monkeypatch_env}
    os.environ.update(monkeypatch_env)
    try:
        EmailController(db).connect_google_workspace()
        registry = GoogleWorkspaceAccountRegistry(db)
        account = registry.default_account()
        assert account is not None
        registry.log_action(account.id, "send_direct", status="success", recipients=["to@example.com"])
        row = db._execute("SELECT * FROM email_action_audit_logs").fetchone()  # noqa: SLF001
        assert row["target_hash"]
        assert "to@example.com" not in str(tuple(row))
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        db.close()


def test_existing_email_button_binding_opens_email_window(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    opened = {"value": False}
    panel = WorkspaceActionPanel()
    panel.add_icon_action(
        action_id="email",
        icon_kind="email",
        tooltip="email",
        callback=lambda: opened.__setitem__("value", True),
    )
    panel._buttons["email"].click()  # noqa: SLF001
    assert opened["value"] is True


def test_disconnected_email_window_shows_connect_panel(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    win = EmailWindow(_db(tmp_path))
    win.refresh()
    assert not win.disconnected_panel.isHidden()
