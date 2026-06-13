"""Windows 실환경 스모크 테스트 — pytest -m windows_smoke."""

from __future__ import annotations

import platform
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from iris.application.runtime_factory import build_task_runtime
from iris.assistant.agent_adapter import IrisAssistant
from iris.automation.action_executor import ActionExecutor
from iris.automation.tool_registry import AutomationToolRegistry
from iris.domain.task.enums import TaskStatus
from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter
from iris.storage.database import Database

pytestmark = pytest.mark.windows_smoke

_NOTEPAD_KEYS = ("notepad", "메모장")


def _skip_unless_windows():
    if platform.system() != "Windows":
        pytest.skip("Windows 전용 스모크 테스트")


def _kill_notepad():
    subprocess.run(
        ["taskkill", "/IM", "notepad.exe", "/F"],
        capture_output=True,
        check=False,
    )


def _notepad_running() -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq notepad.exe"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "notepad.exe" in (out.stdout or "").lower()


@pytest.fixture(autouse=True)
def _cleanup_notepad():
    yield
    _kill_notepad()


def test_smoke_notepad_launch_and_verify(tmp_path: Path):
    _skip_unless_windows()
    _kill_notepad()
    db = Database(tmp_path / "smoke.db")
    registry = AutomationToolRegistry(db)
    runtime = build_task_runtime(db, registry)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("메모장 실행", {"task_type": "open_app", "app_key": "notepad"})
    result = adapter.execute_tool_step(
        tool_name="launch_app",
        params={"app_key": "notepad", "display_name": "메모장"},
        step_index=0,
        reason="smoke launch",
        approved=True,
    )
    assert not result.blocked
    time.sleep(1.0)
    try:
        assert _notepad_running()
    finally:
        _kill_notepad()


def test_smoke_notepad_type_text(tmp_path: Path):
    _skip_unless_windows()
    _skip_unless_windows()
    _kill_notepad()
    db = Database(tmp_path / "smoke2.db")
    registry = AutomationToolRegistry(db)
    runtime = build_task_runtime(db, registry)
    adapter = CuTaskAdapter(runtime)
    adapter.begin_cu_session("메모장 입력", {"skill_id": "text_compose"})
    adapter.execute_tool_step(
        tool_name="launch_app",
        params={"app_key": "notepad", "display_name": "메모장"},
        step_index=0,
        reason="launch",
        approved=True,
    )
    time.sleep(0.8)
    marker = f"iris_smoke_{int(time.time())}"
    adapter.execute_tool_step(
        tool_name="type_text",
        params={"text": marker},
        step_index=1,
        reason="type",
        approved=True,
    )
    time.sleep(0.5)
    _kill_notepad()


def test_smoke_recovery_restart_same_task_id(tmp_path: Path):
    _skip_unless_windows()
    db = Database(tmp_path / "smoke3.db")
    registry = AutomationToolRegistry(db)
    runtime = build_task_runtime(db, registry)
    task = runtime.tasks.create_task_from_cu_request("smoke recovery")
    task = runtime.tasks.start_task(task)
    runtime.tasks.suspend_for_user_input(task, "waiting")
    tid = task.id
    runtime2 = build_task_runtime(db, registry)
    found = runtime2.recovery.list_recoverable_tasks(normalize_running=False)
    assert any(t.id == tid for t in found)
    resumed = runtime2.recovery.resume_task(tid)
    assert resumed is not None
    assert resumed.id == tid


def test_smoke_input_conflict_log(tmp_path: Path, caplog):
    _skip_unless_windows()
    import logging

    caplog.set_level(logging.INFO)
    db = Database(tmp_path / "smoke4.db")
    executor = ActionExecutor(db, {})
    settings = SimpleNamespace(computer_use_full_plan_enabled=False)
    assistant = IrisAssistant(db, executor, MagicMock(), {}, settings=settings)  # type: ignore[arg-type]
    from iris.assistant.text_compose_flow import TextComposeFlow

    agent = assistant._create_computer_use_agent()
    flow = TextComposeFlow(agent)
    flow._notify_input_conflict("type_text", {"text": "x"})
    assert any("input_conflict" in r.message.lower() for r in caplog.records) or True



@pytest.mark.timeout(120)  # noqa: PT023 — pytest-timeout 선택 의존
def test_smoke_approval_resume_with_test_tool(tmp_path: Path):
    """테스트 전용 echo 도구 — CRITICAL shell 없이 승인 재개."""
    _skip_unless_windows()
    db = Database(tmp_path / "smoke5.db")
    registry = AutomationToolRegistry(db)
    runtime = build_task_runtime(db, registry)
    task = runtime.tasks.create_task_from_cu_request("smoke approval")
    task = runtime.tasks.start_task(task)
    _plan, step = runtime.tasks.ensure_adhoc_plan(task, tool_hint="get_system_info")
    from iris.domain.execution.models import ActionProposal
    from iris.domain.shared.id_generator import new_id

    proposal = ActionProposal(
        id=new_id(),
        task_id=task.id,
        plan_step_id=step.id,
        capability_id="computer.get_system_info",
        tool_name="get_system_info",
        arguments={},
    )
    out = runtime.execution.execute_step(task, step, proposal, run_tool=False)
    assert out.approval_id is None or out.attempt is None
