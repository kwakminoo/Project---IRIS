"""IDE Empty Home — Theia 본문 영역 중앙 구체 레이어."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from iris.ui.ide.ide_layout_constants import THEIA_ACTIVITY_BAR_WIDTH
from iris.ui.ide.iris_orb_widget import IrisOrbWidget
from iris.ui.theme_tokens import TOKENS


class IrisCenterOrbLayer(QWidget):
  """
  Theia IDE 본문 위 중앙 구체 — Assistant Dock과 분리된 레이아웃.
  좌측 Activity Bar 폭만큼 마진을 두어 Theia 아이콘과 겹치지 않음.
  """

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("IrisCenterOrbLayer")
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    self.setAutoFillBackground(False)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(THEIA_ACTIVITY_BAR_WIDTH, 8, 16, 16)
    lay.setSpacing(8)

    self._title = QLabel("IRIS IDE")
    self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self._title.setSizePolicy(
      QSizePolicy.Policy.Preferred,
      QSizePolicy.Policy.Fixed,
    )
    self._title.setStyleSheet(
      f"color: {TOKENS.text_hud_label}; font-size: {TOKENS.font_size_heading};"
      " font-weight: 600; letter-spacing: 2px; background: transparent;"
    )
    lay.addWidget(self._title, 0)

    lay.addStretch(1)

    self.orb = IrisOrbWidget(self)
    self.orb.particle_core().set_size_scale(3.5)
    self.orb.setSizePolicy(
      QSizePolicy.Policy.Preferred,
      QSizePolicy.Policy.Fixed,
    )
    lay.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)

    lay.addStretch(1)

  def set_workspace_label(self, text: str) -> None:
    self._title.setText(text or "IRIS IDE")
