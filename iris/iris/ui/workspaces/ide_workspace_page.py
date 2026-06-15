"""IDE Workspace 페이지."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from iris.ui.ide.embedded_theia_view import EmbeddedTheiaView
from iris.ui.ide.iris_coding_panel import IrisCodingPanel


class IdeWorkspacePage(QWidget):
  """Theia + Iris Coding Panel."""

  theia_retry = pyqtSignal()
  theia_back = pyqtSignal()
  theia_view_log = pyqtSignal()

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IdeWorkspacePage")
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)

    self._splitter = QSplitter(Qt.Orientation.Horizontal)
    self._splitter.setChildrenCollapsible(False)
    self._splitter.setHandleWidth(0)

    self.theia = EmbeddedTheiaView(self)
    self.coding_panel = IrisCodingPanel(self)

    self._splitter.addWidget(self.theia)
    self._splitter.addWidget(self.coding_panel)
    self._splitter.setStretchFactor(0, 3)
    self._splitter.setStretchFactor(1, 1)
    self._splitter.setSizes([900, 320])

    lay.addWidget(self._splitter)

    self.theia.retry_requested.connect(self.theia_retry.emit)
    self.theia.back_to_assistant_requested.connect(self.theia_back.emit)
    self.theia.view_log_requested.connect(self.theia_view_log.emit)

  def save_splitter_state(self) -> bytes:
    return bytes(self._splitter.saveState())

  def restore_splitter_state(self, data: bytes) -> None:
    if data:
      self._splitter.restoreState(data)
