"""Windows 실환경 스모크 테스트 — pytest -m windows_smoke."""

from __future__ import annotations

from pathlib import Path

import psutil
import pytest

from iris.application.runtime_factory import build_task_runtime
from iris.domain.execution.enums import VerificationStatus
from iris.domain.execution.models import ActionProposal
from iris.domain.shared.id_generator import new_id
from iris.domain.task.enums import StepStatus, TaskStatus
from iris.infrastructure.adapters.cu_task_adapter import CuTaskAdapter

from .diagnostics import (
    NotepadWindow,
    close_notepad_without_save,
    dump_process_state,
    dump_task_history,
    dump_uia_tree,
    find_notepad_windows_for_pid,
    focus_window_hwnd,
    read_notepad_editor_text,
    wait_until,
    write_diagnostic_bundle,
)
from .smoke_tools import smoke_execution_count

pytestmark = [pytest.mark.windows_smoke, pytest.mark.windows_only]


def _notepad_pids() -> set[int]:
    pids: set[int] = set()
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if (proc.info.get("name") or "").lower() == "notepad.exe":
                pids.add(int(proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def _finalize_smoke_task(adapter: CuTaskAdapter) -> None:
    adapter.on_cu_finished(success=True, message="smoke complete")


def _action_result_for_attempt(db, attempt_id: str):
    row = db._execute(
        "SELECT * FROM action_results WHERE attempt_id = ?",
        (attempt_id,),
    ).fetchone()
    return row


def _assert_verification_success(runtime, attempt_id: str) -> None:
    vr = runtime.repos.verifications.get_by_attempt(attempt_id)
    assert vr is not None, "VerificationResult 없음"
    assert vr.status == VerificationStatus.SUCCESS


@pytest.mark.timeout(120)
def test_smoke_notepad_launch_creates_verified_task(
    require_windows,
    smoke_runtime,
    smoke_db,
):
    """Task → launch_app → 프로세스·창·Verification → Step/Task 완료."""
    before_pids = _notepad_pids()
    adapter = CuTaskAdapter(smoke_runtime)
    adapter.begin_cu_session("메모장 실행", {"task_type": "open_app", "app_key": "notepad"})
    task_id = adapter.task_id
    assert task_id

    result = adapter.execute_tool_step(
        tool_name="launch_app",
        params={"app_key": "notepad", "display_name": "메모장"},
        step_index=0,
        reason="smoke launch",
        approved=True,
    )
    assert not result.blocked
    assert result.tool_success is True
    assert result.attempt_id
    assert result.proposal_id

    attempts = smoke_runtime.repos.execution.get_attempts_for_proposal(result.proposal_id)
    assert len(attempts) == 1
    attempt = attempts[0]

    row = _action_result_for_attempt(smoke_db, attempt.id)
    assert row is not None
    assert int(row["tool_success"]) == 1

    def _new_notepad_running() -> bool:
        return len(_notepad_pids() - before_pids) >= 1

    assert wait_until(_new_notepad_running, timeout=10.0), "notepad.exe 프로세스 없음"
    new_pids = _notepad_pids() - before_pids
    target_pid = next(iter(new_pids))

    from iris.automation import window_controller

    def _has_notepad_window() -> bool:
        if find_notepad_windows_for_pid(target_pid):
            return True
        for sub in ("메모장", "Notepad"):
            if window_controller.find_windows_by_title_substring(sub):
                return True
        return False

    assert wait_until(_has_notepad_window, timeout=15.0), "메모장 창 미감지"
    wins = find_notepad_windows_for_pid(target_pid)
    if not wins:
        for sub in ("메모장", "Notepad"):
            for w in window_controller.find_windows_by_title_substring(sub):
                wins = [NotepadWindow(pid=target_pid, hwnd=w.hwnd, title=w.title)]
                break
            if wins:
                break
    assert wins, f"PID {target_pid}에 연결된 창 없음"
    assert any("메모장" in w.title or "Notepad" in w.title for w in wins)

    _assert_verification_success(smoke_runtime, attempt.id)

    plan = smoke_runtime.repos.plans.get_latest_plan_for_task(task_id)
    assert plan is not None
    step = smoke_runtime.repos.plans.get_steps(plan.id)[0]
    assert step.status == StepStatus.SUCCEEDED

    _finalize_smoke_task(adapter)
    task = smoke_runtime.repos.tasks.get_by_id(task_id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED

    write_diagnostic_bundle(
        "test_smoke_notepad_launch_creates_verified_task",
        task_history=dump_task_history(smoke_db, task_id),
        process=dump_process_state(target_pid),
    )

    for w in wins:
        close_notepad_without_save(w.hwnd, target_pid)


@pytest.mark.timeout(120)
def test_smoke_notepad_text_input_is_read_back(
    require_windows,
    notepad_session,
    smoke_runtime,
    smoke_marker,
):
    """Fixture 메모장 → 포커스 → type_text → UIA 재확인."""
    np = notepad_session
    from iris.automation import window_controller
    from iris.automation.window_controller import focus_and_place

    def _notepad_is_active() -> bool:
        t = window_controller.get_active_window_title()
        return "메모장" in t or "Notepad" in t

    if not _notepad_is_active():
        for sub in ("메모장", "Notepad"):
            focus_and_place(sub, 40, 40, 900, 700)
            if wait_until(_notepad_is_active, timeout=3.0):
                break
        if not _notepad_is_active():
            focus_window_hwnd(np.hwnd)
            wait_until(_notepad_is_active, timeout=2.0)

    active_before = window_controller.get_active_window_title()
    assert "메모장" in active_before or "Notepad" in active_before

    adapter = CuTaskAdapter(smoke_runtime)
    adapter.begin_cu_session("메모장 입력", {"skill_id": "text_compose"})
    result = adapter.execute_tool_step(
        tool_name="type_text",
        params={"text": smoke_marker},
        step_index=0,
        reason="smoke type",
        approved=True,
        finalize_if_no_checkpoint=False,
    )
    assert result.tool_success is True
    assert result.attempt_id

    def _text_present() -> bool:
        ok, text = read_notepad_editor_text(np.hwnd)
        return ok and smoke_marker in text

    assert wait_until(_text_present, timeout=8.0), (
        f"UIA에서 marker 미확인: {read_notepad_editor_text(np.hwnd)}"
    )

    ok, actual = read_notepad_editor_text(np.hwnd)
    assert ok
    assert smoke_marker in actual

    write_diagnostic_bundle(
        "test_smoke_notepad_text_input_is_read_back",
        marker=smoke_marker,
        uia_tree=dump_uia_tree(np.hwnd),
        editor_text=actual,
    )


@pytest.mark.timeout(120)
def test_smoke_approval_executes_exact_proposal_once(
    require_windows,
    smoke_runtime,
    smoke_marker,
    tmp_path: Path,
):
    """승인 전 미실행 → 승인 후 동일 Proposal 1회 실행."""
    assert smoke_execution_count() == 0
    adapter = CuTaskAdapter(smoke_runtime)
    task = smoke_runtime.tasks.create_task_from_cu_request("smoke approval")
    task = smoke_runtime.tasks.start_task(task)
    adapter._task = task
    _plan, step = smoke_runtime.tasks.ensure_adhoc_plan(
        task, tool_hint="smoke_requires_approval"
    )
    adapter._adhoc_step = step
    adapter._step_by_index[0] = step

    out_dir = str(tmp_path / "approval")
    params = {"marker": smoke_marker, "output_dir": out_dir}

    out_pending = adapter.on_tool_execute(
        tool_name="smoke_requires_approval",
        params=params,
        step_index=0,
        reason="approval smoke",
        run_tool=False,
    )
    assert out_pending.approval_required
    assert out_pending.proposal_id
    proposal_id = out_pending.proposal_id
    approval_id = out_pending.approval_id
    assert approval_id

    attempts_before = smoke_runtime.repos.execution.get_attempts_for_proposal(proposal_id)
    assert len(attempts_before) == 0
    assert smoke_execution_count() == 0
    assert not (tmp_path / "approval" / f"{smoke_marker}.txt").exists()

    task = smoke_runtime.repos.tasks.get_by_id(task.id)
    assert task is not None
    assert task.status == TaskStatus.WAITING_APPROVAL

    granted = smoke_runtime.approvals.grant(
        approval_id,
        tool_name="smoke_requires_approval",
        arguments=params,
    )
    assert granted is not None

    res = adapter.execute_approved_proposal(
        proposal_id=proposal_id,
        approval_id=approval_id,
        tool_name="smoke_requires_approval",
        params=params,
        step_index=0,
    )
    assert not res.blocked
    assert res.tool_success is True

    attempts_after = smoke_runtime.repos.execution.get_attempts_for_proposal(proposal_id)
    assert len(attempts_after) == 1
    assert smoke_execution_count() == 1
    marker_file = tmp_path / "approval" / f"{smoke_marker}.txt"
    assert marker_file.is_file()
    assert marker_file.read_text(encoding="utf-8") == smoke_marker

    _finalize_smoke_task(adapter)
    task = smoke_runtime.repos.tasks.get_by_id(task.id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.timeout(120)
def test_smoke_runtime_restart_preserves_task_identity(
    require_windows,
    smoke_db,
    smoke_registry,
):
    """Runtime 폐기·재생성 후 Task·Plan·Step·Proposal ID 유지."""
    runtime1 = build_task_runtime(smoke_db, smoke_registry)

    task = runtime1.tasks.create_task_from_cu_request("smoke recovery")
    task = runtime1.tasks.start_task(task)
    tid = task.id
    plan, step = runtime1.tasks.ensure_adhoc_plan(task, tool_hint="get_system_info")
    pid = plan.id
    sid = step.id

    proposal = ActionProposal(
        id=new_id(),
        task_id=tid,
        plan_step_id=sid,
        capability_id="computer.get_system_info",
        tool_name="get_system_info",
        arguments={},
    )
    runtime1.repos.execution.save_proposal(proposal)
    prid = proposal.id

    runtime1.tasks.suspend_for_user_input(task, "waiting")
    del runtime1

    runtime2 = build_task_runtime(smoke_db, smoke_registry)
    found = runtime2.recovery.list_recoverable_tasks(normalize_running=False)
    match = next((t for t in found if t.id == tid), None)
    assert match is not None

    resumed = runtime2.recovery.resume_task(tid)
    assert resumed is not None
    assert resumed.id == tid

    plan2 = runtime2.repos.plans.get_latest_plan_for_task(tid)
    assert plan2 is not None
    assert plan2.id == pid
    steps = runtime2.repos.plans.get_steps(plan2.id)
    assert any(s.id == sid for s in steps)
    saved_proposal = runtime2.repos.execution.get_proposal(prid)
    assert saved_proposal is not None
    assert saved_proposal.id == prid

    rows = smoke_db._execute("PRAGMA foreign_key_check").fetchall()
    assert rows == []

    resumed2 = runtime2.recovery.resume_task(tid)
    assert resumed2 is not None
    assert resumed2.id == tid
