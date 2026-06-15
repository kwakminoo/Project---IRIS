"""기존 Iris Assistant UI를 감싸는 Workspace 페이지."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget


class AssistantWorkspacePage(QWidget):
  """
  중앙·우측 Iris UI 컨테이너.
  내부 2열 Splitter: [Visualizer+Activity+Chat | Monitor+Notification]
  """

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("AssistantWorkspacePage")
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    self._splitter = QSplitter(Qt.Orientation.Horizontal)
    self._splitter.setChildrenCollapsible(False)
    self._splitter.setHandleWidth(8)

    self.center_column = QWidget()
    self.center_column.setObjectName("WorkspacePanel")
    self.center_layout = QVBoxLayout(self.center_column)
    self.center_layout.setContentsMargins(0, 0, 0, 0)
    self.center_layout.setSpacing(10)

    self.right_column = QWidget()
    self.right_column.setObjectName("WorkspacePanel")
    self.right_layout = QVBoxLayout(self.right_column)
    self.right_layout.setContentsMargins(0, 0, 0, 0)
    self.right_layout.setSpacing(10)

    self._splitter.addWidget(self.center_column)
    self._splitter.addWidget(self.right_column)
    self._splitter.setSizes([760, 390])
    self._splitter.setStretchFactor(0, 2)
    self._splitter.setStretchFactor(1, 1)

    lay.addWidget(self._splitter)

  def save_splitter_state(self) -> bytes:
    return bytes(self._splitter.saveState())

  def restore_splitter_state(self, data: bytes) -> None:
    if data:
      self._splitter.restoreState(data)
