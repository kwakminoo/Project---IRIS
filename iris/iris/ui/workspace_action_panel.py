"""Workspace 전환 액션 버튼 패널."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from iris.ui.theme_tokens import TOKENS


@dataclass
class WorkspaceAction:
  action_id: str
  title: str
  tooltip: str
  callback: Callable[[], None]


class WorkspaceActionPanel(QWidget):
  """향후 확장 가능한 Workspace 액션 버튼 영역."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self.setObjectName("WorkspaceActionPanel")
    self._lay = QVBoxLayout(self)
    self._lay.setContentsMargins(6, 4, 6, 8)
    self._lay.setSpacing(4)
    self._buttons: dict[str, QPushButton] = {}
    self._actions: dict[str, WorkspaceAction] = {}

  def add_action(
    self,
    *,
    action_id: str,
    title: str,
    tooltip: str,
    callback: Callable[[], None],
  ) -> None:
    if action_id in self._buttons:
      self.update_action(action_id, title=title, tooltip=tooltip)
      self._actions[action_id] = WorkspaceAction(action_id, title, tooltip, callback)
      return
    btn = QPushButton(title)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
      f"""
      QPushButton {{
        background: {TOKENS.accent_primary};
        color: {TOKENS.text_primary};
        border-radius: 6px;
        padding: 8px;
        font-weight: 600;
      }}
      QPushButton:hover {{ background: {TOKENS.accent_hover}; }}
      """
    )
    btn.clicked.connect(callback)
    self._buttons[action_id] = btn
    self._actions[action_id] = WorkspaceAction(action_id, title, tooltip, callback)
    self._lay.addWidget(btn)

  def update_action(
    self,
    action_id: str,
    *,
    title: str | None = None,
    tooltip: str | None = None,
  ) -> None:
    btn = self._buttons.get(action_id)
    if btn is None:
      return
    if title is not None:
      btn.setText(title)
    if tooltip is not None:
      btn.setToolTip(tooltip)
    action = self._actions.get(action_id)
    if action is not None:
      self._actions[action_id] = WorkspaceAction(
        action_id,
        title or action.title,
        tooltip or action.tooltip,
        action.callback,
      )
