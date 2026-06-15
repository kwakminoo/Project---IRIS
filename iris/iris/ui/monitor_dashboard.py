"""모니터링 대시보드 — 등록 대상 카드."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from iris.storage.database import Database

_STATUS_COLOR = {
    "NORMAL": "#22c55e",
    "APPROVAL_WAITING": "#eab308",
    "ERROR_DETECTED": "#ef4444",
    "GENERATION_FAILED": "#ef4444",
    "TASK_STALLED": "#f97316",
    "RESPONSE_READY": "#3b82f6",
    "BUILD_NOT_STARTED": "#3b82f6",
    "USER_ACTION_REQUIRED": "#eab308",
    "UNKNOWN": "#64748b",
}


class MonitorDashboard(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db: Optional["Database"] = None
        root = QVBoxLayout(self)
        title = QLabel("모니터링 대시보드")
        title.setObjectName("PanelTitle")
        root.addWidget(title)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

    def set_database(self, db: "Database") -> None:
        self._db = db

    def refresh_cards(self) -> None:
        if not self._db:
            return
        while self._inner_lay.count():
            item = self._inner_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        rows = self._db.list_targets(True)
        if not rows:
            hint = QLabel("등록된 모니터링 대상이 없습니다. 작업/게임 모드 실행 시 앱이 등록됩니다.")
            hint.setWordWrap(True)
            self._inner_lay.addWidget(hint)
        for row in rows:
            self._inner_lay.addWidget(self._make_card(row))
        self._inner_lay.addStretch(1)

    def _make_card(self, row) -> QFrame:
        fr = QFrame()
        fr.setFrameShape(QFrame.Shape.StyledPanel)
        g = QGridLayout(fr)
        status = str(row["status"] or "UNKNOWN")
        color = _STATUS_COLOR.get(status, "#94a3b8")
        name = QLabel(f"<b>{row['title']}</b>")
        name.setTextFormat(Qt.TextFormat.RichText)
        g.addWidget(name, 0, 0, 1, 2)
        g.addWidget(QLabel("유형"), 1, 0)
        g.addWidget(QLabel(str(row["type"])), 1, 1)
        st = QLabel(f"상태: {status}")
        st.setStyleSheet(f"color: {color}; font-weight: 600;")
        g.addWidget(st, 2, 0, 1, 2)
        g.addWidget(QLabel("추천 조치 / 요약"), 3, 0)
        ev = QLabel(str(row["last_event"] or "-"))
        ev.setWordWrap(True)
        g.addWidget(ev, 3, 1)
        g.addWidget(QLabel("마지막 확인"), 4, 0)
        g.addWidget(QLabel(str(row["last_checked_at"] or "-")), 4, 1)
        return fr
