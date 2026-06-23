"""IDE 우측 Iris Assistant Dock — 구체·워크스페이스·채팅·파형 통합 레이아웃."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from iris.core.state_machine import AppState
from iris.ui.ide.coding_chat_view import CodingChatView
from iris.ui.ide.ide_layout_constants import (
  ASSISTANT_DOCK_MAX_WIDTH,
  ASSISTANT_DOCK_MIN_WIDTH,
  ASSISTANT_DOCK_ORB_HEIGHT,
  THEIA_MENU_BAR_HEIGHT,
  THEIA_STATUS_BAR_HEIGHT,
)
from iris.ui.ide.ide_orb_placement import (
  apply_dock_orb_geometry,
  mount_orb,
  unmount_orb,
)
from iris.ui.ide.iris_orb_widget import IrisOrbWidget
from iris.ui.mic_waveform_bar import MicWaveformBar
from iris.ui.theme_tokens import TOKENS


class IrisAssistantDock(QWidget):
  """
  우측 Assistant 영역 — 구체는 IdeShellLayout이 필요 시 mount.
  """

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IrisAssistantDock")
    self.setMinimumWidth(ASSISTANT_DOCK_MIN_WIDTH)
    self.setMaximumWidth(ASSISTANT_DOCK_MAX_WIDTH)
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    root = QVBoxLayout(self)
    root.setContentsMargins(6, THEIA_MENU_BAR_HEIGHT, 6, THEIA_STATUS_BAR_HEIGHT)
    root.setSpacing(4)

    self._status_slot = QWidget()
    self._status_slot.setObjectName("CodingPanelStatusSlot")
    self._status_slot_lay = QVBoxLayout(self._status_slot)
    self._status_slot_lay.setContentsMargins(0, 0, 0, 0)
    self._status_slot_lay.setSpacing(0)
    self._status_slot.hide()
    self._status_slot.setMaximumHeight(0)
    root.addWidget(self._status_slot, 0)

    self._orb_slot = QWidget(self)
    self._orb_slot.setObjectName("IrisAssistantDockOrbSlot")
    self._orb_slot_lay = QVBoxLayout(self._orb_slot)
    self._orb_slot_lay.setContentsMargins(0, 0, 0, 0)
    self._orb_slot_lay.setSpacing(0)
    self._orb_slot.setSizePolicy(
      QSizePolicy.Policy.Preferred,
      QSizePolicy.Policy.Fixed,
    )
    root.addWidget(self._orb_slot, 0)

    self._workspace_label = QLabel("Workspace: —")
    self._workspace_label.setObjectName("CodingPanelWorkspaceLabel")
    self._workspace_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self._workspace_label.setWordWrap(True)
    self._workspace_label.setSizePolicy(
      QSizePolicy.Policy.Preferred,
      QSizePolicy.Policy.Fixed,
    )
    self._workspace_label.setStyleSheet(
      f"color: {TOKENS.text_secondary}; font-size: {TOKENS.font_size_caption};"
      " background: transparent; padding: 2px 4px;"
    )
    root.addWidget(self._workspace_label, 0)

    self.chat = CodingChatView(self)
    self.chat.setSizePolicy(
      QSizePolicy.Policy.Preferred,
      QSizePolicy.Policy.Expanding,
    )
    root.addWidget(self.chat, 1)

    self.wave = MicWaveformBar(self)
    self.wave.setSizePolicy(
      QSizePolicy.Policy.Expanding,
      QSizePolicy.Policy.Fixed,
    )
    root.addWidget(self.wave, 0)

    root.setStretch(root.indexOf(self.chat), 1)
    self._mounted_orb: IrisOrbWidget | None = None
    self.mount_orb(IrisOrbWidget(self))

  def mount_orb(self, orb: IrisOrbWidget) -> None:
    apply_dock_orb_geometry(orb)
    # unmount 시 setFixedHeight(0) — 재마운트 시 슬롯 높이 복원 필수
    self._orb_slot.setFixedHeight(ASSISTANT_DOCK_ORB_HEIGHT)
    mount_orb(self._orb_slot, self._orb_slot_lay, orb)
    self._orb_slot.show()
    self._mounted_orb = orb

  def unmount_orb(self, orb: IrisOrbWidget) -> None:
    unmount_orb(self._orb_slot_lay, orb)
    self._orb_slot.setFixedHeight(0)
    self._orb_slot.hide()
    self._mounted_orb = None

  @property
  def orb(self) -> IrisOrbWidget | None:
    return self._mounted_orb

  def place_status_strip(self, strip: QWidget) -> None:
    while self._status_slot_lay.count():
      item = self._status_slot_lay.takeAt(0)
      if item.widget() is not None:
        item.widget().setParent(None)
    strip.setParent(self._status_slot)
    self._status_slot_lay.addWidget(strip)

  def set_workspace_label(self, text: str) -> None:
    self._workspace_label.setText(text or "Workspace: —")

  def set_app_state(self, state: AppState) -> None:
    if self._mounted_orb is not None:
      self._mounted_orb.set_state(state)

  def set_mic_level(self, level: float) -> None:
    if self._mounted_orb is not None:
      self._mounted_orb.set_mic_level(level)
    self.wave.set_level(level)
