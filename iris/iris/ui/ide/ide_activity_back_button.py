"""Theia Activity Bar 하단 — Iris Assistant 복귀 버튼 (interactive overlay)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton, QSizePolicy

from iris.ui.ide.ide_layout_constants import THEIA_ACTIVITY_TAB_SIZE
from iris.ui.ide.ide_overlay_mouse import ensure_interactive_overlay
from iris.ui.theme_tokens import TOKENS

_MIN_HIT_SIZE = THEIA_ACTIVITY_TAB_SIZE  # 48×48 최소 hit area


class IdeActivityBackButton(QPushButton):
  """
  Interactive overlay — Activity Bar 하단 IRIS 복귀.
  WA_TransparentForMouseEvents 미적용; Theia 본문을 넓게 덮지 않는 최소 geometry.
  """

  back_clicked = pyqtSignal()

  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self.setObjectName("IdeActivityBackButton")
    self.setToolTip("기존 Iris 화면으로 복귀 (Alt+←)")
    self.setAccessibleName("Iris Assistant로 돌아가기")
    self.setAccessibleDescription("Theia IDE에서 기존 Iris 작업 화면으로 복귀합니다.")
    self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    self.setMinimumSize(_MIN_HIT_SIZE, _MIN_HIT_SIZE)
    self.setFixedSize(_MIN_HIT_SIZE, _MIN_HIT_SIZE)
    self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    self.setFlat(True)
    self.setText("\u2190")
    self.setAutoFillBackground(False)
    ensure_interactive_overlay(self)

    font = QFont(self.font())
    font.setPointSize(17)
    font.setBold(True)
    self.setFont(font)
    self.setStyleSheet(
      f"QPushButton#IdeActivityBackButton {{"
      f" color: {TOKENS.text_secondary}; background: transparent; border: none;"
      f" border-radius: 0; padding: 0;"
      f"}}"
      f"QPushButton#IdeActivityBackButton:hover {{"
      f" background: rgba(37, 99, 235, 0.18); color: {TOKENS.neon_cyan};"
      f"}}"
      f"QPushButton#IdeActivityBackButton:pressed {{"
      f" background: rgba(37, 99, 235, 0.32); color: {TOKENS.neon_cyan};"
      f"}}"
      f"QPushButton#IdeActivityBackButton:focus {{"
      f" border: 1px solid {TOKENS.neon_cyan};"
      f" background: rgba(37, 99, 235, 0.12);"
      f"}}"
    )
    self.clicked.connect(self.back_clicked.emit)
