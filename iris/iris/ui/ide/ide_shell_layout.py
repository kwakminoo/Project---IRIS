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
from iris.ui.ide.ide_overlay_debug import (
  IdeOverlayClickDebugFilter,
  overlay_debug_enabled,
)
from iris.ui.ide.iris_assistant_dock import IrisAssistantDock
from iris.ui.ide.iris_ide_welcome_layer import IrisIdeWelcomeLayer
from iris.ui.ide.iris_orb_widget import IrisOrbWidget


class TheiaIdeHost(QWidget):
  """
  Theia IDE 호스트 — PyQt 오버레이 레이어 역할 분리:

  1. ``theia`` — 실제 IDE 상호작용 (QWebEngineView)
  2. ``welcome_home`` — 폴더 미열림 웰컴 (Activity Bar 제외 interactive)
  3. ``back_button`` — interactive overlay (Activity Bar 하단 슬롯만)
  """

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("TheiaIdeHost")
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    self.setAutoFillBackground(False)
    self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    self.theia = EmbeddedTheiaView(self)
    self.welcome_home = IrisIdeWelcomeLayer(self)
    self.center_orb = self.welcome_home
    self.back_button = IdeActivityBackButton(self)

    grid = QGridLayout(self)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(0)
    grid.addWidget(self.theia, 0, 0)
    grid.addWidget(self.welcome_home, 0, 0)
    self.welcome_home.raise_()
    self.back_button.raise_()

    self._debug_filter: IdeOverlayClickDebugFilter | None = None
    if overlay_debug_enabled():
      self._debug_filter = IdeOverlayClickDebugFilter(self, self)
      self.installEventFilter(self._debug_filter)

  def set_welcome_visible(self, visible: bool) -> None:
    self.welcome_home.setVisible(visible)
    if visible:
      self.welcome_home.refresh_recent_folders()

  def set_center_orb_visible(self, visible: bool) -> None:
    self.set_welcome_visible(visible)

  def resizeEvent(self, event) -> None:  # noqa: N802
    super().resizeEvent(event)
    self._position_back_button()

  def _position_back_button(self) -> None:
    bottom_edge = self.height() - THEIA_STATUS_BAR_HEIGHT
    y = bottom_edge - THEIA_ACTIVITY_TAB_SIZE * 2
    slot_h = max(THEIA_ACTIVITY_TAB_SIZE, self.back_button.minimumHeight())
    self.back_button.setGeometry(
      0,
      max(0, y),
      THEIA_ACTIVITY_BAR_WIDTH,
      slot_h,
    )
    self.back_button.raise_()


class IdeShellLayout(QWidget):
  """
  IDE 작업공간 루트 레이아웃.
  [ TheiaIdeHost (stretch) | IrisAssistantDock (fixed) ]

  Iris 구체는 단일 인스턴스 — 웰컴(좌) ↔ Dock(우) 재배치.
  """

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IdeShellLayout")
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    self.setAutoFillBackground(False)

    self._dock_width = ASSISTANT_DOCK_DEFAULT_WIDTH
    self._layout_mode = "empty_home"
    self._folder_open = False

    root = QHBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    self.theia_host = TheiaIdeHost(self)
    self.assistant_dock = IrisAssistantDock(self)
    self.iris_orb = IrisOrbWidget(self)

    root.addWidget(self.theia_host, 1)
    root.addWidget(self.assistant_dock, 0)

    self.theia = self.theia_host.theia
    self.welcome_home = self.theia_host.welcome_home
    self.center_orb = self.theia_host.center_orb
    self.back_button = self.theia_host.back_button

    self.welcome_home.folder_opened.connect(self._on_welcome_folder_opened)
    self.welcome_home.folder_created.connect(self._on_welcome_folder_opened)

    self.show_empty_home()

  @property
  def folder_open(self) -> bool:
    return self._folder_open

  def _on_welcome_folder_opened(self, path: str) -> None:
    del path
    self.set_workspace_folder_open(True)

  def set_workspace_folder_open(self, opened: bool) -> None:
    self._folder_open = opened
    if opened:
      self.show_folder_workspace()
    else:
      self.show_empty_home()

  def _mount_orb_welcome(self) -> None:
    self.assistant_dock.unmount_orb(self.iris_orb)
    self.welcome_home.mount_orb(self.iris_orb)

  def _mount_orb_dock(self) -> None:
    self.welcome_home.unmount_orb(self.iris_orb)
    self.assistant_dock.mount_orb(self.iris_orb)

  def set_dock_width(self, width: int) -> None:
    self._dock_width = max(
      ASSISTANT_DOCK_MIN_WIDTH,
      min(ASSISTANT_DOCK_MAX_WIDTH, width),
    )
    self._apply_dock_width()

  def show_empty_home(self) -> None:
    self._layout_mode = "empty_home"
    self._folder_open = False
    self.theia_host.set_welcome_visible(True)
    self._mount_orb_welcome()
    self.assistant_dock.show()
    self._apply_dock_width()

  def show_folder_workspace(self) -> None:
    """폴더 열림·생성 후 — 웰컴 숨김, 구체 우측 Dock."""
    self._layout_mode = "folder_workspace"
    self._folder_open = True
    self.theia_host.set_welcome_visible(False)
    self._mount_orb_dock()
    self.assistant_dock.show()
    self._apply_dock_width()

  def show_editor_with_assistant(self) -> None:
    self.show_folder_workspace()

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
