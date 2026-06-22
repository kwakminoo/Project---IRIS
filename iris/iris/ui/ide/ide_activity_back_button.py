"""Theia Activity Bar 하단 — Iris Assistant 복귀 버튼."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton

from iris.ui.ide.ide_layout_constants import THEIA_ACTIVITY_TAB_SIZE
from iris.ui.theme_tokens import TOKENS


class IdeActivityBackButton(QPushButton):
  """뒤로가기 화살표 — Activity Bar 아이콘과 동일한 밝기."""

  back_clicked = pyqtSignal()

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self.setObjectName("IdeActivityBackButton")
    self.setToolTip("기존 Iris 화면으로 복귀")
    self.setFixedSize(THEIA_ACTIVITY_TAB_SIZE, THEIA_ACTIVITY_TAB_SIZE)
    self.setFlat(True)
    self.setText("\u2190")
    self.setAutoFillBackground(False)
    font = QFont(self.font())
    font.setPointSize(17)
    font.setBold(True)
    self.setFont(font)
    self.setStyleSheet(
      f"color: {TOKENS.text_secondary}; background: transparent; border: none;"
    )
    self.clicked.connect(self.back_clicked.emit)
