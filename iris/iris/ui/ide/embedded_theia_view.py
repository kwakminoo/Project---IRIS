"""QWebEngineView 기반 내장 Theia 뷰."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
  QFrame,
  QHBoxLayout,
  QLabel,
  QPushButton,
  QStackedWidget,
  QVBoxLayout,
  QWidget,
)

from iris.ui.theme_tokens import TOKENS

logger = logging.getLogger(__name__)

_LOG_PATH = Path.home() / ".iris" / "logs" / "ide-webengine.log"

_WEBENGINE_IMPORT_ERROR: str | None = None
_WEBENGINE = False
QWebEngineView = None  # type: ignore[misc, assignment]

try:
  from PyQt6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView

  QWebEngineView = _QWebEngineView
  _WEBENGINE = True
except (ImportError, OSError) as exc:
  _WEBENGINE_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


# Theia 1.55 — 실제 DOM 기반 복수 조건 (iris-ide 빌드·CSS 확인)
_THEIA_READINESS_JS = """
(function() {
  var selectors = [
    '.theia-ApplicationShell',
    '#theia-app-shell',
    'body.iris-ide-shell',
    '.theia-Navigator',
    '#theia-left-side-panel',
    '.theia-Editor',
    '.monaco-editor',
    '.p-Panel-main'
  ];
  var matched = selectors.map(function(sel) {
    return { selector: sel, found: Boolean(document.querySelector(sel)) };
  });
  var bodyText = (document.body && document.body.innerText) || '';
  var isErrorPage =
    /cannot GET/i.test(bodyText) ||
    /application error/i.test(bodyText) ||
    (bodyText.length < 200 && /404|error/i.test(bodyText));
  var preloadOnly =
    document.querySelector('.theia-preload') &&
    !matched.some(function(m) { return m.found; });
  var wsOk = false;
  try {
    wsOk = Boolean(window.__THEIA_WEBSOCKET_ENDPOINT__) ||
      (typeof window.monaco !== 'undefined');
  } catch (e) {}
  var shellFound = matched.some(function(m) { return m.found; });
  var workbenchHint = shellFound && bodyText.length > 80 && !preloadOnly;
  var fallbackOk = bodyText.length > 200 && shellFound && !isErrorPage;
  var ok =
    document.readyState === 'complete' &&
    !isErrorPage &&
    !preloadOnly &&
    (workbenchHint || fallbackOk || wsOk);
  return JSON.stringify({
    ok: ok,
    readyState: document.readyState,
    matched: matched,
    title: document.title,
    url: location.href,
    bodyLength: bodyText.length,
    preloadOnly: preloadOnly,
    wsOk: wsOk,
    reason: isErrorPage
      ? 'error-page'
      : preloadOnly
        ? 'preload-only'
        : ok
          ? 'shell-found'
          : 'shell-not-found'
  });
})()
"""

_READINESS_INITIAL_DELAY_MS = 500
_READINESS_INTERVAL_MS = 750
_READINESS_MAX_WAIT_MS = 45000
_READINESS_MAX_ATTEMPTS = _READINESS_MAX_WAIT_MS // _READINESS_INTERVAL_MS + 2


class TheiaViewState(str, Enum):
  NOT_STARTED = "NOT_STARTED"
  PREFLIGHT = "PREFLIGHT"
  BACKEND_STARTING = "BACKEND_STARTING"
  FRONTEND_LOADING = "FRONTEND_LOADING"
  SHELL_PROBING = "SHELL_PROBING"
  READY = "READY"
  ERROR = "ERROR"
  STOPPED = "STOPPED"


_STATE_ORDER: dict[TheiaViewState, int] = {
  TheiaViewState.NOT_STARTED: 0,
  TheiaViewState.PREFLIGHT: 1,
  TheiaViewState.BACKEND_STARTING: 2,
  TheiaViewState.FRONTEND_LOADING: 3,
  TheiaViewState.SHELL_PROBING: 4,
  TheiaViewState.READY: 5,
  TheiaViewState.ERROR: -1,
  TheiaViewState.STOPPED: -2,
}


def webengine_available() -> bool:
  return _WEBENGINE


def webengine_import_error() -> str | None:
  return _WEBENGINE_IMPORT_ERROR


def _is_allowed_local_url(url: str) -> bool:
  parsed = urlparse(url)
  return parsed.hostname in ("127.0.0.1", "localhost") and parsed.scheme in ("http", "https")


def _append_theia_log(line: str) -> None:
  _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
  ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
  try:
    with _LOG_PATH.open("a", encoding="utf-8") as fp:
      fp.write(f"[{ts}] [theia-view] {line}\n")
  except OSError:
    pass


class _WebContainer(QWidget):
  """QWebEngineView + 로딩 오버레이."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self._overlay: QFrame | None = None

  def set_overlay(self, overlay: QFrame) -> None:
    self._overlay = overlay
    overlay.setParent(self)
    overlay.raise_()

  def resizeEvent(self, event) -> None:  # noqa: ANN001
    super().resizeEvent(event)
    if self._overlay is not None:
      self._overlay.setGeometry(self.rect())


