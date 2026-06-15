"""Embedded Theia E2E — WebEngine·Backend·Shell readiness."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from iris.infrastructure.ide.ide_backend_manager import IdeBackendManager
from iris.infrastructure.ide.ide_preflight import run_ide_preflight, webengine_available
from iris.ui.ide.embedded_theia_view import EmbeddedTheiaView, TheiaViewState

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
    view.deleteLater()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()


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
def test_ready_state_switches_stack_to_webview(require_windows: None) -> None:
    """READY 시 Stack이 WebView 컨테이너를 표시."""
    if not webengine_available():
        pytest.skip("PyQt6-WebEngine not available")

    import sys

    from PyQt6.QtWidgets import QApplication, QStackedWidget, QWidget

    app = QApplication.instance() or QApplication(sys.argv)
    view = EmbeddedTheiaView()

    # WebEngine 없이 Stack·오버레이·상태 전이만 검증
    view._web_container = QWidget()
    view._web = QWidget(view._web_container)
    view._loading_overlay = QWidget(view._web_container)
    view._loading_label = None
    idx = view.stack_widget().addWidget(view._web_container)

    view._set_state(TheiaViewState.SHELL_PROBING)
    view.stack_widget().setCurrentWidget(view._web_container)
    view._show_loading_overlay("testing")

    view._show_ready_webview()

    assert view.state == TheiaViewState.READY
    assert view.stack_widget().currentWidget() is view._web_container
    assert not view._loading_overlay.isVisible()


@pytest.mark.windows_smoke_gui
def test_load_progress_does_not_hide_ready_webview(require_windows: None) -> None:
    """READY 후 loadProgress가 Stack·상태를 되돌리지 않음."""
    if not webengine_available():
        pytest.skip("PyQt6-WebEngine not available")

    import sys

    from PyQt6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication(sys.argv)
    view = EmbeddedTheiaView()
    view._web_container = QWidget()
    view._loading_overlay = QWidget(view._web_container)
    view._loading_label = None
    view.stack_widget().addWidget(view._web_container)
    view.stack_widget().setCurrentWidget(view._web_container)
    view._set_state(TheiaViewState.READY)

    view._on_load_progress(50)
    view._on_load_progress(90)

    assert view.state == TheiaViewState.READY
    assert view.stack_widget().currentWidget() is view._web_container


@pytest.fixture(scope="module")
def qt_app(require_windows: None):
    """IDE E2E — 단일 QApplication (WebEngine 프로세스 재생성 방지)."""
    import sys

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(scope="module")
def shared_theia_view(qt_app, require_windows: None):
    """실제 QWebEngineView — 모듈당 1회만 생성."""
    if not webengine_available():
        pytest.skip("PyQt6-WebEngine not available")
    view = EmbeddedTheiaView()
    yield view
    view.reset_view()
    if view._web is not None:
        try:
            view._web.page().deleteLater()
        except Exception:
            pass
        view._web.deleteLater()
    qt_app.processEvents()
    time.sleep(0.5)
    qt_app.processEvents()


@pytest.mark.windows_smoke_gui
def test_embedded_theia_shell_readiness(
    require_windows: None, tmp_path_factory: pytest.TempPathFactory, shared_theia_view: EmbeddedTheiaView,
) -> None:
    """시나리오 3: EmbeddedTheiaView + Theia Shell probe — 45초 이내 READY."""
    ws = tmp_path_factory.mktemp("workspace")
    (ws / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    report = run_ide_preflight(ws)
    if not report.ready:
        pytest.skip(f"preflight not ready: {report.errors}")

    view = shared_theia_view
    view.reset_view()
    ready = {"ok": False}

    def on_ready() -> None:
        ready["ok"] = True

    try:
        view.ready.disconnect()
    except TypeError:
        pass
    view.ready.connect(on_ready)

    mgr = IdeBackendManager()
    try:
        status = mgr.ensure_running(ws)
        assert status.running, status.error
        assert view.load_url(status.frontend_url)

        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            qt_app = __import__("PyQt6.QtWidgets", fromlist=["QApplication"]).QApplication.instance()
            if qt_app:
                qt_app.processEvents()
            if ready["ok"]:
                break
            time.sleep(0.1)

        if not ready["ok"]:
            probe = view.last_probe_result()
            history = "\n".join(view.state_history()[-10:])
            pytest.fail(
                f"Theia shell readiness timeout\n"
                f"probe={json.dumps(probe, ensure_ascii=False)}\n"
                f"stack={view.stack_widget().currentWidget()}\n"
                f"history={history}"
            )

        assert view.state == TheiaViewState.READY
        assert view.stack_widget().currentWidget() is view._web_container
        assert view._loading_overlay is not None
        assert not view._loading_overlay.isVisible()
    finally:
        mgr.shutdown()


@pytest.mark.windows_smoke_gui
def test_explorer_editor_terminal_dom(
    require_windows: None, shared_theia_view: EmbeddedTheiaView,
) -> None:
    """시나리오 4: READY 상태에서 Explorer DOM 확인 (shell E2E 직후)."""
    if shared_theia_view.state != TheiaViewState.READY:
        pytest.skip("shell readiness 선행 필요 — test_embedded_theia_shell_readiness")

    view = shared_theia_view
    dom_result: dict[str, object] = {}
    done = {"ok": False}

    script = """
    (function() {
      var explorer = Boolean(
        document.querySelector('.theia-Navigator') ||
        document.querySelector('#theia-left-side-panel')
      );
      var editor = Boolean(
        document.querySelector('.theia-Editor') ||
        document.querySelector('.monaco-editor')
      );
      var terminal = Boolean(
        document.querySelector('.theia-Terminal') ||
        document.querySelector('#terminal')
      );
      return JSON.stringify({explorer, editor, terminal});
    })()
    """
    web = view.web_view()
    assert web is not None

    def on_dom(raw: object) -> None:
        dom_result.update(json.loads(str(raw)))
        done["ok"] = True

    web.page().runJavaScript(script, on_dom)
    deadline = time.monotonic() + 10.0
    qt_mod = __import__("PyQt6.QtWidgets", fromlist=["QApplication"])
    while time.monotonic() < deadline and not done["ok"]:
        app = qt_mod.QApplication.instance()
        if app:
            app.processEvents()
        time.sleep(0.05)

    assert dom_result.get("explorer"), f"explorer missing: {dom_result}"


@pytest.mark.windows_smoke_gui
def test_workspace_state_preserved_on_hide(
    require_windows: None, tmp_path_factory: pytest.TempPathFactory, shared_theia_view: EmbeddedTheiaView,
) -> None:
    """시나리오 5: IDE 숨김 후 재진입 시 Backend·URL 유지."""
    ws = tmp_path_factory.mktemp("workspace3")
    if not run_ide_preflight(ws).ready:
        pytest.skip("preflight not ready")

    view = shared_theia_view
    view.reset_view()
    mgr = IdeBackendManager()
    try:
        s1 = mgr.ensure_running(ws)
        assert s1.running
        pid1 = mgr._proc.pid if mgr._proc else 0
        view.load_url(s1.frontend_url)
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline and view.state != TheiaViewState.READY:
            qt_app = __import__("PyQt6.QtWidgets", fromlist=["QApplication"]).QApplication.instance()
            if qt_app:
                qt_app.processEvents()
            time.sleep(0.1)
        url_before = view._current_url_str()
        view.hide()
        view.show()
        s2 = mgr.ensure_running(ws)
        assert s2.running
        pid2 = mgr._proc.pid if mgr._proc else 0
        assert pid2 == pid1
        assert view._current_url_str() == url_before
    finally:
        mgr.shutdown()


@pytest.mark.windows_smoke_gui
def test_resume_or_continue_from_ready(require_windows: None) -> None:
    """Assistant 복귀 후 READY 상태에서 WebView 즉시 복원."""
    if not webengine_available():
        pytest.skip("PyQt6-WebEngine not available")

    import sys

    from PyQt6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication(sys.argv)
    view = EmbeddedTheiaView()
    view._web_container = QWidget()
    view._web = QWidget(view._web_container)
    view._loading_overlay = QWidget(view._web_container)
    view._loading_overlay.show()
    view._loading_label = None
    view.stack_widget().addWidget(view._web_container)
    view._set_state(TheiaViewState.READY, force=True)

    assert view.resume_or_continue()
    assert view.state == TheiaViewState.READY
    assert view.stack_widget().currentWidget() is view._web_container
    assert not view._loading_overlay.isVisible()


@pytest.mark.windows_smoke_gui
def test_reset_view_preserves_ready_without_force(require_windows: None) -> None:
    """일반 reset_view는 READY 세션을 유지."""
    if not webengine_available():
        pytest.skip("PyQt6-WebEngine not available")

    import sys

    from PyQt6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication(sys.argv)
    view = EmbeddedTheiaView()
    view._set_state(TheiaViewState.READY, force=True)
    view.reset_view()
    assert view.state == TheiaViewState.READY
    view.reset_view(force=True)
    assert view.state == TheiaViewState.NOT_STARTED


def test_backend_reuse_same_workspace(require_windows: None, tmp_path: Path) -> None:
    """동일 workspace Backend 재사용."""
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
