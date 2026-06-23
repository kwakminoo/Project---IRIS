"""Locate the Android SDK command-line runtime on Windows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AndroidSdkStatus:
    sdk_root: Path | None
    sdkmanager_path: Path | None
    avdmanager_path: Path | None
    adb_path: Path | None
    emulator_path: Path | None
    missing_components: tuple[str, ...]

    @property
    def is_ready(self) -> bool:
        return not self.missing_components


class AndroidSdkLocator:
    def __init__(self, search_roots: list[Path] | None = None) -> None:
        self._search_roots = search_roots

    def locate(self) -> AndroidSdkStatus:
        roots = self._search_roots or self._candidate_roots()
        best = roots[0] if roots else None
        for root in roots:
            status = self._status_for(root)
            if status.is_ready:
                return status
            if status.sdk_root is not None:
                best = root
        return self._status_for(best) if best is not None else self._missing(None)

    def _candidate_roots(self) -> list[Path]:
        roots: list[Path] = []
        for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            raw = os.getenv(key, "").strip()
            if raw:
                roots.append(Path(raw).expanduser())
        local = os.getenv("LOCALAPPDATA", "").strip()
        if local:
            roots.append(Path(local) / "Android" / "Sdk")
        home = Path.home()
        roots.extend([home / "AppData" / "Local" / "Android" / "Sdk", home / "Android" / "Sdk"])
        return list(dict.fromkeys(roots))

    def _status_for(self, root: Path | None) -> AndroidSdkStatus:
        if root is None:
            return self._missing(None)
        sdk_root = root if root.exists() else None
        sdkmanager = self._first_file(root / "cmdline-tools" / "latest" / "bin", "sdkmanager")
        avdmanager = self._first_file(root / "cmdline-tools" / "latest" / "bin", "avdmanager")
        adb = self._first_file(root / "platform-tools", "adb")
        emulator = self._first_file(root / "emulator", "emulator")
        missing = []
        if sdkmanager is None:
            missing.append("Android SDK Command-line Tools / sdkmanager")
        if avdmanager is None:
            missing.append("Android SDK Command-line Tools / avdmanager")
        if adb is None:
            missing.append("platform-tools / adb")
        if emulator is None:
            missing.append("emulator")
        return AndroidSdkStatus(sdk_root, sdkmanager, avdmanager, adb, emulator, tuple(missing))

    @staticmethod
    def _missing(root: Path | None) -> AndroidSdkStatus:
        return AndroidSdkStatus(
            root,
            None,
            None,
            None,
            None,
            (
                "Android SDK Command-line Tools / sdkmanager",
                "Android SDK Command-line Tools / avdmanager",
                "platform-tools / adb",
                "emulator",
            ),
        )

    @staticmethod
    def _first_file(folder: Path, stem: str) -> Path | None:
        for name in (f"{stem}.bat", f"{stem}.exe", stem):
            path = folder / name
            try:
                if path.is_file():
                    return path
            except OSError:
                continue
        return None
