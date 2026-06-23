"""Qt worker for Android mobile runtime operations."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.mobile.android_emulator_manager import AndroidEmulatorManager, EmulatorResult
from iris.infrastructure.mobile.android_sdk_installer import AndroidSdkInstallerProtocol
from iris.infrastructure.mobile.android_sdk_locator import AndroidSdkLocator


class MobileRuntimeWorker(QThread):
    finished_result = pyqtSignal(object)

    def __init__(self, *, install_if_missing: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._install_if_missing = install_if_missing

    def run(self) -> None:
        locator = AndroidSdkLocator()
        status = locator.locate()
        if not status.is_ready:
            preview = AndroidSdkInstallerProtocol().build_preview(status)
            if self._install_if_missing and status.sdkmanager_path is not None:
                install = AndroidSdkInstallerProtocol().run_approved_install(preview)
                if install.returncode != 0:
                    self.finished_result.emit(
                        {
                            "status": "failed",
                            "missing": status.missing_components,
                            "preview": AndroidSdkInstallerProtocol.powershell_preview(preview),
                            "error": (install.stderr or install.stdout or "sdkmanager install failed")[:2000],
                        }
                    )
                    return
                status = locator.locate()
                if status.is_ready:
                    result = AndroidEmulatorManager(locator).start_or_focus_default_avd()
                    self.finished_result.emit(result)
                    return
            self.finished_result.emit(
                {
                    "status": "sdk_missing",
                    "missing": status.missing_components,
                    "preview": AndroidSdkInstallerProtocol.powershell_preview(preview),
                }
            )
            return
        result: EmulatorResult = AndroidEmulatorManager(locator).start_or_focus_default_avd()
        self.finished_result.emit(result)
