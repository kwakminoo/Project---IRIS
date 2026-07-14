from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from iris.infrastructure.mobile.android_emulator_manager import AndroidEmulatorManager
from iris.infrastructure.mobile.android_sdk_installer import AndroidSdkInstallerProtocol
from iris.infrastructure.mobile.android_sdk_locator import AndroidSdkLocator


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _mock_sdk(root: Path) -> Path:
    _touch(root / "cmdline-tools" / "latest" / "bin" / "sdkmanager.bat")
    _touch(root / "cmdline-tools" / "latest" / "bin" / "avdmanager.bat")
    _touch(root / "platform-tools" / "adb.exe")
    _touch(root / "emulator" / "emulator.exe")
    return root


def test_android_sdk_locator_detects_mock_sdk(tmp_path: Path) -> None:
    root = _mock_sdk(tmp_path / "Sdk")
    status = AndroidSdkLocator([root]).locate()
    assert status.is_ready
    assert status.sdk_root == root
    assert status.adb_path == root / "platform-tools" / "adb.exe"
    assert status.emulator_path == root / "emulator" / "emulator.exe"


def test_android_sdk_locator_reports_missing_components(tmp_path: Path) -> None:
    root = tmp_path / "Sdk"
    root.mkdir()
    _touch(root / "platform-tools" / "adb.exe")
    status = AndroidSdkLocator([root]).locate()
    assert not status.is_ready
    assert "platform-tools / adb" not in status.missing_components
    assert "emulator" in status.missing_components
    assert "Android SDK Command-line Tools / sdkmanager" in status.missing_components


def test_installer_preview_contains_required_packages(tmp_path: Path) -> None:
    status = AndroidSdkLocator([_mock_sdk(tmp_path / "Sdk")]).locate()
    preview = AndroidSdkInstallerProtocol().build_preview(status)
    joined = " ".join(preview.install_command)
    assert "platform-tools" in joined
    assert "emulator" in joined
    assert "platforms;android-35" in joined
    assert "system-images;android-35;google_apis_playstore;x86_64" in joined
    assert "IRIS_Mobile_Play" in preview.create_avd_command


def test_emulator_manager_builds_avd_create_command(tmp_path: Path) -> None:
    status = AndroidSdkLocator([_mock_sdk(tmp_path / "Sdk")]).locate()
    command = AndroidEmulatorManager().create_avd_command(status)
    assert command[1:4] == ["create", "avd", "-n"]
    assert "IRIS_Mobile_Play" in command
    assert "pixel_7" in command


def test_emulator_manager_starts_existing_avd_with_mock_runner(tmp_path: Path) -> None:
    root = _mock_sdk(tmp_path / "Sdk")
    locator = AndroidSdkLocator([root])
    calls: list[list[str]] = []
    launched: list[list[str]] = []

    def runner(command: list[str], timeout_sec: int) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        text = " ".join(command)
        if "-list-avds" in text:
            return subprocess.CompletedProcess(command, 0, stdout="IRIS_Mobile_Play\n", stderr="")
        if "devices -l" in text:
            stdout = "List of devices attached\nemulator-5554 device product:sdk model:Pixel_7\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        if "wait-for-device" in text:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "sys.boot_completed" in text:
            return subprocess.CompletedProcess(command, 0, stdout="1\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    manager = AndroidEmulatorManager(
        locator,
        runner=runner,
        popen_factory=lambda command: launched.append(command),
    )
    result = manager.start_or_focus_default_avd(boot_timeout_sec=1)
    assert result.status == "running"
    assert result.ready
    assert result.serial == "emulator-5554"
    assert launched == []


def test_emulator_manager_creates_missing_avd_before_launch(tmp_path: Path) -> None:
    root = _mock_sdk(tmp_path / "Sdk")
    locator = AndroidSdkLocator([root])
    launched: list[list[str]] = []
    devices_calls = 0
    create_calls: list[list[str]] = []

    def runner(command: list[str], timeout_sec: int) -> subprocess.CompletedProcess[str]:
        nonlocal devices_calls
        text = " ".join(command)
        if "-list-avds" in text:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "create avd" in text:
            create_calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "devices -l" in text:
            devices_calls += 1
            stdout = "List of devices attached\n"
            if launched and devices_calls > 1:
                stdout += "emulator-5554 device product:sdk model:Pixel_7\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        if "wait-for-device" in text:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "sys.boot_completed" in text:
            return subprocess.CompletedProcess(command, 0, stdout="1\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    manager = AndroidEmulatorManager(
        locator,
        runner=runner,
        popen_factory=lambda command: launched.append(command),
    )
    result = manager.start_or_focus_default_avd(boot_timeout_sec=1)
    assert result.status == "ready"
    assert create_calls
    assert "--force" in create_calls[0]
    assert launched == [[str(root / "emulator" / "emulator.exe"), "-avd", "IRIS_Mobile_Play"]]


