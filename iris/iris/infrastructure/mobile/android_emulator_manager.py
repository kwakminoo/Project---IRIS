"""Android Emulator manager for the Iris mobile runtime."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Callable

from iris.infrastructure.mobile.android_sdk_installer import DEFAULT_AVD_NAME, DEFAULT_SYSTEM_IMAGE
from iris.infrastructure.mobile.android_sdk_locator import AndroidSdkLocator, AndroidSdkStatus

Runner = Callable[[list[str], int], subprocess.CompletedProcess[str]]
PopenFactory = Callable[[list[str]], subprocess.Popen[str]]


@dataclass(frozen=True)
class EmulatorResult:
    status: str
    ready: bool = False
    serial: str = ""
    error_message: str = ""
    missing_components: tuple[str, ...] = ()
    command_preview: tuple[str, ...] = ()


class AndroidEmulatorManager:
    def __init__(
        self,
        locator: AndroidSdkLocator | None = None,
        *,
        runner: Runner | None = None,
        popen_factory: PopenFactory | None = None,
        avd_name: str = DEFAULT_AVD_NAME,
    ) -> None:
        self._locator = locator or AndroidSdkLocator()
        self._runner = runner or self._run
        self._popen = popen_factory or (lambda cmd: subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True))
        self._avd_name = avd_name

    def create_avd_command(self, status: AndroidSdkStatus) -> list[str]:
        avdmanager = str(status.avdmanager_path) if status.avdmanager_path else "avdmanager"
        return [
            avdmanager,
            "create",
            "avd",
            "-n",
            self._avd_name,
            "-k",
            DEFAULT_SYSTEM_IMAGE,
            "-d",
            "pixel_7",
            "--force",
        ]

    def start_or_focus_default_avd(self, boot_timeout_sec: int = 180) -> EmulatorResult:
        status = self._locator.locate()
        if not status.is_ready:
            return EmulatorResult("sdk_missing", missing_components=status.missing_components)
        assert status.adb_path and status.emulator_path
        running = self._running_emulator_serial(status)
        if running:
            return EmulatorResult("running", ready=True, serial=running)
        avds = self._list_avds(status)
        if self._avd_name not in avds:
            create_command = self.create_avd_command(status)
            create = self._runner(create_command, 300)
            if create.returncode != 0:
                return EmulatorResult(
                    "avd_missing",
                    command_preview=tuple(create_command),
                    error_message=(create.stderr or create.stdout or f"AVD {self._avd_name} create failed")[:1000],
                )
        self._popen([str(status.emulator_path), "-avd", self._avd_name])
        wait = self._runner([str(status.adb_path), "wait-for-device"], boot_timeout_sec)
        if wait.returncode != 0:
            return EmulatorResult("failed", error_message=(wait.stderr or wait.stdout or "adb wait-for-device failed")[:1000])
        serial = self._running_emulator_serial(status)
        if not serial:
            return EmulatorResult("booting", error_message="emulator process started, adb serial not visible yet")
        if not self._wait_for_boot(status, serial, boot_timeout_sec):
            return EmulatorResult("booting", serial=serial, error_message="sys.boot_completed timed out")
        return EmulatorResult("ready", ready=True, serial=serial)

    def _list_avds(self, status: AndroidSdkStatus) -> list[str]:
        assert status.emulator_path
        result = self._runner([str(status.emulator_path), "-list-avds"], 30)
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _running_emulator_serial(self, status: AndroidSdkStatus) -> str:
        assert status.adb_path
        result = self._runner([str(status.adb_path), "devices", "-l"], 30)
        if result.returncode != 0:
            return ""
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0].startswith("emulator-") and "device" in parts:
                return parts[0]
        return ""

    def _wait_for_boot(self, status: AndroidSdkStatus, serial: str, timeout_sec: int) -> bool:
        assert status.adb_path
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            result = self._runner(
                [str(status.adb_path), "-s", serial, "shell", "getprop", "sys.boot_completed"],
                15,
            )
            if result.returncode == 0 and result.stdout.strip() == "1":
                return True
            time.sleep(2)
        return False

    @staticmethod
    def _run(command: list[str], timeout_sec: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
