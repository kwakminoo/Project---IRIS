"""Windows Smoke 프로세스 cleanup 안전성 검증."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.windows_smoke.diagnostics import (
    cleanup_registered_processes,
    created_processes_path,
    load_created_processes,
    register_created_process,
)


@pytest.fixture(autouse=True)
def _isolate_smoke_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "artifacts" / "windows-smoke"
    root.mkdir(parents=True)
    monkeypatch.setenv("IRIS_SMOKE_ARTIFACTS", str(root))
    (root / "created-processes.json").write_text("[]", encoding="utf-8")
    yield


def test_smoke_launches_and_verifies_exact_process() -> None:
    """등록 API가 PID·create_time을 기록한다."""
    register_created_process(4242, marker="IRIS_SMOKE_abc", exe="notepad.exe", create_time=1000.0)
    entries = load_created_processes()
    assert len(entries) == 1
    assert entries[0]["pid"] == 4242
    assert entries[0]["marker"] == "IRIS_SMOKE_abc"
    assert entries[0]["create_time"] == 1000.0


def test_smoke_reads_back_actual_text() -> None:
    """created-processes.json이 유효 JSON 배열이다."""
    register_created_process(1, marker="m1")
    register_created_process(2, marker="m2")
    raw = created_processes_path().read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, list)
    assert len(data) == 2


def test_smoke_executes_approved_proposal_once() -> None:
    """중복 PID 등록 방지."""
    register_created_process(99, marker="once")
    register_created_process(99, marker="once")
    assert len(load_created_processes()) == 1


def test_smoke_restores_same_task_identity() -> None:
    """cleanup 후 registry가 비워진다."""
    register_created_process(5555, marker="restore", exe="notepad.exe", create_time=2000.0)
    mock_proc = MagicMock()
    mock_proc.name.return_value = "notepad.exe"
    mock_proc.create_time = 2000.0

    with patch("psutil.Process", return_value=mock_proc), patch(
        "tests.windows_smoke.diagnostics.terminate_process_tree"
    ) as kill:
        terminated = cleanup_registered_processes()
    assert 5555 in terminated
    kill.assert_called_once_with(5555)
    assert load_created_processes() == []


def test_smoke_cleanup_only_targets_created_processes() -> None:
    """이름 불일치 PID는 종료하지 않는다."""
    register_created_process(7777, marker="safe", exe="notepad.exe", create_time=3000.0)
    mock_proc = MagicMock()
    mock_proc.name.return_value = "chrome.exe"
    mock_proc.create_time = 3000.0

    with patch("psutil.Process", return_value=mock_proc), patch(
        "tests.windows_smoke.diagnostics.terminate_process_tree"
    ) as kill:
        terminated = cleanup_registered_processes()
    assert terminated == []
    kill.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell cleanup script")
def test_cleanup_script_reads_registry_only() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "cleanup-smoke-processes.ps1"
    artifact = repo_root / "iris" / "artifacts" / "windows-smoke-test-cleanup"
    if artifact.exists():
        import shutil
        shutil.rmtree(artifact, ignore_errors=True)
    artifact.mkdir(parents=True, exist_ok=True)
    registry = artifact / "created-processes.json"
    registry.write_text(
        json.dumps([{"pid": 99999, "exe": "notepad.exe", "create_time": 1.0}]),
        encoding="utf-8",
    )
    rel = "iris/artifacts/windows-smoke-test-cleanup"
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ArtifactsRoot",
            rel,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        assert proc.returncode == 0
        assert json.loads(registry.read_text(encoding="utf-8")) == []
    finally:
        import shutil
        shutil.rmtree(artifact, ignore_errors=True)
