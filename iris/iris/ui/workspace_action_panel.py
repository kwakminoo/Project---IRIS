"""Workspace 전환 액션 — HUD 모드 트리거 버튼."""

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
    """향후 확장 가능한 Workspace 액션 — 네온 라인 HUD 버튼."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspaceActionPanel")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 4, 6, 8)
        self._lay.setSpacing(6)
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
        btn = QPushButton(title.upper())
        btn.setObjectName("HudModeButton")
        btn.setToolTip(tooltip)
        btn.setProperty("active", False)
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
        active: bool | None = None,
    ) -> None:
        btn = self._buttons.get(action_id)
        if btn is None:
            return
        if title is not None:
            btn.setText(title.upper())
        if tooltip is not None:
            btn.setToolTip(tooltip)
        if active is not None:
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        action = self._actions.get(action_id)
        if action is not None:
            self._actions[action_id] = WorkspaceAction(
                action_id,
                title or action.title,
                tooltip or action.tooltip,
                action.callback,
            )

    def set_action_active(self, action_id: str, active: bool) -> None:
        self.update_action(action_id, active=active)

    def set_action_visible(self, action_id: str, visible: bool) -> None:
        btn = self._buttons.get(action_id)
        if btn is not None:
            btn.setVisible(visible)
