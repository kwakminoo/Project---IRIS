"""Embedded Theia E2E — WebEngine·Backend·Shell readiness."""

from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from iris.infrastructure.ide.ide_backend_manager import IdeBackendManager, _find_node
from iris.infrastructure.ide.ide_preflight import run_ide_preflight, webengine_available

pytestmark = [
    pytest.mark.windows_smoke,
    pytest.mark.ide_e2e,
]


def _repo_root() -> Path:
    from iris.infrastructure.ide.ide_workspace_resolver import _find_repo_root

    return _find_repo_root()


def _http_ok(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return int(resp.status), resp.read(65536).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


@pytest.mark.windows_smoke_gui
def test_webengine_local_html(require_windows: None) -> None:
    """시나리오 1: QWebEngineView 로컬 HTML."""
    if not webengine_available():
        pytest.skip("PyQt6-WebEngine not available")

    import sys

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    app = QApplication.instance() or QApplication(sys.argv)
    view = QWebEngineView()
    state = {"load": False, "title": ""}

    def on_load(ok: bool) -> None:
        state["load"] = ok
        if ok:
            view.page().runJavaScript("document.title", lambda t: state.update(title=str(t)))

    view.loadFinished.connect(on_load)
    view.setHtml(
        "<html><head><title>IRIS_WEBENGINE_OK</title></head>"
        "<body><h1>OK</h1></body></html>"
    )
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        app.processEvents()
        if state["load"] and state["title"] == "IRIS_WEBENGINE_OK":
            break
        time.sleep(0.05)
    assert state["load"] is True
    assert state["title"] == "IRIS_WEBENGINE_OK"


def test_theia_backend_health(require_windows: None, tmp_path: Path) -> None:
    """시나리오 2: Backend 시작·HTTP·bundle."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "hello.py").write_text("print('hello')\n", encoding="utf-8")

    report = run_ide_preflight(ws)
    if not report.backend_entry:
        pytest.skip("Theia backend not built")

    mgr = IdeBackendManager()
    try:
        status = mgr.ensure_running(ws)
        assert status.running, status.error
        code, body = _http_ok(status.frontend_url + "/")
        assert 200 <= code < 500, f"HTTP {code}"
        assert "theia" in body.lower() or "preload" in body.lower()
        bcode, _ = _http_ok(status.frontend_url + "/bundle.js")
        assert bcode == 0 or bcode < 500
    finally:
        mgr.shutdown()


@pytest.mark.windows_smoke_gui
def test_embedded_theia_shell_readiness(require_windows: None, tmp_path: Path) -> None:
    """시나리오 3: EmbeddedTheiaView + Theia Shell probe."""
    if not webengine_available():
        pytest.skip("PyQt6-WebEngine not available")

    ws = tmp_path / "workspace"
    ws.mkdir()
    report = run_ide_preflight(ws)
    if not report.ready:
        pytest.skip(f"preflight not ready: {report.errors}")

    import sys

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from iris.ui.ide.embedded_theia_view import EmbeddedTheiaView

    mgr = IdeBackendManager()
    app = QApplication.instance() or QApplication(sys.argv)
    view = EmbeddedTheiaView()
    ready = {"ok": False, "error": ""}

    def on_ready() -> None:
        ready["ok"] = True

    view.ready.connect(on_ready)

    try:
        status = mgr.ensure_running(ws)
        assert status.running, status.error
        assert view.load_url(status.frontend_url)

        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            app.processEvents()
            if ready["ok"]:
                break
            time.sleep(0.1)
        assert ready["ok"], "Theia shell readiness timeout"
    finally:
        mgr.shutdown()


def test_backend_reuse_same_workspace(require_windows: None, tmp_path: Path) -> None:
    """시나리오 5: 동일 workspace Backend 재사용."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    if not run_ide_preflight(ws).backend_entry:
        pytest.skip("no backend")

    mgr = IdeBackendManager()
    try:
        s1 = mgr.ensure_running(ws)
        assert s1.running
        port1 = s1.port
        s2 = mgr.ensure_running(ws)
        assert s2.running
        assert s2.port == port1
    finally:
        mgr.shutdown()
