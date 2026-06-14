"""Windows 스모크 테스트 진단·대기 헬퍼."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# GitHub Runner에서는 스크린샷 기본 활성화
_SCREENSHOTS_ENABLED = os.environ.get(
    "IRIS_SMOKE_SCREENSHOTS",
    "1" if os.environ.get("GITHUB_ACTIONS") == "true" else "0",
).strip() in ("1", "true", "yes")


def smoke_artifacts_root() -> Path:
    root = Path(os.environ.get("IRIS_SMOKE_ARTIFACTS", "artifacts/windows-smoke"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_artifact_dir(test_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in test_name)
    d = smoke_artifacts_root() / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def wait_until(
    condition: Callable[[], bool],
    *,
    timeout: float = 30.0,
    interval: float = 0.25,
    desc: str = "",
) -> bool:
    """조건 충족까지 폴링 — 고정 sleep 대신 사용."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    _ = desc
    return False


def capture_active_window() -> dict[str, Any]:
    """현재 활성 창 정보."""
    import sys

    out: dict[str, Any] = {"platform": platform.system()}
    if sys.platform != "win32":
        return out
    try:
        from iris.automation import window_controller

        out["title"] = window_controller.get_active_window_title()
    except Exception as exc:
        out["error"] = str(exc)
    try:
        import win32gui  # type: ignore
        import win32process  # type: ignore

        hwnd = int(win32gui.GetForegroundWindow() or 0)
        out["hwnd"] = hwnd
        if hwnd:
            _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            out["pid"] = int(pid)
            out["title_win32"] = win32gui.GetWindowText(hwnd)
    except Exception as exc:
        out.setdefault("errors", []).append(f"win32: {exc}")
    return out


def dump_open_windows() -> list[dict[str, Any]]:
    """열린 창 목록."""
    import sys

    if sys.platform != "win32":
        return []
    try:
        from iris.automation.window_controller import list_visible_windows

        return [
            {
                "title": w.title,
                "hwnd": w.hwnd,
                "left": w.left,
                "top": w.top,
                "width": w.width,
                "height": w.height,
            }
            for w in list_visible_windows()
        ]
    except Exception:
        return []


def dump_process_state(pid: int) -> dict[str, Any]:
    """프로세스 상태."""
    import sys

    info: dict[str, Any] = {"pid": pid, "alive": False}
    if sys.platform != "win32":
        return info
    try:
        import psutil

        proc = psutil.Process(pid)
        info["alive"] = proc.is_running()
        info["name"] = proc.name()
        info["status"] = proc.status()
        info["create_time"] = proc.create_time()
    except Exception as exc:
        info["error"] = str(exc)
    return info


def capture_screenshot(path: Path) -> bool:
    """전체 화면 스크린샷 (설정 또는 GITHUB_ACTIONS에서만)."""
    import sys

    if not _SCREENSHOTS_ENABLED:
        return False
    if sys.platform != "win32":
        return False
    try:
        import mss
        from PIL import Image

        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path)
            return True
    except Exception:
        return False


def dump_uia_tree(hwnd: int, *, max_depth: int = 4) -> str:
    """UIA 트리 요약 JSON."""
    import sys

    if sys.platform != "win32" or hwnd <= 0:
        return "{}"
    try:
        from pywinauto import Desktop  # type: ignore

        win = Desktop(backend="uia").window(handle=hwnd)

        def _walk(elem: Any, depth: int) -> dict[str, Any]:
            if depth > max_depth:
                return {"truncated": True}
            node: dict[str, Any] = {
                "control_type": getattr(elem.element_info, "control_type", ""),
                "name": getattr(elem.element_info, "name", "") or "",
                "automation_id": getattr(elem.element_info, "automation_id", "") or "",
            }
            try:
                children = elem.children()
                if children:
                    node["children"] = [_walk(c, depth + 1) for c in children[:12]]
            except Exception:
                pass
            return node

        return json.dumps(_walk(win, 0), ensure_ascii=False, indent=2)[:8000]
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def dump_task_history(db: Any, task_id: str) -> dict[str, Any]:
    """Task Runtime DB 실행 기록 요약."""
    out: dict[str, Any] = {"task_id": task_id}
    try:
        task = db._execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        out["task_row"] = dict(task) if task else None
        plans = db._execute(
            "SELECT id, task_id, version FROM task_plans WHERE task_id=? ORDER BY version",
            (task_id,),
        ).fetchall()
        out["plans"] = [dict(r) for r in plans]
        attempts = db._execute(
            """
            SELECT aa.id, aa.proposal_id, aa.status, ap.tool_name
            FROM action_attempts aa
            JOIN action_proposals ap ON ap.id = aa.proposal_id
            WHERE ap.task_id=?
            """,
            (task_id,),
        ).fetchall()
        out["attempts"] = [dict(r) for r in attempts]
        vrs = db._execute(
            """
            SELECT vr.id, vr.status, vr.failure_reason, aa.id AS attempt_id
            FROM verification_results vr
            JOIN action_attempts aa ON aa.id = vr.attempt_id
            JOIN action_proposals ap ON ap.id = aa.proposal_id
            WHERE ap.task_id=?
            """,
            (task_id,),
        ).fetchall()
        out["verifications"] = [dict(r) for r in vrs]
    except Exception as exc:
        out["error"] = str(exc)
    return out


