"""IDE Shell — Theia 본문과 Iris Assistant Dock을 겹침 없이 배치."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
  QGridLayout,
  QHBoxLayout,
  QSizePolicy,
  QWidget,
)

from iris.ui.ide.embedded_theia_view import EmbeddedTheiaView
from iris.ui.ide.ide_activity_back_button import IdeActivityBackButton
from iris.ui.ide.ide_layout_constants import (
  ASSISTANT_DOCK_DEFAULT_WIDTH,
  ASSISTANT_DOCK_MAX_WIDTH,
  ASSISTANT_DOCK_MIN_WIDTH,
  EDITOR_MIN_WIDTH,
  THEIA_ACTIVITY_BAR_WIDTH,
  THEIA_ACTIVITY_TAB_SIZE,
  THEIA_STATUS_BAR_HEIGHT,
)
from iris.ui.ide.iris_assistant_dock import IrisAssistantDock
from iris.ui.ide.iris_center_orb_layer import IrisCenterOrbLayer


class TheiaIdeHost(QWidget):
  """Theia WebView + Empty Home 중앙 구체 — Iris Dock과 분리."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("TheiaIdeHost")
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    self.setAutoFillBackground(False)
    self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    self.theia = EmbeddedTheiaView(self)
    self.center_orb = IrisCenterOrbLayer(self)
    self.back_button = IdeActivityBackButton(self)

    grid = QGridLayout(self)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(0)
    grid.addWidget(self.theia, 0, 0)
    grid.addWidget(self.center_orb, 0, 0)
    self.center_orb.raise_()
    self.back_button.raise_()

  def set_center_orb_visible(self, visible: bool) -> None:
    self.center_orb.setVisible(visible)

  def resizeEvent(self, event) -> None:  # noqa: N802
    super().resizeEvent(event)
    # Activity Bar 하단 슬롯 — Theia 호스트 내부에서만 절대 배치
    bottom_edge = self.height() - THEIA_STATUS_BAR_HEIGHT
    y = bottom_edge - THEIA_ACTIVITY_TAB_SIZE * 2
    self.back_button.setGeometry(
      0,
      max(0, y),
      THEIA_ACTIVITY_BAR_WIDTH,
      THEIA_ACTIVITY_TAB_SIZE,
    )
    self.back_button.raise_()


class IdeShellLayout(QWidget):
  """
  IDE 작업공간 루트 레이아웃.
  [ TheiaIdeHost (stretch) | IrisAssistantDock (fixed) ] — 수평 분할, 겹침 없음.
  """

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IdeShellLayout")
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    self.setAutoFillBackground(False)

    self._dock_width = ASSISTANT_DOCK_DEFAULT_WIDTH
    self._layout_mode = "empty_home"

    root = QHBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    self.theia_host = TheiaIdeHost(self)
    self.assistant_dock = IrisAssistantDock(self)

    root.addWidget(self.theia_host, 1)
    root.addWidget(self.assistant_dock, 0)

    self.theia = self.theia_host.theia
    self.center_orb = self.theia_host.center_orb
    self.back_button = self.theia_host.back_button

    self.show_empty_home()

  def set_dock_width(self, width: int) -> None:
    self._dock_width = max(
      ASSISTANT_DOCK_MIN_WIDTH,
      min(ASSISTANT_DOCK_MAX_WIDTH, width),
    )
    self._apply_dock_width()

  def show_empty_home(self) -> None:
    self._layout_mode = "empty_home"
    self.theia_host.set_center_orb_visible(True)
    self.assistant_dock.show()
    self._apply_dock_width()

  def show_editor_with_assistant(self) -> None:
    self._layout_mode = "editor_with_assistant"
    self.theia_host.set_center_orb_visible(False)
    self.assistant_dock.show()
    self._apply_dock_width()

  def resizeEvent(self, event) -> None:  # noqa: N802
    super().resizeEvent(event)
    self._apply_dock_width()

  def _apply_dock_width(self) -> None:
    if not self.assistant_dock.isVisible():
      return

    total_w = max(self.width(), 1)
    dock_w = self._dock_width
    min_theia_w = THEIA_ACTIVITY_BAR_WIDTH + EDITOR_MIN_WIDTH
    if total_w - dock_w < min_theia_w:
      dock_w = max(ASSISTANT_DOCK_MIN_WIDTH, total_w - min_theia_w)
    if total_w < 1280:
      dock_w = min(dock_w, ASSISTANT_DOCK_MIN_WIDTH)
    dock_w = max(ASSISTANT_DOCK_MIN_WIDTH, min(dock_w, ASSISTANT_DOCK_MAX_WIDTH))

    self.assistant_dock.setFixedWidth(dock_w)
