"""알림 패널 — 쿨다운·클릭 시 창 포커스."""

from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from iris.automation import window_controller


class NotificationPanel(QWidget):
    """동일 (target_id, category) 알림은 cooldown 초 내 생략."""

    def __init__(
        self,
        cooldown_seconds: float = 90.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cooldown_sec = cooldown_seconds
        self._last_shown: dict[tuple[int, str], float] = {}
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("알림"))
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_click)
        lay.addWidget(self._list, 1)

    def add_note(self, text: str) -> None:
        """레거시 단순 문자열."""
        self._list.addItem(text)

    def try_add_alert(
        self,
        target_id: int,
        category: str,
        title: str,
        message: str,
        focus_hint: str,
    ) -> bool:
        """쿨다운 통과 시 True."""
        key = (target_id, category)
        now = time.monotonic()
        last = self._last_shown.get(key, 0.0)
        if now - last < self._cooldown_sec:
            return False
        self._last_shown[key] = now
        line = f"[{category}] {title}\n{message}"
        item = QListWidgetItem(line)
        item.setData(Qt.ItemDataRole.UserRole, focus_hint)
        self._list.insertItem(0, item)
        while self._list.count() > 80:
            self._list.takeItem(self._list.count() - 1)
        return True

    def _on_click(self, item: QListWidgetItem) -> None:
        hint = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(hint, str) or not hint.strip():
            return
        window_controller.focus_and_place(hint.strip(), 40, 40, 1000, 700)
