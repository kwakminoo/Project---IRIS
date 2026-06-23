"""IDE 오버레이 마우스 이벤트 경계 — visual-only vs interactive."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


def set_visual_only_overlay(widget: QWidget) -> None:
  """장식용 오버레이 — 보이지만 클릭·휠·포커스를 가로채지 않음."""
  widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
  widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def ensure_interactive_overlay(widget: QWidget) -> None:
  """명시적 interactive overlay — 마우스 이벤트를 받아야 함."""
  widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
