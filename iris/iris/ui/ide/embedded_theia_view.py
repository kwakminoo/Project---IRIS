"""QWebEngineView 기반 내장 Theia 뷰."""

from __future__ import annotations

from enum import Enum
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
  QHBoxLayout,
  QLabel,
  QPushButton,
  QStackedWidget,
  QVBoxLayout,
  QWidget,
)

from iris.ui.theme_tokens import TOKENS

try:
  from PyQt6.QtWebEngineWidgets import QWebEngineView

  _WEBENGINE = True
except ImportError:
  QWebEngineView = None  # type: ignore[misc, assignment]
  _WEBENGINE = False


class TheiaViewState(str, Enum):
  NOT_STARTED = "NOT_STARTED"
  STARTING = "STARTING"
  READY = "READY"
  ERROR = "ERROR"
  STOPPED = "STOPPED"


def _is_allowed_local_url(url: str) -> bool:
  parsed = urlparse(url)
  return parsed.hostname in ("127.0.0.1", "localhost") and parsed.scheme in ("http", "https")


class EmbeddedTheiaView(QWidget):
  """Theia Browser Frontend 임베드 + 로딩/오류 UI."""

  retry_requested = pyqtSignal()
  back_to_assistant_requested = pyqtSignal()
  view_log_requested = pyqtSignal()

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("EmbeddedTheiaView")
    self._state = TheiaViewState.NOT_STARTED
    self._last_error = ""
    self._log_path = ""

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
    if _WEBENGINE:
      self._web = QWebEngineView(self)
      self._stack.addWidget(self._web)
    else:
      no_engine = self._build_placeholder(
        "PyQt6-WebEngine이 설치되지 않았습니다.\n"
        "pip install PyQt6-WebEngine"
      )
      self._stack.addWidget(no_engine)

  def _build_placeholder(self, text: str) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {TOKENS.text_secondary}; padding: 24px;")
    v.addWidget(lbl)
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
    log_btn = QPushButton("로그 보기")
    log_btn.clicked.connect(self.view_log_requested.emit)
    back = QPushButton("기존 화면으로 돌아가기")
    back.clicked.connect(self.back_to_assistant_requested.emit)
    row.addWidget(retry)
    row.addWidget(log_btn)
    row.addWidget(back)
    v.addLayout(row)
    return w

  @property
  def state(self) -> TheiaViewState:
    return self._state

  def set_starting(self) -> None:
    self._state = TheiaViewState.STARTING
    self._stack.setCurrentWidget(self._starting)

  def set_error(self, message: str, *, log_path: str = "") -> None:
    self._state = TheiaViewState.ERROR
    self._last_error = message
    self._log_path = log_path
    self._error_label.setText(f"Iris IDE를 시작하지 못했습니다.\n\n{message}")
    self._stack.setCurrentWidget(self._error_panel)

  def load_url(self, url: str) -> bool:
    if not _WEBENGINE or self._web is None:
      self.set_error("PyQt6-WebEngine을 사용할 수 없습니다.")
      return False
    if not _is_allowed_local_url(url):
      self.set_error("허용되지 않은 URL입니다. 127.0.0.1만 로드합니다.")
      return False
    self.set_starting()
    self._web.setUrl(QUrl(url))
    self._stack.setCurrentWidget(self._web)
    self._state = TheiaViewState.READY
    return True

  def run_javascript(self, script: str) -> None:
    if self._web is not None and self._state == TheiaViewState.READY:
      self._web.page().runJavaScript(script)

  def last_log_path(self) -> str:
    return self._log_path
