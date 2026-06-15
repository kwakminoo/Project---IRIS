"""항상 유지되는 좌측 사이드바."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from iris.ui.window_list_panel import WindowListPanel


_SIDEBAR_WIDTH = 220


class LeftSidebarPanel(QWidget):
  """
  상단: 실행 중인 창 목록
  하단: CPU·GPU·메모리 + Workspace 액션
  """

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("LeftSidebarPanel")
    self.setFixedWidth(_SIDEBAR_WIDTH)

    root = QVBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    self._splitter = QSplitter(Qt.Orientation.Vertical)
    self._splitter.setChildrenCollapsible(False)
    self._splitter.setHandleWidth(6)

    self.window_list = WindowListPanel(self)
    from iris.ui.sidebar_utility_panel import SidebarUtilityPanel

    self.utility = SidebarUtilityPanel(self)

    self._splitter.addWidget(self.window_list)
    self._splitter.addWidget(self.utility)
    self._splitter.setStretchFactor(0, 1)
    self._splitter.setStretchFactor(1, 1)
    self._splitter.setSizes([280, 280])

    root.addWidget(self._splitter)