def write_diagnostic_bundle(test_name: str, **sections: Any) -> Path:
    """진단 JSON·스크린샷 묶음 저장."""
    d = test_artifact_dir(test_name)
    meta = {
        "test": test_name,
        "timestamp": time.time(),
        "active_window": capture_active_window(),
        "open_windows": dump_open_windows(),
        **sections,
    }
    (d / "diagnostics.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    capture_screenshot(d / "screenshot.png")
    return d


def _pids_in_tree(pid: int) -> set[int]:
    """프로세스 트리 PID (자식 포함)."""
    pids = {int(pid)}
    try:
        import psutil

        proc = psutil.Process(pid)
        for child in proc.children(recursive=True):
            pids.add(int(child.pid))
    except Exception:
        pass
    return pids


@dataclass(frozen=True)
class NotepadWindow:
    pid: int
    hwnd: int
    title: str


def find_notepad_windows_for_pid(pid: int) -> list[NotepadWindow]:
    """특정 PID에 연결된 메모장 창."""
    import sys

    if sys.platform != "win32":
        return []
    results: list[NotepadWindow] = []
    target_pids = _pids_in_tree(pid)
    try:
        import win32gui  # type: ignore
        import win32process  # type: ignore

        def _cb(hwnd: int, _arg: object) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                _tid, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                if int(win_pid) not in target_pids:
                    return True
                title = win32gui.GetWindowText(hwnd) or ""
                if not title.strip():
                    return True
                results.append(NotepadWindow(pid=int(pid), hwnd=int(hwnd), title=title))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return results


def read_notepad_editor_text(hwnd: int) -> tuple[bool, str]:
    """메모장 편집 영역 UIA 텍스트 — Document/Edit 폴백."""
    import sys

    if sys.platform != "win32" or hwnd <= 0:
        return False, ""
    try:
        from pywinauto import Desktop  # type: ignore

        win = Desktop(backend="uia").window(handle=hwnd)
        for ctrl_type in ("Document", "Edit"):
            try:
                ctrl = win.child_window(control_type=ctrl_type)
                if not ctrl.exists(timeout=0.5):
                    continue
                wrapper = ctrl.wrapper_object()
                if hasattr(wrapper, "window_text"):
                    text = wrapper.window_text() or ""
                    if text:
                        return True, text
                if hasattr(wrapper, "iface_value"):
                    val = wrapper.iface_value.CurrentValue  # type: ignore[attr-defined]
                    if val:
                        return True, str(val)
            except Exception:
                continue
        # descendants 폴백
        for desc in win.descendants():
            try:
                ctype = getattr(desc.element_info, "control_type", "")
                if ctype not in ("Document", "Edit"):
                    continue
                w = desc.wrapper_object()
                txt = w.window_text() if hasattr(w, "window_text") else ""
                if txt:
                    return True, txt
            except Exception:
                continue
    except Exception:
        pass
    return False, ""


def find_newest_notepad_window(*, after_monotonic: float) -> NotepadWindow | None:
    """최근 시작된 notepad.exe 창 (PID 트리 매칭 실패 시 폴백)."""
    import psutil

    candidates: list[tuple[float, NotepadWindow]] = []
    for proc in psutil.process_iter(["name", "pid", "create_time"]):
        try:
            if (proc.info.get("name") or "").lower() != "notepad.exe":
                continue
            pid = int(proc.info["pid"])
            wins = find_notepad_windows_for_pid(pid)
            for w in wins:
                candidates.append((float(proc.info.get("create_time") or 0), w))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def resolve_notepad_exe() -> str:
    """메모장 실행 파일 경로."""
    import os

    root = os.environ.get("SystemRoot", r"C:\Windows")
    classic = Path(root) / "System32" / "notepad.exe"
    if classic.is_file():
        return str(classic)
    return "notepad.exe"


def focus_window_hwnd(hwnd: int) -> bool:
    """HWND 포커스 — window_controller + pygetwindow 폴백."""
    import sys

    if sys.platform != "win32" or hwnd <= 0:
        return False
    try:
        from iris.automation.window_controller import focus_window_by_hwnd

        if focus_window_by_hwnd(hwnd):
            return True
    except Exception:
        pass
    try:
        import pygetwindow as gw  # type: ignore

        for w in gw.getAllWindows():
            if int(getattr(w, "_hWnd", 0) or 0) == hwnd:
                w.activate()
                return True
    except Exception:
        pass
    return False


def close_notepad_without_save(hwnd: int, pid: int) -> None:
    """저장 확인 대화상자 — '저장 안 함' 처리 후 프로세스 종료."""
    import sys

    if sys.platform != "win32":
        return
    try:
        import win32con  # type: ignore
        import win32gui  # type: ignore

        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            time.sleep(0.4)
            # Windows 11 저장 대화상자 — Alt+N (저장 안 함)
            try:
                import pyautogui  # type: ignore

                pyautogui.hotkey("alt", "n")
                time.sleep(0.3)
            except Exception:
                pass
    except Exception:
        pass
    terminate_process_tree(pid)


def terminate_process_tree(pid: int) -> None:
    """테스트가 시작한 PID만 종료."""
    if pid <= 0:
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        check=False,
    )


def log_environment() -> dict[str, str]:
    """CI 진단용 환경 정보."""
    import sys

    return {
        "python": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
    }
