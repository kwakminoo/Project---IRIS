"""app_index 스캔·병합·resolve 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from iris.config import app_index
from iris.config.app_index import (
    AppScanResult,
    build_merged_app_paths,
    resolve_app_for_goal,
    scan_installed_apps,
    scan_results_as_tuples,
    set_lnk_resolver,
    slug_app_key,
    verify_exe_stable,
)
from iris.storage.database import Database


def test_slug_app_key() -> None:
    assert slug_app_key("Notepad.exe") == "notepad"
    assert slug_app_key("Visual Studio Code") == "visual_studio_code"


def test_verify_exe_stable_same_size(tmp_path: Path) -> None:
    exe = tmp_path / "app.exe"
    exe.write_bytes(b"x" * 64)
    assert verify_exe_stable(exe, checks=2, interval_sec=0) is True


def test_verify_exe_stable_missing(tmp_path: Path) -> None:
    assert verify_exe_stable(tmp_path / "nope.exe", checks=2, interval_sec=0) is False


def test_scan_merge_dedupe_by_key() -> None:
    fake_reg = [
        AppScanResult("notepad", "Notepad", r"C:\Windows\System32\notepad.exe", "scan"),
    ]
    fake_menu = [
        AppScanResult("notepad", "메모장", r"C:\Windows\System32\notepad.exe", "scan"),
    ]
    with (
        patch.object(app_index, "_scan_registry_app_paths", return_value=fake_reg),
        patch.object(app_index, "_scan_start_menu", return_value=fake_menu),
        patch.object(app_index, "builtin_scan_fallbacks", return_value=[]),
    ):
        results = scan_installed_apps()
    assert len(results) == 1
    assert results[0].app_key == "notepad"


def test_lnk_resolver_mock(tmp_path: Path) -> None:
    lnk = tmp_path / "MyApp.lnk"
    lnk.write_text("stub", encoding="utf-8")
    exe = tmp_path / "MyApp.exe"
    exe.write_bytes(b"MZ" + b"\0" * 62)

    set_lnk_resolver(lambda p: str(exe) if p.name == "MyApp.lnk" else None)

    def fake_menu() -> list[AppScanResult]:
        target = app_index.resolve_lnk(lnk)
        return [AppScanResult("myapp", "MyApp", target, "scan")] if target else []

    try:
        with (
            patch.object(app_index, "_scan_registry_app_paths", return_value=[]),
            patch.object(app_index, "_scan_start_menu", side_effect=fake_menu),
            patch.object(app_index, "builtin_scan_fallbacks", return_value=[]),
        ):
            results = scan_installed_apps()
        assert any(r.app_key == "myapp" for r in results)
    finally:
        set_lnk_resolver(None)


def test_build_merged_app_paths_db(tmp_path: Path) -> None:
    exe = tmp_path / "notepad.exe"
    exe.write_bytes(b"MZ" + b"\0" * 64)
    db = Database(path=tmp_path / "idx.db")
    db.upsert_app_launcher_entry("notepad", "메모장", str(exe), "manual")
    merged = build_merged_app_paths(db)
    assert merged["notepad"] == str(exe)


def test_resolve_app_for_goal_notepad_alias(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "r.db")
    paths = {"notepad": r"C:\Windows\System32\notepad.exe"}
    db.upsert_app_launcher_entry(
        "notepad", "메모장", r"C:\Windows\System32\notepad.exe", "scan"
    )
    key, exe = resolve_app_for_goal("메모장 켜줘", paths, db=db)
    assert key == "notepad"
    assert exe is not None


def test_merge_scan_results_tuples(tmp_path: Path) -> None:
    db = Database(path=tmp_path / "m.db")
    tuples = scan_results_as_tuples(
        [AppScanResult("calc", "계산기", r"C:\Windows\System32\calc.exe", "scan")]
    )
    n, names = db.merge_scan_results(tuples)
    assert n == 1
    assert "계산기" in names
    n2, _ = db.merge_scan_results(tuples)
    assert n2 == 0
