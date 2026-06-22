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
  ASSISTANT_DOCK_ORB_TOP_PAD,
  THEIA_MENU_BAR_HEIGHT,
  THEIA_STATUS_BAR_HEIGHT,
)
from iris.ui.ide.iris_orb_widget import IrisOrbWidget
from iris.ui.mic_waveform_bar import MicWaveformBar
from iris.ui.theme_tokens import TOKENS


class IrisAssistantDock(QWidget):
  """
  우측 Assistant 영역 — 단일 QVBoxLayout.
  Theia chrome과 겹치지 않도록 상·하단 여백을 레이아웃 마진으로 처리.
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

    self.orb = IrisOrbWidget(self)
    core = self.orb.particle_core()
    orb_inner_h = ASSISTANT_DOCK_ORB_HEIGHT - ASSISTANT_DOCK_ORB_TOP_PAD
    orb_lay = self.orb.layout()
    if orb_lay is not None:
      orb_lay.setContentsMargins(0, ASSISTANT_DOCK_ORB_TOP_PAD, 0, 0)
    self.orb.setFixedHeight(ASSISTANT_DOCK_ORB_HEIGHT)
    core.setMinimumHeight(orb_inner_h)
    core.setMaximumHeight(orb_inner_h)
    # dock 폭 기준 glow fit — 크기 확정 후 scale 적용
    core.set_size_scale(1.65)
    self.orb.setSizePolicy(
      QSizePolicy.Policy.Preferred,
      QSizePolicy.Policy.Fixed,
    )
    root.addWidget(self.orb, 0)

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

  def place_status_strip(self, strip: QWidget) -> None:
    """모델·상태·TTS 스트립을 구체 위에 배치."""
    while self._status_slot_lay.count():
      item = self._status_slot_lay.takeAt(0)
      if item.widget() is not None:
        item.widget().setParent(None)
    strip.setParent(self._status_slot)
    self._status_slot_lay.addWidget(strip)

  def set_workspace_label(self, text: str) -> None:
    self._workspace_label.setText(text or "Workspace: —")

  def set_app_state(self, state: AppState) -> None:
    self.orb.set_state(state)

  def set_mic_level(self, level: float) -> None:
    self.orb.set_mic_level(level)
    self.wave.set_level(level)
