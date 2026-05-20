"""시작 메뉴·App Paths 변화 감지 — 설치 완료 후에만 인덱스 반영 (24h 주기 스캔 없음)."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from iris.config.app_index import (
    AppScanResult,
    resolve_lnk,
    slug_app_key,
    verify_exe_stable,
)


class AppInstallWatcher(QObject):
    """
    QFileSystemWatcher + debounce.
    install_complete(app_key, display_name, exe_path) — exe 안정화 확인 후 emit.
    """

    install_complete = pyqtSignal(str, str, str)

    def __init__(self, parent: QObject | None = None, *, debounce_ms: int = 3000) -> None:
        super().__init__(parent)
        self._debounce_ms = debounce_ms
        self._pending_lnks: set[str] = set()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._on_debounce)
        self._watcher = None
        if os.name == "nt":
            from PyQt6.QtCore import QFileSystemWatcher

            self._watcher = QFileSystemWatcher(self)
            self._watcher.directoryChanged.connect(self._on_dir_changed)
            self._watcher.fileChanged.connect(self._on_file_changed)
            for root in self._watch_roots():
                self._watcher.addPath(str(root))

    @staticmethod
    def _watch_roots() -> list[Path]:
        roots: list[Path] = []
        for env in ("ProgramData", "APPDATA"):
            base = os.environ.get(env, "")
            if not base:
                continue
            sm = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if sm.is_dir():
                roots.append(sm)
        return roots

    def _on_dir_changed(self, _path: str) -> None:
        self._schedule_process()

    def _on_file_changed(self, path: str) -> None:
        if path.lower().endswith(".lnk"):
            self._pending_lnks.add(path)
        self._schedule_process()

    def _schedule_process(self) -> None:
        self._debounce.start(self._debounce_ms)

    def _on_debounce(self) -> None:
        # 새 .lnk 후보 — 안정화 확인 후에만 emit (주기 전체 스캔 없음)
        for lnk_str in list(self._pending_lnks):
            self._try_emit_from_lnk(Path(lnk_str))
        self._pending_lnks.clear()

    def _try_emit_from_lnk(self, lnk: Path) -> None:
        if not lnk.is_file():
            return
        exe = resolve_lnk(lnk)
        # debounce(3s) 후 검사 — UI 스레드에서 sleep 하지 않음
        if not exe or not verify_exe_stable(exe, checks=2, interval_sec=0):
            return
        key = slug_app_key(lnk.stem)
        disp = lnk.stem
        self.install_complete.emit(key, disp, exe)


def process_pending_install(
    exe_path: str,
    display_name: str | None = None,
) -> AppScanResult | None:
    """debounce 후 단독 검증 (단위 테스트·수동 호출)."""
    if not verify_exe_stable(exe_path, checks=2, interval_sec=0):
        return None
    disp = display_name or Path(exe_path).stem
    key = slug_app_key(disp)
    return AppScanResult(key, disp, exe_path, "install_watch")
