"""CI 구성·의존성·pytest marker 검증."""

from __future__ import annotations

import configparser
import platform
import subprocess
import sys
from pathlib import Path

import pytest

_IRIS_ROOT = Path(__file__).resolve().parents[1]


def _read_requirements(name: str) -> set[str]:
    path = _IRIS_ROOT / name
    lines: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        pkg = line.split(";")[0].strip()
        base = pkg.split(">=")[0].split("==")[0].split("[")[0].strip().lower()
        if base:
            lines.add(base)
    return lines


def test_requirements_files_exist() -> None:
    for name in (
        "requirements.txt",
        "requirements-base.txt",
        "requirements-windows.txt",
        "requirements-dev.txt",
    ):
        assert (_IRIS_ROOT / name).is_file(), name


def test_base_requirements_resolve_without_windows_packages() -> None:
    """Linux CI — Windows 전용 패키지가 base/dev에 없음."""
    base = _read_requirements("requirements-base.txt")
    dev = _read_requirements("requirements-dev.txt")
    combined = base | dev
    windows_only = {"pywin32", "pywinauto", "pygetwindow", "pyautogui"}
    assert not combined & windows_only


def test_windows_requirements_include_automation_packages() -> None:
    win = _read_requirements("requirements-windows.txt")
    assert "pywin32" in win
    assert "pywinauto" in win


def test_dev_requirements_include_pytest_timeout() -> None:
    dev = _read_requirements("requirements-dev.txt")
    assert "pytest" in dev
    assert "pytest-timeout" in dev


def test_pytest_timeout_is_available() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--help"],
        capture_output=True,
        text=True,
        check=False,
        cwd=_IRIS_ROOT,
    )
    assert out.returncode == 0
    assert "--timeout" in out.stdout


def test_markers_are_registered() -> None:
    ini = configparser.ConfigParser()
    ini.read(_IRIS_ROOT / "pytest.ini", encoding="utf-8")
    markers_raw = ini.get("pytest", "markers", fallback="")
    names = []
    for line in markers_raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        names.append(line.split(":")[0].strip())
    for expected in ("integration", "windows_only", "windows_smoke", "slow"):
        assert expected in names, f"marker missing: {expected}"


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows 전용")
def test_requirements_resolve_on_windows() -> None:
    """Windows — 전체 requirements.txt 파싱."""
    req = (_IRIS_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "-r requirements-base.txt" in req
    assert "-r requirements-windows.txt" in req
    assert "-r requirements-dev.txt" in req
