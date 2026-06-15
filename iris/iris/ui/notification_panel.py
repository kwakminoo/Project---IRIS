"""알림 패널 — SQLite 쿨다운·무시·스누즈·대상 비활성."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.ui.section_header import (
    SECTION_CONTENT_GAP,
    apply_section_panel_layout,
    make_section_header,
)
from iris.ui.theme_tokens import TOKENS

if TYPE_CHECKING:
    from iris.monitoring.notification_policy import NotificationPolicy


class _AlertPayload:
    """리스트 아이템에 실리는 알림 메타."""

    __slots__ = ("target_id", "category", "event_id", "focus_hint", "title")

    def __init__(
        self,
        target_id: int,
        category: str,
        event_id: int,
        focus_hint: str,
        title: str,
    ) -> None:
        self.target_id = target_id
        self.category = category
        self.event_id = event_id
        self.focus_hint = focus_hint
        self.title = title


class NotificationPanel(QWidget):
    """DB 정책 + 인메모리 보조. 우클릭: 무시·스누즈·대상 끄기."""

    action_requested = pyqtSignal(str, int, str, int)  # decision, target_id, category, event_id

    def __init__(
        self,
        cooldown_seconds: float = 90.0,
        policy: Optional["NotificationPolicy"] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NotificationPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(
            f"""
            QWidget#NotificationPanel {{
                background: transparent;
                border: none;
            }}
            QWidget#NotificationPanel QListWidget {{
                background: transparent;
                border: none;
                padding: 4px 0;
                color: {TOKENS.text_secondary};
                font-size: {TOKENS.font_size_micro};
            }}
            QWidget#NotificationPanel QPushButton#AlertActionButton {{
                background: transparent;
                border: none;
                color: {TOKENS.text_secondary};
                padding: 4px 8px;
                font-size: {TOKENS.font_size_micro};
            }}
            QWidget#NotificationPanel QPushButton#AlertActionButton:hover {{
                color: {TOKENS.text_accent};
                background: transparent;
            }}
            """
        )
        self._cooldown_sec = cooldown_seconds
        self._policy = policy
        lay = QVBoxLayout(self)
        apply_section_panel_layout(lay)
        lay.addWidget(make_section_header("ALERTS"))
        self._list = QListWidget()
        self._list.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        list_pal = self._list.palette()
        list_pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        self._list.setPalette(list_pal)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        self._list.itemClicked.connect(self._on_click)
        lay.addWidget(self._list, 1)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SECTION_CONTENT_GAP)
        self._btn_snooze = QPushButton("나중에 (15분)")
        self._btn_snooze.setObjectName("AlertActionButton")
        self._btn_snooze.clicked.connect(lambda: self._on_decision("snooze"))
        btn_row.addWidget(self._btn_snooze)
        self._btn_ignore = QPushButton("이 유형 무시")
        self._btn_ignore.setObjectName("AlertActionButton")
        self._btn_ignore.clicked.connect(lambda: self._on_decision("ignore"))
        btn_row.addWidget(self._btn_ignore)
        self._btn_disable = QPushButton("대상 끄기")
        self._btn_disable.setObjectName("AlertActionButton")
        self._btn_disable.clicked.connect(lambda: self._on_decision("disable_target"))
        btn_row.addWidget(self._btn_disable)
        lay.addLayout(btn_row)

    def set_policy(self, policy: "NotificationPolicy") -> None:
        self._policy = policy

    def add_note(self, text: str) -> None:
        self._list.addItem(text)

    def try_add_alert(
        self,
        target_id: int,
        category: str,
        title: str,
        message: str,
        focus_hint: str,
        event_id: int = 0,
    ) -> bool:
        """정책 통과 시 True (MonitorManager가 DB 쿨다운 처리 후 UI만 표시)."""
        line = f"[{category}] {title}\n{message}"
        item = QListWidgetItem(line)
        payload = _AlertPayload(target_id, category, event_id, focus_hint, title)
        item.setData(Qt.ItemDataRole.UserRole, payload)
        self._list.insertItem(0, item)
        while self._list.count() > 80:
            self._list.takeItem(self._list.count() - 1)
        return True

    def _current_payload(self) -> _AlertPayload | None:
        item = self._list.currentItem()
        if item is None and self._list.count() > 0:
            item = self._list.item(0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, _AlertPayload) else None

    def _on_decision(self, decision: str) -> None:
        p = self._current_payload()
        if p is None:
            return
        if self._policy:
            if decision == "ignore":
                self._policy.dismiss_permanently(p.target_id, p.category)
            elif decision == "snooze":
                self._policy.snooze(p.target_id, p.category, 15)
            elif decision == "disable_target":
                self._policy.disable_target(p.target_id)
            self._policy.log_notification(
                p.target_id,
                p.event_id or None,
                p.category,
                p.title,
                "",
                user_decision=decision,
            )
        self.action_requested.emit(decision, p.target_id, p.category, p.event_id)

    def _context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        self._list.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("나중에 (15분)", lambda: self._on_decision("snooze"))
        menu.addAction("이 유형 무시", lambda: self._on_decision("ignore"))
        menu.addAction("대상 모니터링 끄기", lambda: self._on_decision("disable_target"))
        menu.exec(self._list.mapToGlobal(pos))

    def _on_click(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, _AlertPayload) and data.focus_hint.strip():
            window_controller.focus_and_place(data.focus_hint.strip(), 40, 40, 1000, 700)
