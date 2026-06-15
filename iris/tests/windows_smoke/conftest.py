"""Windows 스모크 테스트 공통 fixture."""

from __future__ import annotations

import platform
import subprocess
import time
import uuid
from pathlib import Path
from typing import Generator

import pytest

from iris.application.runtime_factory import TaskRuntimeServices, build_task_runtime
from iris.automation.tool_registry import AutomationToolRegistry
from iris.automation.tool_types import AutomationToolContext
from iris.config.app_index import build_merged_app_paths
from iris.storage.database import Database

from .diagnostics import (
    NotepadWindow,
    cleanup_registered_processes,
    close_notepad_without_save,
    find_newest_notepad_window,
    find_notepad_windows_for_pid,
    focus_window_hwnd,
    log_environment,
    register_created_process,
    resolve_notepad_exe,
    terminate_process_tree,
    test_artifact_dir,
    wait_until,
    write_diagnostic_bundle,
)
from .smoke_tools import SmokeRequiresApprovalTool, reset_smoke_execution_count


def _smoke_app_paths(db: Database) -> dict[str, str]:
    """launch_app 스모크 — notepad 경로 보장."""
    paths = build_merged_app_paths(db)
    if "notepad" not in paths:
        np = resolve_notepad_exe()
        if Path(np).is_file() or np == "notepad.exe":
            paths["notepad"] = np
    return paths


@pytest.fixture(scope="session")
def require_windows() -> None:
    """Windows가 아니면 skip."""
    if platform.system() != "Windows":
        pytest.skip("Windows 전용 스모크 테스트")


@pytest.fixture
def smoke_marker() -> str:
    """테스트마다 고유 marker — underscore는 type_text에서 누락될 수 있어 사용하지 않음."""
    return f"IRISSMOKE{uuid.uuid4().hex[:12]}"


@pytest.fixture
def smoke_artifacts_dir(request: pytest.FixtureRequest) -> Path:
    return test_artifact_dir(request.node.name)


@pytest.fixture
def smoke_db(tmp_path: Path) -> Database:
    return Database(tmp_path / "smoke.db")


@pytest.fixture
def smoke_registry(smoke_db: Database) -> AutomationToolRegistry:
    registry = AutomationToolRegistry(smoke_db)
    registry.register_tool(SmokeRequiresApprovalTool())
    return registry


@pytest.fixture
def smoke_runtime(smoke_db: Database, smoke_registry: AutomationToolRegistry) -> TaskRuntimeServices:
    app_paths = _smoke_app_paths(smoke_db)

    def ctx_factory(**kwargs) -> AutomationToolContext:
        return AutomationToolContext(
            params=kwargs.get("params") or {},
            approved=bool(kwargs.get("approved")),
            summary=str(kwargs.get("summary") or ""),
            app_paths=app_paths,
            database=smoke_db,
        )

    return build_task_runtime(smoke_db, smoke_registry, ctx_factory=ctx_factory)


@pytest.fixture
def notepad_session(require_windows: None, smoke_marker: str) -> Generator[NotepadWindow, None, None]:
    """메모장 실행 — 테스트가 시작한 PID만 종료."""
    started = time.monotonic()
    exe = resolve_notepad_exe()
    proc = subprocess.Popen([exe], shell=False)  # noqa: S603
    pid = int(proc.pid)
    register_created_process(pid, marker=smoke_marker, exe=Path(exe).name)
    session: NotepadWindow | None = None

    def _ready() -> bool:
        nonlocal session
        wins = find_notepad_windows_for_pid(pid)
        if wins:
            session = wins[0]
            return True
        fallback = find_newest_notepad_window(after_monotonic=started)
        if fallback:
            session = fallback
            return True
        return False

    if not wait_until(_ready, timeout=20.0, desc="notepad window"):
        terminate_process_tree(pid)
        pytest.fail(f"메모장 창을 찾지 못함 (pid={pid}, exe={exe})")

    assert session is not None
    from iris.automation.window_controller import focus_and_place

    for sub in ("메모장", "Notepad"):
        ok, _ = focus_and_place(sub, 40, 40, 900, 700)
        if ok:
            break
    else:
        focus_window_hwnd(session.hwnd)
    yield session
    close_notepad_without_save(session.hwnd, session.pid)


@pytest.fixture(autouse=True)
def _reset_smoke_tool_counter() -> Generator[None, None, None]:
    reset_smoke_execution_count()
    yield


@pytest.fixture(autouse=True)
def _log_smoke_env(require_windows: None) -> None:
    _ = log_environment()


@pytest.fixture(autouse=True)
def _smoke_process_cleanup(require_windows: None) -> Generator[None, None, None]:
    """실패 시에도 등록된 PID만 정리."""
    yield
    cleanup_registered_processes()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator[None, None, None]:
    """실패 시 진단 artifact 저장."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed and "windows_smoke" in item.keywords:
        extra: dict = {}
        if hasattr(item, "funcargs"):
            if "notepad_session" in item.funcargs:
                np = item.funcargs["notepad_session"]
                extra["notepad"] = {"pid": np.pid, "hwnd": np.hwnd, "title": np.title}
            if "smoke_db" in item.funcargs and "smoke_runtime" in item.funcargs:
                pass
        write_diagnostic_bundle(item.name, failure=str(report.longrepr), **extra)
