"""IDE Workspace 페이지 — Theia Shell + Iris Assistant Dock."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from iris.ui.ide.ide_back_navigation_controller import IdeBackNavigationController
from iris.ui.ide.ide_shell_layout import IdeShellLayout


class IdeWorkspacePage(QWidget):
  """통합 IDE 작업공간 — Theia·웰컴·Assistant Dock."""

  theia_retry = pyqtSignal()
  theia_back = pyqtSignal()
  theia_view_log = pyqtSignal()
  coding_send_clicked = pyqtSignal(str)

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IdeWorkspacePage")
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    self.setAutoFillBackground(False)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    self._shell = IdeShellLayout(self)
    lay.addWidget(self._shell)

    self.theia = self._shell.theia
    self.coding_panel = self._shell.assistant_dock
    self.empty_home = self._shell.center_orb
    self.back_button = self._shell.back_button
    self.iris_orb = self._shell.iris_orb

    self._has_open_editor = False
    self._splitter_state = b""

    self._back_nav = IdeBackNavigationController(self)
    self._back_nav.connect_pyqt_button(self.back_button)
    self._back_nav.connect_theia_view(self.theia)
    self._back_nav.back_requested.connect(self.theia_back.emit)

    self.theia.retry_requested.connect(self.theia_retry.emit)
    self.theia.view_log_requested.connect(self.theia_view_log.emit)

    self.coding_panel.chat.send_clicked.connect(self._forward_coding_send)

  def _forward_coding_send(self, text: str) -> None:
    self.coding_send_clicked.emit(text)

  def set_editor_state(
    self,
    has_open_editor: bool,
    title: str = "",
    language_id: str = "",
  ) -> None:
    """Theia editorStateChanged → 레이아웃·구체 배치."""
    del language_id
    self._has_open_editor = has_open_editor
    if has_open_editor:
      self._shell.set_workspace_folder_open(True)
      if title:
        self.coding_panel.set_workspace_label(f"파일: {title}")
    elif not self._shell.folder_open:
      self.show_empty_home()
      self.coding_panel.set_workspace_label("Workspace: —")
    else:
      self.coding_panel.set_workspace_label("Workspace: —")

  def set_workspace_folder_open(self, opened: bool) -> None:
    self._shell.set_workspace_folder_open(opened)

  def show_empty_home(self) -> None:
    self._shell.show_empty_home()
    if hasattr(self.empty_home, "refresh_recent_folders"):
      self.empty_home.refresh_recent_folders()

  def show_editor_with_assistant(self) -> None:
    self._shell.show_folder_workspace()

  def set_workspace_label(self, text: str) -> None:
    self.empty_home.set_workspace_label(text)
    self.coding_panel.set_workspace_label(text)

  @property
  def has_open_editor(self) -> bool:
    return self._has_open_editor

  def active_chat(self):
    return self.coding_panel.chat

  def set_app_state(self, state: object) -> None:
    from iris.core.state_machine import AppState

    if isinstance(state, AppState):
      self.iris_orb.set_state(state)

  def set_mic_level(self, level: float) -> None:
    self.iris_orb.set_mic_level(level)
    self.coding_panel.wave.set_level(level)

  def append_live_activity(self, line: str) -> None:
    del line

  def save_splitter_state(self) -> bytes:
    return self._splitter_state

  def restore_splitter_state(self, data: bytes) -> None:
    if data:
      self._splitter_state = data
