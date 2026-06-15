"""IdeBackendManager 테스트."""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

from iris.infrastructure.ide.ide_backend_manager import IdeBackendManager, _HOST


def test_backend_manager_binds_only_to_localhost() -> None:
    mgr = IdeBackendManager()
    port = mgr._pick_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((_HOST, port))
        assert s.getsockname()[0] in ("127.0.0.1", "0.0.0.0")


def test_backend_manager_selects_available_port() -> None:
    mgr = IdeBackendManager()
    p1 = mgr._pick_port()
    p2 = mgr._pick_port()
    assert 3100 <= p1 <= 3199
    assert 3100 <= p2 <= 3199


def test_backend_manager_does_not_use_shell(tmp_path: Path) -> None:
    mgr = IdeBackendManager()
    with patch.object(mgr, "_find_backend_entry", return_value=None):
        status = mgr.ensure_running(tmp_path)
    assert not status.running
    assert "준비되지 않았습니다" in status.error or status.error


def test_backend_failure_does_not_close_iris(tmp_path: Path) -> None:
    mgr = IdeBackendManager()
    status = mgr.ensure_running(tmp_path)
    assert not status.running
    mgr.shutdown()


def test_backend_manager_reuses_running_process(tmp_path: Path) -> None:
    mgr = IdeBackendManager()
    proc = MagicMock()
    proc.poll.return_value = None
    mgr._proc = proc
    mgr._port = 3105
    mgr._workspace = tmp_path.resolve()
    with patch.object(mgr, "_health_ok", return_value=True):
        status = mgr.ensure_running(tmp_path)
    assert status.running
    assert status.port == 3105
