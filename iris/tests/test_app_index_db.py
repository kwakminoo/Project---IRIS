"""app_launcher_entries DB CRUD·idempotent upsert."""

from __future__ import annotations

from pathlib import Path

from iris.storage.database import Database


def test_upsert_idempotent(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "a.db")
    db.upsert_app_launcher_entry("notepad", "메모장", r"C:\a\notepad.exe", "manual")
    db.upsert_app_launcher_entry("notepad", "메모장", r"C:\a\notepad.exe", "manual")
    rows = db.list_app_launcher_entries()
    assert len(rows) == 1
    assert rows[0]["exe_path"] == r"C:\a\notepad.exe"


def test_manual_add_and_delete(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "b.db")
    db.upsert_app_launcher_entry("foo", "Foo App", r"C:\apps\foo.exe", "manual")
    assert db.get_app_launcher_entry("foo") is not None
    assert db.delete_app_launcher_entry("foo") is True
    assert db.get_app_launcher_entry("foo") is None


def test_merge_scan_only_new_keys(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "c.db")
    db.upsert_app_launcher_entry("chrome", "Chrome", r"C:\chrome.exe", "scan")
    n, names = db.merge_scan_results(
        [
            ("chrome", "Chrome", r"C:\chrome.exe", "scan"),
            ("edge", "Edge", r"C:\edge.exe", "scan"),
        ]
    )
    assert n == 1
    assert names == ["Edge"]
    row = db.get_app_launcher_entry("chrome")
    assert row is not None