class EmbeddedTheiaView(QWidget):
  """Theia Browser Frontend 임베드 + 로딩/오류 UI."""

  retry_requested = pyqtSignal()
  back_to_assistant_requested = pyqtSignal()
  view_log_requested = pyqtSignal()
  diagnose_requested = pyqtSignal()
  recover_env_requested = pyqtSignal()
  ready = pyqtSignal()

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("EmbeddedTheiaView")
    self._state = TheiaViewState.NOT_STARTED
    self._last_error = ""
    self._log_path = ""
    self._pending_url = ""
    self._readiness_timer: QTimer | None = None
    self._readiness_timeout_timer: QTimer | None = None
    self._readiness_attempts = 0
    self._last_probe_result: dict[str, object] = {}
    self._state_history: list[str] = []
    self._load_started_at = ""

    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)

    self._stack = QStackedWidget(self)
    lay.addWidget(self._stack)

    self._placeholder = self._build_placeholder("Iris IDE")
    self._error_panel = self._build_error_panel()

    self._stack.addWidget(self._placeholder)
    self._stack.addWidget(self._error_panel)

    self._web: QWebEngineView | None = None
    self._page = None
    self._web_container: _WebContainer | None = None
    self._loading_overlay: QFrame | None = None
    self._loading_label: QLabel | None = None
    self._web_stack_index: int | None = None

  def _ensure_web_view(self) -> bool:
    if self._web is not None:
      return True
    if not _WEBENGINE or QWebEngineView is None:
      if self._web_stack_index is None:
        no_engine = self._build_webengine_missing_panel()
        self._web_stack_index = self._stack.addWidget(no_engine)
      return False

    from iris.ui.ide.iris_webengine_page import IrisWebEnginePage

    self._web_container = _WebContainer(self)
    container_lay = QVBoxLayout(self._web_container)
    container_lay.setContentsMargins(0, 0, 0, 0)

    self._web = QWebEngineView(self._web_container)
    container_lay.addWidget(self._web)

    self._loading_overlay = QFrame(self._web_container)
    self._loading_overlay.setObjectName("TheiaLoadingOverlay")
    self._loading_overlay.setStyleSheet(
      f"background: {TOKENS.background_primary};"
    )
    overlay_lay = QVBoxLayout(self._loading_overlay)
    self._loading_label = QLabel("Iris IDE를 불러오는 중…")
    self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self._loading_label.setWordWrap(True)
    self._loading_label.setStyleSheet(f"color: {TOKENS.text_secondary}; padding: 24px;")
    overlay_lay.addWidget(self._loading_label)
    self._web_container.set_overlay(self._loading_overlay)
    self._loading_overlay.hide()

    self._page = IrisWebEnginePage(self._web, ide_port_callback=self._current_ide_port)
    self._web.setPage(self._page)
    self._web.loadStarted.connect(self._on_load_started)
    self._web.loadProgress.connect(self._on_load_progress)
    self._web.loadFinished.connect(self._on_load_finished)
    self._web.renderProcessTerminated.connect(self._on_render_terminated)
    self._web.urlChanged.connect(self._on_url_changed)
    self._web.titleChanged.connect(self._on_title_changed)
    self._web_stack_index = self._stack.addWidget(self._web_container)
    return True

  def _current_ide_port(self) -> int | None:
    if not self._pending_url:
      return None
    parsed = urlparse(self._pending_url)
    if parsed.port:
      return parsed.port
    return None

  def _build_placeholder(self, text: str) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {TOKENS.text_secondary}; padding: 24px;")
    v.addWidget(lbl)
    return w

  def _build_webengine_missing_panel(self) -> QWidget:
    import sys

    try:
      from importlib.metadata import version

      pyqt_ver = version("PyQt6")
      we_ver = "not installed"
    except Exception:
      pyqt_ver = we_ver = "unknown"

    msg = (
      "PyQt6-WebEngine을 사용할 수 없습니다.\n\n"
      f"원인: {_WEBENGINE_IMPORT_ERROR or 'import failed'}\n"
      f"Python: {sys.executable}\n"
      f"PyQt6: {pyqt_ver}\n"
      f"PyQt6-WebEngine: {we_ver}\n\n"
      "진단: scripts\\diagnose-iris-ide.ps1"
    )
    w = QWidget()
    v = QVBoxLayout(w)
    lbl = QLabel(msg)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {TOKENS.text_secondary}; padding: 24px;")
    v.addWidget(lbl)
    row = QHBoxLayout()
    diag = QPushButton("환경 진단")
    diag.clicked.connect(self.diagnose_requested.emit)
    recover = QPushButton("IDE 환경 복구")
    recover.clicked.connect(self.recover_env_requested.emit)
    back = QPushButton("기존 화면으로 돌아가기")
    back.clicked.connect(self.back_to_assistant_requested.emit)
    row.addWidget(diag)
    row.addWidget(recover)
    row.addWidget(back)
    v.addLayout(row)
    return w

  def _build_error_panel(self) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    self._error_label = QLabel()
    self._error_label.setWordWrap(True)
    self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    v.addWidget(self._error_label)
    row = QHBoxLayout()
    retry = QPushButton("다시 시도")
    retry.clicked.connect(self.retry_requested.emit)
    diag = QPushButton("환경 진단")
    diag.clicked.connect(self.diagnose_requested.emit)
    recover = QPushButton("IDE 환경 복구")
    recover.clicked.connect(self.recover_env_requested.emit)
    log_btn = QPushButton("로그 보기")
    log_btn.clicked.connect(self.view_log_requested.emit)
    back = QPushButton("기존 화면으로 돌아가기")
    back.clicked.connect(self.back_to_assistant_requested.emit)
    row.addWidget(retry)
    row.addWidget(diag)
    row.addWidget(recover)
    row.addWidget(log_btn)
    row.addWidget(back)
    v.addLayout(row)
    return w

  @property
  def state(self) -> TheiaViewState:
    return self._state

  def _set_state(
    self,
    state: TheiaViewState,
    *,
    message: str | None = None,
    detail: str | None = None,
    force: bool = False,
  ) -> None:
    # READY 이후 동일·이전 단계로 되돌아가지 않음 (force·ERROR·STOPPED 제외)
    if (
      not force
      and self._state == TheiaViewState.READY
      and state
      not in {
        TheiaViewState.ERROR,
        TheiaViewState.STOPPED,
        TheiaViewState.READY,
      }
    ):
      _append_theia_log(
        f"state blocked backward {state.value} from READY stack={self._stack_current_name()}"
      )
      return

    prev = self._state
    if not force and state not in {TheiaViewState.ERROR, TheiaViewState.STOPPED}:
      prev_order = _STATE_ORDER.get(prev, -99)
      new_order = _STATE_ORDER.get(state, -99)
      if prev_order >= 0 and new_order >= 0 and new_order < prev_order:
        _append_theia_log(
          f"state blocked backward {prev.value}->{state.value}"
        )
        return

    self._state = state
    line = (
      f"state {prev.value} -> {state.value}"
      f" stack={self._stack_current_name()}"
      f" url={self._current_url_str()}"
    )
    if message:
      line += f" msg={message}"
    if detail:
      line += f" detail={detail}"
    self._state_history.append(line)
    _append_theia_log(line)
    logger.info(line)

    if message and self._loading_label is not None:
      self._loading_label.setText(message)

  def _stack_current_name(self) -> str:
    w = self._stack.currentWidget()
    if w is self._placeholder:
      return "placeholder"
    if w is self._error_panel:
      return "error"
    if w is self._web_container:
      return "web_container"
    if self._web is not None and w is self._web:
      return "web"
    return type(w).__name__ if w else "none"

  def _current_url_str(self) -> str:
    if self._web is not None and hasattr(self._web, "url"):
      try:
        return self._web.url().toString()
      except Exception:
        pass
    return self._pending_url

  def _show_loading_overlay(self, message: str) -> None:
    if self._loading_label is not None:
      self._loading_label.setText(message)
    if self._loading_overlay is not None:
      self._loading_overlay.show()
      self._loading_overlay.raise_()

  def _hide_loading_overlay(self) -> None:
    if self._loading_overlay is not None:
      self._loading_overlay.hide()

  def set_starting(self, message: str = "Iris IDE를 준비하고 있습니다…") -> None:
    """Backend 시작·Preflight 단계 — Placeholder 또는 오버레이."""
    if self._state == TheiaViewState.READY:
      return
    target = (
      TheiaViewState.BACKEND_STARTING
      if self._state in {TheiaViewState.NOT_STARTED, TheiaViewState.PREFLIGHT, TheiaViewState.BACKEND_STARTING}
      else TheiaViewState.FRONTEND_LOADING
    )
    self._set_state(target, message=message)
    if self._web_container is not None and self._stack.indexOf(self._web_container) >= 0:
      self._stack.setCurrentWidget(self._web_container)
      self._show_loading_overlay(message)
    else:
      self._placeholder.layout().itemAt(0).widget().setText(message)  # type: ignore[union-attr]
      self._stack.setCurrentWidget(self._placeholder)

  def set_preflight(self, message: str = "Iris IDE 환경을 확인하는 중…") -> None:
    self._set_state(TheiaViewState.PREFLIGHT, message=message)
    self._placeholder.layout().itemAt(0).widget().setText(message)  # type: ignore[union-attr]
    self._stack.setCurrentWidget(self._placeholder)

  def set_error(
    self,
    message: str,
    *,
    log_path: str = "",
    detail: str | None = None,
    failure_kind: str = "unknown",
  ) -> None:
    self._cancel_readiness_probe()
    self._set_state(TheiaViewState.ERROR, message=message, detail=detail or failure_kind)
    self._last_error = message
    self._log_path = log_path
    extra = ""
    if self._last_probe_result:
      extra = (
        f"\n\n마지막 Probe:\n"
        f"readyState={self._last_probe_result.get('readyState')}\n"
        f"reason={self._last_probe_result.get('reason')}\n"
        f"title={self._last_probe_result.get('title')}\n"
        f"url={self._last_probe_result.get('url')}"
      )
    if detail:
      extra += f"\n\n{detail}"
    self._error_label.setText(f"Iris IDE를 시작하지 못했습니다.\n\n{message}{extra}")
    self._stack.setCurrentWidget(self._error_panel)
    _append_theia_log(f"ERROR kind={failure_kind} {message}")
    logger.error("EmbeddedTheiaView error [%s]: %s log=%s", failure_kind, message, log_path)

  def reset_view(self, *, force: bool = False) -> None:
    """재시도 전 WebEngine 초기화. READY 재진입 시에는 force 없이 호출하지 않음."""
    if self._state == TheiaViewState.READY and not force:
      _append_theia_log("reset_view skipped — READY session preserved")
      return
    self._cancel_readiness_probe()
    if self._web is not None:
      self._web.stop()
      self._web.setUrl(QUrl("about:blank"))
    self._hide_loading_overlay()
    self._pending_url = ""
    self._last_probe_result = {}
    self._load_started_at = ""
    self._set_state(TheiaViewState.NOT_STARTED, force=True)
    self._stack.setCurrentWidget(self._placeholder)

  def show_ready_webview(self) -> None:
    """READY 유지 — Assistant 복귀 후 IDE 재진입 시 WebView만 복원."""
    if self._state != TheiaViewState.READY or self._web is None or self._web_container is None:
      return
    self._cancel_readiness_probe()
    self._hide_loading_overlay()
    self._stack.setCurrentWidget(self._web_container)
    self._web.show()
    self._web.raise_()
    self._web.setFocus()
    _append_theia_log(f"resume READY stack={self._stack_current_name()} url={self._current_url_str()}")

  def resume_or_continue(self) -> bool:
    """이미 READY이거나 Shell Probe 중이면 Frontend 재로드 없이 UI만 복원."""
    if self._state == TheiaViewState.READY:
      self.show_ready_webview()
      return True
    if self._state == TheiaViewState.SHELL_PROBING and self._web is not None:
      self._stack.setCurrentWidget(self._web_container)
      self._show_loading_overlay("Theia Shell 준비 확인 중…")
      if self._readiness_timer is None:
        self._start_readiness_probe()
      _append_theia_log("resume SHELL_PROBING — probe continued")
      return True
    return False

  def load_url(self, url: str) -> bool:
    if not self._ensure_web_view() or self._web is None or self._web_container is None:
      import sys

      try:
        from importlib.metadata import version

        pyqt_ver = version("PyQt6")
        we_ver = version("PyQt6-WebEngine")
      except Exception:
        pyqt_ver = we_ver = "unknown"
      self.set_error(
        "WebEngine 의존성 실패\n\n"
        f"{_WEBENGINE_IMPORT_ERROR or 'PyQt6-WebEngine import failed'}\n"
        f"Python: {sys.executable}\n"
        f"PyQt6: {pyqt_ver}\n"
        f"PyQt6-WebEngine: {we_ver}\n\n"
        "진단: scripts\\diagnose-iris-ide.ps1",
        failure_kind="WebEngineLoadFailure",
      )
      return False
    if not _is_allowed_local_url(url):
      self.set_error(
        "허용되지 않은 URL입니다. 127.0.0.1만 로드합니다.",
        failure_kind="FrontendHttpFailure",
      )
      return False

    # localhost → 127.0.0.1 통일
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    if host == "localhost":
      host = "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    normalized = f"{parsed.scheme}://{host}:{port}{path}{query}"

    self._pending_url = normalized
    reloading = self._state == TheiaViewState.READY
    self._set_state(
      TheiaViewState.FRONTEND_LOADING,
      message="Theia Frontend를 로드하는 중…",
      force=reloading,
    )
    self._stack.setCurrentWidget(self._web_container)
    self._show_loading_overlay("Theia Frontend를 로드하는 중…")
    _append_theia_log(f"load_url {normalized} stack=web_container")
    self._web.setUrl(QUrl(normalized))
    return True

  def _cancel_readiness_probe(self) -> None:
    if self._readiness_timer is not None:
      self._readiness_timer.stop()
      self._readiness_timer.deleteLater()
      self._readiness_timer = None
    if self._readiness_timeout_timer is not None:
      self._readiness_timeout_timer.stop()
      self._readiness_timeout_timer.deleteLater()
      self._readiness_timeout_timer = None
    self._readiness_attempts = 0

  def _start_readiness_probe(self) -> None:
    self._cancel_readiness_probe()
    self._readiness_attempts = 0
    self._readiness_timer = QTimer(self)
    self._readiness_timer.setInterval(_READINESS_INTERVAL_MS)
    self._readiness_timer.timeout.connect(self._probe_theia_ready)
    self._readiness_timeout_timer = QTimer(self)
    self._readiness_timeout_timer.setSingleShot(True)
    self._readiness_timeout_timer.timeout.connect(self._readiness_timeout)
    self._readiness_timeout_timer.start(_READINESS_MAX_WAIT_MS)
    QTimer.singleShot(_READINESS_INITIAL_DELAY_MS, self._probe_theia_ready)
    self._readiness_timer.start()
    _append_theia_log("readiness_probe started")

  def _readiness_timeout(self) -> None:
    if self._state != TheiaViewState.SHELL_PROBING:
      return
    self._cancel_readiness_probe()
    probe = self._last_probe_result
    detail = (
      f"readyState={probe.get('readyState', '?')}\n"
      f"reason={probe.get('reason', '?')}\n"
      f"title={probe.get('title', '?')}\n"
      f"url={probe.get('url', self._current_url_str())}\n"
      f"bodyLength={probe.get('bodyLength', '?')}"
    )
    self.set_error(
      "Theia Shell 준비 시간이 초과되었습니다.",
      detail=detail,
      failure_kind="TheiaShellReadinessFailure",
    )

  def _probe_theia_ready(self) -> None:
    if self._web is None or self._state != TheiaViewState.SHELL_PROBING:
      return
    self._readiness_attempts += 1
    if self._readiness_attempts > _READINESS_MAX_ATTEMPTS:
      self._readiness_timeout()
      return

    def _on_result(raw: object) -> None:
      if self._state != TheiaViewState.SHELL_PROBING:
        return
      try:
        data = json.loads(str(raw) if raw is not None else "{}")
      except Exception as exc:
        self._last_probe_result = {"reason": f"probe-parse-error: {exc}"}
        _append_theia_log(f"probe parse error: {exc}")
        return
      if not isinstance(data, dict):
        return
      self._last_probe_result = data
      _append_theia_log(f"probe #{self._readiness_attempts} {json.dumps(data, ensure_ascii=False)[:500]}")
      if data.get("ok"):
        self._show_ready_webview()

    try:
      self._web.page().runJavaScript(_THEIA_READINESS_JS, _on_result)
    except Exception as exc:
      self._last_probe_result = {"reason": f"probe-exec-error: {exc}"}
      _append_theia_log(f"probe exec error: {exc}")

  def _show_ready_webview(self) -> None:
    """READY 성공 경로의 유일한 진입점."""
    if self._web is None or self._web_container is None:
      self.set_error("QWebEngineView가 존재하지 않습니다.", failure_kind="WebEngineLoadFailure")
      return
    if self._state == TheiaViewState.READY:
      return

    self._cancel_readiness_probe()
    self._hide_loading_overlay()
    self._stack.setCurrentWidget(self._web_container)
    self._web.show()
    self._web.raise_()
    self._web.setFocus()
    self._set_state(TheiaViewState.READY, message="Theia Workbench 준비 완료")
    _append_theia_log(
      f"READY stack={self._stack_current_name()} url={self._current_url_str()}"
    )
    self.ready.emit()

  def _validate_loaded_url(self) -> str | None:
    url = self._web.url().toString() if self._web else ""
    if not url or url in ("about:blank", ""):
      return "빈 URL"
    if url.startswith("chrome-error://"):
      return f"chrome-error: {url}"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
      return f"예상하지 않은 scheme: {parsed.scheme}"
    if parsed.hostname not in ("127.0.0.1", "localhost"):
      return f"예상하지 않은 host: {parsed.hostname}"
    return None

  def _on_load_started(self) -> None:
    if self._state == TheiaViewState.READY:
      return
    self._load_started_at = datetime.now(timezone.utc).isoformat()
    if self._state not in {TheiaViewState.FRONTEND_LOADING, TheiaViewState.SHELL_PROBING}:
      self._set_state(TheiaViewState.FRONTEND_LOADING)
    _append_theia_log(f"loadStarted at={self._load_started_at} url={self._current_url_str()}")

  def _on_load_progress(self, progress: int) -> None:
    if self._state not in {
      TheiaViewState.FRONTEND_LOADING,
      TheiaViewState.SHELL_PROBING,
    }:
      return
    if self._loading_label is not None:
      self._loading_label.setText(f"Iris IDE Frontend 로드 중… {progress}%")
    _append_theia_log(f"loadProgress={progress} state={self._state.value}")

  def _on_load_finished(self, ok: bool) -> None:
    _append_theia_log(f"loadFinished ok={ok} url={self._current_url_str()}")
    if not ok:
      self.set_error(
        "Theia Frontend를 불러오지 못했습니다.",
        detail=f"url={self._current_url_str()}",
        failure_kind="WebEngineLoadFailure",
      )
      return

    url_err = self._validate_loaded_url()
    if url_err:
      self.set_error(
        "Theia Frontend URL 검증 실패",
        detail=url_err,
        failure_kind="FrontendHttpFailure",
      )
      return

    self._set_state(
      TheiaViewState.SHELL_PROBING,
      message="Theia Shell 준비 확인 중…",
      force=True,
    )
    self._show_loading_overlay("Theia Shell 준비 확인 중…")
    self._start_readiness_probe()

  def _on_render_terminated(self, status: object, exit_code: int) -> None:
    from iris.ui.ide.iris_webengine_page import _enum_label

    label = _enum_label(status)
    self.set_error(
      f"Render Process 종료 (status={label}, exit={exit_code})",
      failure_kind="WebEngineLoadFailure",
    )

  def _on_url_changed(self, url: QUrl) -> None:
    logger.debug("Theia url changed: %s", url.toString())
    _append_theia_log(f"urlChanged {url.toString()}")

  def _on_title_changed(self, title: str) -> None:
    logger.debug("Theia title: %s", title)

  def run_javascript(self, script: str) -> None:
    if self._web is not None and self._state == TheiaViewState.READY:
      self._web.page().runJavaScript(script)

  def last_log_path(self) -> str:
    return self._log_path

  def state_history(self) -> list[str]:
    return list(self._state_history)

  def last_probe_result(self) -> dict[str, object]:
    return dict(self._last_probe_result)

  def web_view(self) -> QWebEngineView | None:
    return self._web

  def stack_widget(self) -> QStackedWidget:
    return self._stack
