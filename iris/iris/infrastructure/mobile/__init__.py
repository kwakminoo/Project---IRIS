"""Android mobile runtime support for Iris."""

from iris.infrastructure.mobile.android_emulator_manager import (
    AndroidEmulatorManager,
    EmulatorResult,
)
from iris.infrastructure.mobile.android_sdk_installer import AndroidSdkInstallerProtocol
from iris.infrastructure.mobile.android_sdk_locator import AndroidSdkLocator, AndroidSdkStatus

__all__ = [
    "AndroidEmulatorManager",
    "AndroidSdkInstallerProtocol",
    "AndroidSdkLocator",
    "AndroidSdkStatus",
    "EmulatorResult",
]