def test_emulator_manager_falls_back_to_existing_avd(tmp_path: Path) -> None:
    root = _mock_sdk(tmp_path / "Sdk")
    locator = AndroidSdkLocator([root])
    launched: list[list[str]] = []

    def runner(command: list[str], timeout_sec: int) -> subprocess.CompletedProcess[str]:
        text = " ".join(command)
        if "-list-avds" in text:
            return subprocess.CompletedProcess(command, 0, stdout="Medium_Phone_API_36.1\nPixel_9a\n", stderr="")
        if "devices -l" in text:
            stdout = "List of devices attached\n"
            if launched:
                stdout += "emulator-5554 device product:sdk model:Pixel_7\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        if "wait-for-device" in text:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "sys.boot_completed" in text:
            return subprocess.CompletedProcess(command, 0, stdout="1\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    manager = AndroidEmulatorManager(
        locator,
        runner=runner,
        popen_factory=lambda command: launched.append(command),
    )
    result = manager.start_or_focus_default_avd(boot_timeout_sec=1)
    assert result.status == "ready"
    assert launched == [[str(root / "emulator" / "emulator.exe"), "-avd", "Medium_Phone_API_36.1"]]


pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from iris.ui.system_metrics_panel import (  # noqa: E402
    _METRIC_LABEL_BAR_GAP_PX,
    _METRIC_ROW_GAP_PX,
    SystemMetricsPanel,
    _MetricRow,
)
from iris.ui.theme_tokens import TOKENS  # noqa: E402
from iris.ui.workspace_action_panel import WorkspaceActionPanel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_system_metrics_spacing_is_three_pixels(qapp) -> None:
    panel = SystemMetricsPanel()
    row = _MetricRow("CPU", TOKENS.metric_fill_cpu)
    inner = panel.findChild(QWidget, "SystemMetricsPanelInner")
    assert inner is not None
    assert inner.layout().spacing() == _METRIC_ROW_GAP_PX
    assert row.layout().spacing() == _METRIC_LABEL_BAR_GAP_PX
    assert row.layout().contentsMargins().bottom() == _METRIC_ROW_GAP_PX


def test_workspace_action_panel_accepts_mobile_action(qapp) -> None:
    hits: list[str] = []
    panel = WorkspaceActionPanel()
    panel.add_icon_action(
        action_id="mobile",
        icon_kind="mobile",
        tooltip="Android 에뮬레이터 실행",
        callback=lambda: hits.append("mobile"),
    )
    assert "mobile" in panel._buttons  # noqa: SLF001
    assert panel._buttons["mobile"].toolTip() == "Android 에뮬레이터 실행"  # noqa: SLF001
    panel._buttons["mobile"].click()  # noqa: SLF001
    assert hits == ["mobile"]


def test_mobile_runtime_worker_finished_clears_alive_check(qapp) -> None:
    """deleteLater 후에도 isRunning 조회가 RuntimeError로 앱을 죽이지 않아야 한다."""
    from PyQt6 import sip
    from PyQt6.QtCore import QTimer

    from iris.infrastructure.mobile.mobile_runtime_worker import MobileRuntimeWorker

    holder: dict[str, MobileRuntimeWorker | None] = {}

    def is_running() -> bool:
        worker = holder.get("w")
        if worker is None:
            return False
        try:
            if sip.isdeleted(worker):
                holder["w"] = None
                return False
            return bool(worker.isRunning())
        except RuntimeError:
            holder["w"] = None
            return False

    w = MobileRuntimeWorker(install_if_missing=False)
    holder["w"] = w

    def after_delete() -> None:
        assert is_running() is False
        assert holder["w"] is None
        assert is_running() is False
        qapp.quit()

    w.deleteLater()
    QTimer.singleShot(0, after_delete)
    QTimer.singleShot(2000, qapp.quit)
    qapp.exec()
    assert holder["w"] is None
