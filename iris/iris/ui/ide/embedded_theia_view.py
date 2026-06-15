"""QWebEngineView 기반 내장 Theia 뷰."""

from __future__ import annotations

import logging
from enum import Enum
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
  QHBoxLayout,
  QLabel,
  QPushButton,
  QStackedWidget,
  QVBoxLayout,
  QWidget,
)

from iris.ui.theme_tokens import TOKENS

logger = logging.getLogger(__name__)

_WEBENGINE_IMPORT_ERROR: str | None = None
_WEBENGINE = False
QWebEngineView = None  # type: ignore[misc, assignment]

try:
  from PyQt6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView

  QWebEngineView = _QWebEngineView
  _WEBENGINE = True
except (ImportError, OSError) as exc:
  _WEBENGINE_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


# Theia 1.55 ApplicationShell DOM — preload 제거·shell 표시 후 READY
_THEIA_READINESS_JS = """
(function() {
  if (document.readyState !== 'complete') return JSON.stringify({ok:false, reason:'document-not-complete'});
  var shell = document.querySelector('.theia-ApplicationShell') ||
              document.querySelector('#theia-app-shell') ||
              document.querySelector('.iris-ide-shell');
  if (!shell) return JSON.stringify({ok:false, reason:'no-theia-shell'});
  var main = shell.querySelector('.p-Panel-main') || shell.querySelector('.p-Widget');
  if (!main) return JSON.stringify({ok:false, reason:'no-main-area'});
  var bodyText = (document.body && document.body.innerText) || '';
  if (/cannot GET|404|error/i.test(bodyText) && bodyText.length < 200) {
    return JSON.stringify({ok:false, reason:'error-page'});
  }
  return JSON.stringify({ok:true});
})()
"""


class TheiaViewState(str, Enum):
  NOT_STARTED = "NOT_STARTED"
  STARTING = "STARTING"
  READY = "READY"
  ERROR = "ERROR"
  STOPPED = "STOPPED"


def webengine_available() -> bool:
  return _WEBENGINE


def webengine_import_error() -> str | None:
  return _WEBENGINE_IMPORT_ERROR


