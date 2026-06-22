"""항상 유지되는 좌측 사이드바."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QSizePolicy, QVBoxLayout, QWidget

from iris.ui.window_list_panel import WindowListPanel


_SIDEBAR_MIN_WIDTH = 200
_SIDEBAR_MAX_WIDTH = 300


class LeftSidebarPanel(QWidget):
  """
  상단: 실행 중인 창 목록
  하단: CPU·GPU·메모리 + Workspace 액션
  """

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("LeftSidebarPanel")
    self.setMinimumWidth(_SIDEBAR_MIN_WIDTH)
    self.setMaximumWidth(_SIDEBAR_MAX_WIDTH)
    self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    root = QVBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    self._splitter = QSplitter(Qt.Orientation.Vertical)
    self._splitter.setChildrenCollapsible(False)
    self._splitter.setHandleWidth(0)

    self.window_list = WindowListPanel(self)
    from iris.ui.sidebar_utility_panel import SidebarUtilityPanel

    self.utility = SidebarUtilityPanel(self)

    self._splitter.addWidget(self.window_list)
    self._splitter.addWidget(self.utility)
    self._splitter.setStretchFactor(0, 1)
    self._splitter.setStretchFactor(1, 1)
    self._splitter.setSizes([280, 280])

    root.addWidget(self._splitter)

  def set_workspace_mode(self, mode: str) -> None:
    """assistant: Running Windows·메트릭 표시 / ide: Theia Activity Bar에 복귀 버튼 위임."""
    is_ide = mode == "ide"
    if is_ide:
      # IDE 모드 — 외부 사이드바 숨김(복귀는 Theia Activity Bar 내부 버튼)
      self.hide()
      self.setMinimumWidth(0)
      self.setMaximumWidth(0)
      return

    self.show()
    self.window_list.setVisible(True)
    self.utility.metrics.setVisible(True)
    self.utility.actions.setVisible(True)
    self.setMinimumWidth(_SIDEBAR_MIN_WIDTH)
    self.setMaximumWidth(_SIDEBAR_MAX_WIDTH)
    self._splitter.setSizes([280, 280])
