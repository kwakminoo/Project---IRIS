"""User-approved Android SDK install protocol."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from iris.infrastructure.mobile.android_sdk_locator import AndroidSdkStatus

DEFAULT_ANDROID_API = "android-35"
DEFAULT_SYSTEM_IMAGE = "system-images;android-35;google_apis_playstore;x86_64"
DEFAULT_PACKAGES = (
    "platform-tools",
    "emulator",
    f"platforms;{DEFAULT_ANDROID_API}",
    DEFAULT_SYSTEM_IMAGE,
)
DEFAULT_AVD_NAME = "IRIS_Mobile_Play"

RunResult = subprocess.CompletedProcess[str]
Runner = Callable[[list[str], int], RunResult]


@dataclass(frozen=True)
class InstallPreview:
    missing_components: tuple[str, ...]
    install_command: list[str]
    license_command: list[str]
    create_avd_command: list[str]
    notes: str


class AndroidSdkInstallerProtocol:
    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner or self._run

    def build_preview(self, status: AndroidSdkStatus, avd_name: str = DEFAULT_AVD_NAME) -> InstallPreview:
        sdkmanager = str(status.sdkmanager_path) if status.sdkmanager_path else "sdkmanager"
        avdmanager = str(status.avdmanager_path) if status.avdmanager_path else "avdmanager"
        return InstallPreview(
            missing_components=status.missing_components,
            install_command=[sdkmanager, "--install", *DEFAULT_PACKAGES],
            license_command=[sdkmanager, "--licenses"],
            create_avd_command=[
                avdmanager,
                "create",
                "avd",
                "-n",
                avd_name,
                "-k",
                DEFAULT_SYSTEM_IMAGE,
                "-d",
                "pixel_7",
                "--force",
            ],
            notes=(
                "Android SDK Command-line Tools must be installed first if sdkmanager is missing. "
                "Android SDK licenses require separate user approval."
            ),
        )

    def run_approved_install(self, preview: InstallPreview, timeout_sec: int = 900) -> RunResult:
        return self._runner(preview.install_command, timeout_sec)

    def run_approved_license_acceptance(self, preview: InstallPreview, timeout_sec: int = 600) -> RunResult:
        return self._runner(preview.license_command, timeout_sec)

    @staticmethod
    def powershell_preview(preview: InstallPreview) -> str:
        return "\n".join(_quote_ps(cmd) for cmd in (
            preview.install_command,
            preview.license_command,
            preview.create_avd_command,
        ))

    @staticmethod
    def _run(command: list[str], timeout_sec: int) -> RunResult:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )


def _quote_ps(command: list[str]) -> str:
    def q(part: str) -> str:
        return f'"{part}"' if any(ch in part for ch in " ;&()") or Path(part).suffix else part

    return " ".join(q(part) for part in command)
