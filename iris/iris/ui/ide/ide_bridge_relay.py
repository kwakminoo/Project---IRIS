"""IDE Bridge 이벤트를 Qt 메인 스레드로 전달."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class IdeBridgeRelay(QObject):
  """Theia editorStateChanged → PyQt 시그널."""

  editor_state_changed = pyqtSignal(bool, str, str, str)

  def push(self, has_open_editor: bool, title: str, uri: str, language_id: str) -> None:
    self.editor_state_changed.emit(has_open_editor, title, uri, language_id)