def _is_allowed_local_url(url: str) -> bool:
  parsed = urlparse(url)
  return parsed.hostname in ("127.0.0.1", "localhost") and parsed.scheme in ("http", "https")


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
    self._readiness_attempts = 0

    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)

    self._stack = QStackedWidget(self)
    lay.addWidget(self._stack)

    self._placeholder = self._build_placeholder("Iris IDE")
    self._starting = self._build_placeholder("Iris IDE를 준비하고 있습니다…")
    self._error_panel = self._build_error_panel()

    self._stack.addWidget(self._placeholder)
    self._stack.addWidget(self._starting)
    self._stack.addWidget(self._error_panel)

    self._web: QWebEngineView | None = None
    self._page = None
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

    self._web = QWebEngineView(self)
    self._page = IrisWebEnginePage(self._web)
    self._web.setPage(self._page)
    self._web.loadStarted.connect(self._on_load_started)
    self._web.loadProgress.connect(self._on_load_progress)
    self._web.loadFinished.connect(self._on_load_finished)
    self._web.renderProcessTerminated.connect(self._on_render_terminated)
    self._web.urlChanged.connect(self._on_url_changed)
    self._web.titleChanged.connect(self._on_title_changed)
    self._web_stack_index = self._stack.addWidget(self._web)
    return True

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

  def set_starting(self, message: str = "Iris IDE를 준비하고 있습니다…") -> None:
    self._state = TheiaViewState.STARTING
    self._starting.layout().itemAt(0).widget().setText(message)  # type: ignore[union-attr]
    self._stack.setCurrentWidget(self._starting)

  def set_error(self, message: str, *, log_path: str = "") -> None:
    self._state = TheiaViewState.ERROR
    self._last_error = message
    self._log_path = log_path
    self._error_label.setText(f"Iris IDE를 시작하지 못했습니다.\n\n{message}")
    self._stack.setCurrentWidget(self._error_panel)
    logger.error("EmbeddedTheiaView error: %s log=%s", message, log_path)

  def reset_view(self) -> None:
    """재시도 전 WebEngine 페이지 초기화."""
    self._cancel_readiness_probe()
    if self._web is not None:
      self._web.setUrl(QUrl("about:blank"))
    self._state = TheiaViewState.NOT_STARTED
    self._pending_url = ""

  def load_url(self, url: str) -> bool:
    if not self._ensure_web_view() or self._web is None:
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
        "진단: scripts\\diagnose-iris-ide.ps1"
      )
      return False
    if not _is_allowed_local_url(url):
      self.set_error("허용되지 않은 URL입니다. 127.0.0.1만 로드합니다.")
      return False
    self._pending_url = url
    self.set_starting("Theia Frontend를 로드하는 중…")
    self._stack.setCurrentWidget(self._web)
    self._state = TheiaViewState.STARTING
    self._web.setUrl(QUrl(url))
    return True

  def _cancel_readiness_probe(self) -> None:
    if self._readiness_timer is not None:
      self._readiness_timer.stop()
      self._readiness_timer.deleteLater()
      self._readiness_timer = None
    self._readiness_attempts = 0

  def _schedule_readiness_probe(self) -> None:
    self._cancel_readiness_probe()
    self._readiness_timer = QTimer(self)
    self._readiness_timer.setInterval(400)
    self._readiness_timer.timeout.connect(self._probe_theia_ready)
    self._readiness_timer.start()
    QTimer.singleShot(30000, self._readiness_timeout)

  def _readiness_timeout(self) -> None:
    if self._state != TheiaViewState.STARTING:
      return
    self._cancel_readiness_probe()
    self.set_error("Theia Shell 준비 실패 — workbench가 표시되지 않았습니다.")

  def _probe_theia_ready(self) -> None:
    if self._web is None or self._state != TheiaViewState.STARTING:
      self._cancel_readiness_probe()
      return
    self._readiness_attempts += 1
    if self._readiness_attempts > 75:
      self._cancel_readiness_probe()
      self.set_error("Theia Shell 준비 실패 (timeout)")
      return

    def _on_result(raw: object) -> None:
      try:
        import json

        data = json.loads(str(raw) if raw is not None else "{}")
      except Exception:
        return
      if not isinstance(data, dict) or not data.get("ok"):
        return
      self._cancel_readiness_probe()
      self._state = TheiaViewState.READY
      self.ready.emit()
      logger.info("Theia shell ready url=%s", self._pending_url)

    self._web.page().runJavaScript(_THEIA_READINESS_JS, _on_result)

  def _on_load_started(self) -> None:
    self._state = TheiaViewState.STARTING

  def _on_load_progress(self, progress: int) -> None:
    if progress > 0 and progress < 100:
      self.set_starting(f"Theia Frontend 로드 중… {progress}%")

  def _on_load_finished(self, ok: bool) -> None:
    if not ok:
      self.set_error("Frontend Load 실패 — HTTP 또는 네트워크 오류")
      return
    self._schedule_readiness_probe()

  def _on_render_terminated(self, status: object, exit_code: int) -> None:
    from iris.ui.ide.iris_webengine_page import _enum_label

    label = _enum_label(status)
    self.set_error(f"Render Process 종료 (status={label}, exit={exit_code})")

  def _on_url_changed(self, url: QUrl) -> None:
    logger.debug("Theia url changed: %s", url.toString())

  def _on_title_changed(self, title: str) -> None:
    logger.debug("Theia title: %s", title)

  def run_javascript(self, script: str) -> None:
    if self._web is not None and self._state == TheiaViewState.READY:
      self._web.page().runJavaScript(script)

  def last_log_path(self) -> str:
    return self._log_path
