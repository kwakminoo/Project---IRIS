"""IDE 오른쪽 Iris 코딩 패널."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from iris.core.state_machine import AppState
from iris.ui.ide.coding_chat_view import CodingChatView
from iris.ui.ide.iris_orb_widget import IrisOrbWidget


class IrisCodingPanel(QWidget):
  """상태 스트립 + 구체 + 코딩 채팅."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IrisCodingPanel")
    self.setMinimumWidth(260)
    lay = QVBoxLayout(self)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.setSpacing(4)

    self._status_slot = QWidget()
    self._status_slot.setObjectName("CodingPanelStatusSlot")
    self._status_slot_lay = QVBoxLayout(self._status_slot)
    self._status_slot_lay.setContentsMargins(0, 0, 0, 0)
    self._status_slot_lay.setSpacing(0)
    lay.addWidget(self._status_slot)

    self.orb = IrisOrbWidget(self)
    lay.addWidget(self.orb)

    self.chat = CodingChatView(self)
    lay.addWidget(self.chat, 1)

  def place_status_strip(self, strip: QWidget) -> None:
    """모델·상태·TTS 스트립을 구체 위에 배치."""
    while self._status_slot_lay.count():
      item = self._status_slot_lay.takeAt(0)
      if item.widget() is not None:
        item.widget().setParent(None)
    strip.setParent(self._status_slot)
    self._status_slot_lay.addWidget(strip)

  def set_app_state(self, state: AppState) -> None:
    self.orb.set_state(state)

  def set_mic_level(self, level: float) -> None:
    self.orb.set_mic_level(level)
