"""IDE 시작 전 사전 점검 — WebEngine·Node·Theia 빌드 산출물."""

from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from iris.infrastructure.ide.ide_backend_manager import (
    IdeBackendManager,
    _find_frontend_entry,
    _find_node,
)

logger = logging.getLogger(__name__)

_WEBENGINE_IMPORT_ERROR: str | None = None
_WEBENGINE_AVAILABLE = False

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

    _WEBENGINE_AVAILABLE = True
except (ImportError, OSError) as exc:
    _WEBENGINE_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


def webengine_import_error() -> str | None:
    return _WEBENGINE_IMPORT_ERROR


def webengine_available() -> bool:
    return _WEBENGINE_AVAILABLE


def _pkg_version(dist_name: str) -> str:
    try:
        from importlib.metadata import version

        return version(dist_name)
    except Exception:
        return "unknown"


@dataclass
class IdePreflightReport:
    webengine_available: bool
    webengine_error: str
    python_executable: str
    pyqt_version: str
    webengine_version: str
    node_executable: str
    node_version: str
    backend_entry: str
    frontend_entry: str
    workspace_path: str
    ready: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_ide_preflight(
    workspace: Path,
    *,
    log_path: Path | None = None,
) -> IdePreflightReport:
    """IDE 버튼 클릭 전 구조화된 사전 점검."""
    errors: list[str] = []
    warnings: list[str] = []

    py_exe = sys.executable
    pyqt_ver = _pkg_version("PyQt6")
    we_ver = _pkg_version("PyQt6-WebEngine") if _WEBENGINE_AVAILABLE else "not installed"
    we_err = _WEBENGINE_IMPORT_ERROR or ""

    if not _WEBENGINE_AVAILABLE:
        errors.append(
            f"PyQt6-WebEngine import 실패: {we_err or 'unknown'}\n"
            f"Python: {py_exe}\n"
            f"복구: iris\\.venv\\Scripts\\python.exe -m pip install PyQt6-WebEngine==6.11.0"
        )

    node = _find_node() or ""
    node_ver = ""
    if not node:
        errors.append("Node.js를 찾을 수 없습니다. scripts\\setup-iris-ide.ps1 실행 후 재시도하세요.")
    else:
        try:
            import subprocess

            out = subprocess.run(
                [node, "-v"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
            )
            node_ver = (out.stdout or out.stderr or "").strip()
        except Exception as exc:
            warnings.append(f"Node 버전 확인 실패: {exc}")

    mgr = IdeBackendManager()
    backend = mgr._find_backend_entry()
    frontend = _find_frontend_entry()
    backend_s = str(backend) if backend else ""
    frontend_s = str(frontend) if frontend else ""

    if backend is None:
        errors.append(
            "Theia backend entry(main.js) 없음.\n"
            "빌드: scripts\\build-iris-ide.ps1"
        )
    if frontend is None:
        errors.append(
            "Theia frontend entry(index.html) 없음.\n"
            "빌드: scripts\\build-iris-ide.ps1"
        )

    ws = workspace.resolve()
    if not ws.is_dir():
        errors.append(f"Workspace 경로가 유효하지 않습니다: {ws}")

    ready = not errors
    report = IdePreflightReport(
        webengine_available=_WEBENGINE_AVAILABLE,
        webengine_error=we_err,
        python_executable=py_exe,
        pyqt_version=pyqt_ver,
        webengine_version=we_ver,
        node_executable=node,
        node_version=node_ver,
        backend_entry=backend_s,
        frontend_entry=frontend_s,
        workspace_path=str(ws),
        ready=ready,
        errors=errors,
        warnings=warnings,
    )

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "=== Iris IDE Preflight ===",
            f"python: {report.python_executable}",
            f"PyQt6: {report.pyqt_version}",
            f"PyQt6-WebEngine: {report.webengine_version}",
            f"webengine_ok: {report.webengine_available}",
            f"webengine_error: {report.webengine_error}",
            f"node: {report.node_executable} ({report.node_version})",
            f"backend: {report.backend_entry}",
            f"frontend: {report.frontend_entry}",
            f"workspace: {report.workspace_path}",
            f"ready: {report.ready}",
        ]
        for e in report.errors:
            lines.append(f"ERROR: {e}")
        for w in report.warnings:
            lines.append(f"WARN: {w}")
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return report


def format_preflight_error(report: IdePreflightReport) -> str:
    """오류 UI용 요약."""
    parts: list[str] = []
    if not report.webengine_available:
        parts.append("WebEngine 의존성 실패")
        parts.append(report.webengine_error or "PyQt6-WebEngine을 import할 수 없습니다.")
        parts.append(f"Python: {report.python_executable}")
        parts.append(f"PyQt6: {report.pyqt_version}")
        parts.append(f"PyQt6-WebEngine: {report.webengine_version}")
    for err in report.errors:
        if "WebEngine" not in err:
            parts.append(err)
    parts.append("\n진단: scripts\\diagnose-iris-ide.ps1")
    return "\n".join(parts)
