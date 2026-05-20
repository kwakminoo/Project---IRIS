"""설치 완료 debounce 휴리스틱 (플랫폼 독립)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from iris.config.app_install_watcher import process_pending_install


def test_process_pending_install_stable(tmp_path: Path) -> None:
    exe = tmp_path / "NewApp.exe"
    exe.write_bytes(b"MZ" + b"\0" * 100)
    result = process_pending_install(str(exe), "NewApp")
    assert result is not None
    assert result.app_key == "newapp"
    assert result.source == "install_watch"


@pytest.mark.skipif(os.name != "nt", reason="Windows QFileSystemWatcher 통합")
def test_install_watcher_import() -> None:
    from iris.config.app_install_watcher import AppInstallWatcher

    w = AppInstallWatcher()
    assert w is not None
