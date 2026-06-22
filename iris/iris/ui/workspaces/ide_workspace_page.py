"""IDE Workspace 페이지 — Theia Shell + Iris Assistant Dock."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from iris.ui.ide.ide_shell_layout import IdeShellLayout


class IdeWorkspacePage(QWidget):
  """통합 IDE 작업공간 — Theia·중앙 구체·Assistant Dock 레이아웃 분리."""

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

    self._has_open_editor = False
    self._splitter_state = b""

    self.theia.retry_requested.connect(self.theia_retry.emit)
    self.theia.back_to_assistant_requested.connect(self.theia_back.emit)
    self.back_button.back_clicked.connect(self.theia_back.emit)
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
    """Theia editorStateChanged → 레이아웃 모드 전환."""
    self._has_open_editor = has_open_editor
    if has_open_editor:
      self.show_editor_with_assistant()
      if title:
        self.coding_panel.set_workspace_label(f"파일: {title}")
    else:
      self.show_empty_home()
      self.coding_panel.set_workspace_label("Workspace: —")

  def show_empty_home(self) -> None:
    self._shell.show_empty_home()

  def show_editor_with_assistant(self) -> None:
    self._shell.show_editor_with_assistant()

  def set_workspace_label(self, text: str) -> None:
    self.empty_home.set_workspace_label(text)
    self.coding_panel.set_workspace_label(text)

  @property
  def has_open_editor(self) -> bool:
    return self._has_open_editor

  def active_chat(self):
    """채팅은 Empty Home·Editor 모두 우측 Assistant Dock을 사용."""
    return self.coding_panel.chat

  def set_app_state(self, state: object) -> None:
    from iris.core.state_machine import AppState

    if isinstance(state, AppState):
      self.coding_panel.set_app_state(state)
      self.empty_home.orb.set_state(state)

  def set_mic_level(self, level: float) -> None:
    self.coding_panel.set_mic_level(level)
    if not self._has_open_editor:
      self.empty_home.orb.set_mic_level(level)

  def append_live_activity(self, line: str) -> None:
    """IDE 우측 패널에는 Live Activity를 표시하지 않음."""
    del line

  def save_splitter_state(self) -> bytes:
    return self._splitter_state

  def restore_splitter_state(self, data: bytes) -> None:
    if data:
      self._splitter_state = data
