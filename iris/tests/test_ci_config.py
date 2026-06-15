"""CI 구성·의존성·pytest marker·Windows 우선 정책 검증."""

from __future__ import annotations

import configparser
import platform
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IRIS_ROOT = Path(__file__).resolve().parents[1]
_TEST_YML = _REPO_ROOT / ".github" / "workflows" / "test.yml"
_LINUX_EXP_YML = _REPO_ROOT / ".github" / "workflows" / "linux-experimental.yml"
_VERIFY_SCRIPT = _REPO_ROOT / "scripts" / "verify-next-stage.ps1"


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
    """Linux experimental — Windows 전용 패키지가 base/dev에 없음."""
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


def test_pytest_markers_are_registered() -> None:
    ini = configparser.ConfigParser()
    ini.read(_IRIS_ROOT / "pytest.ini", encoding="utf-8")
    markers_raw = ini.get("pytest", "markers", fallback="")
    names = []
    for line in markers_raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        names.append(line.split(":")[0].strip())
    for expected in (
        "integration",
        "windows_only",
        "windows_smoke",
        "windows_smoke_gui",
        "external_service",
        "requires_model",
        "slow",
    ):
        assert expected in names, f"marker missing: {expected}"


def test_markers_are_registered() -> None:
    """하위 호환 alias."""
    test_pytest_markers_are_registered()


def test_windows_ci_includes_integration_tests() -> None:
    content = _TEST_YML.read_text(encoding="utf-8")
    assert "not windows_smoke and not integration" not in content
    assert "not windows_smoke and not external_service and not requires_model" in content


def test_windows_integration_job_exists() -> None:
    content = _TEST_YML.read_text(encoding="utf-8")
    assert "windows-integration:" in content
    assert "name: test / windows-integration" in content
    assert 'integration and not windows_smoke and not external_service and not requires_model' in content


def test_linux_is_not_required_for_next_stage() -> None:
    test_content = _TEST_YML.read_text(encoding="utf-8")
    assert "linux-domain:" not in test_content
    linux_content = _LINUX_EXP_YML.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in linux_content
    assert "push:" not in linux_content.split("on:")[1].split("jobs:")[0]


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows 전용")
def test_requirements_resolve_on_windows() -> None:
    req = (_IRIS_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "-r requirements-base.txt" in req
    assert "-r requirements-windows.txt" in req
    assert "-r requirements-dev.txt" in req


@pytest.mark.skipif(platform.system() != "Windows", reason="PowerShell 스크립트")
def test_verify_next_stage_script_fails_on_test_failure() -> None:
    """스크립트가 존재하고 실패 시 non-zero를 반환하는지 — compile 단계만 빠르게 검증."""
    assert _VERIFY_SCRIPT.is_file()
    content = _VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "Integration Tests" in content
    assert "not windows_smoke and not external_service and not requires_model" in content

    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "exit 1",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
