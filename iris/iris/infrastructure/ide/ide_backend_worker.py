"""Theia Backend 시작 Worker — UI 스레드 블로킹 방지."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from iris.infrastructure.ide.ide_backend_manager import BackendStatus, IdeBackendManager
from iris.infrastructure.ide.ide_preflight import IdePreflightReport, run_ide_preflight


class IdeBackendWorker(QObject):
    """백그라운드에서 preflight + backend ensure_running."""

    preflight_done = pyqtSignal(object)  # IdePreflightReport
    backend_starting = pyqtSignal()
    backend_log = pyqtSignal(str)
    backend_ready = pyqtSignal(object)  # BackendStatus
    backend_failed = pyqtSignal(object)  # BackendStatus

    def __init__(self, manager: IdeBackendManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._workspace: Path | None = None

    def start_backend(self, workspace: Path) -> None:
        self._workspace = workspace
        log_dir = Path.home() / ".iris" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        preflight_log = log_dir / "ide-preflight.log"
        report = run_ide_preflight(workspace, log_path=preflight_log)
        self.preflight_done.emit(report)
        if not report.ready:
            self.backend_failed.emit(
                BackendStatus(False, error="; ".join(report.errors), log_path=str(preflight_log))
            )
            return

        self.backend_starting.emit()
        self.backend_log.emit(f"Workspace: {workspace}")
        status = self._manager.ensure_running(workspace)
        if status.running:
            self.backend_ready.emit(status)
        else:
            self.backend_failed.emit(status)
