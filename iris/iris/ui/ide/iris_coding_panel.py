"""IDE 오른쪽 Iris 코딩 패널."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from iris.core.state_machine import AppState
from iris.ui.ide.coding_chat_view import CodingChatView
from iris.ui.ide.iris_orb_widget import IrisOrbWidget
from iris.ui.theme_tokens import TOKENS


class IrisCodingPanel(QWidget):
  """구체 + 상태 + 코딩 채팅."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IrisCodingPanel")
    self.setMinimumWidth(260)
    lay = QVBoxLayout(self)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.setSpacing(4)

    self.orb = IrisOrbWidget(self)
    lay.addWidget(self.orb)

    self._status = QLabel("상태: IDLE")
    self._status.setStyleSheet(f"color: {TOKENS.text_secondary}; font-size: 12px;")
    lay.addWidget(self._status)

    self.chat = CodingChatView(self)
    lay.addWidget(self.chat, 1)

  def set_app_state(self, state: AppState) -> None:
    self.orb.set_state(state)
    self._status.setText(f"상태: {state.name}")

  def set_mic_level(self, level: float) -> None:
    self.orb.set_mic_level(level)
